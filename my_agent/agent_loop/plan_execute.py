"""
本文件负责推进 Plan-and-Execute 状态机、执行限制、工具调用与 Checkpoint 时序。
本文件不实现具体 Planner、工具业务或持久化 Store。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from typing import Any
from uuid import uuid4

from my_agent.agent_loop.plan_actions import (
    AbortPlanAction,
    CompleteStepAction,
    PlannerProtocolError,
    SkipStepAction,
    StepDecision,
)
from my_agent.agent_loop.plan_planner import (
    CreatePlanRequest,
    FinalizePlanRequest,
    PlanDefinition,
    StepDecisionRequest,
    StepPlanner,
    TaskPlanner,
)
from my_agent.agent_loop.planner import FinalAnswerAction, ToolAction
from my_agent.core.json_value import validate_json_native
from my_agent.state.checkpoint_recorder import CheckpointRecorder
from my_agent.state.plan_state import (
    PlanOutcome,
    PlanState,
    PlanStateConsistencyError,
    PlanStatus,
    PlanStep,
    PlanStepStatus,
)
from my_agent.state.run_state import PendingToolCall, RunState, RunStatus
from my_agent.state.session import SessionMessage, SessionState
from my_agent.state.trace import ToolTraceRecord
from my_agent.tools.executor import ToolExecutor
from my_agent.tools.schema import ToolCallRequest, ToolCallResult, ToolDefinition


class PlanAndExecuteAgentLoop:
    """执行可恢复的任务计划，并由 StepPlanner 显式决定每个步骤终态。"""

    def __init__(
        self,
        task_planner: TaskPlanner,
        step_planner: StepPlanner,
        tool_executor: ToolExecutor,
        tool_definitions: list[ToolDefinition],
        session_state: SessionState,
        run_state: RunState | None = None,
        checkpoint_recorder: CheckpointRecorder | None = None,
        max_plan_steps: int = 8,
        max_tool_calls_per_step: int = 3,
        max_total_tool_calls: int = 10,
    ) -> None:
        if not isinstance(task_planner, TaskPlanner):
            raise TypeError("task_planner must be a TaskPlanner")
        if not isinstance(step_planner, StepPlanner):
            raise TypeError("step_planner must be a StepPlanner")
        if not isinstance(tool_executor, ToolExecutor):
            raise TypeError("tool_executor must be a ToolExecutor")
        if not isinstance(tool_definitions, list) or not all(
            isinstance(definition, ToolDefinition) for definition in tool_definitions
        ):
            raise ValueError("tool_definitions must be a list[ToolDefinition]")
        if not isinstance(session_state, SessionState):
            raise TypeError("session_state must be a SessionState")
        for name, limit in (
            ("max_plan_steps", max_plan_steps),
            ("max_tool_calls_per_step", max_tool_calls_per_step),
            ("max_total_tool_calls", max_total_tool_calls),
        ):
            if not isinstance(limit, int) or limit <= 0:
                raise ValueError(f"{name} must be a positive integer")
        self._task_planner = task_planner
        self._step_planner = step_planner
        self._tool_executor = tool_executor
        self._tool_definitions = list(tool_definitions)
        self._session_state = session_state
        self._run_state = run_state
        self._checkpoint_recorder = checkpoint_recorder
        self._max_plan_steps = max_plan_steps
        self._max_tool_calls_per_step = max_tool_calls_per_step
        self._max_total_tool_calls = max_total_tool_calls

    def bind_run_state(
        self,
        run_state: RunState | None,
        checkpoint_recorder: CheckpointRecorder | None,
    ) -> None:
        """为当前 Runtime 回合绑定可恢复状态和 Checkpoint Recorder。"""
        if run_state is not None and not isinstance(run_state, RunState):
            raise TypeError("run_state must be a RunState or None")
        if checkpoint_recorder is not None and not isinstance(
            checkpoint_recorder, CheckpointRecorder
        ):
            raise TypeError(
                "checkpoint_recorder must be a CheckpointRecorder or None"
            )
        self._run_state = run_state
        self._checkpoint_recorder = checkpoint_recorder

    def run(self, user_input: str) -> str:
        """执行或恢复计划，直到写入整个计划的最终回答。"""
        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("user_input must be a non-empty string")
        if self._run_state is None:
            raise ValueError("PlanAndExecuteAgentLoop requires a bound RunState")
        try:
            self._ensure_plan(user_input)
            while True:
                phase = self._run_state.cursor.agent_phase
                if phase == "plan_step_deciding":
                    self._decide_current_step()
                    continue
                if phase == "plan_tool_pending":
                    self._execute_pending_tool()
                    continue
                if phase == "plan_finalizing":
                    return self._finalize_plan()
                if phase == "plan_final_answer_written":
                    return self._read_saved_final_answer()
                raise PlanStateConsistencyError(f"unsupported plan phase: {phase}")
        except PlannerProtocolError as error:
            self._record_planner_protocol_failure(error)
            raise

    def _record_planner_protocol_failure(
        self, error: PlannerProtocolError
    ) -> None:
        """在抛出协议错误前保存稳定错误结构和当前计划快照。"""
        state = self._require_run_state()
        state.status = RunStatus.FAILED
        state.error = {
            "type": error.__class__.__name__,
            "code": error.code,
            "message": str(error),
        }
        self._record_checkpoint({"reason": "planner_protocol_failed"})

    def _ensure_plan(self, user_input: str) -> None:
        """写入用户消息并在尚无持久化计划时创建新计划。"""
        state = self._require_run_state()
        phase = state.cursor.agent_phase
        if phase == "not_started":
            state.user_input = user_input
            self._session_state.add_message("user", user_input)
            state.cursor.agent_phase = "plan_creating"
            self._record_checkpoint({"reason": "after_user_input"})
            phase = "plan_creating"
        if phase != "plan_creating":
            return
        definition = self._task_planner.create_plan(
            CreatePlanRequest(
                user_input=state.user_input,
                messages=self._message_snapshots(),
                tool_definitions=self._tool_definition_snapshots(),
                max_plan_steps=self._max_plan_steps,
            )
        )
        self._validate_plan_definition(definition)
        steps = [
            PlanStep(
                step_id=f"step-{index}",
                instruction=step.instruction,
                status=(
                    PlanStepStatus.RUNNING
                    if index == 1
                    else PlanStepStatus.PENDING
                ),
            )
            for index, step in enumerate(definition.steps, start=1)
        ]
        state.plan_state = PlanState(
            plan_id=str(uuid4()),
            goal=definition.goal,
            status=PlanStatus.RUNNING,
            outcome=None,
            current_step_id=steps[0].step_id,
            steps=steps,
            total_tool_call_count=0,
            total_retry_count=0,
            max_tool_calls_per_step=self._max_tool_calls_per_step,
            max_total_tool_calls=self._max_total_tool_calls,
        )
        state.cursor.agent_phase = "plan_step_deciding"
        self._record_checkpoint({"reason": "after_plan_created"})

    def _validate_plan_definition(self, definition: PlanDefinition) -> None:
        """拒绝 TaskPlanner 越过 Loop 的计划规模限制。"""
        if not isinstance(definition, PlanDefinition):
            raise PlannerProtocolError("TaskPlanner must return PlanDefinition")
        if len(definition.steps) > self._max_plan_steps:
            raise PlannerProtocolError("plan exceeds max_plan_steps")

    def _decide_current_step(self) -> None:
        """调用 StepPlanner，并由 Loop 应用经过校验的决策。"""
        state = self._require_run_state()
        plan = self._require_plan_state()
        step = plan.current_step()
        observations = self._build_step_observations(step)
        remaining_step = plan.max_tool_calls_per_step - step.attempt_count
        remaining_total = plan.max_total_tool_calls - plan.total_tool_call_count
        request = StepDecisionRequest(
            user_input=state.user_input,
            plan=plan.to_dict(),
            current_step=step.to_dict(),
            previous_step_summaries=tuple(
                item.result_summary
                for item in plan.steps
                if item.step_id != step.step_id and item.result_summary is not None
            ),
            observations=observations,
            recent_observation=observations[-1] if observations else None,
            messages=self._message_snapshots(),
            tool_definitions=self._tool_definition_snapshots(),
            remaining_step_tool_calls=remaining_step,
            remaining_total_tool_calls=remaining_total,
            can_call_tool=remaining_step > 0 and remaining_total > 0,
        )
        decision = self._step_planner.decide(request)
        if not isinstance(decision, StepDecision):
            raise PlannerProtocolError("StepPlanner must return StepDecision")
        action = decision.action
        if isinstance(action, ToolAction):
            self._accept_tool_action(
                action,
                request,
                observations,
                decision.reflection,
            )
            return
        if isinstance(action, CompleteStepAction):
            step.reflection = decision.reflection
            step.status = PlanStepStatus.COMPLETED
            step.result_summary = action.result_summary
            self._advance_after_step("after_step_completed")
            return
        if isinstance(action, SkipStepAction):
            step.reflection = decision.reflection
            step.status = PlanStepStatus.SKIPPED
            step.result_summary = action.result_summary or action.reason
            step.failure_reason = action.reason
            self._advance_after_step("after_step_skipped")
            return
        if isinstance(action, AbortPlanAction):
            step.reflection = decision.reflection
            step.status = PlanStepStatus.FAILED
            step.failure_reason = action.reason
            plan.status = PlanStatus.ABORTED
            plan.abort_reason = action.reason
            plan.current_step_id = None
            plan.outcome = self._calculate_outcome(plan)
            state.cursor.agent_phase = "plan_finalizing"
            self._record_checkpoint({"reason": "after_plan_aborted"})
            return
        raise PlannerProtocolError("unsupported step action")

    def _accept_tool_action(
        self,
        action: ToolAction,
        request: StepDecisionRequest,
        observations: tuple[dict[str, Any], ...],
        reflection: str | None,
    ) -> None:
        """由 Loop 生成 call ID、增加计数并持久化完整 pending 调用。"""
        if action.call_id is not None:
            raise PlannerProtocolError("StepPlanner must not provide call_id")
        if not request.can_call_tool:
            raise PlannerProtocolError("tool call exceeds persisted execution limits")
        try:
            validate_json_native(action.arguments)
        except ValueError as error:
            raise PlannerProtocolError(
                "ToolAction arguments must be JSON-serializable"
            ) from error
        state = self._require_run_state()
        plan = self._require_plan_state()
        step = plan.current_step()
        step.reflection = reflection
        is_retry = bool(observations and not observations[-1]["success"])
        step.attempt_count += 1
        plan.total_tool_call_count += 1
        if is_retry:
            step.retry_count += 1
            plan.total_retry_count += 1
        call_id = str(uuid4())
        step.tool_call_ids.append(call_id)
        state.pending_tool_call = PendingToolCall(
            tool_name=action.tool_name,
            arguments=deepcopy(action.arguments),
            call_id=call_id,
        )
        state.cursor.agent_phase = "plan_tool_pending"
        self._record_checkpoint(
            {
                "reason": "before_tool_execution",
                "step_id": step.step_id,
                "call_id": call_id,
            }
        )

    def _execute_pending_tool(self) -> None:
        """执行唯一 pending 调用并把 observation 原子写回计划状态。"""
        state = self._require_run_state()
        pending = state.pending_tool_call
        if pending is None:
            raise PlanStateConsistencyError(
                "plan_tool_pending requires pending_tool_call"
            )
        trace_start_index = len(self._session_state.list_tool_traces())
        result = self._tool_executor.execute(
            ToolCallRequest(
                name=pending.tool_name,
                arguments=deepcopy(pending.arguments),
                call_id=pending.call_id,
            )
        )
        if not isinstance(result, ToolCallResult):
            raise PlanStateConsistencyError(
                "ToolExecutor must return ToolCallResult"
            )
        if result.name != pending.tool_name or result.call_id != pending.call_id:
            raise PlanStateConsistencyError(
                "tool result must match pending tool name and call ID"
            )
        self._ensure_session_tool_trace(pending, result, trace_start_index)
        self._session_state.add_message(
            "assistant",
            self._format_tool_result(result),
            metadata={
                "message_type": "tool_observation",
                "tool_name": result.name,
                "call_id": result.call_id,
                "arguments": deepcopy(pending.arguments),
                "success": result.success,
            },
        )
        step = self._require_plan_state().current_step()
        step.last_observation_summary = self._summarize_tool_result(result)
        state.pending_tool_call = None
        state.cursor.agent_phase = "plan_step_deciding"
        self._record_checkpoint(
            {
                "reason": "after_tool_observation",
                "step_id": step.step_id,
                "call_id": result.call_id,
                "success": result.success,
            }
        )

    def _ensure_session_tool_trace(
        self,
        pending: PendingToolCall,
        result: ToolCallResult,
        trace_start_index: int,
    ) -> None:
        """保证 observation 的 Trace 存在于本 Loop 绑定的 Session。"""
        if any(
            trace.call_id == pending.call_id
            for trace in self._session_state.list_tool_traces()[trace_start_index:]
        ):
            return
        self._session_state.add_tool_trace(
            ToolTraceRecord(
                trace_id=str(uuid4()),
                tool_name=pending.tool_name,
                call_id=pending.call_id,
                arguments=deepcopy(pending.arguments),
                success=result.success,
                result=deepcopy(result.data) if result.success else None,
                error=None if result.success else deepcopy(result.error),
                duration_ms=result.duration_ms,
                token_usage=None,
            )
        )

    def _build_step_observations(
        self, step: PlanStep
    ) -> tuple[dict[str, Any], ...]:
        """按步骤 call ID 顺序重建历史，同一 ID 仅保留最新 Trace。"""
        latest_by_call_id: dict[str, ToolTraceRecord] = {}
        for trace in self._require_run_state().tool_traces:
            if trace.call_id is not None:
                latest_by_call_id[trace.call_id] = trace
        observations = []
        for call_id in step.tool_call_ids:
            trace = latest_by_call_id.get(call_id)
            if trace is None:
                raise PlanStateConsistencyError(
                    "step tool call is missing a persisted observation"
                )
            observations.append(
                {
                    "call_id": call_id,
                    "tool_name": trace.tool_name,
                    "arguments": deepcopy(trace.arguments),
                    "success": trace.success,
                    "result": deepcopy(trace.result),
                    "error": deepcopy(trace.error),
                }
            )
        return tuple(observations)

    def _advance_after_step(self, reason: str) -> None:
        """原子完成当前步骤并选择下一步骤或进入 finalization。"""
        state = self._require_run_state()
        plan = self._require_plan_state()
        next_step = next(
            (step for step in plan.steps if step.status is PlanStepStatus.PENDING),
            None,
        )
        if next_step is not None:
            next_step.status = PlanStepStatus.RUNNING
            plan.current_step_id = next_step.step_id
            state.cursor.agent_phase = "plan_step_deciding"
        else:
            plan.current_step_id = None
            plan.outcome = self._calculate_outcome(plan)
            plan.status = PlanStatus.FINALIZING
            state.cursor.agent_phase = "plan_finalizing"
        self._record_checkpoint({"reason": reason})

    def _calculate_outcome(self, plan: PlanState) -> PlanOutcome:
        """根据步骤终态确定计划结果，不接受 Planner 覆盖。"""
        completed_count = sum(
            step.status is PlanStepStatus.COMPLETED for step in plan.steps
        )
        if completed_count == len(plan.steps):
            return PlanOutcome.SUCCEEDED
        if completed_count > 0:
            return PlanOutcome.PARTIAL
        return PlanOutcome.FAILED

    def _finalize_plan(self) -> str:
        """调用可重放的 TaskPlanner finalization 并原子保存最终回答。"""
        state = self._require_run_state()
        plan = self._require_plan_state()
        if plan.outcome is None:
            raise PlanStateConsistencyError("finalizing plan requires outcome")
        action = self._task_planner.finalize_plan(
            FinalizePlanRequest(
                user_input=state.user_input,
                plan=plan.to_dict(),
                outcome=plan.outcome.value,
                abort_reason=plan.abort_reason,
                messages=self._message_snapshots(),
            )
        )
        if not isinstance(action, FinalAnswerAction):
            raise PlannerProtocolError(
                "TaskPlanner.finalize_plan must return FinalAnswerAction"
            )
        self._session_state.add_message(
            "assistant",
            action.answer,
            metadata={
                "message_type": "plan_final_answer",
                "run_id": state.run_id,
                "plan_id": plan.plan_id,
            },
        )
        if plan.status is PlanStatus.FINALIZING:
            plan.status = PlanStatus.COMPLETED
        state.cursor.agent_phase = "plan_final_answer_written"
        self._record_checkpoint({"reason": "after_final_answer"})
        return action.answer

    def _read_saved_final_answer(self) -> str:
        """读取当前 run 和 plan 已持久化的唯一最终回答。"""
        state = self._require_run_state()
        plan = self._require_plan_state()
        matches = [
            message
            for message in self._session_state.list_messages()
            if message.role == "assistant"
            and message.metadata.get("message_type") == "plan_final_answer"
            and message.metadata.get("run_id") == state.run_id
            and message.metadata.get("plan_id") == plan.plan_id
        ]
        if len(matches) != 1:
            raise PlanStateConsistencyError(
                "plan final answer checkpoint must contain one matching message"
            )
        return matches[0].content

    def _record_checkpoint(self, metadata: dict[str, Any]) -> None:
        """同步 Session 快照、校验一致性并按需写入 Checkpoint。"""
        state = self._require_run_state()
        state.messages = self._session_state.list_messages()
        state.tool_traces = self._session_state.list_tool_traces()
        state.updated_at_utc = datetime.now(timezone.utc).isoformat()
        state.validate_consistency()
        if self._checkpoint_recorder is not None:
            self._checkpoint_recorder.record(metadata)

    def _message_snapshots(self) -> tuple[dict[str, Any], ...]:
        """构造与 SessionState 引用隔离的消息快照。"""
        return tuple(
            {
                "role": message.role,
                "content": message.content,
                "metadata": deepcopy(message.metadata),
            }
            for message in self._session_state.list_messages()
        )

    def _tool_definition_snapshots(self) -> tuple[dict[str, Any], ...]:
        """构造与 ToolDefinition 引用隔离的工具 schema 快照。"""
        return tuple(
            {
                "name": definition.name,
                "description": definition.description,
                "parameters": deepcopy(definition.parameters),
                "tags": list(definition.tags),
            }
            for definition in self._tool_definitions
        )

    def _format_tool_result(self, result: ToolCallResult) -> str:
        """把工具结果压缩为稳定 observation 摘要。"""
        payload = result.data if result.success else result.error
        status = "成功" if result.success else "失败"
        return (
            f"工具 {result.name} 执行{status}，结果："
            f"{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
        )

    def _summarize_tool_result(self, result: ToolCallResult) -> str:
        """只保存工具索引与成败，完整结果继续由 Tool Trace 持有。"""
        success = "true" if result.success else "false"
        summary = (
            f"tool={result.name}; call_id={result.call_id}; success={success}"
        )
        if not result.success and isinstance(result.error, dict):
            error_type = result.error.get("type")
            if isinstance(error_type, str) and error_type:
                summary = f"{summary}; error_type={error_type}"
        return summary

    def _require_run_state(self) -> RunState:
        """返回已绑定 RunState，避免在各阶段重复可空判断。"""
        if self._run_state is None:
            raise PlanStateConsistencyError("run_state is not bound")
        return self._run_state

    def _require_plan_state(self) -> PlanState:
        """返回已创建的 PlanState。"""
        plan = self._require_run_state().plan_state
        if plan is None:
            raise PlanStateConsistencyError("plan_state is missing")
        return plan

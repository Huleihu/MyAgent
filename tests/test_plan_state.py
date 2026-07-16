"""
本文件负责验证 Plan-and-Execute 持久化状态、序列化和跨状态一致性约束。
本文件不执行 Planner、工具或 Runtime 节点。
"""

from __future__ import annotations

import unittest

from my_agent.state.plan_state import (
    PlanOutcome,
    PlanState,
    PlanStateConsistencyError,
    PlanStatus,
    PlanStep,
    PlanStepStatus,
)
from my_agent.state.run_state import (
    ExecutionCursor,
    PendingToolCall,
    RunState,
    RunStatus,
)
from my_agent.state.session import SessionMessage
from my_agent.state.trace import ToolTraceRecord


def build_plan_state(
    *,
    status: PlanStatus = PlanStatus.RUNNING,
    outcome: PlanOutcome | None = None,
    tool_call_ids: list[str] | None = None,
) -> PlanState:
    """构造包含单个运行步骤的最小计划状态。"""
    call_ids = [] if tool_call_ids is None else list(tool_call_ids)
    step_status = (
        PlanStepStatus.RUNNING
        if status is PlanStatus.RUNNING
        else PlanStepStatus.COMPLETED
    )
    return PlanState(
        plan_id="plan-1",
        goal="查询资料并总结",
        status=status,
        outcome=outcome,
        current_step_id="step-1" if status is PlanStatus.RUNNING else None,
        steps=[
            PlanStep(
                step_id="step-1",
                instruction="查询资料",
                status=step_status,
                attempt_count=len(call_ids),
                tool_call_ids=call_ids,
                result_summary="已完成" if step_status is PlanStepStatus.COMPLETED else None,
            )
        ],
        total_tool_call_count=len(call_ids),
        total_retry_count=0,
        max_tool_calls_per_step=3,
        max_total_tool_calls=5,
    )


def build_trace(call_id: str) -> ToolTraceRecord:
    """构造可用于恢复 observation 的成功工具 Trace。"""
    return ToolTraceRecord(
        trace_id=f"trace-{call_id}",
        tool_name="retrieval.search",
        call_id=call_id,
        arguments={"query": "checkpoint"},
        success=True,
        result={"items": []},
        error=None,
        duration_ms=1.0,
    )


def build_run_state(
    plan_state: PlanState | None,
    *,
    phase: str,
    pending_tool_call: PendingToolCall | None = None,
    tool_traces: list[ToolTraceRecord] | None = None,
) -> RunState:
    """构造用于校验 Plan phase 组合的运行状态。"""
    return RunState(
        run_id="run-1",
        session_id="session-1",
        workflow_id="workflow-1",
        status=RunStatus.RUNNING,
        user_input="查询资料",
        tool_traces=[] if tool_traces is None else tool_traces,
        cursor=ExecutionCursor(next_node_id="agent", agent_phase=phase),
        pending_tool_call=pending_tool_call,
        plan_state=plan_state,
    )


class PlanStateTest(unittest.TestCase):
    def test_retry_count_zero_is_valid_without_attempts(self):
        step = PlanStep(
            "step-1",
            "尚未调用工具",
            PlanStepStatus.RUNNING,
            attempt_count=0,
            retry_count=0,
            tool_call_ids=[],
        )

        self.assertEqual(step.retry_count, 0)

    def test_retry_count_zero_is_valid_for_first_attempt(self):
        step = PlanStep(
            "step-1",
            "首次调用工具",
            PlanStepStatus.RUNNING,
            attempt_count=1,
            retry_count=0,
            tool_call_ids=["call-1"],
        )

        self.assertEqual(step.retry_count, 0)

    def test_retry_count_one_is_invalid_for_first_attempt(self):
        with self.assertRaisesRegex(
            PlanStateConsistencyError,
            "retry_count must not exceed completed attempts before the latest call",
        ):
            PlanStep(
                "step-1",
                "首次调用工具",
                PlanStepStatus.RUNNING,
                attempt_count=1,
                retry_count=1,
                tool_call_ids=["call-1"],
            )

    def test_retry_count_two_is_valid_for_three_attempts(self):
        step = PlanStep(
            "step-1",
            "第三次调用工具",
            PlanStepStatus.RUNNING,
            attempt_count=3,
            retry_count=2,
            tool_call_ids=["call-1", "call-2", "call-3"],
        )

        self.assertEqual(step.retry_count, 2)

    def test_retry_count_three_is_invalid_for_three_attempts(self):
        with self.assertRaisesRegex(
            PlanStateConsistencyError,
            "retry_count must not exceed completed attempts before the latest call",
        ):
            PlanStep(
                "step-1",
                "第三次调用工具",
                PlanStepStatus.RUNNING,
                attempt_count=3,
                retry_count=3,
                tool_call_ids=["call-1", "call-2", "call-3"],
            )

    def test_pending_step_rejects_execution_history(self):
        with self.assertRaises(PlanStateConsistencyError):
            PlanStep(
                "step-1",
                "尚未执行",
                PlanStepStatus.PENDING,
                attempt_count=1,
                tool_call_ids=["call-1"],
                last_observation_summary="旧结果",
            )

    def test_terminal_step_requires_matching_summary_or_failure_reason(self):
        with self.assertRaises(PlanStateConsistencyError):
            PlanStep("step-1", "完成", PlanStepStatus.COMPLETED)
        with self.assertRaises(PlanStateConsistencyError):
            PlanStep("step-1", "跳过", PlanStepStatus.SKIPPED)
        with self.assertRaises(PlanStateConsistencyError):
            PlanStep("step-1", "终止", PlanStepStatus.FAILED)

    def test_aborted_plan_preserves_failed_frontier_and_pending_suffix(self):
        plan = PlanState(
            plan_id="plan-1",
            goal="顺序执行",
            status=PlanStatus.ABORTED,
            outcome=PlanOutcome.PARTIAL,
            current_step_id=None,
            steps=[
                PlanStep(
                    "step-1",
                    "第一步",
                    PlanStepStatus.COMPLETED,
                    result_summary="完成",
                ),
                PlanStep(
                    "step-2",
                    "第二步",
                    PlanStepStatus.FAILED,
                    failure_reason="终止",
                ),
                PlanStep("step-3", "第三步", PlanStepStatus.PENDING),
            ],
            total_tool_call_count=0,
            total_retry_count=0,
            max_tool_calls_per_step=3,
            max_total_tool_calls=5,
            abort_reason="终止",
        )

        self.assertEqual(plan.steps[-1].status, PlanStepStatus.PENDING)

    def test_non_aborted_plan_rejects_abort_reason(self):
        with self.assertRaises(PlanStateConsistencyError):
            PlanState(
                plan_id="plan-1",
                goal="顺序执行",
                status=PlanStatus.RUNNING,
                outcome=None,
                current_step_id="step-1",
                steps=[PlanStep("step-1", "第一步", PlanStepStatus.RUNNING)],
                total_tool_call_count=0,
                total_retry_count=0,
                max_tool_calls_per_step=3,
                max_total_tool_calls=5,
                abort_reason="不应存在",
            )

    def test_running_plan_rejects_pending_step_before_current_step(self):
        with self.assertRaises(PlanStateConsistencyError):
            PlanState(
                plan_id="plan-1",
                goal="顺序执行",
                status=PlanStatus.RUNNING,
                outcome=None,
                current_step_id="step-2",
                steps=[
                    PlanStep("step-1", "第一步", PlanStepStatus.PENDING),
                    PlanStep("step-2", "第二步", PlanStepStatus.RUNNING),
                    PlanStep("step-3", "第三步", PlanStepStatus.PENDING),
                ],
                total_tool_call_count=0,
                total_retry_count=0,
                max_tool_calls_per_step=3,
                max_total_tool_calls=5,
            )

    def test_finalizing_plan_rejects_unexecuted_pending_step(self):
        with self.assertRaises(PlanStateConsistencyError):
            PlanState(
                plan_id="plan-1",
                goal="顺序执行",
                status=PlanStatus.FINALIZING,
                outcome=PlanOutcome.PARTIAL,
                current_step_id=None,
                steps=[
                    PlanStep(
                        "step-1",
                        "第一步",
                        PlanStepStatus.COMPLETED,
                        result_summary="完成",
                    ),
                    PlanStep("step-2", "第二步", PlanStepStatus.PENDING),
                ],
                total_tool_call_count=0,
                total_retry_count=0,
                max_tool_calls_per_step=3,
                max_total_tool_calls=5,
            )

    def test_round_trip_preserves_steps_limits_and_call_ids(self):
        state = build_plan_state(tool_call_ids=["call-1"])

        restored = PlanState.from_dict(state.to_dict())

        self.assertEqual(restored, state)
        self.assertEqual(restored.steps[0].attempt_count, 1)
        self.assertEqual(restored.max_total_tool_calls, 5)

    def test_rejects_attempt_count_that_does_not_match_call_ids(self):
        with self.assertRaises(PlanStateConsistencyError):
            PlanState(
                plan_id="plan-1",
                goal="查询资料",
                status=PlanStatus.RUNNING,
                outcome=None,
                current_step_id="step-1",
                steps=[
                    PlanStep(
                        step_id="step-1",
                        instruction="查询",
                        status=PlanStepStatus.RUNNING,
                        attempt_count=2,
                        tool_call_ids=["call-1"],
                    )
                ],
                total_tool_call_count=2,
                total_retry_count=0,
                max_tool_calls_per_step=3,
                max_total_tool_calls=5,
            )

    def test_run_state_round_trip_preserves_plan_state(self):
        plan_state = build_plan_state(tool_call_ids=["call-1"])
        state = build_run_state(
            plan_state,
            phase="plan_step_deciding",
            tool_traces=[build_trace("call-1")],
        )

        restored = RunState.from_dict(state.to_dict())

        self.assertEqual(restored.plan_state, plan_state)

    def test_old_run_state_payload_defaults_plan_state_to_none(self):
        state = build_run_state(None, phase="not_started")
        payload = state.to_dict()
        payload.pop("plan_state", None)

        restored = RunState.from_dict(payload)

        self.assertIsNone(restored.plan_state)

    def test_plan_tool_pending_requires_matching_pending_call(self):
        plan_state = build_plan_state(tool_call_ids=["call-1"])

        with self.assertRaises(PlanStateConsistencyError):
            build_run_state(plan_state, phase="plan_tool_pending")

        state = build_run_state(
            plan_state,
            phase="plan_tool_pending",
            pending_tool_call=PendingToolCall(
                tool_name="retrieval.search",
                arguments={"query": "checkpoint"},
                call_id="call-1",
            ),
        )
        self.assertEqual(state.pending_tool_call.call_id, "call-1")

    def test_plan_step_deciding_requires_trace_for_each_call_id(self):
        plan_state = build_plan_state(tool_call_ids=["call-1"])

        with self.assertRaises(PlanStateConsistencyError):
            build_run_state(plan_state, phase="plan_step_deciding")

    def test_rejects_outcome_inconsistent_with_step_terminal_states(self):
        with self.assertRaises(PlanStateConsistencyError):
            build_plan_state(
                status=PlanStatus.FINALIZING,
                outcome=PlanOutcome.FAILED,
            )

    def test_final_answer_phase_requires_current_run_message(self):
        plan_state = build_plan_state(
            status=PlanStatus.COMPLETED,
            outcome=PlanOutcome.SUCCEEDED,
        )

        with self.assertRaisesRegex(
            PlanStateConsistencyError,
            "agent_phase='plan_final_answer_written' with PlanStatus='completed' "
            "requires exactly one plan final answer for run_id='run-1' and "
            "plan_id='plan-1'; found 0",
        ):
            build_run_state(plan_state, phase="plan_final_answer_written")

    def test_final_answer_phase_identifies_tagged_message_when_not_last(self):
        plan_state = build_plan_state(
            status=PlanStatus.COMPLETED,
            outcome=PlanOutcome.SUCCEEDED,
        )
        messages = [
            SessionMessage(
                role="assistant",
                content="最终回答",
                metadata={
                    "message_type": "plan_final_answer",
                    "run_id": "run-1",
                    "plan_id": "plan-1",
                },
            ),
            SessionMessage(role="user", content="异常尾消息"),
        ]

        state = RunState(
            run_id="run-1",
            session_id="session-1",
            workflow_id="workflow-1",
            status=RunStatus.RUNNING,
            user_input="查询资料",
            messages=messages,
            cursor=ExecutionCursor(
                next_node_id="agent",
                agent_phase="plan_final_answer_written",
            ),
            plan_state=plan_state,
        )

        self.assertEqual(state.messages[0].content, "最终回答")

    def test_completed_phase_requires_current_run_final_message(self):
        plan_state = build_plan_state(
            status=PlanStatus.COMPLETED,
            outcome=PlanOutcome.SUCCEEDED,
        )

        with self.assertRaisesRegex(
            PlanStateConsistencyError,
            "agent_phase='completed' with PlanStatus='completed' requires exactly "
            "one plan final answer for run_id='run-1' and plan_id='plan-1'; found 0",
        ):
            RunState(
                run_id="run-1",
                session_id="session-1",
                workflow_id="workflow-1",
                status=RunStatus.COMPLETED,
                user_input="查询资料",
                cursor=ExecutionCursor(
                    next_node_id=None,
                    agent_phase="completed",
                ),
                plan_state=plan_state,
            )

    def test_active_plan_phase_rejects_completed_runtime_status(self):
        plan_state = build_plan_state()

        with self.assertRaises(PlanStateConsistencyError):
            RunState(
                run_id="run-1",
                session_id="session-1",
                workflow_id="workflow-1",
                status=RunStatus.COMPLETED,
                user_input="查询资料",
                cursor=ExecutionCursor(
                    next_node_id="agent",
                    agent_phase="plan_step_deciding",
                ),
                plan_state=plan_state,
            )

    def test_pending_call_must_match_latest_step_call_id(self):
        plan_state = build_plan_state(tool_call_ids=["call-1"])

        with self.assertRaises(PlanStateConsistencyError):
            build_run_state(
                plan_state,
                phase="plan_tool_pending",
                pending_tool_call=PendingToolCall(
                    tool_name="retrieval.search",
                    arguments={},
                    call_id="different-call",
                ),
            )

    def test_pending_phase_requires_traces_for_earlier_step_calls(self):
        plan_state = build_plan_state(
            tool_call_ids=["completed-call", "pending-call"]
        )

        with self.assertRaises(PlanStateConsistencyError):
            build_run_state(
                plan_state,
                phase="plan_tool_pending",
                pending_tool_call=PendingToolCall(
                    tool_name="retrieval.search",
                    arguments={"query": "checkpoint"},
                    call_id="pending-call",
                ),
            )


if __name__ == "__main__":
    unittest.main()

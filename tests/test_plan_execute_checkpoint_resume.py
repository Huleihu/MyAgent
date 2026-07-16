"""
本文件负责验证 Plan-and-Execute 的 Checkpoint 恢复、at-least-once 和失败持久化。
本文件不访问真实模型服务或外部工具平台。
"""

from __future__ import annotations

import unittest
from pathlib import Path
from uuid import uuid4

from my_agent.agent_loop.plan_actions import (
    CompleteStepAction,
    PlannerProtocolError,
    StepDecision,
)
from my_agent.agent_loop.plan_execute import PlanAndExecuteAgentLoop
from my_agent.agent_loop.plan_planner import PlanDefinition, PlanStepDefinition
from my_agent.agent_loop.planner import FinalAnswerAction, ToolAction
from my_agent.dsl.loader import WorkflowLoader
from my_agent.runtime.conversation import ConversationRuntime, RunExecutionFailedError
from my_agent.runtime.executor import RuntimeExecutor
from my_agent.runtime.graph import RuntimeGraph
from my_agent.runtime.node_runner import (
    AgentLoopNodeRunner,
    BeginNodeRunner,
    MessageNodeRunner,
)
from my_agent.state.checkpoint_recorder import CheckpointRecorder
from my_agent.state.checkpoint import Checkpoint
from my_agent.state.checkpoint_store import InMemoryCheckpointStore
from my_agent.state.plan_state import (
    PlanOutcome,
    PlanState,
    PlanStatus,
    PlanStep,
    PlanStepStatus,
)
from my_agent.state.recorder import TraceRecorder
from my_agent.state.run_state import (
    ExecutionCursor,
    PendingToolCall,
    RunState,
    RunStatus,
)
from my_agent.state.session import SessionMessage, SessionState
from my_agent.state.trace import ToolTraceRecord
from my_agent.state.sqlite_checkpoint_store import SQLiteCheckpointStore
from my_agent.tools.executor import ToolExecutor
from my_agent.tools.function_tool import FunctionTool
from my_agent.tools.registry import ToolRegistry


class StaticTaskPlanner:
    """生成单步骤计划和固定最终回答。"""

    def create_plan(self, request):
        return PlanDefinition(
            goal="执行计数工具",
            steps=(PlanStepDefinition("调用工具并确认"),),
        )

    def finalize_plan(self, request):
        return FinalAnswerAction("执行完成")


class CountingTaskPlanner(StaticTaskPlanner):
    """记录恢复阶段是否错误地创建或重复终结计划。"""

    def __init__(self):
        self.create_calls = 0
        self.finalize_calls = 0

    def create_plan(self, request):
        self.create_calls += 1
        return super().create_plan(request)

    def finalize_plan(self, request):
        self.finalize_calls += 1
        return super().finalize_plan(request)


class RaisingToolExecutor(ToolExecutor):
    """模拟工具边界直接抛出异常而非返回失败结果。"""

    def __init__(self, registry):
        super().__init__(registry)
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        raise RuntimeError("executor transport failed")


class QueueStepPlanner:
    """按顺序返回步骤决策并记录调用次数。"""

    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.requests = []

    def decide(self, request):
        self.requests.append(request)
        return self.decisions.pop(0)


class FailingObservationSession(SessionState):
    """模拟工具成功后、observation 写入前的进程崩溃。"""

    def add_message(self, role, content, metadata=None):
        if metadata and metadata.get("message_type") == "tool_observation":
            raise RuntimeError("crash before observation checkpoint")
        return super().add_message(role, content, metadata)


def build_counter_tool(call_ids, effect_count):
    """构造记录 call ID 外部效果的本地工具。"""
    def execute(arguments):
        effect_count["value"] += 1
        return {"value": effect_count["value"]}

    return FunctionTool(
        name="counter.increment",
        description="增加计数",
        parameters={"type": "object", "properties": {}},
        func=execute,
    )


def build_loop(
    session,
    run_state,
    store,
    step_planner,
    effect_count,
    call_ids,
    task_planner=None,
    tool_executor=None,
):
    """构造使用共享 Store 和外部效果计数器的 Loop。"""
    tool = build_counter_tool(call_ids, effect_count)
    registry = ToolRegistry()
    registry.register(tool)
    executor = tool_executor or ToolExecutor(registry, TraceRecorder(session))
    if tool_executor is None:
        original_execute = executor.execute

        def record_call(request):
            call_ids.append(request.call_id)
            return original_execute(request)

        executor.execute = record_call
    recorder = CheckpointRecorder(session, run_state, store)
    return PlanAndExecuteAgentLoop(
        task_planner=task_planner or StaticTaskPlanner(),
        step_planner=step_planner,
        tool_executor=executor,
        tool_definitions=[tool.definition],
        session_state=session,
        run_state=run_state,
        checkpoint_recorder=recorder,
        max_tool_calls_per_step=1,
        max_total_tool_calls=1,
    )


def build_run_state(session_id="session-1"):
    """构造尚未创建计划的 Runtime 状态。"""
    return RunState(
        run_id="run-1",
        session_id=session_id,
        workflow_id="plan-resume-test",
        status=RunStatus.RUNNING,
        user_input="执行计数",
        cursor=ExecutionCursor(next_node_id="agent", agent_phase="not_started"),
    )


def build_conversation_runtime(
    session,
    store,
    step_planner,
    effect_count,
    call_ids,
):
    """构造通过现有 DSL 和 ConversationRuntime 执行计划的实例。"""
    tool = build_counter_tool(call_ids, effect_count)
    registry = ToolRegistry()
    registry.register(tool)
    executor = ToolExecutor(registry, TraceRecorder(session))
    original_execute = executor.execute

    def record_call(request):
        call_ids.append(request.call_id)
        return original_execute(request)

    executor.execute = record_call
    loop = PlanAndExecuteAgentLoop(
        task_planner=StaticTaskPlanner(),
        step_planner=step_planner,
        tool_executor=executor,
        tool_definitions=[tool.definition],
        session_state=session,
        max_tool_calls_per_step=2,
        max_total_tool_calls=2,
    )
    workflow = WorkflowLoader().load_dict(
        {
            "workflow_id": "plan-resume-test",
            "nodes": [
                {"node_id": "begin", "node_type": "begin"},
                {
                    "node_id": "agent",
                    "node_type": "agent_loop",
                    "inputs": {"user_input": "{{user_input}}"},
                },
                {
                    "node_id": "message",
                    "node_type": "message",
                    "inputs": {"content": "{{agent.output}}"},
                },
            ],
            "edges": [
                {"source": "begin", "target": "agent"},
                {"source": "agent", "target": "message"},
            ],
        }
    )
    runtime_executor = RuntimeExecutor(
        RuntimeGraph(workflow),
        {
            "begin": BeginNodeRunner(),
            "agent_loop": AgentLoopNodeRunner(loop),
            "message": MessageNodeRunner(),
        },
    )
    return ConversationRuntime(
        runtime_executor,
        session,
        store,
        workflow.workflow_id,
    )


class PlanExecuteCheckpointResumeTest(unittest.TestCase):
    def test_sqlite_restore_uses_persisted_limits_over_new_runtime_config(self):
        path = Path.cwd() / f"plan-limits-{uuid4().hex}.db"
        store = SQLiteCheckpointStore(path)
        try:
            trace = ToolTraceRecord(
                trace_id="trace-1",
                tool_name="counter.increment",
                call_id="call-1",
                arguments={},
                success=True,
                result={"value": 1},
                error=None,
                duration_ms=1.0,
            )
            session = SessionState(session_id="session-1")
            session.add_message("user", "执行计数")
            session.add_tool_trace(trace)
            plan = PlanState(
                plan_id="plan-1",
                goal="执行计数",
                status=PlanStatus.RUNNING,
                outcome=None,
                current_step_id="step-1",
                steps=[
                    PlanStep(
                        "step-1",
                        "确认结果",
                        PlanStepStatus.RUNNING,
                        attempt_count=1,
                        tool_call_ids=["call-1"],
                    )
                ],
                total_tool_call_count=1,
                total_retry_count=0,
                max_tool_calls_per_step=1,
                max_total_tool_calls=1,
            )
            state = RunState(
                run_id="run-1",
                session_id="session-1",
                workflow_id="plan-resume-test",
                status=RunStatus.RUNNING,
                user_input="执行计数",
                messages=session.list_messages(),
                tool_traces=session.list_tool_traces(),
                cursor=ExecutionCursor(
                    next_node_id="agent",
                    agent_phase="plan_step_deciding",
                ),
                plan_state=plan,
            )
            store.save(Checkpoint.create(state))
            restored_state = store.get_latest("run-1").run_state
            restored_session = SessionState(session_id="session-1")
            restored_session.restore_snapshot(
                restored_state.messages,
                restored_state.tool_traces,
            )
            step_planner = QueueStepPlanner(
                [StepDecision(CompleteStepAction("达到持久化限制后完成"))]
            )
            tool = build_counter_tool([], {"value": 0})
            registry = ToolRegistry()
            registry.register(tool)
            loop = PlanAndExecuteAgentLoop(
                task_planner=CountingTaskPlanner(),
                step_planner=step_planner,
                tool_executor=ToolExecutor(registry),
                tool_definitions=[tool.definition],
                session_state=restored_session,
                run_state=restored_state,
                max_tool_calls_per_step=9,
                max_total_tool_calls=9,
            )

            loop.run("执行计数")

            request = step_planner.requests[0]
            self.assertFalse(request.can_call_tool)
            self.assertEqual(request.remaining_step_tool_calls, 0)
            self.assertEqual(request.remaining_total_tool_calls, 0)
            self.assertEqual(restored_state.plan_state.max_total_tool_calls, 1)
        finally:
            store.close()
            if path.exists():
                path.unlink()

    def test_executor_exception_preserves_pending_call_and_counters(self):
        session = SessionState(session_id="session-1")
        state = build_run_state()
        store = InMemoryCheckpointStore()
        registry = ToolRegistry()
        raising_executor = RaisingToolExecutor(registry)
        loop = build_loop(
            session,
            state,
            store,
            QueueStepPlanner(
                [StepDecision(ToolAction("counter.increment", {}))]
            ),
            {"value": 0},
            [],
            tool_executor=raising_executor,
        )

        with self.assertRaisesRegex(RuntimeError, "executor transport failed"):
            loop.run("执行计数")

        checkpoint_state = store.get_latest("run-1").run_state
        self.assertEqual(checkpoint_state.cursor.agent_phase, "plan_tool_pending")
        self.assertEqual(checkpoint_state.plan_state.total_tool_call_count, 1)
        self.assertEqual(checkpoint_state.plan_state.total_retry_count, 0)
        self.assertEqual(len(raising_executor.requests), 1)
        self.assertEqual(
            raising_executor.requests[0].call_id,
            checkpoint_state.pending_tool_call.call_id,
        )

    def test_plan_creating_resume_only_recreates_plan_once(self):
        session = SessionState(session_id="session-1")
        session.add_message("user", "执行计数")
        state = build_run_state()
        state.messages = session.list_messages()
        state.cursor.agent_phase = "plan_creating"
        task_planner = CountingTaskPlanner()
        loop = build_loop(
            session,
            state,
            InMemoryCheckpointStore(),
            QueueStepPlanner([StepDecision(CompleteStepAction("无需工具"))]),
            {"value": 0},
            [],
            task_planner,
        )

        loop.run("执行计数")

        self.assertEqual(task_planner.create_calls, 1)
        self.assertEqual(task_planner.finalize_calls, 1)
        self.assertEqual(
            [message.role for message in session.list_messages()].count("user"),
            1,
        )

    def test_plan_step_deciding_resume_skips_task_creation(self):
        session = SessionState(session_id="session-1")
        session.add_message("user", "执行计数")
        plan = PlanState(
            plan_id="plan-1",
            goal="执行计数",
            status=PlanStatus.RUNNING,
            outcome=None,
            current_step_id="step-1",
            steps=[PlanStep("step-1", "确认结果", PlanStepStatus.RUNNING)],
            total_tool_call_count=0,
            total_retry_count=0,
            max_tool_calls_per_step=1,
            max_total_tool_calls=1,
        )
        state = RunState(
            run_id="run-1",
            session_id="session-1",
            workflow_id="plan-resume-test",
            status=RunStatus.RUNNING,
            user_input="执行计数",
            messages=session.list_messages(),
            cursor=ExecutionCursor(
                next_node_id="agent", agent_phase="plan_step_deciding"
            ),
            plan_state=plan,
        )
        task_planner = CountingTaskPlanner()
        step_planner = QueueStepPlanner(
            [StepDecision(CompleteStepAction("已确认"))]
        )
        loop = build_loop(
            session,
            state,
            InMemoryCheckpointStore(),
            step_planner,
            {"value": 0},
            [],
            task_planner,
        )

        loop.run("执行计数")

        self.assertEqual(task_planner.create_calls, 0)
        self.assertEqual(task_planner.finalize_calls, 1)
        self.assertEqual(len(step_planner.requests), 1)

    def test_plan_finalizing_resume_only_repeats_pure_finalization(self):
        session = SessionState(session_id="session-1")
        session.add_message("user", "执行计数")
        plan = PlanState(
            plan_id="plan-1",
            goal="执行计数",
            status=PlanStatus.FINALIZING,
            outcome=PlanOutcome.SUCCEEDED,
            current_step_id=None,
            steps=[
                PlanStep(
                    "step-1",
                    "确认结果",
                    PlanStepStatus.COMPLETED,
                    result_summary="已确认",
                )
            ],
            total_tool_call_count=0,
            total_retry_count=0,
            max_tool_calls_per_step=1,
            max_total_tool_calls=1,
        )
        state = RunState(
            run_id="run-1",
            session_id="session-1",
            workflow_id="plan-resume-test",
            status=RunStatus.RUNNING,
            user_input="执行计数",
            messages=session.list_messages(),
            cursor=ExecutionCursor(
                next_node_id="agent", agent_phase="plan_finalizing"
            ),
            plan_state=plan,
        )
        task_planner = CountingTaskPlanner()
        step_planner = QueueStepPlanner([])
        loop = build_loop(
            session,
            state,
            InMemoryCheckpointStore(),
            step_planner,
            {"value": 0},
            [],
            task_planner,
        )

        self.assertEqual(loop.run("执行计数"), "执行完成")
        self.assertEqual(task_planner.create_calls, 0)
        self.assertEqual(task_planner.finalize_calls, 1)
        self.assertEqual(len(step_planner.requests), 0)

    def test_final_answer_written_resume_returns_tagged_answer_without_planner(self):
        final_message = SessionMessage(
            role="assistant",
            content="已持久化回答",
            metadata={
                "message_type": "plan_final_answer",
                "run_id": "run-1",
                "plan_id": "plan-1",
            },
        )
        session = SessionState(
            session_id="session-1",
            messages=[final_message, SessionMessage("user", "无关尾消息")],
        )
        plan = PlanState(
            plan_id="plan-1",
            goal="执行计数",
            status=PlanStatus.COMPLETED,
            outcome=PlanOutcome.SUCCEEDED,
            current_step_id=None,
            steps=[
                PlanStep(
                    "step-1",
                    "确认结果",
                    PlanStepStatus.COMPLETED,
                    result_summary="已确认",
                )
            ],
            total_tool_call_count=0,
            total_retry_count=0,
            max_tool_calls_per_step=1,
            max_total_tool_calls=1,
        )
        state = RunState(
            run_id="run-1",
            session_id="session-1",
            workflow_id="plan-resume-test",
            status=RunStatus.RUNNING,
            user_input="执行计数",
            messages=session.list_messages(),
            cursor=ExecutionCursor(
                next_node_id="agent",
                agent_phase="plan_final_answer_written",
            ),
            plan_state=plan,
        )
        task_planner = CountingTaskPlanner()
        step_planner = QueueStepPlanner([])
        loop = build_loop(
            session,
            state,
            InMemoryCheckpointStore(),
            step_planner,
            {"value": 0},
            [],
            task_planner,
        )

        self.assertEqual(loop.run("执行计数"), "已持久化回答")
        self.assertEqual(task_planner.create_calls, 0)
        self.assertEqual(task_planner.finalize_calls, 0)
        self.assertEqual(len(step_planner.requests), 0)
        self.assertEqual(len(session.list_messages()), 2)

    def test_pending_resume_reuses_call_id_without_incrementing_attempt(self):
        store = InMemoryCheckpointStore()
        effect_count = {"value": 0}
        call_ids = []
        first_session = FailingObservationSession(session_id="session-1")
        first_state = build_run_state()
        first_loop = build_loop(
            first_session,
            first_state,
            store,
            QueueStepPlanner(
                [StepDecision(ToolAction("counter.increment", {}))]
            ),
            effect_count,
            call_ids,
        )

        with self.assertRaisesRegex(RuntimeError, "crash before observation"):
            first_loop.run("执行计数")

        checkpoint = store.get_latest("run-1")
        self.assertEqual(checkpoint.run_state.cursor.agent_phase, "plan_tool_pending")
        persisted_call_id = checkpoint.run_state.pending_tool_call.call_id
        self.assertEqual(checkpoint.run_state.plan_state.steps[0].attempt_count, 1)

        restored_state = checkpoint.run_state
        restored_session = SessionState(session_id="session-1")
        restored_session.restore_snapshot(
            restored_state.messages,
            restored_state.tool_traces,
        )
        restored_step_planner = QueueStepPlanner(
            [StepDecision(CompleteStepAction("计数已确认"))]
        )
        restored_task_planner = CountingTaskPlanner()
        restored_loop = build_loop(
            restored_session,
            restored_state,
            store,
            restored_step_planner,
            effect_count,
            call_ids,
            restored_task_planner,
        )

        restored_loop.run("执行计数")

        self.assertEqual(effect_count["value"], 2)
        self.assertEqual(call_ids, [persisted_call_id, persisted_call_id])
        self.assertEqual(restored_state.plan_state.steps[0].attempt_count, 1)
        self.assertEqual(restored_state.plan_state.steps[0].retry_count, 0)
        self.assertEqual(len(restored_step_planner.requests), 1)
        self.assertEqual(restored_task_planner.create_calls, 0)
        self.assertEqual(restored_task_planner.finalize_calls, 1)

    def test_tool_action_over_persisted_limit_writes_failed_checkpoint(self):
        store = InMemoryCheckpointStore()
        effect_count = {"value": 0}
        call_ids = []
        session = SessionState(session_id="session-1")
        state = build_run_state()
        step_planner = QueueStepPlanner(
            [
                StepDecision(ToolAction("missing.tool", {})),
                StepDecision(
                    ToolAction("counter.increment", {}),
                    reflection="该无效决策不应落盘",
                ),
            ]
        )
        loop = build_loop(
            session,
            state,
            store,
            step_planner,
            effect_count,
            call_ids,
        )

        with self.assertRaises(PlannerProtocolError):
            loop.run("执行计数")

        latest = store.get_latest("run-1").run_state
        self.assertEqual(latest.status, RunStatus.FAILED)
        self.assertEqual(latest.error["code"], "planner_protocol_error")
        self.assertEqual(latest.plan_state.total_tool_call_count, 1)
        self.assertEqual(effect_count["value"], 0)
        self.assertIsNone(latest.pending_tool_call)
        self.assertIsNone(latest.plan_state.steps[0].reflection)

    def test_sqlite_cross_runtime_resume_restores_plan_and_session(self):
        path = Path.cwd() / f"plan-runtime-{uuid4().hex}.db"
        effect_count = {"value": 0}
        call_ids = []
        try:
            first_store = SQLiteCheckpointStore(path)
            first_runtime = build_conversation_runtime(
                FailingObservationSession(session_id="session-1"),
                first_store,
                QueueStepPlanner(
                    [StepDecision(ToolAction("counter.increment", {}))]
                ),
                effect_count,
                call_ids,
            )

            with self.assertRaises(RunExecutionFailedError) as raised:
                first_runtime.start("执行计数")
            run_id = raised.exception.run_id
            pending_call_id = first_store.get_latest(
                run_id
            ).run_state.pending_tool_call.call_id
            first_store.close()

            second_store = SQLiteCheckpointStore(path)
            second_session = SessionState(session_id="session-1")
            result = build_conversation_runtime(
                second_session,
                second_store,
                QueueStepPlanner(
                    [StepDecision(CompleteStepAction("计数已确认"))]
                ),
                effect_count,
                call_ids,
            ).resume(run_id)

            self.assertEqual(result.output_text, "执行完成")
            self.assertEqual(effect_count["value"], 2)
            self.assertEqual(call_ids, [pending_call_id, pending_call_id])
            latest = second_store.get_latest(run_id).run_state
            self.assertEqual(latest.status, RunStatus.COMPLETED)
            self.assertEqual(latest.cursor.agent_phase, "completed")
            self.assertEqual(latest.plan_state.status.value, "completed")
            self.assertEqual(
                second_session.list_messages()[-1].metadata["message_type"],
                "plan_final_answer",
            )
            second_store.close()
        finally:
            if path.exists():
                path.unlink()

    def test_runtime_failure_checkpoint_preserves_planner_error_code(self):
        store = InMemoryCheckpointStore()
        session = SessionState(session_id="session-1")
        runtime = build_conversation_runtime(
            session,
            store,
            QueueStepPlanner(
                [
                    StepDecision(
                        ToolAction(
                            "counter.increment",
                            {},
                            call_id="provider-controlled-call",
                        )
                    )
                ]
            ),
            {"value": 0},
            [],
        )

        with self.assertRaises(RunExecutionFailedError) as raised:
            runtime.start("执行计数")

        latest = store.get_latest(raised.exception.run_id).run_state
        self.assertEqual(latest.status, RunStatus.FAILED)
        self.assertEqual(latest.error["code"], "planner_protocol_error")


if __name__ == "__main__":
    unittest.main()

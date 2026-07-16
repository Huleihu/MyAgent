"""
本文件负责验证 Plan-and-Execute 的计划推进、显式步骤终态和多工具历史关联。
本文件不测试真实模型服务或跨进程 SQLite 恢复。
"""

from __future__ import annotations

import unittest

from my_agent.agent_loop.plan_actions import (
    AbortPlanAction,
    CompleteStepAction,
    SkipStepAction,
    StepDecision,
    PlannerProtocolError,
)
from my_agent.agent_loop.plan_execute import PlanAndExecuteAgentLoop
from my_agent.agent_loop.plan_planner import (
    PlanDefinition,
    PlanStepDefinition,
)
from my_agent.agent_loop.planner import FinalAnswerAction, ToolAction
from my_agent.state.plan_state import (
    PlanOutcome,
    PlanState,
    PlanStateConsistencyError,
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
from my_agent.state.session import SessionState
from my_agent.state.trace import ToolTraceRecord
from my_agent.tools.executor import ToolExecutor
from my_agent.tools.function_tool import FunctionTool
from my_agent.tools.registry import ToolRegistry
from my_agent.tools.schema import ToolCallResult


class MismatchedResultExecutor(ToolExecutor):
    """模拟违反 ToolExecutor 结果关联契约的适配器。"""

    def execute(self, request):
        return ToolCallResult.success_result(
            name="other.tool",
            data={"result": 99},
            duration_ms=0,
            call_id="other-call",
        )


class FakeTaskPlanner:
    """按固定计划和最终回答驱动任务级测试。"""

    def __init__(self) -> None:
        self.create_calls = 0
        self.finalize_calls = 0

    def create_plan(self, request):
        self.create_calls += 1
        return PlanDefinition(
            goal="完成两次计算",
            steps=(PlanStepDefinition("计算并确认结果"),),
        )

    def finalize_plan(self, request):
        self.finalize_calls += 1
        return FinalAnswerAction("计划执行完成")


class FakeStepPlanner:
    """按固定决策顺序返回动作并记录每次输入快照。"""

    def __init__(self, decisions):
        self._decisions = list(decisions)
        self.requests = []

    def decide(self, request):
        self.requests.append(request)
        return self._decisions.pop(0)


class MutatingStepPlanner:
    """主动修改全部嵌套快照，验证不会反向污染真实状态。"""

    def decide(self, request):
        request.plan["steps"][0]["instruction"] = "污染计划"
        request.current_step["instruction"] = "污染当前步骤"
        request.messages[0]["metadata"]["nested"]["value"] = "污染消息"
        request.tool_definitions[0]["parameters"]["properties"]["a"][
            "type"
        ] = "string"
        request.observations[0]["result"]["nested"]["items"].append("污染结果")
        return StepDecision(CompleteStepAction("快照隔离已确认"))


def build_tool_definition():
    """构造计算工具定义。"""
    return FunctionTool(
        name="calculator.add",
        description="计算两个数字之和",
        parameters={
            "type": "object",
            "properties": {
                "a": {"type": "number"},
                "b": {"type": "number"},
            },
            "required": ["a", "b"],
        },
        func=lambda arguments: {"result": arguments["a"] + arguments["b"]},
    )


def build_loop(step_planner):
    """构造带 RunState 和 Trace 的 Plan-and-Execute Loop。"""
    session = SessionState(session_id="session-1")
    tool = build_tool_definition()
    registry = ToolRegistry()
    registry.register(tool)
    run_state = RunState(
        run_id="run-1",
        session_id=session.session_id,
        workflow_id="plan-test",
        status=RunStatus.RUNNING,
        user_input="执行计算",
        cursor=ExecutionCursor(next_node_id="agent", agent_phase="not_started"),
    )
    task_planner = FakeTaskPlanner()
    loop = PlanAndExecuteAgentLoop(
        task_planner=task_planner,
        step_planner=step_planner,
        tool_executor=ToolExecutor(registry, TraceRecorder(session)),
        tool_definitions=[tool.definition],
        session_state=session,
        run_state=run_state,
        max_tool_calls_per_step=3,
        max_total_tool_calls=5,
    )
    return loop, task_planner, session, run_state


class PlanAndExecuteAgentLoopTest(unittest.TestCase):
    def test_step_planner_nested_mutations_do_not_change_runtime_state(self):
        session = SessionState(session_id="session-1")
        session.add_message(
            "user",
            "恢复计算",
            metadata={"nested": {"value": "原始消息"}},
        )
        trace = ToolTraceRecord(
            trace_id="trace-1",
            tool_name="calculator.add",
            call_id="call-1",
            arguments={"a": 1, "b": 2},
            success=True,
            result={"nested": {"items": ["原始结果"]}},
            error=None,
            duration_ms=1.0,
        )
        session.add_tool_trace(trace)
        plan = PlanState(
            plan_id="plan-1",
            goal="确认快照隔离",
            status=PlanStatus.RUNNING,
            outcome=None,
            current_step_id="step-1",
            steps=[
                PlanStep(
                    "step-1",
                    "原始步骤",
                    PlanStepStatus.RUNNING,
                    attempt_count=1,
                    tool_call_ids=["call-1"],
                )
            ],
            total_tool_call_count=1,
            total_retry_count=0,
            max_tool_calls_per_step=2,
            max_total_tool_calls=2,
        )
        run_state = RunState(
            run_id="run-1",
            session_id="session-1",
            workflow_id="plan-test",
            status=RunStatus.RUNNING,
            user_input="恢复计算",
            messages=session.list_messages(),
            tool_traces=session.list_tool_traces(),
            cursor=ExecutionCursor(
                next_node_id="agent", agent_phase="plan_step_deciding"
            ),
            plan_state=plan,
        )
        tool = build_tool_definition()
        registry = ToolRegistry()
        registry.register(tool)
        loop = PlanAndExecuteAgentLoop(
            task_planner=FakeTaskPlanner(),
            step_planner=MutatingStepPlanner(),
            tool_executor=ToolExecutor(registry),
            tool_definitions=[tool.definition],
            session_state=session,
            run_state=run_state,
        )

        loop.run("恢复计算")

        self.assertEqual(plan.steps[0].instruction, "原始步骤")
        self.assertEqual(
            session.list_messages()[0].metadata["nested"]["value"],
            "原始消息",
        )
        self.assertEqual(
            tool.definition.parameters["properties"]["a"]["type"],
            "number",
        )
        self.assertEqual(
            session.list_tool_traces()[0].result["nested"]["items"],
            ["原始结果"],
        )

    def test_observations_follow_call_id_order_when_traces_are_physically_reversed(self):
        session = SessionState(session_id="session-1")
        session.add_message("user", "恢复计算")
        for call_id, result in (("call-2", 2), ("call-1", 1)):
            session.add_tool_trace(
                ToolTraceRecord(
                    trace_id=f"trace-{call_id}",
                    tool_name="calculator.add",
                    call_id=call_id,
                    arguments={"a": result, "b": 0},
                    success=True,
                    result={"result": result},
                    error=None,
                    duration_ms=1.0,
                )
            )
        plan = PlanState(
            plan_id="plan-1",
            goal="确认顺序",
            status=PlanStatus.RUNNING,
            outcome=None,
            current_step_id="step-1",
            steps=[
                PlanStep(
                    "step-1",
                    "确认两次结果",
                    PlanStepStatus.RUNNING,
                    attempt_count=2,
                    tool_call_ids=["call-1", "call-2"],
                )
            ],
            total_tool_call_count=2,
            total_retry_count=0,
            max_tool_calls_per_step=3,
            max_total_tool_calls=3,
        )
        run_state = RunState(
            run_id="run-1",
            session_id="session-1",
            workflow_id="plan-test",
            status=RunStatus.RUNNING,
            user_input="恢复计算",
            messages=session.list_messages(),
            tool_traces=session.list_tool_traces(),
            cursor=ExecutionCursor(
                next_node_id="agent", agent_phase="plan_step_deciding"
            ),
            plan_state=plan,
        )
        step_planner = FakeStepPlanner(
            [StepDecision(CompleteStepAction("顺序已确认"))]
        )
        tool = build_tool_definition()
        registry = ToolRegistry()
        registry.register(tool)
        loop = PlanAndExecuteAgentLoop(
            task_planner=FakeTaskPlanner(),
            step_planner=step_planner,
            tool_executor=ToolExecutor(registry),
            tool_definitions=[tool.definition],
            session_state=session,
            run_state=run_state,
        )

        loop.run("恢复计算")

        self.assertEqual(
            [item["call_id"] for item in step_planner.requests[0].observations],
            ["call-1", "call-2"],
        )
        self.assertEqual(
            [item["result"]["result"] for item in step_planner.requests[0].observations],
            [1, 2],
        )

    def test_mismatched_tool_result_is_rejected_before_observation(self):
        session = SessionState(session_id="session-1")
        tool = build_tool_definition()
        registry = ToolRegistry()
        registry.register(tool)
        run_state = RunState(
            run_id="run-1",
            session_id="session-1",
            workflow_id="plan-test",
            status=RunStatus.RUNNING,
            user_input="执行计算",
            cursor=ExecutionCursor(next_node_id="agent", agent_phase="not_started"),
        )
        loop = PlanAndExecuteAgentLoop(
            task_planner=FakeTaskPlanner(),
            step_planner=FakeStepPlanner(
                [StepDecision(ToolAction("calculator.add", {"a": 1, "b": 2}))]
            ),
            tool_executor=MismatchedResultExecutor(registry),
            tool_definitions=[tool.definition],
            session_state=session,
            run_state=run_state,
        )

        with self.assertRaises(PlanStateConsistencyError):
            loop.run("执行计算")

        self.assertEqual(run_state.cursor.agent_phase, "plan_tool_pending")
        self.assertIsNotNone(run_state.pending_tool_call)
        self.assertEqual(len(session.list_tool_traces()), 0)
        self.assertFalse(
            any(
                message.metadata.get("message_type") == "tool_observation"
                for message in session.list_messages()
            )
        )

    def test_non_serializable_tool_arguments_fail_before_state_changes(self):
        step_planner = FakeStepPlanner(
            [
                StepDecision(
                    ToolAction(
                        "calculator.add",
                        {"a": 1, "b": 2, "invalid": {"not-json"}},
                    )
                )
            ]
        )
        loop, _, session, run_state = build_loop(step_planner)

        with self.assertRaises(PlannerProtocolError):
            loop.run("执行计算")

        step = run_state.plan_state.steps[0]
        self.assertEqual(step.attempt_count, 0)
        self.assertEqual(step.tool_call_ids, [])
        self.assertIsNone(run_state.pending_tool_call)
        self.assertEqual(session.list_tool_traces(), [])

    def test_json_coercing_tool_arguments_fail_before_state_changes(self):
        step_planner = FakeStepPlanner(
            [
                StepDecision(
                    ToolAction(
                        "calculator.add",
                        {"a": 1, "b": 2, "items": (1, 2)},
                    )
                )
            ]
        )
        loop, _, _, run_state = build_loop(step_planner)

        with self.assertRaises(PlannerProtocolError):
            loop.run("执行计算")

        self.assertEqual(run_state.plan_state.total_tool_call_count, 0)
        self.assertIsNone(run_state.pending_tool_call)

    def test_pending_replay_uses_new_failure_over_old_success_and_counts_retry(self):
        session = SessionState(session_id="session-1")
        session.add_message("user", "恢复计算")
        session.add_tool_trace(
            ToolTraceRecord(
                trace_id="trace-old",
                tool_name="calculator.add",
                call_id="call-1",
                arguments={"a": 1, "b": 1},
                success=True,
                result={"result": 1},
                error=None,
                duration_ms=1.0,
            )
        )
        tool = build_tool_definition()
        registry = ToolRegistry()
        registry.register(tool)
        step_planner = FakeStepPlanner(
            [
                StepDecision(ToolAction("calculator.add", {"a": 1, "b": 2})),
                StepDecision(CompleteStepAction("重试结果已确认")),
            ]
        )
        plan = PlanState(
            plan_id="plan-1",
            goal="恢复计算",
            status=PlanStatus.RUNNING,
            outcome=None,
            current_step_id="step-1",
            steps=[
                PlanStep(
                    step_id="step-1",
                    instruction="重新执行待处理调用",
                    status=PlanStepStatus.RUNNING,
                    attempt_count=1,
                    tool_call_ids=["call-1"],
                )
            ],
            total_tool_call_count=1,
            total_retry_count=0,
            max_tool_calls_per_step=2,
            max_total_tool_calls=2,
        )
        run_state = RunState(
            run_id="run-1",
            session_id="session-1",
            workflow_id="plan-test",
            status=RunStatus.RUNNING,
            user_input="恢复计算",
            messages=session.list_messages(),
            tool_traces=session.list_tool_traces(),
            cursor=ExecutionCursor(
                next_node_id="agent",
                agent_phase="plan_tool_pending",
            ),
            pending_tool_call=PendingToolCall(
                tool_name="calculator.add",
                arguments={"a": 1},
                call_id="call-1",
            ),
            plan_state=plan,
        )
        loop = PlanAndExecuteAgentLoop(
            task_planner=FakeTaskPlanner(),
            step_planner=step_planner,
            tool_executor=ToolExecutor(registry),
            tool_definitions=[tool.definition],
            session_state=session,
            run_state=run_state,
        )

        loop.run("恢复计算")

        self.assertEqual(len(session.list_tool_traces()), 3)
        self.assertFalse(step_planner.requests[0].observations[0]["success"])
        self.assertEqual(run_state.plan_state.steps[0].retry_count, 1)
        self.assertEqual(run_state.plan_state.steps[0].attempt_count, 2)

    def test_loop_records_required_trace_when_executor_has_no_recorder(self):
        session = SessionState(session_id="session-1")
        tool = build_tool_definition()
        registry = ToolRegistry()
        registry.register(tool)
        step_planner = FakeStepPlanner(
            [
                StepDecision(ToolAction("calculator.add", {"a": 1, "b": 2})),
                StepDecision(CompleteStepAction("结果为 3")),
            ]
        )
        run_state = RunState(
            run_id="run-1",
            session_id="session-1",
            workflow_id="plan-test",
            status=RunStatus.RUNNING,
            user_input="执行计算",
            cursor=ExecutionCursor(next_node_id="agent", agent_phase="not_started"),
        )
        loop = PlanAndExecuteAgentLoop(
            task_planner=FakeTaskPlanner(),
            step_planner=step_planner,
            tool_executor=ToolExecutor(registry),
            tool_definitions=[tool.definition],
            session_state=session,
            run_state=run_state,
        )

        answer = loop.run("执行计算")

        self.assertEqual(answer, "计划执行完成")
        self.assertEqual(len(session.list_tool_traces()), 1)
        self.assertEqual(len(step_planner.requests[-1].observations), 1)

    def test_loop_records_trace_in_its_session_when_executor_uses_other_session(self):
        session = SessionState(session_id="session-1")
        other_session = SessionState(session_id="other-session")
        tool = build_tool_definition()
        registry = ToolRegistry()
        registry.register(tool)
        step_planner = FakeStepPlanner(
            [
                StepDecision(ToolAction("calculator.add", {"a": 1, "b": 2})),
                StepDecision(CompleteStepAction("结果为 3")),
            ]
        )
        run_state = RunState(
            run_id="run-1",
            session_id="session-1",
            workflow_id="plan-test",
            status=RunStatus.RUNNING,
            user_input="执行计算",
            cursor=ExecutionCursor(next_node_id="agent", agent_phase="not_started"),
        )
        loop = PlanAndExecuteAgentLoop(
            task_planner=FakeTaskPlanner(),
            step_planner=step_planner,
            tool_executor=ToolExecutor(registry, TraceRecorder(other_session)),
            tool_definitions=[tool.definition],
            session_state=session,
            run_state=run_state,
        )

        loop.run("执行计算")

        self.assertEqual(len(other_session.list_tool_traces()), 1)
        self.assertEqual(len(session.list_tool_traces()), 1)

    def test_tool_success_requires_step_planner_to_complete_step(self):
        step_planner = FakeStepPlanner(
            [
                StepDecision(ToolAction("calculator.add", {"a": 1, "b": 2})),
                StepDecision(CompleteStepAction("计算结果为 3")),
            ]
        )
        loop, task_planner, session, run_state = build_loop(step_planner)

        answer = loop.run("执行计算")

        self.assertEqual(answer, "计划执行完成")
        self.assertEqual(len(step_planner.requests), 2)
        self.assertEqual(len(step_planner.requests[0].observations), 0)
        self.assertEqual(len(step_planner.requests[1].observations), 1)
        self.assertTrue(step_planner.requests[1].recent_observation["success"])
        self.assertEqual(
            run_state.plan_state.steps[0].status,
            PlanStepStatus.COMPLETED,
        )
        self.assertEqual(run_state.plan_state.status, PlanStatus.COMPLETED)
        self.assertEqual(run_state.plan_state.outcome, PlanOutcome.SUCCEEDED)
        self.assertEqual(task_planner.finalize_calls, 1)
        self.assertEqual(len(session.list_tool_traces()), 1)
        call_id = run_state.plan_state.steps[0].tool_call_ids[0]
        self.assertEqual(
            run_state.plan_state.steps[0].last_observation_summary,
            f"tool=calculator.add; call_id={call_id}; success=true",
        )

    def test_same_step_receives_complete_ordered_multi_tool_history(self):
        step_planner = FakeStepPlanner(
            [
                StepDecision(ToolAction("calculator.add", {"a": 1, "b": 2})),
                StepDecision(ToolAction("calculator.add", {"a": 3, "b": 4})),
                StepDecision(CompleteStepAction("两次计算已确认")),
            ]
        )
        loop, _, _, run_state = build_loop(step_planner)

        loop.run("执行两次计算")

        self.assertEqual(
            [len(request.observations) for request in step_planner.requests],
            [0, 1, 2],
        )
        last_request = step_planner.requests[-1]
        self.assertEqual(
            [item["result"]["result"] for item in last_request.observations],
            [3, 7],
        )
        call_ids = run_state.plan_state.steps[0].tool_call_ids
        self.assertEqual(len(call_ids), 2)
        self.assertEqual(len(set(call_ids)), 2)
        self.assertEqual(run_state.plan_state.steps[0].attempt_count, 2)
        self.assertEqual(run_state.plan_state.steps[0].retry_count, 0)

    def test_failed_observation_followed_by_tool_action_counts_retry(self):
        step_planner = FakeStepPlanner(
            [
                StepDecision(ToolAction("calculator.add", {"a": 1})),
                StepDecision(ToolAction("calculator.add", {"a": 1, "b": 2})),
                StepDecision(CompleteStepAction("重试后结果为 3")),
            ]
        )
        loop, _, _, run_state = build_loop(step_planner)

        loop.run("执行计算")

        step = run_state.plan_state.steps[0]
        self.assertEqual(step.attempt_count, 2)
        self.assertEqual(step.retry_count, 1)
        self.assertEqual(run_state.plan_state.total_retry_count, 1)
        self.assertFalse(step_planner.requests[1].recent_observation["success"])

    def test_skip_step_produces_failed_outcome_without_marking_completed(self):
        step_planner = FakeStepPlanner(
            [StepDecision(SkipStepAction("缺少必要资料"))]
        )
        loop, _, _, run_state = build_loop(step_planner)

        loop.run("执行计算")

        plan = run_state.plan_state
        self.assertEqual(plan.steps[0].status, PlanStepStatus.SKIPPED)
        self.assertEqual(plan.outcome, PlanOutcome.FAILED)
        self.assertEqual(plan.status, PlanStatus.COMPLETED)

    def test_abort_keeps_plan_aborted_after_final_answer(self):
        step_planner = FakeStepPlanner(
            [StepDecision(AbortPlanAction("任务条件不成立"))]
        )
        loop, _, _, run_state = build_loop(step_planner)

        loop.run("执行计算")

        plan = run_state.plan_state
        self.assertEqual(plan.steps[0].status, PlanStepStatus.FAILED)
        self.assertEqual(plan.outcome, PlanOutcome.FAILED)
        self.assertEqual(plan.status, PlanStatus.ABORTED)
        self.assertEqual(plan.abort_reason, "任务条件不成立")

    def test_duplicate_trace_for_same_call_id_uses_latest_observation(self):
        session = SessionState(session_id="session-1")
        session.add_message("user", "恢复计算")
        traces = [
            ToolTraceRecord(
                trace_id="trace-old",
                tool_name="calculator.add",
                call_id="call-1",
                arguments={"a": 1, "b": 1},
                success=True,
                result={"result": 1},
                error=None,
                duration_ms=1.0,
            ),
            ToolTraceRecord(
                trace_id="trace-new",
                tool_name="calculator.add",
                call_id="call-1",
                arguments={"a": 1, "b": 1},
                success=True,
                result={"result": 2},
                error=None,
                duration_ms=1.0,
            ),
        ]
        for trace in traces:
            session.add_tool_trace(trace)
        plan = PlanState(
            plan_id="plan-1",
            goal="确认恢复结果",
            status=PlanStatus.RUNNING,
            outcome=None,
            current_step_id="step-1",
            steps=[
                PlanStep(
                    step_id="step-1",
                    instruction="确认结果",
                    status=PlanStepStatus.RUNNING,
                    attempt_count=1,
                    tool_call_ids=["call-1"],
                )
            ],
            total_tool_call_count=1,
            total_retry_count=0,
            max_tool_calls_per_step=2,
            max_total_tool_calls=2,
        )
        run_state = RunState(
            run_id="run-1",
            session_id="session-1",
            workflow_id="plan-test",
            status=RunStatus.RUNNING,
            user_input="恢复计算",
            messages=session.list_messages(),
            tool_traces=session.list_tool_traces(),
            cursor=ExecutionCursor(
                next_node_id="agent",
                agent_phase="plan_step_deciding",
            ),
            plan_state=plan,
        )
        step_planner = FakeStepPlanner(
            [StepDecision(CompleteStepAction("采用最新结果"))]
        )
        tool = build_tool_definition()
        registry = ToolRegistry()
        registry.register(tool)
        loop = PlanAndExecuteAgentLoop(
            task_planner=FakeTaskPlanner(),
            step_planner=step_planner,
            tool_executor=ToolExecutor(registry, TraceRecorder(session)),
            tool_definitions=[tool.definition],
            session_state=session,
            run_state=run_state,
        )

        loop.run("恢复计算")

        self.assertEqual(len(step_planner.requests[0].observations), 1)
        self.assertEqual(
            step_planner.requests[0].observations[0]["result"]["result"],
            2,
        )


if __name__ == "__main__":
    unittest.main()

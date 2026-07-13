"""
本文件负责验证 Runtime Eval MVP 的固定用例评估、失败报告与用例隔离行为。
本文件不测试真实 LLM 语义等价性、报告落盘或多轮会话评估。
"""

import unittest

from my_agent.agent_loop.planner import FinalAnswerAction, Planner, ToolAction
from my_agent.agent_loop.react import ReActAgentLoop
from my_agent.dsl.loader import WorkflowLoader
from my_agent.runtime.conversation import ConversationRuntime
from my_agent.runtime.eval_models import ExpectedToolCall, RuntimeEvalCase
from my_agent.runtime.evaluator import RuntimeEvaluator
from my_agent.runtime.executor import RuntimeExecutor
from my_agent.runtime.graph import RuntimeGraph
from my_agent.runtime.node_runner import (
    AgentLoopNodeRunner,
    BeginNodeRunner,
    MessageNodeRunner,
)
from my_agent.state.recorder import TraceRecorder
from my_agent.state.session import SessionState
from my_agent.tools.executor import ToolExecutor
from my_agent.tools.function_tool import FunctionTool
from my_agent.tools.registry import ToolRegistry


def build_workflow_dict():
    return {
        "workflow_id": "runtime-eval-workflow",
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


class PresetPlanner(Planner):
    """按预设动作顺序返回结果，并记录每个实例的调用次数。"""

    def __init__(self, actions):
        self._actions = list(actions)
        self._next_index = 0
        self.plan_call_count = 0

    def plan(self, user_input, session):
        self.plan_call_count += 1
        action = self._actions[self._next_index]
        self._next_index += 1
        return action


def build_add_tool():
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


def build_conversation_runtime(actions):
    session = SessionState(session_id="runtime-eval-session")
    planner = PresetPlanner(actions)
    registry = ToolRegistry()
    registry.register(build_add_tool())
    agent_loop = ReActAgentLoop(
        planner=planner,
        tool_executor=ToolExecutor(registry, trace_recorder=TraceRecorder(session)),
        session_state=session,
        max_rounds=3,
    )
    workflow = WorkflowLoader().load_dict(build_workflow_dict())
    executor = RuntimeExecutor(
        graph=RuntimeGraph(workflow),
        node_runners={
            "begin": BeginNodeRunner(),
            "agent_loop": AgentLoopNodeRunner(agent_loop),
            "message": MessageNodeRunner(),
        },
    )
    return ConversationRuntime(executor=executor, session_state=session), session, planner


class RuntimeEvalTest(unittest.TestCase):
    def test_evaluate_returns_passed_result_for_matching_output_path_and_tools(self):
        evaluator = RuntimeEvaluator(
            lambda: build_conversation_runtime(
                [
                    ToolAction(
                        tool_name="calculator.add",
                        arguments={"a": 1, "b": 2},
                    ),
                    FinalAnswerAction(answer="计算完成"),
                ]
            )[0]
        )
        case = RuntimeEvalCase(
            case_id="matching-case",
            user_input="计算 1 加 2",
            expected_output_text="计算完成",
            expected_node_ids=("begin", "agent", "message"),
            expected_tool_calls=(
                ExpectedToolCall(tool_name="calculator.add", success=True),
            ),
        )

        result = evaluator.evaluate(case)

        self.assertTrue(result.passed)
        self.assertEqual(result.failures, ())
        self.assertEqual(result.actual_node_ids, ("begin", "agent", "message"))
        self.assertEqual(
            result.actual_tool_calls,
            (ExpectedToolCall(tool_name="calculator.add", success=True),),
        )
        self.assertIsNotNone(result.turn_result)

    def test_evaluate_collects_all_completed_run_mismatches(self):
        evaluator = RuntimeEvaluator(
            lambda: build_conversation_runtime(
                [FinalAnswerAction(answer="实际回答")]
            )[0]
        )
        case = RuntimeEvalCase(
            case_id="mismatch-case",
            user_input="问题",
            expected_output_text="期望回答",
            expected_node_ids=("begin", "message"),
            expected_tool_calls=(
                ExpectedToolCall(tool_name="calculator.add", success=True),
            ),
        )

        result = evaluator.evaluate(case)

        self.assertFalse(result.passed)
        self.assertEqual(
            [failure.check_name for failure in result.failures],
            ["output_text", "node_path", "tool_calls"],
        )
        self.assertEqual(result.actual_node_ids, ("begin", "agent", "message"))
        self.assertEqual(result.actual_tool_calls, ())

    def test_evaluate_converts_runtime_exception_to_execution_failure(self):
        def raise_runtime_error():
            raise ValueError("运行失败")

        evaluator = RuntimeEvaluator(raise_runtime_error)
        case = RuntimeEvalCase(
            case_id="execution-error-case",
            user_input="问题",
            expected_output_text="回答",
            expected_node_ids=(),
            expected_tool_calls=(),
        )

        result = evaluator.evaluate(case)

        self.assertFalse(result.passed)
        self.assertIsNone(result.turn_result)
        self.assertEqual(result.actual_node_ids, ())
        self.assertEqual(result.actual_tool_calls, ())
        self.assertEqual(len(result.failures), 1)
        self.assertEqual(result.failures[0].check_name, "runtime_execution")
        self.assertEqual(result.failures[0].actual, {"type": "ValueError", "message": "运行失败"})

    def test_evaluate_converts_runtime_execution_exception_to_execution_failure(self):
        evaluator = RuntimeEvaluator(lambda: build_conversation_runtime([])[0])
        case = RuntimeEvalCase(
            case_id="chat-error-case",
            user_input="问题",
            expected_output_text="回答",
            expected_node_ids=(),
            expected_tool_calls=(),
        )

        result = evaluator.evaluate(case)

        self.assertFalse(result.passed)
        self.assertEqual(result.failures[0].check_name, "runtime_execution")
        self.assertEqual(result.failures[0].actual["type"], "IndexError")

    def test_evaluate_many_keeps_order_and_continues_after_failed_case(self):
        created_runtimes = []

        def runtime_factory():
            runtime, session, planner = build_conversation_runtime(
                [
                    ToolAction(
                        tool_name="calculator.add",
                        arguments={"a": 1, "b": 2},
                    ),
                    FinalAnswerAction(answer="固定回答"),
                ]
            )
            created_runtimes.append((runtime, session, planner))
            return runtime

        evaluator = RuntimeEvaluator(runtime_factory)
        cases = (
            RuntimeEvalCase(
                case_id="failed-case",
                user_input="第一个问题",
                expected_output_text="不一致回答",
                expected_node_ids=("begin", "agent", "message"),
                expected_tool_calls=(
                    ExpectedToolCall(tool_name="calculator.add", success=True),
                ),
            ),
            RuntimeEvalCase(
                case_id="passed-case",
                user_input="第二个问题",
                expected_output_text="固定回答",
                expected_node_ids=("begin", "agent", "message"),
                expected_tool_calls=(
                    ExpectedToolCall(tool_name="calculator.add", success=True),
                ),
            ),
        )

        results = evaluator.evaluate_many(cases)

        self.assertEqual([result.case_id for result in results], ["failed-case", "passed-case"])
        self.assertEqual([result.passed for result in results], [False, True])
        self.assertEqual(len(created_runtimes), 2)
        self.assertIsNot(created_runtimes[0][0], created_runtimes[1][0])
        self.assertIsNot(created_runtimes[0][1], created_runtimes[1][1])
        self.assertIsNot(created_runtimes[0][2], created_runtimes[1][2])
        self.assertEqual(created_runtimes[0][2].plan_call_count, 2)
        self.assertEqual(created_runtimes[1][2].plan_call_count, 2)
        self.assertEqual(len(created_runtimes[0][1].list_tool_traces()), 1)
        self.assertEqual(len(created_runtimes[1][1].list_tool_traces()), 1)
        self.assertIsNot(
            created_runtimes[0][1].list_tool_traces()[0],
            created_runtimes[1][1].list_tool_traces()[0],
        )

    def test_eval_models_keep_sequence_fields_as_tuples(self):
        case = RuntimeEvalCase(
            case_id="snapshot-case",
            user_input="问题",
            expected_output_text="回答",
            expected_node_ids=["begin", "agent", "message"],
            expected_tool_calls=[ExpectedToolCall(tool_name="calculator.add", success=True)],
        )
        evaluator = RuntimeEvaluator(
            lambda: build_conversation_runtime(
                [FinalAnswerAction(answer="回答")]
            )[0]
        )

        result = evaluator.evaluate(case)

        self.assertIsInstance(case.expected_node_ids, tuple)
        self.assertIsInstance(case.expected_tool_calls, tuple)
        self.assertIsInstance(result.failures, tuple)
        self.assertIsInstance(result.actual_node_ids, tuple)
        self.assertIsInstance(result.actual_tool_calls, tuple)


if __name__ == "__main__":
    unittest.main()

"""
本文件负责验证单步 ReAct Agent Loop 的编排行为。
本文件不测试真实 LLM，也不测试具体业务工具的内部逻辑。
"""

import unittest

from my_agent.agent_loop.planner import FakePlanner, FinalAnswerAction, Planner, ToolAction
from my_agent.agent_loop.react import ReActAgentLoop
from my_agent.state.recorder import TraceRecorder
from my_agent.state.session import SessionState
from my_agent.tools.executor import ToolExecutor
from my_agent.tools.function_tool import FunctionTool
from my_agent.tools.registry import ToolRegistry


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


def build_executor(session):
    registry = ToolRegistry()
    registry.register(build_add_tool())
    return ToolExecutor(registry, trace_recorder=TraceRecorder(session))


class SpyPlanner(Planner):
    def __init__(self, action):
        self.action = action
        self.seen_user_input = None
        self.seen_session = None

    def plan(self, user_input, session):
        self.seen_user_input = user_input
        self.seen_session = session
        return self.action


class AgentLoopTest(unittest.TestCase):
    def test_final_answer_action_adds_user_and_assistant_messages(self):
        session = SessionState(session_id="session-1")
        planner = FakePlanner([FinalAnswerAction(answer="这是最终回答")])
        agent_loop = ReActAgentLoop(
            planner=planner,
            tool_executor=build_executor(session),
            session_state=session,
        )

        answer = agent_loop.run("你好")

        messages = session.list_messages()
        self.assertEqual(answer, "这是最终回答")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, "user")
        self.assertEqual(messages[0].content, "你好")
        self.assertEqual(messages[1].role, "assistant")
        self.assertEqual(messages[1].content, "这是最终回答")

    def test_tool_action_executes_tool_and_records_trace_with_generated_call_id(self):
        session = SessionState(session_id="session-1")
        planner = FakePlanner(
            [ToolAction(tool_name="calculator.add", arguments={"a": 1, "b": 2})]
        )
        agent_loop = ReActAgentLoop(
            planner=planner,
            tool_executor=build_executor(session),
            session_state=session,
        )

        answer = agent_loop.run("计算 1 + 2")

        messages = session.list_messages()
        traces = session.list_tool_traces()
        self.assertIn("工具 calculator.add 执行成功", answer)
        self.assertIn('"result": 3', answer)
        self.assertEqual(messages[-1].role, "assistant")
        self.assertEqual(messages[-1].content, answer)
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0].tool_name, "calculator.add")
        self.assertIsNotNone(traces[0].call_id)
        self.assertTrue(traces[0].success)

    def test_tool_action_preserves_planner_call_id(self):
        session = SessionState(session_id="session-1")
        planner = FakePlanner(
            [
                ToolAction(
                    tool_name="calculator.add",
                    arguments={"a": 2, "b": 5},
                    call_id="planner-call-1",
                )
            ]
        )
        agent_loop = ReActAgentLoop(
            planner=planner,
            tool_executor=build_executor(session),
            session_state=session,
        )

        agent_loop.run("计算 2 + 5")

        trace = session.list_tool_traces()[0]
        self.assertEqual(trace.call_id, "planner-call-1")

    def test_tool_failure_returns_failure_summary_and_records_error_trace(self):
        session = SessionState(session_id="session-1")
        planner = FakePlanner(
            [ToolAction(tool_name="calculator.add", arguments={"a": 1})]
        )
        agent_loop = ReActAgentLoop(
            planner=planner,
            tool_executor=build_executor(session),
            session_state=session,
        )

        answer = agent_loop.run("计算缺少参数")

        trace = session.list_tool_traces()[0]
        self.assertIn("工具 calculator.add 执行失败", answer)
        self.assertIn("ToolValidationError", answer)
        self.assertFalse(trace.success)
        self.assertEqual(trace.error["type"], "ToolValidationError")

    def test_agent_loop_uses_planner_interface(self):
        session = SessionState(session_id="session-1")
        planner = SpyPlanner(FinalAnswerAction(answer="来自接口的回答"))
        agent_loop = ReActAgentLoop(
            planner=planner,
            tool_executor=build_executor(session),
            session_state=session,
        )

        answer = agent_loop.run("接口测试")

        self.assertEqual(answer, "来自接口的回答")
        self.assertEqual(planner.seen_user_input, "接口测试")
        self.assertIs(planner.seen_session, session)


if __name__ == "__main__":
    unittest.main()

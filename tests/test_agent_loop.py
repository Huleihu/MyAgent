"""
本文件负责验证多轮 ReAct Agent Loop 的编排行为。
本文件不测试真实 LLM，也不测试具体业务工具的内部逻辑。
"""

import unittest

from my_agent.agent_loop.planner import FakePlanner, FinalAnswerAction, Planner, ToolAction
from my_agent.agent_loop.react import ReActAgentLoop
from my_agent.state.checkpoint_recorder import CheckpointRecorder
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

    def test_tool_action_adds_observation_then_continues_to_final_answer(self):
        session = SessionState(session_id="session-1")
        planner = FakePlanner(
            [
                ToolAction(tool_name="calculator.add", arguments={"a": 1, "b": 2}),
                FinalAnswerAction(answer="最终答案是 3"),
            ]
        )
        agent_loop = ReActAgentLoop(
            planner=planner,
            tool_executor=build_executor(session),
            session_state=session,
        )

        answer = agent_loop.run("计算 1 + 2")

        messages = session.list_messages()
        traces = session.list_tool_traces()
        self.assertEqual(answer, "最终答案是 3")
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[1].role, "assistant")
        self.assertIn("工具 calculator.add 执行成功", messages[1].content)
        self.assertEqual(messages[1].metadata["message_type"], "tool_observation")
        self.assertEqual(messages[1].metadata["tool_name"], "calculator.add")
        self.assertTrue(messages[1].metadata["success"])
        self.assertEqual(messages[-1].content, "最终答案是 3")
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
                ),
                FinalAnswerAction(answer="最终答案是 7"),
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
            [
                ToolAction(tool_name="calculator.add", arguments={"a": 1}),
                FinalAnswerAction(answer="无法完成计算"),
            ]
        )
        agent_loop = ReActAgentLoop(
            planner=planner,
            tool_executor=build_executor(session),
            session_state=session,
        )

        answer = agent_loop.run("计算缺少参数")

        trace = session.list_tool_traces()[0]
        messages = session.list_messages()
        self.assertEqual(answer, "无法完成计算")
        self.assertIn("工具 calculator.add 执行失败", messages[1].content)
        self.assertIn("ToolValidationError", messages[1].content)
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

    def test_multiple_tool_actions_run_across_planner_rounds(self):
        session = SessionState(session_id="session-1")
        planner = FakePlanner(
            [
                ToolAction(tool_name="calculator.add", arguments={"a": 1, "b": 2}),
                ToolAction(tool_name="calculator.add", arguments={"a": 3, "b": 4}),
                FinalAnswerAction(answer="两次计算已完成"),
            ]
        )
        agent_loop = ReActAgentLoop(
            planner=planner,
            tool_executor=build_executor(session),
            session_state=session,
            max_rounds=3,
        )

        answer = agent_loop.run("分别计算两组数字")

        messages = session.list_messages()
        traces = session.list_tool_traces()
        self.assertEqual(answer, "两次计算已完成")
        self.assertEqual(len(traces), 2)
        self.assertEqual(messages[1].metadata["message_type"], "tool_observation")
        self.assertEqual(messages[2].metadata["message_type"], "tool_observation")
        self.assertEqual(messages[-1].content, "两次计算已完成")

    def test_max_rounds_limits_planner_decisions(self):
        session = SessionState(session_id="session-1")
        planner = FakePlanner(
            [
                ToolAction(tool_name="calculator.add", arguments={"a": 1, "b": 1}),
                ToolAction(tool_name="calculator.add", arguments={"a": 2, "b": 2}),
            ]
        )
        agent_loop = ReActAgentLoop(
            planner=planner,
            tool_executor=build_executor(session),
            session_state=session,
            max_rounds=1,
        )

        with self.assertRaises(ValueError):
            agent_loop.run("持续调用工具")

    def test_max_rounds_must_be_positive_integer(self):
        session = SessionState(session_id="session-1")
        planner = FakePlanner([FinalAnswerAction(answer="不会执行")])

        with self.assertRaises(ValueError):
            ReActAgentLoop(
                planner=planner,
                tool_executor=build_executor(session),
                session_state=session,
                max_rounds=0,
            )

    def test_checkpoint_recorder_records_user_and_direct_final_answer(self):
        session = SessionState(session_id="session-1")
        recorder = CheckpointRecorder(session)
        planner = FakePlanner([FinalAnswerAction(answer="直接回答")])
        agent_loop = ReActAgentLoop(
            planner=planner,
            tool_executor=build_executor(session),
            session_state=session,
            checkpoint_recorder=recorder,
        )

        agent_loop.run("你好")

        checkpoints = recorder.list_checkpoints()
        self.assertEqual(len(checkpoints), 2)
        self.assertEqual(checkpoints[0].metadata["reason"], "after_user_input")
        self.assertEqual(checkpoints[0].metadata["round_index"], 0)
        self.assertEqual(len(checkpoints[0].list_messages()), 1)
        self.assertEqual(checkpoints[1].metadata["reason"], "after_final_answer")
        self.assertEqual(checkpoints[1].metadata["round_index"], 1)
        self.assertEqual(checkpoints[1].list_messages()[-1].content, "直接回答")

    def test_checkpoint_recorder_records_tool_observation_after_message_written(self):
        session = SessionState(session_id="session-1")
        recorder = CheckpointRecorder(session)
        planner = FakePlanner(
            [
                ToolAction(
                    tool_name="calculator.add",
                    arguments={"a": 2, "b": 3},
                    call_id="tool-call-1",
                ),
                FinalAnswerAction(answer="最终答案是 5"),
            ]
        )
        agent_loop = ReActAgentLoop(
            planner=planner,
            tool_executor=build_executor(session),
            session_state=session,
            checkpoint_recorder=recorder,
        )

        agent_loop.run("计算 2 + 3")

        checkpoints = recorder.list_checkpoints()
        tool_checkpoint = checkpoints[1]
        tool_messages = tool_checkpoint.list_messages()
        self.assertEqual(tool_checkpoint.metadata["reason"], "after_tool_observation")
        self.assertEqual(tool_checkpoint.metadata["round_index"], 1)
        self.assertEqual(tool_checkpoint.metadata["tool_name"], "calculator.add")
        self.assertEqual(tool_checkpoint.metadata["call_id"], "tool-call-1")
        self.assertTrue(tool_checkpoint.metadata["success"])
        self.assertEqual(tool_messages[-1].metadata["message_type"], "tool_observation")
        self.assertEqual(tool_messages[-1].metadata["arguments"], {"a": 2, "b": 3})
        self.assertEqual(len(tool_checkpoint.list_tool_traces()), 1)
        self.assertEqual(checkpoints[2].metadata["reason"], "after_final_answer")
        self.assertEqual(checkpoints[2].metadata["round_index"], 2)

    def test_checkpoint_recorder_uses_planner_round_index_for_multiple_tools(self):
        session = SessionState(session_id="session-1")
        recorder = CheckpointRecorder(session)
        planner = FakePlanner(
            [
                ToolAction(tool_name="calculator.add", arguments={"a": 1, "b": 2}),
                ToolAction(tool_name="calculator.add", arguments={"a": 3, "b": 4}),
                FinalAnswerAction(answer="两次计算已完成"),
            ]
        )
        agent_loop = ReActAgentLoop(
            planner=planner,
            tool_executor=build_executor(session),
            session_state=session,
            checkpoint_recorder=recorder,
            max_rounds=3,
        )

        agent_loop.run("分别计算两组数字")

        checkpoints = recorder.list_checkpoints()
        self.assertEqual(
            [checkpoint.metadata["reason"] for checkpoint in checkpoints],
            [
                "after_user_input",
                "after_tool_observation",
                "after_tool_observation",
                "after_final_answer",
            ],
        )
        self.assertEqual(
            [checkpoint.metadata["round_index"] for checkpoint in checkpoints],
            [0, 1, 2, 3],
        )


if __name__ == "__main__":
    unittest.main()

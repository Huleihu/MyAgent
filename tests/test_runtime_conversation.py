"""
本文件负责验证 ConversationRuntime 的回合编排、会话复用和 Trace 快照行为。
本文件不测试真实 LLM、持久化恢复或并发会话管理。
"""

import unittest

from my_agent.agent_loop.planner import FinalAnswerAction, Planner, ToolAction
from my_agent.agent_loop.react import ReActAgentLoop
from my_agent.dsl.loader import WorkflowLoader
from my_agent.runtime.conversation import ConversationRuntime
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
        "workflow_id": "conversation-workflow",
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


class HistoryAwarePlanner(Planner):
    """记录规划时消息历史，并按预设动作顺序返回结果。"""

    def __init__(self, actions):
        self._actions = list(actions)
        self._next_index = 0
        self.message_snapshots = []

    def plan(self, user_input, session):
        self.message_snapshots.append(
            [(message.role, message.content) for message in session.list_messages()]
        )
        action = self._actions[self._next_index]
        self._next_index += 1
        return action


def build_conversation_runtime(session, planner):
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
    return ConversationRuntime(executor=executor, session_state=session)


def build_single_node_executor(node, runner):
    workflow = WorkflowLoader().load_dict(
        {
            "workflow_id": "single-node-workflow",
            "nodes": [node],
            "edges": [],
        }
    )
    return RuntimeExecutor(
        graph=RuntimeGraph(workflow),
        node_runners={node["node_type"]: runner},
    )


class InvalidLastMessageRunner:
    """模拟违反 ConversationRuntime 输出约定的节点执行器。"""

    def run(self, node, context, inputs):
        context.variables["last_message"] = 123
        return {"content": "无效输出"}


class ConversationRuntimeTest(unittest.TestCase):
    def test_chat_returns_output_context_and_trace_snapshots(self):
        session = SessionState(session_id="session-1")
        runtime = build_conversation_runtime(
            session,
            HistoryAwarePlanner([FinalAnswerAction(answer="第一轮回答")]),
        )

        result = runtime.chat("第一轮问题")

        self.assertEqual(result.output_text, "第一轮回答")
        self.assertIs(result.runtime_context.session_state, session)
        self.assertEqual(result.runtime_context.user_input, "第一轮问题")
        self.assertIsInstance(result.node_traces, tuple)
        self.assertEqual([trace.node_id for trace in result.node_traces], ["begin", "agent", "message"])
        self.assertEqual(result.tool_traces, ())
        result.runtime_context.node_traces.clear()
        self.assertEqual(len(result.node_traces), 3)

    def test_chat_reuses_session_and_planner_sees_previous_turn_history(self):
        session = SessionState(session_id="session-1")
        planner = HistoryAwarePlanner(
            [
                FinalAnswerAction(answer="第一轮回答"),
                FinalAnswerAction(answer="第二轮回答"),
            ]
        )
        runtime = build_conversation_runtime(session, planner)

        first_result = runtime.chat("第一轮问题")
        second_result = runtime.chat("第二轮问题")

        self.assertIs(first_result.runtime_context.session_state, session)
        self.assertIs(second_result.runtime_context.session_state, session)
        self.assertIsNot(first_result.runtime_context, second_result.runtime_context)
        self.assertEqual(first_result.output_text, "第一轮回答")
        self.assertEqual(second_result.output_text, "第二轮回答")
        self.assertEqual(
            planner.message_snapshots[1],
            [
                ("user", "第一轮问题"),
                ("assistant", "第一轮回答"),
                ("user", "第二轮问题"),
            ],
        )

    def test_chat_returns_only_current_turn_tool_traces(self):
        session = SessionState(session_id="session-1")
        planner = HistoryAwarePlanner(
            [
                ToolAction(tool_name="calculator.add", arguments={"a": 1, "b": 2}),
                FinalAnswerAction(answer="第一轮工具回答"),
                FinalAnswerAction(answer="第二轮普通回答"),
            ]
        )
        runtime = build_conversation_runtime(session, planner)

        first_result = runtime.chat("计算 1 加 2")
        second_result = runtime.chat("无需工具的问题")

        self.assertIsInstance(first_result.tool_traces, tuple)
        self.assertEqual(len(first_result.tool_traces), 1)
        self.assertEqual(first_result.tool_traces[0].tool_name, "calculator.add")
        self.assertEqual(second_result.tool_traces, ())
        self.assertEqual(len(session.list_tool_traces()), 1)

    def test_chat_rejects_empty_input_before_writing_session_state(self):
        session = SessionState(session_id="session-1")
        runtime = build_conversation_runtime(
            session,
            HistoryAwarePlanner([FinalAnswerAction(answer="不会执行")]),
        )

        with self.assertRaisesRegex(ValueError, "user_input must be a non-empty string"):
            runtime.chat(" ")

        self.assertEqual(session.list_messages(), [])
        self.assertEqual(session.list_tool_traces(), [])

    def test_chat_rejects_missing_last_message_output(self):
        session = SessionState(session_id="session-1")
        runtime = ConversationRuntime(
            executor=build_single_node_executor(
                {"node_id": "begin", "node_type": "begin"},
                BeginNodeRunner(),
            ),
            session_state=session,
        )

        with self.assertRaisesRegex(ValueError, "last_message is missing"):
            runtime.chat("缺少输出")

    def test_chat_rejects_non_string_last_message_output(self):
        session = SessionState(session_id="session-1")
        runtime = ConversationRuntime(
            executor=build_single_node_executor(
                {
                    "node_id": "message",
                    "node_type": "message",
                    "inputs": {"content": "固定内容"},
                },
                InvalidLastMessageRunner(),
            ),
            session_state=session,
        )

        with self.assertRaisesRegex(ValueError, "last_message must be a non-empty string"):
            runtime.chat("无效输出")


if __name__ == "__main__":
    unittest.main()

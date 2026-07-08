"""
本文件负责验证 Agent 会话状态的消息与工具调用记录管理。
本文件不测试持久化、Checkpoint 或 Agent Loop 执行。
"""

import unittest

from my_agent.state.session import SessionState
from my_agent.state.trace import ToolTraceRecord


class StateSessionTest(unittest.TestCase):
    def test_session_state_adds_messages(self):
        session = SessionState(session_id="session-1")

        session.add_message(
            role="user",
            content="什么是 Agentic RAG？",
            metadata={"source": "chat"},
        )

        messages = session.list_messages()
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].role, "user")
        self.assertEqual(messages[0].content, "什么是 Agentic RAG？")
        self.assertEqual(messages[0].metadata["source"], "chat")

    def test_session_state_adds_tool_traces(self):
        session = SessionState(session_id="session-1")
        trace = ToolTraceRecord(
            trace_id="trace-1",
            tool_name="retrieval.search",
            call_id="call-1",
            arguments={"query": "Agentic RAG"},
            success=True,
            result={"chunks": []},
            error=None,
            duration_ms=2.0,
        )

        session.add_tool_trace(trace)

        traces = session.list_tool_traces()
        self.assertEqual(len(traces), 1)
        self.assertIs(traces[0], trace)

    def test_session_state_list_methods_return_copies(self):
        session = SessionState(session_id="session-1")
        session.add_message(role="user", content="hello")
        trace = ToolTraceRecord(
            trace_id="trace-1",
            tool_name="calculator.add",
            call_id=None,
            arguments={"a": 1, "b": 2},
            success=True,
            result={"result": 3},
            error=None,
            duration_ms=1.0,
        )
        session.add_tool_trace(trace)

        messages = session.list_messages()
        traces = session.list_tool_traces()
        messages.clear()
        traces.clear()

        self.assertEqual(len(session.list_messages()), 1)
        self.assertEqual(len(session.list_tool_traces()), 1)

    def test_session_state_rejects_invalid_trace(self):
        session = SessionState(session_id="session-1")

        with self.assertRaises(ValueError):
            session.add_tool_trace({"trace_id": "trace-1"})


if __name__ == "__main__":
    unittest.main()

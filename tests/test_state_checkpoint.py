"""
本文件负责验证 Agent 会话 Checkpoint 快照模型。
本文件不测试文件持久化、数据库存储或 Agent Loop 恢复流程。
"""

import unittest

from my_agent.state.checkpoint import Checkpoint
from my_agent.state.session import SessionState
from my_agent.state.trace import ToolTraceRecord


def build_trace(trace_id="trace-1"):
    return ToolTraceRecord(
        trace_id=trace_id,
        tool_name="calculator.add",
        call_id="call-1",
        arguments={"a": 1, "b": 2},
        success=True,
        result={"result": 3},
        error=None,
        duration_ms=1.0,
    )


class StateCheckpointTest(unittest.TestCase):
    def test_checkpoint_from_session_keeps_current_state_snapshot(self):
        session = SessionState(session_id="session-1")
        message = session.add_message(
            role="user",
            content="计算 1 + 2",
            metadata={"source": "chat"},
        )
        trace = build_trace()
        session.add_tool_trace(trace)

        checkpoint = Checkpoint.from_session(
            checkpoint_id="checkpoint-1",
            session_state=session,
            metadata={"reason": "before-final-answer"},
        )

        self.assertEqual(checkpoint.checkpoint_id, "checkpoint-1")
        self.assertEqual(checkpoint.session_id, "session-1")
        self.assertEqual(checkpoint.metadata["reason"], "before-final-answer")
        self.assertEqual(checkpoint.list_messages(), [message])
        self.assertEqual(checkpoint.list_tool_traces(), [trace])

    def test_checkpoint_is_not_changed_by_later_session_updates(self):
        session = SessionState(session_id="session-1")
        session.add_message(role="user", content="第一轮问题")
        session.add_tool_trace(build_trace("trace-1"))

        checkpoint = Checkpoint.from_session(
            checkpoint_id="checkpoint-1",
            session_state=session,
        )

        session.add_message(role="assistant", content="后续回答")
        session.add_tool_trace(build_trace("trace-2"))

        self.assertEqual(len(checkpoint.list_messages()), 1)
        self.assertEqual(len(checkpoint.list_tool_traces()), 1)
        self.assertEqual(checkpoint.list_messages()[0].content, "第一轮问题")
        self.assertEqual(checkpoint.list_tool_traces()[0].trace_id, "trace-1")

    def test_checkpoint_list_methods_return_copies(self):
        session = SessionState(session_id="session-1")
        session.add_message(role="user", content="hello")
        session.add_tool_trace(build_trace())
        checkpoint = Checkpoint.from_session(
            checkpoint_id="checkpoint-1",
            session_state=session,
        )

        messages = checkpoint.list_messages()
        traces = checkpoint.list_tool_traces()
        messages.clear()
        traces.clear()

        self.assertEqual(len(checkpoint.list_messages()), 1)
        self.assertEqual(len(checkpoint.list_tool_traces()), 1)

    def test_checkpoint_rejects_invalid_fields(self):
        session = SessionState(session_id="session-1")

        with self.assertRaises(ValueError):
            Checkpoint.from_session(checkpoint_id="", session_state=session)

        with self.assertRaises(TypeError):
            Checkpoint.from_session(
                checkpoint_id="checkpoint-1",
                session_state={"session_id": "session-1"},
            )

        with self.assertRaises(ValueError):
            Checkpoint.from_session(
                checkpoint_id="checkpoint-1",
                session_state=session,
                metadata=["not", "dict"],
            )

    def test_checkpoint_constructor_rejects_invalid_snapshot_lists(self):
        with self.assertRaises(ValueError):
            Checkpoint(
                checkpoint_id="checkpoint-1",
                session_id="session-1",
                messages=["not message"],
                tool_traces=[],
                metadata={},
            )

        with self.assertRaises(ValueError):
            Checkpoint(
                checkpoint_id="checkpoint-1",
                session_id="session-1",
                messages=[],
                tool_traces=["not trace"],
                metadata={},
            )


if __name__ == "__main__":
    unittest.main()

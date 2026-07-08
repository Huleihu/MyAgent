"""
本文件负责验证 TraceRecorder 对工具调用 Trace 的写入边界。
本文件不测试工具执行器，也不测试状态持久化。
"""

import unittest

from my_agent.state.recorder import TraceRecorder
from my_agent.state.session import SessionState
from my_agent.state.trace import ToolTraceRecord


class TraceRecorderTest(unittest.TestCase):
    def test_record_tool_call_appends_trace_to_session_state(self):
        session = SessionState(session_id="session-1")
        recorder = TraceRecorder(session)
        trace = ToolTraceRecord(
            trace_id="trace-1",
            tool_name="calculator.add",
            call_id="call-1",
            arguments={"a": 1, "b": 2},
            success=True,
            result={"result": 3},
            error=None,
            duration_ms=1.0,
        )

        recorder.record_tool_call(trace)

        traces = session.list_tool_traces()
        self.assertEqual(len(traces), 1)
        self.assertIs(traces[0], trace)

    def test_trace_recorder_rejects_non_session_state(self):
        with self.assertRaises(TypeError):
            TraceRecorder(session_state={"session_id": "session-1"})

    def test_record_tool_call_rejects_non_tool_trace_record(self):
        session = SessionState(session_id="session-1")
        recorder = TraceRecorder(session)

        with self.assertRaises(TypeError):
            recorder.record_tool_call({"trace_id": "trace-1"})


if __name__ == "__main__":
    unittest.main()

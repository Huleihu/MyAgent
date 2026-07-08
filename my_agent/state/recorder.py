"""
本文件负责把工具调用 Trace 写入会话状态。
本文件不负责执行工具、生成工具结果或持久化状态。
"""

from __future__ import annotations

from my_agent.state.session import SessionState
from my_agent.state.trace import ToolTraceRecord


class TraceRecorder:
    """记录工具调用 Trace 的轻量写入器。"""

    def __init__(self, session_state: SessionState) -> None:
        if not isinstance(session_state, SessionState):
            raise TypeError("session_state must be a SessionState")
        self._session_state = session_state

    def record_tool_call(self, trace: ToolTraceRecord) -> None:
        """写入一次工具调用 Trace，并保持记录逻辑与工具执行解耦。"""
        if not isinstance(trace, ToolTraceRecord):
            raise TypeError("trace must be a ToolTraceRecord")
        self._session_state.add_tool_trace(trace)

"""
本文件负责管理单次 Agent 会话的内存状态。
本文件不负责状态持久化、Checkpoint 恢复或 Agent Loop 执行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from my_agent.state.trace import ToolTraceRecord


def _validate_non_empty_text(field_name: str, field_value: str) -> None:
    """校验会话关键文本字段，避免产生无法追踪的状态记录。"""
    if not isinstance(field_value, str) or not field_value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True)
class SessionMessage:
    """表示一次 Agent 会话中的单条对话消息。"""

    role: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_non_empty_text("role", self.role)
        _validate_non_empty_text("content", self.content)
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dict")


@dataclass
class SessionState:
    """保存一次 Agent 运行过程中的消息与工具调用 Trace。"""

    session_id: str
    messages: list[SessionMessage] = field(default_factory=list)
    tool_traces: list[ToolTraceRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validate_non_empty_text("session_id", self.session_id)
        if not isinstance(self.messages, list) or not all(
            isinstance(message, SessionMessage) for message in self.messages
        ):
            raise ValueError("messages must be a list[SessionMessage]")
        if not isinstance(self.tool_traces, list) or not all(
            isinstance(trace, ToolTraceRecord) for trace in self.tool_traces
        ):
            raise ValueError("tool_traces must be a list[ToolTraceRecord]")

    def add_message(
        self,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> SessionMessage:
        """追加一条会话消息，并返回实际写入的消息对象。"""
        message = SessionMessage(
            role=role,
            content=content,
            metadata={} if metadata is None else metadata,
        )
        self.messages.append(message)
        return message

    def add_tool_trace(self, trace: ToolTraceRecord) -> None:
        """追加一次工具调用 Trace，保持执行记录与会话状态分离。"""
        if not isinstance(trace, ToolTraceRecord):
            raise ValueError("trace must be a ToolTraceRecord")
        self.tool_traces.append(trace)

    def list_messages(self) -> list[SessionMessage]:
        """返回消息列表副本，避免调用方直接修改内部状态。"""
        return list(self.messages)

    def list_tool_traces(self) -> list[ToolTraceRecord]:
        """返回工具调用 Trace 列表副本，避免调用方直接修改内部状态。"""
        return list(self.tool_traces)

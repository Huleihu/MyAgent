"""
本文件负责定义 Agent 会话 Checkpoint 快照模型。
本文件不负责文件持久化、数据库存储或 Agent Loop 恢复。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from my_agent.state.session import SessionMessage, SessionState
from my_agent.state.trace import ToolTraceRecord


def _validate_non_empty_text(field_name: str, field_value: str) -> None:
    """校验 Checkpoint 关键标识字段，避免生成不可追踪的快照。"""
    if not isinstance(field_value, str) or not field_value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True)
class Checkpoint:
    """表示某一时刻 Agent 会话状态的内存快照。"""

    checkpoint_id: str
    session_id: str
    messages: list[SessionMessage] = field(default_factory=list)
    tool_traces: list[ToolTraceRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_non_empty_text("checkpoint_id", self.checkpoint_id)
        _validate_non_empty_text("session_id", self.session_id)

        if not isinstance(self.messages, list) or not all(
            isinstance(message, SessionMessage) for message in self.messages
        ):
            raise ValueError("messages must be a list[SessionMessage]")
        if not isinstance(self.tool_traces, list) or not all(
            isinstance(trace, ToolTraceRecord) for trace in self.tool_traces
        ):
            raise ValueError("tool_traces must be a list[ToolTraceRecord]")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dict")

    @classmethod
    def from_session(
        cls,
        checkpoint_id: str,
        session_state: SessionState,
        metadata: dict[str, Any] | None = None,
    ) -> "Checkpoint":
        """从当前会话状态创建快照，不绑定后续会话列表变化。"""
        if not isinstance(session_state, SessionState):
            raise TypeError("session_state must be a SessionState")
        return cls(
            checkpoint_id=checkpoint_id,
            session_id=session_state.session_id,
            messages=session_state.list_messages(),
            tool_traces=session_state.list_tool_traces(),
            metadata={} if metadata is None else metadata,
        )

    def list_messages(self) -> list[SessionMessage]:
        """返回消息快照副本，避免调用方直接修改内部列表。"""
        return list(self.messages)

    def list_tool_traces(self) -> list[ToolTraceRecord]:
        """返回工具调用 Trace 快照副本，避免调用方直接修改内部列表。"""
        return list(self.tool_traces)

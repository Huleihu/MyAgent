"""
本文件负责定义一次可恢复 Runtime 运行的状态、执行游标和待执行工具调用。
本文件只保存可序列化数据，不保存 Planner、工具实例、Runtime 或外部连接。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from my_agent.runtime.trace import NodeExecutionRecord
from my_agent.state.session import SessionMessage
from my_agent.state.trace import ToolTraceRecord


class RunStatus(str, Enum):
    """表示可恢复运行的生命周期状态。"""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class PendingToolCall:
    """保存已由 Planner 决定、尚未写入 observation 的工具调用。"""

    tool_name: str
    arguments: dict[str, Any]
    call_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.tool_name, str) or not self.tool_name.strip():
            raise ValueError("tool_name must be a non-empty string")
        if not isinstance(self.arguments, dict):
            raise ValueError("arguments must be a dict")
        if not isinstance(self.call_id, str) or not self.call_id.strip():
            raise ValueError("call_id must be a non-empty string")


@dataclass
class ExecutionCursor:
    """记录 Runtime 与 Agent Loop 的下一步执行位置。"""

    next_node_id: str
    completed_node_ids: list[str] = field(default_factory=list)
    agent_round_index: int = 0
    agent_phase: str = "not_started"

    def __post_init__(self) -> None:
        if not isinstance(self.next_node_id, str) or not self.next_node_id.strip():
            raise ValueError("next_node_id must be a non-empty string")
        if not isinstance(self.completed_node_ids, list) or not all(
            isinstance(node_id, str) and node_id.strip()
            for node_id in self.completed_node_ids
        ):
            raise ValueError("completed_node_ids must be a list[str]")
        if not isinstance(self.agent_round_index, int) or self.agent_round_index < 0:
            raise ValueError("agent_round_index must be a non-negative integer")
        if not isinstance(self.agent_phase, str) or not self.agent_phase.strip():
            raise ValueError("agent_phase must be a non-empty string")


@dataclass
class RunState:
    """保存恢复一次用户消息运行所需的会话、节点与执行控制数据。"""

    run_id: str
    session_id: str
    workflow_id: str
    status: RunStatus
    user_input: str
    messages: list[SessionMessage] = field(default_factory=list)
    tool_traces: list[ToolTraceRecord] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    node_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    node_traces: list[NodeExecutionRecord] = field(default_factory=list)
    cursor: ExecutionCursor = field(
        default_factory=lambda: ExecutionCursor(next_node_id="begin")
    )
    pending_tool_call: PendingToolCall | None = None
    created_at_utc: str = field(default_factory=lambda: _utc_now())
    updated_at_utc: str = field(default_factory=lambda: _utc_now())
    error: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        for field_name in ("run_id", "session_id", "workflow_id", "user_input"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.status, RunStatus):
            raise TypeError("status must be a RunStatus")
        if not isinstance(self.messages, list) or not all(
            isinstance(message, SessionMessage) for message in self.messages
        ):
            raise ValueError("messages must be a list[SessionMessage]")
        if not isinstance(self.tool_traces, list) or not all(
            isinstance(trace, ToolTraceRecord) for trace in self.tool_traces
        ):
            raise ValueError("tool_traces must be a list[ToolTraceRecord]")
        if not isinstance(self.variables, dict):
            raise ValueError("variables must be a dict")
        if not isinstance(self.node_outputs, dict) or not all(
            isinstance(node_id, str) and isinstance(output, dict)
            for node_id, output in self.node_outputs.items()
        ):
            raise ValueError("node_outputs must be a dict[str, dict]")
        if not isinstance(self.node_traces, list) or not all(
            isinstance(trace, NodeExecutionRecord) for trace in self.node_traces
        ):
            raise ValueError("node_traces must be a list[NodeExecutionRecord]")
        if not isinstance(self.cursor, ExecutionCursor):
            raise TypeError("cursor must be an ExecutionCursor")
        if self.pending_tool_call is not None and not isinstance(
            self.pending_tool_call, PendingToolCall
        ):
            raise TypeError("pending_tool_call must be a PendingToolCall or None")
        if self.error is not None and not isinstance(self.error, dict):
            raise ValueError("error must be a dict or None")

    def to_dict(self) -> dict[str, Any]:
        """转换为仅由 JSON 基础类型组成的持久化数据。"""
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "user_input": self.user_input,
            "messages": [
                {"role": item.role, "content": item.content, "metadata": deepcopy(item.metadata)}
                for item in self.messages
            ],
            "tool_traces": [
                {
                    "trace_id": item.trace_id,
                    "tool_name": item.tool_name,
                    "call_id": item.call_id,
                    "arguments": deepcopy(item.arguments),
                    "success": item.success,
                    "result": deepcopy(item.result),
                    "error": deepcopy(item.error),
                    "duration_ms": item.duration_ms,
                    "token_usage": deepcopy(item.token_usage),
                }
                for item in self.tool_traces
            ],
            "variables": deepcopy(self.variables),
            "node_outputs": deepcopy(self.node_outputs),
            "node_traces": [
                {
                    "node_id": item.node_id,
                    "node_type": item.node_type,
                    "inputs": deepcopy(item.inputs),
                    "output": deepcopy(item.output),
                    "success": item.success,
                    "error": deepcopy(item.error),
                    "duration_ms": item.duration_ms,
                }
                for item in self.node_traces
            ],
            "cursor": {
                "next_node_id": self.cursor.next_node_id,
                "completed_node_ids": list(self.cursor.completed_node_ids),
                "agent_round_index": self.cursor.agent_round_index,
                "agent_phase": self.cursor.agent_phase,
            },
            "pending_tool_call": None
            if self.pending_tool_call is None
            else {
                "tool_name": self.pending_tool_call.tool_name,
                "arguments": deepcopy(self.pending_tool_call.arguments),
                "call_id": self.pending_tool_call.call_id,
            },
            "created_at_utc": self.created_at_utc,
            "updated_at_utc": self.updated_at_utc,
            "error": deepcopy(self.error),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunState":
        """从持久化数据重建运行状态。"""
        if not isinstance(payload, dict):
            raise TypeError("payload must be a dict")
        cursor_payload = payload["cursor"]
        pending_payload = payload.get("pending_tool_call")
        return cls(
            run_id=payload["run_id"],
            session_id=payload["session_id"],
            workflow_id=payload["workflow_id"],
            status=RunStatus(payload["status"]),
            user_input=payload["user_input"],
            messages=[SessionMessage(**item) for item in payload.get("messages", [])],
            tool_traces=[ToolTraceRecord(**item) for item in payload.get("tool_traces", [])],
            variables=deepcopy(payload.get("variables", {})),
            node_outputs=deepcopy(payload.get("node_outputs", {})),
            node_traces=[NodeExecutionRecord(**item) for item in payload.get("node_traces", [])],
            cursor=ExecutionCursor(**cursor_payload),
            pending_tool_call=(
                None if pending_payload is None else PendingToolCall(**pending_payload)
            ),
            created_at_utc=payload["created_at_utc"],
            updated_at_utc=payload["updated_at_utc"],
            error=deepcopy(payload.get("error")),
        )


def _utc_now() -> str:
    """返回便于 SQLite 排序和排障的 UTC 时间文本。"""
    return datetime.now(timezone.utc).isoformat()

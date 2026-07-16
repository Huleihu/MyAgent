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

from my_agent.core.json_value import validate_json_native
from my_agent.runtime.trace import NodeExecutionRecord
from my_agent.state.plan_state import (
    PlanState,
    PlanStateConsistencyError,
    PlanStatus,
)
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
        validate_json_native(self.arguments)
        if not isinstance(self.call_id, str) or not self.call_id.strip():
            raise ValueError("call_id must be a non-empty string")


@dataclass
class ExecutionCursor:
    """记录 Runtime 与 Agent Loop 的下一步执行位置。"""

    next_node_id: str | None
    completed_node_ids: list[str] = field(default_factory=list)
    agent_round_index: int = 0
    agent_phase: str = "not_started"

    def __post_init__(self) -> None:
        if self.next_node_id is not None and (
            not isinstance(self.next_node_id, str) or not self.next_node_id.strip()
        ):
            raise ValueError("next_node_id must be a non-empty string or None")
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
    tool_trace_start_index: int = 0
    created_at_utc: str = field(default_factory=lambda: _utc_now())
    updated_at_utc: str = field(default_factory=lambda: _utc_now())
    error: dict[str, Any] | None = None
    plan_state: PlanState | None = None

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
        if not isinstance(self.tool_trace_start_index, int) or self.tool_trace_start_index < 0:
            raise ValueError("tool_trace_start_index must be a non-negative integer")
        if self.plan_state is not None and not isinstance(self.plan_state, PlanState):
            raise TypeError("plan_state must be a PlanState or None")
        self.validate_consistency()

    def validate_consistency(self) -> None:
        """校验 Plan phase、计划状态、当前步骤与 pending 调用的组合。"""
        phase = self.cursor.agent_phase
        if self.plan_state is None:
            if phase.startswith("plan_") and phase != "plan_creating":
                raise PlanStateConsistencyError("plan phase requires plan_state")
            if phase == "plan_creating" and self.pending_tool_call is not None:
                raise PlanStateConsistencyError(
                    "plan_creating must not have pending_tool_call"
                )
            if phase == "plan_creating" and self.status is RunStatus.COMPLETED:
                raise PlanStateConsistencyError(
                    "plan_creating cannot have completed RunStatus"
                )
            return

        plan = self.plan_state
        plan.validate()
        allowed_phases = {
            "plan_step_deciding",
            "plan_tool_pending",
            "plan_finalizing",
            "plan_final_answer_written",
            "completed",
        }
        if phase not in allowed_phases:
            raise PlanStateConsistencyError(
                "plan_state requires a Plan-and-Execute phase"
            )
        if phase != "completed" and self.status is RunStatus.COMPLETED:
            raise PlanStateConsistencyError(
                "active plan phase cannot have completed RunStatus"
            )
        if phase == "plan_step_deciding":
            self._validate_plan_step_deciding(plan)
            return
        if phase == "plan_tool_pending":
            self._validate_plan_tool_pending(plan)
            return
        if self.pending_tool_call is not None:
            raise PlanStateConsistencyError(
                "pending_tool_call is only allowed in plan_tool_pending"
            )
        if phase == "plan_finalizing":
            if plan.status not in {PlanStatus.FINALIZING, PlanStatus.ABORTED}:
                raise PlanStateConsistencyError(
                    "plan_finalizing requires finalizing or aborted plan"
                )
            return
        if phase == "plan_final_answer_written":
            if plan.status not in {PlanStatus.COMPLETED, PlanStatus.ABORTED}:
                raise PlanStateConsistencyError(
                    "plan_final_answer_written requires completed or aborted plan"
                )
            self._validate_plan_final_message(plan)
            return
        if self.status is not RunStatus.COMPLETED:
            raise PlanStateConsistencyError(
                "completed agent phase requires completed RunStatus"
            )
        if plan.status not in {PlanStatus.COMPLETED, PlanStatus.ABORTED}:
            raise PlanStateConsistencyError(
                "completed agent phase requires completed or aborted plan"
            )
        self._validate_plan_final_message(plan)

    def _validate_plan_step_deciding(self, plan: PlanState) -> None:
        """校验步骤决策阶段已经具备全部 observation。"""
        if plan.status is not PlanStatus.RUNNING:
            raise PlanStateConsistencyError(
                "plan_step_deciding requires running plan"
            )
        if self.pending_tool_call is not None:
            raise PlanStateConsistencyError(
                "plan_step_deciding must not have pending_tool_call"
            )
        trace_call_ids = {
            trace.call_id for trace in self.tool_traces if trace.call_id is not None
        }
        if any(
            call_id not in trace_call_ids
            for call_id in plan.current_step().tool_call_ids
        ):
            raise PlanStateConsistencyError(
                "plan_step_deciding requires traces for all step tool calls"
            )

    def _validate_plan_tool_pending(self, plan: PlanState) -> None:
        """校验待执行工具调用与当前步骤的关联。"""
        if plan.status is not PlanStatus.RUNNING:
            raise PlanStateConsistencyError("plan_tool_pending requires running plan")
        if self.pending_tool_call is None:
            raise PlanStateConsistencyError(
                "plan_tool_pending requires pending_tool_call"
            )
        call_ids = plan.current_step().tool_call_ids
        if not call_ids or call_ids[-1] != self.pending_tool_call.call_id:
            raise PlanStateConsistencyError(
                "pending call must match the current step's latest call ID"
            )
        trace_call_ids = {
            trace.call_id for trace in self.tool_traces if trace.call_id is not None
        }
        if any(call_id not in trace_call_ids for call_id in call_ids[:-1]):
            raise PlanStateConsistencyError(
                "plan_tool_pending requires traces for earlier step tool calls"
            )

    def _validate_plan_final_message(self, plan: PlanState) -> None:
        """校验当前 run 只有一条可恢复的计划最终回答。"""
        final_messages = [
            message
            for message in self.messages
            if message.role == "assistant"
            and message.metadata.get("message_type") == "plan_final_answer"
            and message.metadata.get("run_id") == self.run_id
            and message.metadata.get("plan_id") == plan.plan_id
        ]
        if len(final_messages) != 1:
            raise PlanStateConsistencyError(
                f"agent_phase='{self.cursor.agent_phase}' with "
                f"PlanStatus='{plan.status.value}' requires exactly one plan "
                f"final answer for run_id='{self.run_id}' and "
                f"plan_id='{plan.plan_id}'; found {len(final_messages)}"
            )

    def to_dict(self) -> dict[str, Any]:
        """转换为仅由 JSON 基础类型组成的持久化数据。"""
        self.validate_consistency()
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
            "tool_trace_start_index": self.tool_trace_start_index,
            "created_at_utc": self.created_at_utc,
            "updated_at_utc": self.updated_at_utc,
            "error": deepcopy(self.error),
            "plan_state": None
            if self.plan_state is None
            else self.plan_state.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RunState":
        """从持久化数据重建运行状态。"""
        if not isinstance(payload, dict):
            raise TypeError("payload must be a dict")
        cursor_payload = payload["cursor"]
        pending_payload = payload.get("pending_tool_call")
        plan_payload = payload.get("plan_state")
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
            tool_trace_start_index=payload.get("tool_trace_start_index", 0),
            created_at_utc=payload["created_at_utc"],
            updated_at_utc=payload["updated_at_utc"],
            error=deepcopy(payload.get("error")),
            plan_state=(
                None if plan_payload is None else PlanState.from_dict(plan_payload)
            ),
        )


def _utc_now() -> str:
    """返回便于 SQLite 排序和排障的 UTC 时间文本。"""
    return datetime.now(timezone.utc).isoformat()

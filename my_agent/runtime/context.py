"""
本文件负责保存 Runtime 执行期间的输入、变量、节点输出、节点 Trace 和会话状态。
本文件不负责节点调度，也不执行 Agent Loop。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from my_agent.runtime.trace import NodeExecutionRecord
from my_agent.state.session import SessionState
from my_agent.state.run_state import RunState


@dataclass
class RuntimeContext:
    """保存一次 Runtime 执行过程中的可变上下文。"""

    user_input: str
    variables: dict[str, Any] = field(default_factory=dict)
    node_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    node_traces: list[NodeExecutionRecord] = field(default_factory=list)
    session_state: SessionState | None = None
    run_state: RunState | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.user_input, str) or not self.user_input.strip():
            raise ValueError("user_input must be a non-empty string")
        if not isinstance(self.variables, dict):
            raise ValueError("variables must be a dict")
        if not isinstance(self.node_outputs, dict):
            raise ValueError("node_outputs must be a dict")
        if not isinstance(self.node_traces, list) or not all(
            isinstance(trace, NodeExecutionRecord) for trace in self.node_traces
        ):
            raise ValueError("node_traces must be a list[NodeExecutionRecord]")
        if self.session_state is not None and not isinstance(
            self.session_state, SessionState
        ):
            raise TypeError("session_state must be a SessionState or None")
        if self.run_state is not None and not isinstance(self.run_state, RunState):
            raise TypeError("run_state must be a RunState or None")

    def add_node_trace(self, trace: NodeExecutionRecord) -> None:
        """追加一条节点执行 Trace。"""
        if not isinstance(trace, NodeExecutionRecord):
            raise ValueError("trace must be a NodeExecutionRecord")
        self.node_traces.append(trace)

    def list_node_traces(self) -> list[NodeExecutionRecord]:
        """返回节点执行 Trace 列表副本，避免调用方直接修改内部列表。"""
        return list(self.node_traces)

"""
本文件负责保存 Runtime 执行期间的输入、变量、节点输出和会话状态。
本文件不负责节点调度，也不执行 Agent Loop。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from my_agent.state.session import SessionState


@dataclass
class RuntimeContext:
    """保存一次 Runtime 执行过程中的可变上下文。"""

    user_input: str
    variables: dict[str, Any] = field(default_factory=dict)
    node_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    session_state: SessionState | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.user_input, str) or not self.user_input.strip():
            raise ValueError("user_input must be a non-empty string")
        if not isinstance(self.variables, dict):
            raise ValueError("variables must be a dict")
        if not isinstance(self.node_outputs, dict):
            raise ValueError("node_outputs must be a dict")
        if self.session_state is not None and not isinstance(
            self.session_state, SessionState
        ):
            raise TypeError("session_state must be a SessionState or None")

"""
本文件负责定义 Runtime 节点级执行 Trace 数据模型。
本文件不依赖 ToolExecutor、RAG、LLM SDK 或具体节点执行器。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


def _validate_non_empty_text(field_name: str, field_value: str) -> None:
    """校验 Trace 关键标识字段，避免生成不可追踪的节点记录。"""
    if not isinstance(field_value, str) or not field_value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True)
class NodeExecutionRecord:
    """记录 Runtime 中单个节点的一次执行结果。"""

    node_id: str
    node_type: str
    inputs: dict[str, Any]
    output: dict[str, Any] | None
    success: bool
    error: dict[str, Any] | None
    duration_ms: float

    def __post_init__(self) -> None:
        _validate_non_empty_text("node_id", self.node_id)
        _validate_non_empty_text("node_type", self.node_type)
        if not isinstance(self.inputs, dict):
            raise ValueError("inputs must be a dict")
        if self.output is not None and not isinstance(self.output, dict):
            raise ValueError("output must be a dict or None")
        if not isinstance(self.success, bool):
            raise ValueError("success must be a bool")
        if self.error is not None and not isinstance(self.error, dict):
            raise ValueError("error must be a dict or None")
        if not isinstance(self.duration_ms, (int, float)) or self.duration_ms < 0:
            raise ValueError("duration_ms must be a non-negative number")
        if self.success and self.error is not None:
            raise ValueError("error must be None when success is True")
        if not self.success and self.error is None:
            raise ValueError("error must be provided when success is False")

        object.__setattr__(self, "inputs", deepcopy(self.inputs))
        object.__setattr__(
            self,
            "output",
            None if self.output is None else deepcopy(self.output),
        )
        object.__setattr__(
            self,
            "error",
            None if self.error is None else deepcopy(self.error),
        )

"""
本文件负责定义全局工具调用 Trace 数据模型。
本文件不负责执行工具，也不依赖 RAG 专用评估 Trace。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from my_agent.core.json_value import validate_json_native


def _validate_non_empty_text(field_name: str, field_value: str) -> None:
    """校验 Trace 关键文本字段，避免生成无法定位的执行记录。"""
    if not isinstance(field_value, str) or not field_value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _validate_optional_text(field_name: str, field_value: str | None) -> None:
    """校验可选文本字段，允许未绑定外部调用编号。"""
    if field_value is not None and not isinstance(field_value, str):
        raise ValueError(f"{field_name} must be a string or None")


def _validate_optional_dict(
    field_name: str,
    field_value: dict[str, Any] | None,
) -> None:
    """校验可选结构化字段，避免 Trace 中混入不可解析的自由文本。"""
    if field_value is not None and not isinstance(field_value, dict):
        raise ValueError(f"{field_name} must be a dict or None")


@dataclass(frozen=True)
class ToolTraceRecord:
    """记录一次工具调用的输入、输出、异常、耗时与可选 Token 消耗。"""

    trace_id: str
    tool_name: str
    call_id: str | None
    arguments: dict[str, Any]
    success: bool
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    duration_ms: float
    token_usage: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        _validate_non_empty_text("trace_id", self.trace_id)
        _validate_non_empty_text("tool_name", self.tool_name)
        _validate_optional_text("call_id", self.call_id)

        if not isinstance(self.arguments, dict):
            raise ValueError("arguments must be a dict")
        if not isinstance(self.success, bool):
            raise ValueError("success must be a bool")
        if not isinstance(self.duration_ms, (int, float)) or self.duration_ms < 0:
            raise ValueError("duration_ms must be a non-negative number")

        _validate_optional_dict("result", self.result)
        _validate_optional_dict("error", self.error)
        _validate_optional_dict("token_usage", self.token_usage)
        validate_json_native(self.arguments)
        for field_value in (self.result, self.error, self.token_usage):
            if field_value is not None:
                validate_json_native(field_value)

        if self.success and self.result is None:
            raise ValueError("result must be a dict when success is True")
        if self.success and self.error is not None:
            raise ValueError("error must be None when success is True")
        if not self.success and self.error is None:
            raise ValueError("error must be a dict when success is False")

"""
本文件负责定义 Tool Calling 框架的数据模型与基础校验规则。
本文件不负责工具注册、工具查找和工具执行。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from my_agent.core.errors import ToolValidationError


def _validate_non_empty_text(field_name: str, field_value: str) -> None:
    """校验关键文本字段非空，避免生成不可用的工具契约。"""
    if not isinstance(field_value, str) or not field_value.strip():
        raise ToolValidationError(f"{field_name} must be a non-empty string")


def _validate_parameters_schema(parameters: dict[str, Any]) -> None:
    """校验工具参数必须是最小 object schema。"""
    if not isinstance(parameters, dict):
        raise ToolValidationError("parameters must be a dict")

    if parameters.get("type") != "object":
        raise ToolValidationError('parameters.type must be "object"')

    properties = parameters.get("properties")
    if not isinstance(properties, dict):
        raise ToolValidationError("parameters.properties must be a dict")

    required = parameters.get("required", [])
    if not isinstance(required, list) or not all(
        isinstance(field_name, str) for field_name in required
    ):
        raise ToolValidationError("parameters.required must be a list[str]")

    missing_properties = sorted(
        field_name for field_name in required if field_name not in properties
    )
    if missing_properties:
        joined_fields = ", ".join(missing_properties)
        raise ToolValidationError(
            f"required fields missing from properties: {joined_fields}"
        )


@dataclass(frozen=True)
class ToolDefinition:
    """描述一个可被模型选择、可被 Runtime 执行的工具。"""

    name: str
    description: str
    parameters: dict[str, Any]
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_non_empty_text("name", self.name)
        _validate_non_empty_text("description", self.description)
        _validate_parameters_schema(self.parameters)

        if not isinstance(self.tags, tuple) or not all(
            isinstance(tag, str) for tag in self.tags
        ):
            raise ToolValidationError("tags must be a tuple[str, ...]")


@dataclass(frozen=True)
class ToolCallRequest:
    """表示一次标准化工具调用请求。"""

    name: str
    arguments: dict[str, Any]
    call_id: str | None = None

    def __post_init__(self) -> None:
        _validate_non_empty_text("name", self.name)
        if not isinstance(self.arguments, dict):
            raise ToolValidationError("arguments must be a dict")
        if self.call_id is not None and not isinstance(self.call_id, str):
            raise ToolValidationError("call_id must be a string or None")


@dataclass(frozen=True)
class ToolCallResult:
    """表示一次工具调用的标准化执行结果。"""

    name: str
    success: bool
    data: dict[str, Any] | None = None
    error: dict[str, str] | None = None
    duration_ms: float = 0
    call_id: str | None = None

    def __post_init__(self) -> None:
        _validate_non_empty_text("name", self.name)

        if not isinstance(self.success, bool):
            raise ToolValidationError("success must be a bool")

        if not isinstance(self.duration_ms, (int, float)) or self.duration_ms < 0:
            raise ToolValidationError("duration_ms must be a non-negative number")

        if self.call_id is not None and not isinstance(self.call_id, str):
            raise ToolValidationError("call_id must be a string or None")

        if self.success:
            self._validate_success_result()
        else:
            self._validate_failure_result()

    @classmethod
    def success_result(
        cls,
        name: str,
        data: dict[str, Any],
        duration_ms: float,
        call_id: str | None = None,
    ) -> "ToolCallResult":
        """构造成功结果，统一约束成功时不能携带错误。"""
        return cls(
            name=name,
            success=True,
            data=data,
            error=None,
            duration_ms=duration_ms,
            call_id=call_id,
        )

    @classmethod
    def failure_result(
        cls,
        name: str,
        error_type: str,
        error_message: str,
        duration_ms: float,
        call_id: str | None = None,
    ) -> "ToolCallResult":
        """构造失败结果，统一返回结构化错误信息。"""
        return cls(
            name=name,
            success=False,
            data=None,
            error={
                "type": error_type,
                "message": error_message,
            },
            duration_ms=duration_ms,
            call_id=call_id,
        )

    def _validate_success_result(self) -> None:
        """校验成功结果的数据契约。"""
        if not isinstance(self.data, dict):
            raise ToolValidationError("data must be a dict when success is True")
        if self.error is not None:
            raise ToolValidationError("error must be None when success is True")

    def _validate_failure_result(self) -> None:
        """校验失败结果的结构化错误契约。"""
        if self.data is not None:
            raise ToolValidationError("data must be None when success is False")
        if not isinstance(self.error, dict):
            raise ToolValidationError("error must be a dict when success is False")

        error_type = self.error.get("type")
        error_message = self.error.get("message")
        _validate_non_empty_text("error.type", error_type)
        _validate_non_empty_text("error.message", error_message)

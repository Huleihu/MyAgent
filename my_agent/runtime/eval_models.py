"""
本文件负责定义 Runtime Eval 的固定用例、工具期望、失败项和评估结果数据模型。
本文件不执行 Runtime，也不判断真实 LLM 的语义等价性。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable

from my_agent.runtime.conversation import ConversationTurnResult


def _validate_non_empty_text(field_name: str, field_value: str) -> None:
    """校验关键文本字段，避免生成无法定位的评估记录。"""
    if not isinstance(field_value, str) or not field_value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _as_tuple(field_name: str, field_value: Iterable[Any]) -> tuple[Any, ...]:
    """把可迭代输入转换为元组快照，隔离调用方后续的列表修改。"""
    if isinstance(field_value, (str, bytes)):
        raise ValueError(f"{field_name} must be an iterable, not text")
    try:
        return tuple(field_value)
    except TypeError as exc:
        raise ValueError(f"{field_name} must be iterable") from exc


@dataclass(frozen=True)
class ExpectedToolCall:
    """描述 Runtime Eval 对一次工具调用的最小严格期望。"""

    tool_name: str
    success: bool

    def __post_init__(self) -> None:
        _validate_non_empty_text("tool_name", self.tool_name)
        if not isinstance(self.success, bool):
            raise ValueError("success must be a bool")


@dataclass(frozen=True)
class RuntimeEvalCase:
    """描述一个使用确定性依赖执行的单轮 Runtime 回归用例。"""

    case_id: str
    user_input: str
    expected_output_text: str
    expected_node_ids: tuple[str, ...]
    expected_tool_calls: tuple[ExpectedToolCall, ...]

    def __post_init__(self) -> None:
        _validate_non_empty_text("case_id", self.case_id)
        _validate_non_empty_text("user_input", self.user_input)
        _validate_non_empty_text("expected_output_text", self.expected_output_text)

        node_ids = _as_tuple("expected_node_ids", self.expected_node_ids)
        if not all(isinstance(node_id, str) and node_id.strip() for node_id in node_ids):
            raise ValueError("expected_node_ids must contain non-empty strings")
        tool_calls = _as_tuple("expected_tool_calls", self.expected_tool_calls)
        if not all(isinstance(tool_call, ExpectedToolCall) for tool_call in tool_calls):
            raise ValueError(
                "expected_tool_calls must contain ExpectedToolCall instances"
            )

        object.__setattr__(self, "expected_node_ids", node_ids)
        object.__setattr__(self, "expected_tool_calls", tool_calls)


@dataclass(frozen=True)
class RuntimeEvalFailure:
    """记录一个独立可检查项的期望、实际值与失败说明。"""

    check_name: str
    expected: Any
    actual: Any
    message: str

    def __post_init__(self) -> None:
        _validate_non_empty_text("check_name", self.check_name)
        _validate_non_empty_text("message", self.message)
        object.__setattr__(self, "expected", deepcopy(self.expected))
        object.__setattr__(self, "actual", deepcopy(self.actual))


@dataclass(frozen=True)
class RuntimeEvalResult:
    """保存一次 Runtime Eval 的检查结果与可选调试回合引用。

    failures、实际节点路径和实际工具调用均为元组快照。turn_result 用于调试，
    其中包含可变 RuntimeContext，因此本结果不承诺深度不可变。
    """

    case_id: str
    passed: bool
    failures: tuple[RuntimeEvalFailure, ...]
    actual_node_ids: tuple[str, ...]
    actual_tool_calls: tuple[ExpectedToolCall, ...]
    turn_result: ConversationTurnResult | None

    def __post_init__(self) -> None:
        _validate_non_empty_text("case_id", self.case_id)
        if not isinstance(self.passed, bool):
            raise ValueError("passed must be a bool")

        failures = _as_tuple("failures", self.failures)
        if not all(isinstance(failure, RuntimeEvalFailure) for failure in failures):
            raise ValueError("failures must contain RuntimeEvalFailure instances")
        if self.passed != (not failures):
            raise ValueError("passed must match whether failures is empty")

        node_ids = _as_tuple("actual_node_ids", self.actual_node_ids)
        if not all(isinstance(node_id, str) and node_id.strip() for node_id in node_ids):
            raise ValueError("actual_node_ids must contain non-empty strings")
        tool_calls = _as_tuple("actual_tool_calls", self.actual_tool_calls)
        if not all(isinstance(tool_call, ExpectedToolCall) for tool_call in tool_calls):
            raise ValueError(
                "actual_tool_calls must contain ExpectedToolCall instances"
            )
        if self.turn_result is not None and not isinstance(
            self.turn_result,
            ConversationTurnResult,
        ):
            raise TypeError("turn_result must be a ConversationTurnResult or None")

        object.__setattr__(self, "failures", failures)
        object.__setattr__(self, "actual_node_ids", node_ids)
        object.__setattr__(self, "actual_tool_calls", tool_calls)

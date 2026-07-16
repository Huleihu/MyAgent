"""
本文件负责定义 Plan-and-Execute 的步骤级动作、决策信封和稳定协议错误。
本文件不执行工具，也不修改计划或 Runtime 状态。
"""

from __future__ import annotations

from dataclasses import dataclass

from my_agent.agent_loop.planner import ToolAction


class PlannerProtocolError(ValueError):
    """表示 Planner 输出不符合 Plan-and-Execute 稳定协议。"""

    code = "planner_protocol_error"


def _validate_text(name: str, value: str) -> None:
    """校验 Planner 动作中的必要文本。"""
    if not isinstance(value, str) or not value.strip():
        raise PlannerProtocolError(f"{name} must be a non-empty string")


@dataclass(frozen=True)
class CompleteStepAction:
    """表示当前步骤已经得到足够结果，可以显式完成。"""

    result_summary: str

    def __post_init__(self) -> None:
        _validate_text("result_summary", self.result_summary)


@dataclass(frozen=True)
class SkipStepAction:
    """表示当前步骤无法或无需继续执行。"""

    reason: str
    result_summary: str | None = None

    def __post_init__(self) -> None:
        _validate_text("reason", self.reason)
        if self.result_summary is not None:
            _validate_text("result_summary", self.result_summary)


@dataclass(frozen=True)
class AbortPlanAction:
    """表示当前问题使整个计划不能继续。"""

    reason: str

    def __post_init__(self) -> None:
        _validate_text("reason", self.reason)


StepAction = ToolAction | CompleteStepAction | SkipStepAction | AbortPlanAction


@dataclass(frozen=True)
class StepDecision:
    """封装 StepPlanner 的下一步动作和可选反思摘要。"""

    action: StepAction
    reflection: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(
            self.action,
            (ToolAction, CompleteStepAction, SkipStepAction, AbortPlanAction),
        ):
            raise PlannerProtocolError("unsupported step action")
        if self.reflection is not None:
            _validate_text("reflection", self.reflection)

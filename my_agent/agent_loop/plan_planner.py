"""
本文件负责定义任务级与步骤级 Planner 协议，以及与真实运行状态隔离的输入快照。
本文件不调用具体模型供应商，也不推进计划状态。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from my_agent.agent_loop.plan_actions import PlannerProtocolError, StepDecision
from my_agent.agent_loop.planner import FinalAnswerAction


def _validate_text(name: str, value: str) -> None:
    """校验 Planner 协议的必要文本。"""
    if not isinstance(value, str) or not value.strip():
        raise PlannerProtocolError(f"{name} must be a non-empty string")


def _copy_dict_tuple(items: Any, name: str) -> tuple[dict[str, Any], ...]:
    """深拷贝字典序列，隔离 Planner 与真实运行状态。"""
    if not isinstance(items, (list, tuple)) or not all(
        isinstance(item, dict) for item in items
    ):
        raise PlannerProtocolError(f"{name} must be a sequence of dicts")
    return tuple(deepcopy(item) for item in items)


@dataclass(frozen=True)
class PlanStepDefinition:
    """表示 TaskPlanner 生成的单个步骤定义。"""

    instruction: str

    def __post_init__(self) -> None:
        _validate_text("instruction", self.instruction)


@dataclass(frozen=True)
class PlanDefinition:
    """表示不含运行状态和持久化 ID 的任务计划定义。"""

    goal: str
    steps: tuple[PlanStepDefinition, ...]

    def __post_init__(self) -> None:
        _validate_text("goal", self.goal)
        if not isinstance(self.steps, tuple) or not self.steps or not all(
            isinstance(step, PlanStepDefinition) for step in self.steps
        ):
            raise PlannerProtocolError(
                "steps must be a non-empty tuple[PlanStepDefinition]"
            )


@dataclass(frozen=True)
class CreatePlanRequest:
    """保存创建计划所需的隔离输入快照。"""

    user_input: str
    messages: tuple[dict[str, Any], ...]
    tool_definitions: tuple[dict[str, Any], ...]
    max_plan_steps: int

    def __post_init__(self) -> None:
        _validate_text("user_input", self.user_input)
        if not isinstance(self.max_plan_steps, int) or self.max_plan_steps <= 0:
            raise PlannerProtocolError("max_plan_steps must be a positive integer")
        object.__setattr__(
            self, "messages", _copy_dict_tuple(self.messages, "messages")
        )
        object.__setattr__(
            self,
            "tool_definitions",
            _copy_dict_tuple(self.tool_definitions, "tool_definitions"),
        )


@dataclass(frozen=True)
class StepDecisionRequest:
    """保存当前步骤决策所需的完整隔离快照。"""

    user_input: str
    plan: dict[str, Any]
    current_step: dict[str, Any]
    previous_step_summaries: tuple[str, ...]
    observations: tuple[dict[str, Any], ...]
    recent_observation: dict[str, Any] | None
    messages: tuple[dict[str, Any], ...]
    tool_definitions: tuple[dict[str, Any], ...]
    remaining_step_tool_calls: int
    remaining_total_tool_calls: int
    can_call_tool: bool

    def __post_init__(self) -> None:
        _validate_text("user_input", self.user_input)
        if not isinstance(self.plan, dict) or not isinstance(self.current_step, dict):
            raise PlannerProtocolError("plan and current_step must be dicts")
        object.__setattr__(self, "plan", deepcopy(self.plan))
        object.__setattr__(self, "current_step", deepcopy(self.current_step))
        if not isinstance(self.previous_step_summaries, (list, tuple)) or not all(
            isinstance(item, str) for item in self.previous_step_summaries
        ):
            raise PlannerProtocolError(
                "previous_step_summaries must be a sequence of strings"
            )
        object.__setattr__(
            self, "previous_step_summaries", tuple(self.previous_step_summaries)
        )
        object.__setattr__(
            self, "observations", _copy_dict_tuple(self.observations, "observations")
        )
        if self.recent_observation is not None and not isinstance(
            self.recent_observation, dict
        ):
            raise PlannerProtocolError("recent_observation must be a dict or None")
        object.__setattr__(
            self, "recent_observation", deepcopy(self.recent_observation)
        )
        object.__setattr__(
            self, "messages", _copy_dict_tuple(self.messages, "messages")
        )
        object.__setattr__(
            self,
            "tool_definitions",
            _copy_dict_tuple(self.tool_definitions, "tool_definitions"),
        )
        for name, count in (
            ("remaining_step_tool_calls", self.remaining_step_tool_calls),
            ("remaining_total_tool_calls", self.remaining_total_tool_calls),
        ):
            if not isinstance(count, int) or count < 0:
                raise PlannerProtocolError(
                    f"{name} must be a non-negative integer"
                )
        if not isinstance(self.can_call_tool, bool):
            raise PlannerProtocolError("can_call_tool must be a bool")


@dataclass(frozen=True)
class FinalizePlanRequest:
    """保存生成整个计划最终回答所需的隔离快照。"""

    user_input: str
    plan: dict[str, Any]
    outcome: str
    abort_reason: str | None
    messages: tuple[dict[str, Any], ...]

    def __post_init__(self) -> None:
        _validate_text("user_input", self.user_input)
        _validate_text("outcome", self.outcome)
        if not isinstance(self.plan, dict):
            raise PlannerProtocolError("plan must be a dict")
        if self.abort_reason is not None:
            _validate_text("abort_reason", self.abort_reason)
        object.__setattr__(self, "plan", deepcopy(self.plan))
        object.__setattr__(
            self, "messages", _copy_dict_tuple(self.messages, "messages")
        )


@runtime_checkable
class TaskPlanner(Protocol):
    """定义创建计划和生成计划最终回答的任务级契约。"""

    def create_plan(self, request: CreatePlanRequest) -> PlanDefinition:
        """生成不含执行状态的计划定义。"""

    def finalize_plan(self, request: FinalizePlanRequest) -> FinalAnswerAction:
        """根据已确定的计划结果生成最终回答。"""


@runtime_checkable
class StepPlanner(Protocol):
    """定义当前步骤下一步决策的契约。"""

    def decide(self, request: StepDecisionRequest) -> StepDecision:
        """返回工具调用或步骤终态动作。"""

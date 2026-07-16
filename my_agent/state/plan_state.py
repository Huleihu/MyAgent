"""
本文件负责定义 Plan-and-Execute 可持久化的计划、步骤、执行限制与结果状态。
本文件不调用 Planner、工具或 Checkpoint Store。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PlanStateConsistencyError(ValueError):
    """表示计划状态内部或与 Runtime 的组合不满足恢复约束。"""


class PlanStatus(str, Enum):
    """表示计划编排自身的执行阶段。"""

    RUNNING = "running"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    ABORTED = "aborted"


class PlanOutcome(str, Enum):
    """表示计划执行产生的业务结果。"""

    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class PlanStepStatus(str, Enum):
    """表示单个计划步骤的生命周期状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


def _validate_text(name: str, value: str) -> None:
    """校验计划标识和业务文本。"""
    if not isinstance(value, str) or not value.strip():
        raise PlanStateConsistencyError(f"{name} must be a non-empty string")


def _validate_optional_text(name: str, value: str | None) -> None:
    """校验可选业务文本，存在时不得为空。"""
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise PlanStateConsistencyError(
            f"{name} must be a non-empty string or None"
        )


@dataclass
class PlanStep:
    """保存一个步骤的控制状态及其工具 Trace 关联索引。"""

    step_id: str
    instruction: str
    status: PlanStepStatus
    attempt_count: int = 0
    retry_count: int = 0
    tool_call_ids: list[str] = field(default_factory=list)
    last_observation_summary: str | None = None
    reflection: str | None = None
    result_summary: str | None = None
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """校验步骤计数、状态文本与工具调用索引。"""
        _validate_text("step_id", self.step_id)
        _validate_text("instruction", self.instruction)
        if not isinstance(self.status, PlanStepStatus):
            raise PlanStateConsistencyError("status must be a PlanStepStatus")
        for name, count in (
            ("attempt_count", self.attempt_count),
            ("retry_count", self.retry_count),
        ):
            if not isinstance(count, int) or count < 0:
                raise PlanStateConsistencyError(
                    f"{name} must be a non-negative integer"
                )
        if not isinstance(self.tool_call_ids, list) or not all(
            isinstance(call_id, str) and call_id.strip()
            for call_id in self.tool_call_ids
        ):
            raise PlanStateConsistencyError(
                "tool_call_ids must be a list of non-empty strings"
            )
        if len(set(self.tool_call_ids)) != len(self.tool_call_ids):
            raise PlanStateConsistencyError("tool_call_ids must be unique")
        if self.attempt_count != len(self.tool_call_ids):
            raise PlanStateConsistencyError(
                "attempt_count must equal the number of tool_call_ids"
            )
        if self.retry_count > max(0, self.attempt_count - 1):
            raise PlanStateConsistencyError(
                "retry_count must not exceed completed attempts before the latest call"
            )
        for name, value in (
            ("last_observation_summary", self.last_observation_summary),
            ("reflection", self.reflection),
            ("result_summary", self.result_summary),
            ("failure_reason", self.failure_reason),
        ):
            _validate_optional_text(name, value)
        if self.status is PlanStepStatus.PENDING and any(
            (
                self.attempt_count,
                self.retry_count,
                self.tool_call_ids,
                self.last_observation_summary,
                self.reflection,
                self.result_summary,
                self.failure_reason,
            )
        ):
            raise PlanStateConsistencyError(
                "pending step must not contain execution state"
            )
        if self.status is PlanStepStatus.RUNNING and (
            self.result_summary is not None or self.failure_reason is not None
        ):
            raise PlanStateConsistencyError(
                "running step must not contain terminal result fields"
            )
        if self.status is PlanStepStatus.COMPLETED and (
            self.result_summary is None or self.failure_reason is not None
        ):
            raise PlanStateConsistencyError(
                "completed step requires result_summary without failure_reason"
            )
        if self.status is PlanStepStatus.SKIPPED and (
            self.result_summary is None or self.failure_reason is None
        ):
            raise PlanStateConsistencyError(
                "skipped step requires result_summary and failure_reason"
            )
        if self.status is PlanStepStatus.FAILED and self.failure_reason is None:
            raise PlanStateConsistencyError(
                "failed step requires failure_reason"
            )

    def to_dict(self) -> dict[str, Any]:
        """转换为仅包含 JSON 基础类型的步骤字典。"""
        self.validate()
        return {
            "step_id": self.step_id,
            "instruction": self.instruction,
            "status": self.status.value,
            "attempt_count": self.attempt_count,
            "retry_count": self.retry_count,
            "tool_call_ids": list(self.tool_call_ids),
            "last_observation_summary": self.last_observation_summary,
            "reflection": self.reflection,
            "result_summary": self.result_summary,
            "failure_reason": self.failure_reason,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PlanStep":
        """从持久化字典重建步骤状态。"""
        return cls(
            step_id=payload["step_id"],
            instruction=payload["instruction"],
            status=PlanStepStatus(payload["status"]),
            attempt_count=payload.get("attempt_count", 0),
            retry_count=payload.get("retry_count", 0),
            tool_call_ids=list(payload.get("tool_call_ids", [])),
            last_observation_summary=payload.get("last_observation_summary"),
            reflection=payload.get("reflection"),
            result_summary=payload.get("result_summary"),
            failure_reason=payload.get("failure_reason"),
        )


@dataclass
class PlanState:
    """保存一次 Plan-and-Execute 运行的完整可恢复控制状态。"""

    plan_id: str
    goal: str
    status: PlanStatus
    outcome: PlanOutcome | None
    current_step_id: str | None
    steps: list[PlanStep]
    total_tool_call_count: int
    total_retry_count: int
    max_tool_calls_per_step: int
    max_total_tool_calls: int
    abort_reason: str | None = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """校验计划内部状态，使其可被 Runtime 确定性恢复。"""
        _validate_text("plan_id", self.plan_id)
        _validate_text("goal", self.goal)
        if not isinstance(self.status, PlanStatus):
            raise PlanStateConsistencyError("status must be a PlanStatus")
        if self.outcome is not None and not isinstance(self.outcome, PlanOutcome):
            raise PlanStateConsistencyError("outcome must be a PlanOutcome or None")
        if not isinstance(self.steps, list) or not self.steps or not all(
            isinstance(step, PlanStep) for step in self.steps
        ):
            raise PlanStateConsistencyError(
                "steps must be a non-empty list[PlanStep]"
            )
        for step in self.steps:
            step.validate()
        step_ids = [step.step_id for step in self.steps]
        if len(set(step_ids)) != len(step_ids):
            raise PlanStateConsistencyError("step_id must be unique within a plan")
        call_ids = [call_id for step in self.steps for call_id in step.tool_call_ids]
        if len(set(call_ids)) != len(call_ids):
            raise PlanStateConsistencyError(
                "tool call IDs must be unique within a plan"
            )
        for name, count in (
            ("total_tool_call_count", self.total_tool_call_count),
            ("total_retry_count", self.total_retry_count),
        ):
            if not isinstance(count, int) or count < 0:
                raise PlanStateConsistencyError(
                    f"{name} must be a non-negative integer"
                )
        for name, limit in (
            ("max_tool_calls_per_step", self.max_tool_calls_per_step),
            ("max_total_tool_calls", self.max_total_tool_calls),
        ):
            if not isinstance(limit, int) or limit <= 0:
                raise PlanStateConsistencyError(f"{name} must be a positive integer")
        if self.total_tool_call_count != sum(
            step.attempt_count for step in self.steps
        ):
            raise PlanStateConsistencyError(
                "total_tool_call_count must equal all step attempts"
            )
        if self.total_retry_count != sum(step.retry_count for step in self.steps):
            raise PlanStateConsistencyError(
                "total_retry_count must equal all step retries"
            )
        if any(
            step.attempt_count > self.max_tool_calls_per_step
            for step in self.steps
        ):
            raise PlanStateConsistencyError(
                "step attempts must not exceed max_tool_calls_per_step"
            )
        if self.total_tool_call_count > self.max_total_tool_calls:
            raise PlanStateConsistencyError(
                "total_tool_call_count must not exceed max_total_tool_calls"
            )
        running_steps = [
            step for step in self.steps if step.status is PlanStepStatus.RUNNING
        ]
        if self.status is PlanStatus.RUNNING:
            if self.outcome is not None:
                raise PlanStateConsistencyError("running plan must not have an outcome")
            if self.current_step_id is None:
                raise PlanStateConsistencyError(
                    "running plan requires current_step_id"
                )
            if len(running_steps) != 1 or running_steps[0].step_id != self.current_step_id:
                raise PlanStateConsistencyError(
                    "current_step_id must reference the only running step"
                )
            current_index = self.steps.index(running_steps[0])
            if any(
                step.status
                not in {PlanStepStatus.COMPLETED, PlanStepStatus.SKIPPED}
                for step in self.steps[:current_index]
            ) or any(
                step.status is not PlanStepStatus.PENDING
                for step in self.steps[current_index + 1 :]
            ):
                raise PlanStateConsistencyError(
                    "running plan steps must follow sequential status order"
                )
        else:
            if self.outcome is None:
                raise PlanStateConsistencyError(
                    "terminal or finalizing plan requires an outcome"
                )
            if self.current_step_id is not None or running_steps:
                raise PlanStateConsistencyError(
                    "terminal or finalizing plan must not have a running step"
                )
            completed_count = sum(
                step.status is PlanStepStatus.COMPLETED for step in self.steps
            )
            expected_outcome = (
                PlanOutcome.SUCCEEDED
                if completed_count == len(self.steps)
                else PlanOutcome.PARTIAL
                if completed_count > 0
                else PlanOutcome.FAILED
            )
            if self.outcome is not expected_outcome:
                raise PlanStateConsistencyError(
                    "outcome must match the persisted step terminal states"
                )
            if self.status in {PlanStatus.FINALIZING, PlanStatus.COMPLETED}:
                if any(
                    step.status
                    not in {PlanStepStatus.COMPLETED, PlanStepStatus.SKIPPED}
                    for step in self.steps
                ):
                    raise PlanStateConsistencyError(
                        "finalizing or completed plan must have no pending or failed steps"
                    )
            if self.status is PlanStatus.ABORTED:
                failed_indexes = [
                    index
                    for index, step in enumerate(self.steps)
                    if step.status is PlanStepStatus.FAILED
                ]
                if len(failed_indexes) != 1:
                    raise PlanStateConsistencyError(
                        "aborted plan requires exactly one failed step"
                    )
                failed_index = failed_indexes[0]
                if any(
                    step.status
                    not in {PlanStepStatus.COMPLETED, PlanStepStatus.SKIPPED}
                    for step in self.steps[:failed_index]
                ) or any(
                    step.status is not PlanStepStatus.PENDING
                    for step in self.steps[failed_index + 1 :]
                ):
                    raise PlanStateConsistencyError(
                        "aborted plan steps must preserve the execution frontier"
                    )
        _validate_optional_text("abort_reason", self.abort_reason)
        if self.status is PlanStatus.ABORTED and self.abort_reason is None:
            raise PlanStateConsistencyError("aborted plan requires abort_reason")
        if self.status is not PlanStatus.ABORTED and self.abort_reason is not None:
            raise PlanStateConsistencyError(
                "abort_reason is only allowed for an aborted plan"
            )

    def current_step(self) -> PlanStep:
        """返回当前运行步骤；调用前必须处于 RUNNING 状态。"""
        self.validate()
        for step in self.steps:
            if step.step_id == self.current_step_id:
                return step
        raise PlanStateConsistencyError("current step not found")

    def to_dict(self) -> dict[str, Any]:
        """转换为可持久化的计划状态字典。"""
        self.validate()
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "status": self.status.value,
            "outcome": None if self.outcome is None else self.outcome.value,
            "current_step_id": self.current_step_id,
            "steps": [step.to_dict() for step in self.steps],
            "total_tool_call_count": self.total_tool_call_count,
            "total_retry_count": self.total_retry_count,
            "max_tool_calls_per_step": self.max_tool_calls_per_step,
            "max_total_tool_calls": self.max_total_tool_calls,
            "abort_reason": self.abort_reason,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PlanState":
        """从持久化字典重建计划状态。"""
        if not isinstance(payload, dict):
            raise TypeError("payload must be a dict")
        outcome = payload.get("outcome")
        return cls(
            plan_id=payload["plan_id"],
            goal=payload["goal"],
            status=PlanStatus(payload["status"]),
            outcome=None if outcome is None else PlanOutcome(outcome),
            current_step_id=payload.get("current_step_id"),
            steps=[PlanStep.from_dict(item) for item in payload["steps"]],
            total_tool_call_count=payload.get("total_tool_call_count", 0),
            total_retry_count=payload.get("total_retry_count", 0),
            max_tool_calls_per_step=payload["max_tool_calls_per_step"],
            max_total_tool_calls=payload["max_total_tool_calls"],
            abort_reason=payload.get("abort_reason"),
        )

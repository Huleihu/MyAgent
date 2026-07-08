"""
本文件负责定义 Agent Loop 的规划动作与 Planner 接口。
本文件不执行工具，也不直接依赖具体 LLM 供应商。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from my_agent.state.session import SessionState


class AgentAction:
    """表示 Planner 输出的下一步动作基类。"""


@dataclass(frozen=True)
class ToolAction(AgentAction):
    """表示 Agent 下一步需要调用一个工具。"""

    tool_name: str
    arguments: dict[str, Any]
    call_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tool_name, str) or not self.tool_name.strip():
            raise ValueError("tool_name must be a non-empty string")
        if not isinstance(self.arguments, dict):
            raise ValueError("arguments must be a dict")
        if self.call_id is not None and not isinstance(self.call_id, str):
            raise ValueError("call_id must be a string or None")


@dataclass(frozen=True)
class FinalAnswerAction(AgentAction):
    """表示 Agent 已经得到最终回答。"""

    answer: str

    def __post_init__(self) -> None:
        if not isinstance(self.answer, str) or not self.answer.strip():
            raise ValueError("answer must be a non-empty string")


class Planner(ABC):
    """根据用户输入和当前会话状态决定 Agent 下一步动作。"""

    @abstractmethod
    def plan(self, user_input: str, session: SessionState) -> AgentAction:
        """返回下一步 Agent 动作，具体决策可由 Fake 或真实 LLM 实现。"""


class FakePlanner(Planner):
    """按预设动作顺序返回结果的测试规划器。"""

    def __init__(self, actions: list[AgentAction]) -> None:
        if not isinstance(actions, list) or not all(
            isinstance(action, AgentAction) for action in actions
        ):
            raise ValueError("actions must be a list[AgentAction]")
        self._actions = list(actions)
        self._next_index = 0

    def plan(self, user_input: str, session: SessionState) -> AgentAction:
        """返回下一个预设动作，用于稳定测试 Agent Loop 编排。"""
        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("user_input must be a non-empty string")
        if not isinstance(session, SessionState):
            raise TypeError("session must be a SessionState")
        if self._next_index >= len(self._actions):
            raise ValueError("FakePlanner has no remaining actions")

        action = self._actions[self._next_index]
        self._next_index += 1
        return action

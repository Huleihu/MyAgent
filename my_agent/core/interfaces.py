"""
本文件负责定义 Agent 核心能力的抽象协议。
本文件不提供具体工具实现，也不负责工具注册和执行。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from my_agent.tools.schema import ToolDefinition


class Tool(ABC):
    """定义 Runtime 可调用工具必须满足的最小契约。"""

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """返回工具定义，用于向模型或 DSL Runtime 暴露工具能力。"""

    @abstractmethod
    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """执行工具并返回结构化结果数据。"""

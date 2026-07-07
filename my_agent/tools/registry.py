"""
本文件负责管理可用工具的注册、查找和工具定义导出。
本文件不负责执行工具，也不校验具体工具调用参数。
"""

from __future__ import annotations

from typing import Iterable

from my_agent.core.errors import (
    ToolAlreadyExistsError,
    ToolNotFoundError,
    ToolValidationError,
)
from my_agent.core.interfaces import Tool
from my_agent.tools.schema import ToolDefinition


class ToolRegistry:
    """维护运行时可用工具集合，并向模型或 Runtime 暴露工具定义。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册工具实例，工具名必须全局唯一。"""
        if not isinstance(tool, Tool):
            raise ToolValidationError("tool must inherit from Tool")

        definition = tool.definition
        if definition.name in self._tools:
            raise ToolAlreadyExistsError(f"tool already exists: {definition.name}")

        self._tools[definition.name] = tool

    def get(self, name: str) -> Tool:
        """根据工具名查找工具实例。"""
        if name not in self._tools:
            raise ToolNotFoundError(f"tool not found: {name}")
        return self._tools[name]

    def list_definitions(
        self,
        tags: Iterable[str] | None = None,
    ) -> list[ToolDefinition]:
        """导出工具定义，可按任意 tag 过滤。"""
        tag_set = set(tags or ())
        definitions = [tool.definition for tool in self._tools.values()]

        if tag_set:
            definitions = [
                definition
                for definition in definitions
                if tag_set.intersection(definition.tags)
            ]

        return sorted(definitions, key=lambda definition: definition.name)

"""
本文件负责把普通 Python 函数包装为标准 Tool。
本文件不负责工具注册，也不负责统一异常包装和耗时记录。
"""

from __future__ import annotations

from typing import Any, Callable

from my_agent.core.errors import ToolValidationError
from my_agent.core.interfaces import Tool
from my_agent.tools.schema import ToolDefinition


class FunctionTool(Tool):
    """将接收 dict 参数的 Python 函数适配为 Tool。"""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        func: Callable[[dict[str, Any]], dict[str, Any]],
        tags: tuple[str, ...] = (),
    ) -> None:
        if not callable(func):
            raise ToolValidationError("func must be callable")

        self._definition = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters,
            tags=tags,
        )
        self._func = func

    @property
    def definition(self) -> ToolDefinition:
        """返回函数工具的标准工具定义。"""
        return self._definition

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """调用被包装函数，返回值由后续 ToolExecutor 统一校验。"""
        return self._func(arguments)

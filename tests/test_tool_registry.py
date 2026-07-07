"""
本文件负责验证工具注册表的注册、查找与工具定义导出能力。
本文件不测试工具执行和参数校验流程。
"""

import unittest

from my_agent.core.errors import (
    ToolAlreadyExistsError,
    ToolNotFoundError,
    ToolValidationError,
)
from my_agent.core.interfaces import Tool
from my_agent.tools.registry import ToolRegistry
from my_agent.tools.schema import ToolDefinition


class EchoTool(Tool):
    @property
    def definition(self):
        return ToolDefinition(
            name="debug.echo",
            description="返回输入文本",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                },
                "required": ["text"],
            },
            tags=("debug", "text"),
        )

    def run(self, arguments):
        return {"text": arguments["text"]}


class AddTool(Tool):
    @property
    def definition(self):
        return ToolDefinition(
            name="calculator.add",
            description="计算两个数字之和",
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "number"},
                    "b": {"type": "number"},
                },
                "required": ["a", "b"],
            },
            tags=("math",),
        )

    def run(self, arguments):
        return {"result": arguments["a"] + arguments["b"]}


class NotATool:
    pass


class ToolRegistryTest(unittest.TestCase):
    def test_register_and_get_tool(self):
        registry = ToolRegistry()
        tool = EchoTool()

        registry.register(tool)

        self.assertIs(registry.get("debug.echo"), tool)

    def test_register_rejects_non_tool_object(self):
        registry = ToolRegistry()

        with self.assertRaises(ToolValidationError):
            registry.register(NotATool())

    def test_register_rejects_duplicate_tool_name(self):
        registry = ToolRegistry()
        registry.register(EchoTool())

        with self.assertRaises(ToolAlreadyExistsError):
            registry.register(EchoTool())

    def test_get_missing_tool_raises_not_found(self):
        registry = ToolRegistry()

        with self.assertRaises(ToolNotFoundError):
            registry.get("missing.tool")

    def test_list_definitions_returns_registered_tool_definitions(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        registry.register(AddTool())

        definitions = registry.list_definitions()

        self.assertEqual(
            [definition.name for definition in definitions],
            ["calculator.add", "debug.echo"],
        )

    def test_list_definitions_filters_by_any_tag(self):
        registry = ToolRegistry()
        registry.register(EchoTool())
        registry.register(AddTool())

        definitions = registry.list_definitions(tags=("debug",))

        self.assertEqual([definition.name for definition in definitions], ["debug.echo"])


if __name__ == "__main__":
    unittest.main()

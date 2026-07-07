"""
本文件负责验证 Tool 协议的结构化契约。
本文件不测试工具注册、参数校验和执行流程。
"""

import unittest

from my_agent.core.interfaces import Tool
from my_agent.tools.schema import ToolDefinition


class EchoTool(Tool):
    @property
    def definition(self):
        return ToolDefinition(
            name="debug.echo",
            description="返回输入参数，便于验证工具协议",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                },
                "required": ["text"],
            },
            tags=("debug",),
        )

    def run(self, arguments):
        return {"text": arguments["text"]}


class MissingRunTool:
    @property
    def definition(self):
        return ToolDefinition(
            name="debug.missing_run",
            description="缺少 run 方法的反例工具",
            parameters={
                "type": "object",
                "properties": {},
            },
        )


class StructurallySimilarTool:
    @property
    def definition(self):
        return ToolDefinition(
            name="debug.structural",
            description="结构相似但没有显式继承 Tool 的反例工具",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                },
                "required": ["text"],
            },
        )

    def run(self, arguments):
        return {"text": arguments["text"]}


class ToolInterfaceTest(unittest.TestCase):
    def test_tool_subclass_with_definition_and_run_matches_tool_interface(self):
        tool = EchoTool()

        self.assertIsInstance(tool, Tool)
        self.assertEqual(tool.definition.name, "debug.echo")
        self.assertEqual(tool.run({"text": "hello"}), {"text": "hello"})

    def test_object_missing_run_does_not_match_tool_protocol(self):
        tool = MissingRunTool()

        self.assertNotIsInstance(tool, Tool)

    def test_structurally_similar_object_without_inheritance_is_not_tool(self):
        tool = StructurallySimilarTool()

        self.assertNotIsInstance(tool, Tool)


if __name__ == "__main__":
    unittest.main()

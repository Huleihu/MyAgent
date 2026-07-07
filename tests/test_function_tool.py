"""
本文件负责验证普通 Python 函数到 Tool 的包装能力。
本文件不测试工具注册表和执行器流程。
"""

import unittest

from my_agent.core.errors import ToolValidationError
from my_agent.core.interfaces import Tool
from my_agent.tools.function_tool import FunctionTool


class FunctionToolTest(unittest.TestCase):
    def test_function_tool_is_tool_subclass(self):
        tool = FunctionTool(
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
            func=lambda arguments: {"result": arguments["a"] + arguments["b"]},
            tags=("math",),
        )

        self.assertIsInstance(tool, Tool)
        self.assertEqual(tool.definition.name, "calculator.add")
        self.assertEqual(tool.definition.tags, ("math",))

    def test_run_passes_arguments_to_wrapped_function(self):
        received_arguments = {}

        def echo(arguments):
            received_arguments.update(arguments)
            return {"text": arguments["text"]}

        tool = FunctionTool(
            name="debug.echo",
            description="返回输入文本",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                },
                "required": ["text"],
            },
            func=echo,
        )

        result = tool.run({"text": "hello"})

        self.assertEqual(result, {"text": "hello"})
        self.assertEqual(received_arguments, {"text": "hello"})

    def test_rejects_non_callable_func(self):
        with self.assertRaises(ToolValidationError):
            FunctionTool(
                name="debug.invalid",
                description="无效函数工具",
                parameters={
                    "type": "object",
                    "properties": {},
                },
                func="not callable",
            )


if __name__ == "__main__":
    unittest.main()

"""
本文件负责验证工具执行器的查找、参数校验、调用和结果包装能力。
本文件不测试具体业务工具的内部逻辑。
"""

import unittest

from my_agent.tools.executor import ToolExecutor
from my_agent.tools.function_tool import FunctionTool
from my_agent.tools.registry import ToolRegistry
from my_agent.tools.schema import ToolCallRequest


def build_registry_with_tool(tool):
    registry = ToolRegistry()
    registry.register(tool)
    return registry


class ToolExecutorTest(unittest.TestCase):
    def test_execute_returns_success_result_for_registered_tool(self):
        registry = build_registry_with_tool(
            FunctionTool(
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
            )
        )
        executor = ToolExecutor(registry)

        result = executor.execute(
            ToolCallRequest(
                name="calculator.add",
                arguments={"a": 1, "b": 2},
                call_id="call-1",
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.data, {"result": 3})
        self.assertIsNone(result.error)
        self.assertEqual(result.call_id, "call-1")
        self.assertGreaterEqual(result.duration_ms, 0)

    def test_execute_returns_validation_error_when_required_argument_missing(self):
        registry = build_registry_with_tool(
            FunctionTool(
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
            )
        )
        executor = ToolExecutor(registry)

        result = executor.execute(
            ToolCallRequest(name="calculator.add", arguments={"a": 1})
        )

        self.assertFalse(result.success)
        self.assertEqual(
            result.error,
            {
                "type": "ToolValidationError",
                "message": "Missing required arguments: b",
            },
        )
        self.assertIsNone(result.data)
        self.assertGreaterEqual(result.duration_ms, 0)

    def test_execute_returns_not_found_error_when_tool_missing(self):
        executor = ToolExecutor(ToolRegistry())

        result = executor.execute(
            ToolCallRequest(
                name="missing.tool",
                arguments={},
                call_id="call-missing",
            )
        )

        self.assertFalse(result.success)
        self.assertEqual(result.name, "missing.tool")
        self.assertEqual(result.call_id, "call-missing")
        self.assertEqual(result.error["type"], "ToolNotFoundError")

    def test_execute_returns_execution_error_when_tool_raises(self):
        def fail(_arguments):
            raise ValueError("boom")

        registry = build_registry_with_tool(
            FunctionTool(
                name="debug.fail",
                description="用于验证异常包装的工具",
                parameters={
                    "type": "object",
                    "properties": {},
                },
                func=fail,
            )
        )
        executor = ToolExecutor(registry)

        result = executor.execute(ToolCallRequest(name="debug.fail", arguments={}))

        self.assertFalse(result.success)
        self.assertEqual(result.error["type"], "ToolExecutionError")
        self.assertIn("boom", result.error["message"])

    def test_execute_returns_execution_error_when_tool_returns_non_dict(self):
        registry = build_registry_with_tool(
            FunctionTool(
                name="debug.invalid_return",
                description="用于验证返回值类型校验的工具",
                parameters={
                    "type": "object",
                    "properties": {},
                },
                func=lambda _arguments: "not dict",
            )
        )
        executor = ToolExecutor(registry)

        result = executor.execute(
            ToolCallRequest(name="debug.invalid_return", arguments={})
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error["type"], "ToolExecutionError")
        self.assertIn("must return a dict", result.error["message"])

    def test_execute_returns_failure_for_non_serializable_nested_result(self):
        registry = build_registry_with_tool(
            FunctionTool(
                name="debug.invalid_nested_return",
                description="用于验证嵌套返回值可持久化",
                parameters={"type": "object", "properties": {}},
                func=lambda _arguments: {"items": {"not-json"}},
            )
        )

        result = ToolExecutor(registry).execute(
            ToolCallRequest(
                name="debug.invalid_nested_return",
                arguments={},
                call_id="call-invalid-result",
            )
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error["type"], "ToolExecutionError")
        self.assertEqual(
            result.error["message"],
            "tool result must be JSON-serializable",
        )

    def test_execute_rejects_result_that_json_would_coerce(self):
        registry = build_registry_with_tool(
            FunctionTool(
                name="debug.coercing_return",
                description="用于验证 JSON 类型不被静默转换",
                parameters={"type": "object", "properties": {}},
                func=lambda _arguments: {"items": (1, 2)},
            )
        )

        result = ToolExecutor(registry).execute(
            ToolCallRequest(name="debug.coercing_return", arguments={})
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error["type"], "ToolExecutionError")


if __name__ == "__main__":
    unittest.main()

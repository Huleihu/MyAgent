"""
本文件负责验证 Tool 框架第一阶段的数据模型与异常契约。
本文件不测试工具注册和执行流程。
"""

import unittest

from my_agent.core.errors import ToolValidationError
from my_agent.tools.schema import ToolCallRequest, ToolCallResult, ToolDefinition


class ToolSchemaTest(unittest.TestCase):
    def test_tool_definition_accepts_object_parameters_schema(self):
        definition = ToolDefinition(
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

        self.assertEqual(definition.name, "calculator.add")
        self.assertEqual(definition.tags, ("math",))

    def test_tool_definition_rejects_non_object_parameters_schema(self):
        with self.assertRaises(ToolValidationError):
            ToolDefinition(
                name="calculator.add",
                description="计算两个数字之和",
                parameters={
                    "type": "array",
                    "properties": {},
                },
            )

    def test_tool_definition_rejects_required_field_missing_from_properties(self):
        with self.assertRaises(ToolValidationError):
            ToolDefinition(
                name="calculator.add",
                description="计算两个数字之和",
                parameters={
                    "type": "object",
                    "properties": {
                        "a": {"type": "number"},
                    },
                    "required": ["a", "b"],
                },
            )

    def test_tool_call_request_requires_dict_arguments(self):
        with self.assertRaises(ToolValidationError):
            ToolCallRequest(name="calculator.add", arguments=["not", "dict"])

    def test_success_result_requires_dict_data_and_no_error(self):
        result = ToolCallResult.success_result(
            name="calculator.add",
            data={"result": 3},
            duration_ms=1.2,
            call_id="call-1",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.data, {"result": 3})
        self.assertIsNone(result.error)
        self.assertEqual(result.call_id, "call-1")

    def test_failure_result_uses_structured_error(self):
        result = ToolCallResult.failure_result(
            name="calculator.add",
            error_type="ToolValidationError",
            error_message="Missing required arguments: a, b",
            duration_ms=0.5,
        )

        self.assertFalse(result.success)
        self.assertIsNone(result.data)
        self.assertEqual(
            result.error,
            {
                "type": "ToolValidationError",
                "message": "Missing required arguments: a, b",
            },
        )


if __name__ == "__main__":
    unittest.main()

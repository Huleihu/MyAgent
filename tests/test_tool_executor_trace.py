"""
本文件负责验证 ToolExecutor 可选写入全局工具调用 Trace。
本文件不测试 TraceRecorder 的内部存储细节。
"""

import unittest

from my_agent.state.recorder import TraceRecorder
from my_agent.state.session import SessionState
from my_agent.tools.executor import ToolExecutor
from my_agent.tools.function_tool import FunctionTool
from my_agent.tools.registry import ToolRegistry
from my_agent.tools.schema import ToolCallRequest


def build_registry_with_tool(tool):
    registry = ToolRegistry()
    registry.register(tool)
    return registry


def build_add_tool():
    return FunctionTool(
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


class ToolExecutorTraceTest(unittest.TestCase):
    def test_execute_without_trace_recorder_keeps_existing_behavior(self):
        executor = ToolExecutor(build_registry_with_tool(build_add_tool()))

        result = executor.execute(
            ToolCallRequest(
                name="calculator.add",
                arguments={"a": 1, "b": 2},
                call_id="call-1",
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.data, {"result": 3})
        self.assertEqual(result.call_id, "call-1")

    def test_execute_records_success_trace_when_recorder_exists(self):
        session = SessionState(session_id="session-1")
        executor = ToolExecutor(
            build_registry_with_tool(build_add_tool()),
            trace_recorder=TraceRecorder(session),
        )

        result = executor.execute(
            ToolCallRequest(
                name="calculator.add",
                arguments={"a": 1, "b": 2},
                call_id="call-1",
            )
        )

        traces = session.list_tool_traces()
        self.assertTrue(result.success)
        self.assertEqual(len(traces), 1)
        self.assertTrue(traces[0].trace_id)
        self.assertEqual(traces[0].tool_name, "calculator.add")
        self.assertEqual(traces[0].call_id, "call-1")
        self.assertEqual(traces[0].arguments, {"a": 1, "b": 2})
        self.assertTrue(traces[0].success)
        self.assertEqual(traces[0].result, {"result": 3})
        self.assertIsNone(traces[0].error)
        self.assertEqual(traces[0].duration_ms, result.duration_ms)
        self.assertIsNone(traces[0].token_usage)

    def test_execute_records_not_found_trace(self):
        session = SessionState(session_id="session-1")
        executor = ToolExecutor(ToolRegistry(), trace_recorder=TraceRecorder(session))

        result = executor.execute(
            ToolCallRequest(
                name="missing.tool",
                arguments={"query": "hello"},
                call_id="call-missing",
            )
        )

        trace = session.list_tool_traces()[0]
        self.assertFalse(result.success)
        self.assertFalse(trace.success)
        self.assertEqual(trace.tool_name, "missing.tool")
        self.assertEqual(trace.call_id, "call-missing")
        self.assertIsNone(trace.result)
        self.assertEqual(trace.error["type"], "ToolNotFoundError")

    def test_execute_records_validation_error_trace(self):
        session = SessionState(session_id="session-1")
        executor = ToolExecutor(
            build_registry_with_tool(build_add_tool()),
            trace_recorder=TraceRecorder(session),
        )

        result = executor.execute(
            ToolCallRequest(name="calculator.add", arguments={"a": 1})
        )

        trace = session.list_tool_traces()[0]
        self.assertFalse(result.success)
        self.assertFalse(trace.success)
        self.assertEqual(trace.error["type"], "ToolValidationError")
        self.assertIn("Missing required arguments", trace.error["message"])

    def test_execute_records_tool_exception_trace(self):
        def fail(_arguments):
            raise ValueError("boom")

        session = SessionState(session_id="session-1")
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
        executor = ToolExecutor(registry, trace_recorder=TraceRecorder(session))

        result = executor.execute(ToolCallRequest(name="debug.fail", arguments={}))

        trace = session.list_tool_traces()[0]
        self.assertFalse(result.success)
        self.assertFalse(trace.success)
        self.assertEqual(trace.error["type"], "ToolExecutionError")
        self.assertIn("boom", trace.error["message"])

    def test_execute_records_non_dict_return_trace(self):
        session = SessionState(session_id="session-1")
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
        executor = ToolExecutor(registry, trace_recorder=TraceRecorder(session))

        result = executor.execute(
            ToolCallRequest(name="debug.invalid_return", arguments={})
        )

        trace = session.list_tool_traces()[0]
        self.assertFalse(result.success)
        self.assertFalse(trace.success)
        self.assertEqual(trace.error["type"], "ToolExecutionError")
        self.assertIn("must return a dict", trace.error["message"])


if __name__ == "__main__":
    unittest.main()

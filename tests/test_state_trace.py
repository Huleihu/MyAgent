"""
本文件负责验证全局工具调用 Trace 数据模型的字段契约。
本文件不测试工具执行流程，也不测试 RAG 专用评估 Trace。
"""

import unittest

from my_agent.state.trace import ToolTraceRecord


class StateTraceTest(unittest.TestCase):
    def test_tool_trace_record_keeps_success_call_details(self):
        trace = ToolTraceRecord(
            trace_id="trace-1",
            tool_name="retrieval.search",
            call_id="call-1",
            arguments={"query": "Agentic RAG", "top_k": 3},
            success=True,
            result={"chunks": []},
            error=None,
            duration_ms=12.5,
            token_usage={"prompt_tokens": 10, "completion_tokens": 0},
        )

        self.assertEqual(trace.trace_id, "trace-1")
        self.assertEqual(trace.tool_name, "retrieval.search")
        self.assertEqual(trace.call_id, "call-1")
        self.assertEqual(trace.arguments["query"], "Agentic RAG")
        self.assertTrue(trace.success)
        self.assertEqual(trace.result, {"chunks": []})
        self.assertIsNone(trace.error)
        self.assertEqual(trace.duration_ms, 12.5)
        self.assertEqual(trace.token_usage["prompt_tokens"], 10)

    def test_tool_trace_record_keeps_failure_call_details(self):
        trace = ToolTraceRecord(
            trace_id="trace-2",
            tool_name="calculator.add",
            call_id=None,
            arguments={"a": 1},
            success=False,
            result=None,
            error={
                "type": "ToolValidationError",
                "message": "Missing required arguments: b",
            },
            duration_ms=0.8,
        )

        self.assertFalse(trace.success)
        self.assertIsNone(trace.result)
        self.assertEqual(trace.error["type"], "ToolValidationError")
        self.assertIsNone(trace.call_id)

    def test_tool_trace_record_rejects_negative_duration(self):
        with self.assertRaises(ValueError):
            ToolTraceRecord(
                trace_id="trace-1",
                tool_name="retrieval.search",
                call_id="call-1",
                arguments={},
                success=True,
                result={},
                error=None,
                duration_ms=-1,
            )

    def test_tool_trace_record_requires_dict_fields_or_none(self):
        with self.assertRaises(ValueError):
            ToolTraceRecord(
                trace_id="trace-1",
                tool_name="retrieval.search",
                call_id="call-1",
                arguments=[],
                success=True,
                result={},
                error=None,
                duration_ms=1,
            )

        with self.assertRaises(ValueError):
            ToolTraceRecord(
                trace_id="trace-2",
                tool_name="retrieval.search",
                call_id="call-2",
                arguments={},
                success=False,
                result=None,
                error="boom",
                duration_ms=1,
            )


if __name__ == "__main__":
    unittest.main()

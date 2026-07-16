"""
本文件负责验证可恢复运行状态及执行游标的序列化契约。
本文件不测试 SQLite 持久化或 Runtime 调度。
"""

import unittest

from my_agent.state.run_state import (
    ExecutionCursor,
    PendingToolCall,
    RunState,
    RunStatus,
)
from my_agent.state.session import SessionMessage
from my_agent.state.trace import ToolTraceRecord


class RunStateTest(unittest.TestCase):
    def test_pending_tool_call_rejects_non_json_native_arguments(self):
        for arguments in ({"items": (1, 2)}, {7: "integer-key"}):
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    PendingToolCall(
                        tool_name="calculator.add",
                        arguments=arguments,
                        call_id="call-1",
                    )

    def test_round_trip_preserves_recoverable_runtime_data(self):
        state = RunState(
            run_id="run-1",
            session_id="session-1",
            workflow_id="workflow-1",
            status=RunStatus.RUNNING,
            user_input="计算 1 + 2",
            messages=[SessionMessage(role="user", content="计算 1 + 2")],
            tool_traces=[
                ToolTraceRecord(
                    trace_id="trace-1",
                    tool_name="calculator.add",
                    call_id="call-1",
                    arguments={"a": 1, "b": 2},
                    success=True,
                    result={"result": 3},
                    error=None,
                    duration_ms=1.0,
                )
            ],
            variables={"last_message": "3"},
            node_outputs={"begin": {"user_input": "计算 1 + 2"}},
            node_traces=[],
            cursor=ExecutionCursor(
                next_node_id="agent",
                completed_node_ids=["begin"],
                agent_round_index=1,
                agent_phase="tool_pending",
            ),
            pending_tool_call=PendingToolCall(
                tool_name="calculator.add",
                arguments={"a": 1, "b": 2},
                call_id="call-1",
            ),
        )

        restored = RunState.from_dict(state.to_dict())

        self.assertEqual(restored, state)
        self.assertEqual(restored.cursor.completed_node_ids, ["begin"])
        self.assertEqual(restored.pending_tool_call.call_id, "call-1")


if __name__ == "__main__":
    unittest.main()

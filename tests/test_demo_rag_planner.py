"""
本文件负责验证确定性 DemoRagPlanner 用 observation 的 call_id 精确关联工具 Trace。
本文件不测试真实模型、检索排序或 HTTP 响应序列化。
"""

import unittest

from my_agent.state.session import SessionState
from my_agent.state.trace import ToolTraceRecord
from my_agent.web.demo_runtime import DemoRagPlanner


class DemoRagPlannerTest(unittest.TestCase):
    def test_observation_uses_matching_call_id_instead_of_latest_trace(self):
        session = SessionState(session_id="planner-session")
        session.add_tool_trace(
            ToolTraceRecord(
                trace_id="target-trace",
                tool_name="retrieval.search",
                call_id="target-call",
                arguments={"query": "目标问题"},
                success=True,
                result={"chunks": [{"content": "目标检索内容"}]},
                error=None,
                duration_ms=1.0,
            )
        )
        session.add_tool_trace(
            ToolTraceRecord(
                trace_id="later-trace",
                tool_name="retrieval.search",
                call_id="later-call",
                arguments={"query": "其他问题"},
                success=True,
                result={"chunks": [{"content": "不应使用的最新内容"}]},
                error=None,
                duration_ms=1.0,
            )
        )
        session.add_message(
            "assistant",
            "工具 observation",
            metadata={
                "message_type": "tool_observation",
                "tool_name": "retrieval.search",
                "call_id": "target-call",
                "success": True,
            },
        )

        action = DemoRagPlanner().plan("目标问题", session)

        self.assertEqual(action.answer, "目标检索内容")


if __name__ == "__main__":
    unittest.main()

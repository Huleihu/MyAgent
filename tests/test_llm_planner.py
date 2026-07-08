"""
本文件负责验证 LLMPlanner 把模型响应解析为 AgentAction。
本文件不测试真实模型 SDK，也不测试工具执行逻辑。
"""

import unittest

from my_agent.agent_loop.llm_planner import LLMPlanner
from my_agent.agent_loop.planner import FinalAnswerAction, ToolAction
from my_agent.llm.fake import FakeModelClient
from my_agent.state.session import SessionState
from my_agent.tools.schema import ToolDefinition


class StructuralModelClient:
    """用于验证 LLMPlanner 依赖结构化协议，而不是继承关系。"""

    def __init__(self):
        self.chat_calls = []

    def chat(self, messages, tool_definitions):
        self.chat_calls.append(
            {
                "messages": messages,
                "tool_definitions": tool_definitions,
            }
        )
        return {"type": "final_answer", "answer": "结构化客户端回答"}


def build_tool_definition():
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


class LLMPlannerTest(unittest.TestCase):
    def test_plan_converts_model_tool_call_to_tool_action(self):
        session = SessionState(session_id="session-1")
        session.add_message(role="user", content="计算 1 + 2")
        model_client = FakeModelClient(
            responses=[
                {
                    "type": "tool_call",
                    "tool_name": "calculator.add",
                    "arguments": {"a": 1, "b": 2},
                    "call_id": "model-call-1",
                }
            ]
        )
        planner = LLMPlanner(
            model_client=model_client,
            tool_definitions=[build_tool_definition()],
        )

        action = planner.plan("计算 1 + 2", session)

        self.assertIsInstance(action, ToolAction)
        self.assertEqual(action.tool_name, "calculator.add")
        self.assertEqual(action.arguments, {"a": 1, "b": 2})
        self.assertEqual(action.call_id, "model-call-1")

    def test_plan_converts_model_final_answer_to_final_answer_action(self):
        session = SessionState(session_id="session-1")
        session.add_message(role="user", content="你好")
        model_client = FakeModelClient(
            responses=[
                {
                    "type": "final_answer",
                    "answer": "你好，我可以帮你调用工具。",
                }
            ]
        )
        planner = LLMPlanner(
            model_client=model_client,
            tool_definitions=[build_tool_definition()],
        )

        action = planner.plan("你好", session)

        self.assertIsInstance(action, FinalAnswerAction)
        self.assertEqual(action.answer, "你好，我可以帮你调用工具。")

    def test_plan_accepts_structural_model_client_without_inheritance(self):
        session = SessionState(session_id="session-1")
        session.add_message(role="user", content="你好")
        model_client = StructuralModelClient()
        planner = LLMPlanner(
            model_client=model_client,
            tool_definitions=[build_tool_definition()],
        )

        action = planner.plan("你好", session)

        self.assertIsInstance(action, FinalAnswerAction)
        self.assertEqual(action.answer, "结构化客户端回答")
        self.assertEqual(len(model_client.chat_calls), 1)

    def test_plan_passes_session_messages_and_tool_definitions_to_model(self):
        session = SessionState(session_id="session-1")
        session.add_message(
            role="assistant",
            content="工具 calculator.add 执行成功",
            metadata={"message_type": "tool_observation"},
        )
        model_client = FakeModelClient(
            responses=[{"type": "final_answer", "answer": "已完成"}]
        )
        planner = LLMPlanner(
            model_client=model_client,
            tool_definitions=[build_tool_definition()],
        )

        planner.plan("继续", session)

        call = model_client.chat_calls[0]
        self.assertEqual(call["messages"][0]["role"], "assistant")
        self.assertEqual(call["messages"][0]["metadata"]["message_type"], "tool_observation")
        self.assertEqual(call["tool_definitions"][0]["name"], "calculator.add")
        self.assertEqual(call["tool_definitions"][0]["tags"], ["math"])

    def test_plan_rejects_invalid_model_response(self):
        session = SessionState(session_id="session-1")
        model_client = FakeModelClient(responses=[{"type": "unknown"}])
        planner = LLMPlanner(
            model_client=model_client,
            tool_definitions=[build_tool_definition()],
        )

        with self.assertRaises(ValueError):
            planner.plan("你好", session)

    def test_plan_rejects_invalid_inputs(self):
        model_client = FakeModelClient(
            responses=[{"type": "final_answer", "answer": "不会执行"}]
        )
        planner = LLMPlanner(
            model_client=model_client,
            tool_definitions=[build_tool_definition()],
        )

        with self.assertRaises(ValueError):
            planner.plan("", SessionState(session_id="session-1"))

        with self.assertRaises(TypeError):
            planner.plan("你好", {"session_id": "session-1"})


if __name__ == "__main__":
    unittest.main()

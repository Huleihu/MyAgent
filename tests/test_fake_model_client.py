"""
本文件负责验证 FakeModelClient 的离线模型响应行为。
本文件不测试 AgentAction 解析，也不依赖真实模型服务。
"""

import unittest

from my_agent.llm.fake import FakeModelClient


class FakeModelClientTest(unittest.TestCase):
    def test_chat_returns_preset_response_and_records_request(self):
        client = FakeModelClient(
            responses=[
                {
                    "type": "final_answer",
                    "answer": "这是模型回答",
                }
            ]
        )
        messages = [{"role": "user", "content": "你好"}]
        tool_definitions = [{"name": "calculator.add"}]

        response = client.chat(messages=messages, tool_definitions=tool_definitions)

        self.assertEqual(response["answer"], "这是模型回答")
        self.assertEqual(client.chat_calls[0]["messages"], messages)
        self.assertEqual(client.chat_calls[0]["tool_definitions"], tool_definitions)

    def test_chat_returns_responses_in_order(self):
        client = FakeModelClient(
            responses=[
                {"type": "final_answer", "answer": "第一次"},
                {"type": "final_answer", "answer": "第二次"},
            ]
        )

        first = client.chat(messages=[], tool_definitions=[])
        second = client.chat(messages=[], tool_definitions=[])

        self.assertEqual(first["answer"], "第一次")
        self.assertEqual(second["answer"], "第二次")

    def test_chat_rejects_invalid_inputs(self):
        client = FakeModelClient(responses=[{"type": "final_answer", "answer": "ok"}])

        with self.assertRaises(ValueError):
            client.chat(messages={"role": "user"}, tool_definitions=[])

        with self.assertRaises(ValueError):
            client.chat(messages=[], tool_definitions={"name": "tool"})

    def test_chat_raises_when_no_response_remains(self):
        client = FakeModelClient(responses=[])

        with self.assertRaises(ValueError):
            client.chat(messages=[], tool_definitions=[])


if __name__ == "__main__":
    unittest.main()

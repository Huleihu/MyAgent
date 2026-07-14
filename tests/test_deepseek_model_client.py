"""本文件负责验证 DeepSeek 适配器的请求转换、响应规范化与安全失败行为。"""

import unittest
from types import SimpleNamespace

from my_agent.core.errors import ModelResponseError
from my_agent.llm.config import ModelConfig
from my_agent.llm.deepseek import DeepSeekModelClient


def completion(message):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeClient:
    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))


def tool_definitions():
    return [{"name": "retrieval.search", "description": "search", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}, "tags": ["rag"]}]


class DeepSeekModelClientTest(unittest.TestCase):
    def build_client(self, responses):
        self.sdk_client = FakeClient(responses)
        return DeepSeekModelClient(ModelConfig(provider="deepseek", model_name="deepseek-v4-flash", api_key="secret", base_url="https://api.deepseek.com"), sdk_client=self.sdk_client)

    def test_converts_text_response_and_disables_thinking(self):
        client = self.build_client([completion(SimpleNamespace(content="answer", tool_calls=None))])
        self.assertEqual(client.chat([{"role": "user", "content": "hello", "metadata": {}}], tool_definitions()), {"type": "final_answer", "answer": "answer"})
        request = self.sdk_client.chat.completions.calls[0]
        self.assertEqual(request["tools"][0]["function"]["name"], "retrieval_search")
        self.assertEqual(request["extra_body"], {"thinking": {"type": "disabled"}})
        self.assertNotIn("tags", request["tools"][0]["function"])

    def test_converts_tool_call_and_rebuilds_observation_history(self):
        tool_call = SimpleNamespace(id="call-1", function=SimpleNamespace(name="retrieval_search", arguments='{"query":"中文"}'))
        client = self.build_client([completion(SimpleNamespace(content=None, tool_calls=[tool_call]))])
        response = client.chat([{"role": "user", "content": "question", "metadata": {}}, {"role": "assistant", "content": "tool result", "metadata": {"message_type": "tool_observation", "tool_name": "retrieval.search", "call_id": "call-1", "arguments": {"query": "中文"}, "success": True}}], tool_definitions())
        self.assertEqual(response["tool_name"], "retrieval.search")
        request_messages = self.sdk_client.chat.completions.calls[0]["messages"]
        self.assertEqual([message["role"] for message in request_messages], ["user", "assistant", "tool"])
        self.assertEqual(request_messages[1]["tool_calls"][0]["function"]["name"], "retrieval_search")
        self.assertEqual(request_messages[2]["content"], "tool result")

    def test_rejects_multiple_or_unknown_tool_calls(self):
        first = SimpleNamespace(id="call-1", function=SimpleNamespace(name="retrieval_search", arguments="{}"))
        second = SimpleNamespace(id="call-2", function=SimpleNamespace(name="retrieval_search", arguments="{}"))
        with self.assertRaises(ModelResponseError):
            self.build_client([completion(SimpleNamespace(content=None, tool_calls=[first, second]))]).chat([], tool_definitions())
        unknown = SimpleNamespace(id="call-1", function=SimpleNamespace(name="unknown", arguments="{}"))
        with self.assertRaises(ModelResponseError):
            self.build_client([completion(SimpleNamespace(content=None, tool_calls=[unknown]))]).chat([], tool_definitions())

    def test_hides_provider_error_details(self):
        authentication_error = type("AuthenticationError", (Exception,), {}) ("secret request")
        with self.assertRaisesRegex(Exception, "鉴权失败") as captured:
            self.build_client([authentication_error]).chat([], tool_definitions())
        self.assertNotIn("secret request", str(captured.exception))

    def test_rejects_non_object_tool_arguments(self):
        tool_call = SimpleNamespace(id="call-1", function=SimpleNamespace(name="retrieval_search", arguments="[]"))
        with self.assertRaises(ModelResponseError):
            self.build_client([completion(SimpleNamespace(content=None, tool_calls=[tool_call]))]).chat([], tool_definitions())

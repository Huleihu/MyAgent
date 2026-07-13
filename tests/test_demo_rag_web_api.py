"""
本文件负责验证默认 Web Demo 的确定性 RAG 工具调用、Citation 投影与会话隔离。
本文件不依赖真实模型、外部向量库或真实用户知识库。
"""

import unittest
import warnings

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
    category=UserWarning,
)
from starlette.testclient import TestClient

from my_agent.web.app import create_app


class DemoRagWebApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def create_session(self) -> str:
        response = self.client.post("/sessions")
        self.assertEqual(response.status_code, 201)
        return response.json()["session_id"]

    def send_message(self, session_id: str, user_input: str) -> dict:
        response = self.client.post(
            f"/sessions/{session_id}/messages",
            json={"user_input": user_input},
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_retrieval_query_returns_current_turn_citations_and_tool_trace(self):
        session_id = self.create_session()
        user_input = "Agentic RAG 如何把检索作为工具调用？"

        response = self.send_message(session_id, user_input)

        self.assertEqual(response["session_id"], session_id)
        self.assertEqual(len(response["tool_traces"]), 1)
        trace = response["tool_traces"][0]
        self.assertEqual(trace["tool_name"], "retrieval.search")
        self.assertEqual(trace["arguments"], {"query": user_input, "top_k": 3})
        self.assertTrue(trace["success"])
        self.assertEqual(trace["result"]["retrieval_trace"]["query"], user_input)
        self.assertEqual(trace["result"]["retrieval_trace"]["retrieved_count"], 3)
        self.assertNotIn(
            "content",
            trace["result"]["retrieval_trace"]["retrieved_chunks"][0],
        )
        self.assertTrue(response["citations"])
        self.assertEqual(response["citations"], trace["result"]["citations"])
        self.assertNotIn("演示回答（", response["output_text"])
        self.assertIn(trace["result"]["chunks"][0]["content"], response["output_text"])

    def test_no_match_returns_empty_citations_and_stable_answer(self):
        session_id = self.create_session()

        response = self.send_message(session_id, "zzzxqv_unique_no_match_98765")

        self.assertEqual(response["citations"], [])
        self.assertEqual(
            response["output_text"],
            "演示知识库中未找到与该问题相关的内容。",
        )
        self.assertEqual(len(response["tool_traces"]), 1)
        self.assertTrue(response["tool_traces"][0]["success"])
        retrieval_trace = response["tool_traces"][0]["result"]["retrieval_trace"]
        self.assertEqual(retrieval_trace["query"], "zzzxqv_unique_no_match_98765")
        self.assertEqual(retrieval_trace["retrieved_chunks"], [])
        self.assertEqual(retrieval_trace["reranked_chunks"], [])
        self.assertEqual(retrieval_trace["citations"], [])

    def test_second_turn_uses_only_its_own_tool_trace_and_citations(self):
        session_id = self.create_session()
        first_response = self.send_message(
            session_id,
            "Agentic RAG 如何把检索作为工具调用？",
        )
        second_response = self.send_message(
            session_id,
            "Runtime 与 Agent Loop 如何协作？",
        )

        self.assertEqual(len(first_response["tool_traces"]), 1)
        self.assertEqual(len(second_response["tool_traces"]), 1)
        self.assertEqual(
            second_response["tool_traces"][0]["arguments"]["query"],
            "Runtime 与 Agent Loop 如何协作？",
        )
        self.assertEqual(
            first_response["tool_traces"][0]["result"]["retrieval_trace"]["query"],
            "Agentic RAG 如何把检索作为工具调用？",
        )
        self.assertEqual(
            second_response["tool_traces"][0]["result"]["retrieval_trace"]["query"],
            "Runtime 与 Agent Loop 如何协作？",
        )
        self.assertNotEqual(
            first_response["tool_traces"][0]["result"]["retrieval_trace"]["reranked_chunks"],
            second_response["tool_traces"][0]["result"]["retrieval_trace"]["reranked_chunks"],
        )
        self.assertNotEqual(first_response["citations"], second_response["citations"])
        self.assertEqual(
            second_response["citations"],
            second_response["tool_traces"][0]["result"]["citations"],
        )

    def test_two_sessions_keep_messages_traces_and_citations_isolated(self):
        first_session_id = self.create_session()
        second_session_id = self.create_session()

        first_response = self.send_message(
            first_session_id,
            "Web Session、Trace 与 Citation 有什么关系？",
        )
        second_response = self.send_message(
            second_session_id,
            "Agentic RAG 如何把检索作为工具调用？",
        )

        self.assertEqual(len(first_response["tool_traces"]), 1)
        self.assertEqual(len(second_response["tool_traces"]), 1)
        self.assertNotEqual(first_response["citations"], second_response["citations"])
        self.assertEqual(first_response["session_id"], first_session_id)
        self.assertEqual(second_response["session_id"], second_session_id)


if __name__ == "__main__":
    unittest.main()

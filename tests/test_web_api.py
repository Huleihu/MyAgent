"""
本文件负责验证最小 Web API 的会话隔离、错误契约和回合 Trace 响应。
本文件不测试真实模型、持久化会话或跨进程并发。
"""

import unittest
import warnings

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated.*",
    category=UserWarning,
)
from starlette.testclient import TestClient

from my_agent.runtime.context import RuntimeContext
from my_agent.runtime.conversation import ConversationTurnResult
from my_agent.runtime.trace import NodeExecutionRecord
from my_agent.state.session import SessionState
from my_agent.state.trace import ToolTraceRecord
from my_agent.web.app import _extract_turn_citations
from my_agent.web.session_store import InMemorySessionStore
from my_agent.state.sqlite_checkpoint_store import SQLiteCheckpointStore
from my_agent.state.checkpoint import Checkpoint
from my_agent.state.run_state import ExecutionCursor, RunState, RunStatus
from my_agent.state.trace import ToolTraceRecord
from my_agent.state.session import SessionMessage
from pathlib import Path
from uuid import uuid4
from tests.test_runtime_checkpoint_resume import HistoryPlanner, build_runtime


class FakeConversationRuntime:
    """用独立内存历史模拟可注入的会话 Runtime。"""

    def __init__(self, session_state: SessionState) -> None:
        self.session_id = session_state.session_id
        self._session_state = session_state
        self._history: list[str] = []

    def chat(self, user_input: str) -> ConversationTurnResult:
        self._session_state.add_message("user", user_input)
        self._history.append(user_input)
        turn_index = sum(
            message.role == "user"
            for message in self._session_state.list_messages()
        )
        context = RuntimeContext(
            user_input=user_input,
            session_state=self._session_state,
        )
        trace = NodeExecutionRecord(
            node_id="message",
            node_type="message",
            inputs={"content": user_input},
            output={"content": user_input},
            success=True,
            error=None,
            duration_ms=1.0,
        )
        return ConversationTurnResult(
            output_text=f"第{turn_index}轮：{user_input}",
            runtime_context=context,
            node_traces=(trace,),
            tool_traces=(),
        )


class FailingConversationRuntime:
    """模拟 Runtime 执行异常，验证 HTTP 层不会泄漏内部细节。"""

    def chat(self, user_input: str) -> ConversationTurnResult:
        raise RuntimeError("内部执行细节")


class WebApiTest(unittest.TestCase):
    def setUp(self) -> None:
        from my_agent.web.app import create_app

        self.created_runtimes: list[FakeConversationRuntime] = []

        def runtime_factory(session_state: SessionState) -> FakeConversationRuntime:
            runtime = FakeConversationRuntime(session_state)
            self.created_runtimes.append(runtime)
            return runtime

        self.client = TestClient(create_app(runtime_factory=runtime_factory))

    def create_session(self) -> str:
        response = self.client.post("/sessions")
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertIsInstance(body["session_id"], str)
        self.assertTrue(body["session_id"])
        return body["session_id"]

    def test_health_returns_ready_status(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_each_message_creates_a_runtime_from_its_session_state(self):
        first_session_id = self.create_session()
        second_session_id = self.create_session()
        self.client.post(
            f"/sessions/{first_session_id}/messages",
            json={"user_input": "第一条"},
        )
        self.client.post(
            f"/sessions/{second_session_id}/messages",
            json={"user_input": "第二条"},
        )

        self.assertEqual(len(self.created_runtimes), 2)
        self.assertIsNot(self.created_runtimes[0], self.created_runtimes[1])

    def test_unknown_session_returns_not_found(self):
        response = self.client.post(
            "/sessions/unknown/messages",
            json={"user_input": "问题"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "session not found"})

    def test_invalid_message_body_returns_422(self):
        session_id = self.create_session()

        for payload in ({}, {"user_input": " "}, {"user_input": 1}):
            with self.subTest(payload=payload):
                response = self.client.post(
                    f"/sessions/{session_id}/messages",
                    json=payload,
                )
                self.assertEqual(response.status_code, 422)

    def test_same_session_preserves_history_and_returns_current_turn_traces(self):
        session_id = self.create_session()

        first_response = self.client.post(
            f"/sessions/{session_id}/messages",
            json={"user_input": "第一条"},
        )
        second_response = self.client.post(
            f"/sessions/{session_id}/messages",
            json={"user_input": "第二条"},
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(first_response.json()["output_text"], "第1轮：第一条")
        self.assertEqual(second_response.json()["output_text"], "第2轮：第二条")
        self.assertEqual(first_response.json()["citations"], [])
        self.assertEqual(second_response.json()["citations"], [])
        self.assertEqual(
            second_response.json()["node_traces"],
            [
                {
                    "node_id": "message",
                    "node_type": "message",
                    "inputs": {"content": "第二条"},
                    "output": {"content": "第二条"},
                    "success": True,
                    "error": None,
                    "duration_ms": 1.0,
                }
            ],
        )
        self.assertEqual(second_response.json()["tool_traces"], [])

    def test_two_sessions_do_not_share_runtime_history(self):
        first_session_id = self.create_session()
        second_session_id = self.create_session()

        first_response = self.client.post(
            f"/sessions/{first_session_id}/messages",
            json={"user_input": "第一会话"},
        )
        second_response = self.client.post(
            f"/sessions/{second_session_id}/messages",
            json={"user_input": "第二会话"},
        )

        self.assertEqual(first_response.json()["output_text"], "第1轮：第一会话")
        self.assertEqual(second_response.json()["output_text"], "第1轮：第二会话")

    def test_runtime_exception_returns_stable_internal_error(self):
        from my_agent.web.app import create_app

        client = TestClient(
            create_app(runtime_factory=lambda session_state: FailingConversationRuntime())
        )
        session_id = client.post("/sessions").json()["session_id"]

        with self.assertLogs("my_agent.web.app", level="ERROR"):
            response = client.post(
                f"/sessions/{session_id}/messages",
                json={"user_input": "触发失败"},
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.json(),
            {
                "error": {
                    "code": "runtime_execution_failed",
                    "message": "Runtime execution failed",
                }
            },
        )

    def test_extract_turn_citations_deduplicates_retrieval_results_and_copies_items(self):
        first_citation = {"doc_id": "doc-1", "chunk_id": "doc-1:0", "title": "第一篇"}
        duplicate_citation = {"doc_id": "doc-1", "chunk_id": "doc-1:0", "title": "重复"}
        second_citation = {"doc_id": "doc-2", "chunk_id": "doc-2:0", "title": "第二篇"}
        traces = (
            ToolTraceRecord(
                trace_id="trace-1",
                tool_name="retrieval.search",
                call_id="call-1",
                arguments={"query": "问题"},
                success=True,
                result={"citations": [first_citation, duplicate_citation]},
                error=None,
                duration_ms=1.0,
            ),
            ToolTraceRecord(
                trace_id="trace-2",
                tool_name="retrieval.search",
                call_id="call-2",
                arguments={"query": "问题"},
                success=True,
                result={"citations": [second_citation]},
                error=None,
                duration_ms=1.0,
            ),
        )

        citations = _extract_turn_citations(traces)
        citations[0]["title"] = "已修改副本"

        self.assertEqual(len(citations), 2)
        self.assertEqual(
            citations[1:],
            [second_citation],
        )
        self.assertEqual(first_citation["title"], "第一篇")
        self.assertEqual(citations[0]["doc_id"], "doc-1")

    def test_web_resume_final_answer_written_preserves_session_for_next_message(self):
        path = Path.cwd() / f"web-resume-{uuid4().hex}.db"
        store = SQLiteCheckpointStore(path)
        session_store = InMemorySessionStore()
        counts = {"tool_a": 0, "tool_b": 0}
        planner = HistoryPlanner(counts)
        runtime_factory = lambda session: build_runtime(session, store, planner, counts)
        app = __import__("my_agent.web.app", fromlist=["create_app"]).create_app(runtime_factory, session_store, store)
        client = TestClient(app)
        trace = ToolTraceRecord("trace-a", "tool_a", "call-a", {}, True, {"tool": "tool_a"}, None, 1.0)
        state = RunState(
            run_id="interrupted-run", session_id="recovered-session", workflow_id="checkpoint-test",
            status=RunStatus.RUNNING, user_input="第一轮",
            messages=[SessionMessage("user", "第一轮"), SessionMessage("assistant", "工具 tool_a 执行成功", {"message_type":"tool_observation", "tool_name":"tool_a", "call_id":"call-a"}), SessionMessage("assistant", "已完成")],
            tool_traces=[trace], node_outputs={"begin":{"user_input":"第一轮"}},
            cursor=ExecutionCursor("agent", ["begin"], 2, "final_answer_written"),
        )
        store.save(Checkpoint.create(state))
        response = client.post("/runs/interrupted-run/resume")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(planner.calls, 0)
        handle = session_store.get("recovered-session")
        self.assertIsNotNone(handle)
        restored_session = handle.session_state
        self.assertEqual([item.content for item in restored_session.list_messages()], ["第一轮", "工具 tool_a 执行成功", "已完成"])
        next_response = client.post("/sessions/recovered-session/messages", json={"user_input":"第二轮"})
        self.assertEqual(next_response.status_code, 200)
        self.assertIs(session_store.get("recovered-session").session_state, restored_session)
        self.assertEqual(planner.calls, 2)
        self.assertEqual(store.get_latest("interrupted-run").run_state.status, RunStatus.COMPLETED)
        store.close()
        if path.exists(): path.unlink()


if __name__ == "__main__":
    unittest.main()

"""本文件负责验证持久化 Runtime Checkpoint 的 Web 装配、恢复与错误边界。"""

import os
import unittest
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from starlette.testclient import TestClient

from my_agent.runtime.conversation import RunExecutionFailedError
from my_agent.runtime.conversation import ConversationRuntime
from my_agent.agent_loop.planner import FinalAnswerAction, Planner, ToolAction
from my_agent.state.checkpoint import Checkpoint
from my_agent.state.checkpoint_recorder import CheckpointRecorder
from my_agent.state.run_state import ExecutionCursor, RunState, RunStatus
from my_agent.state.session import SessionState
from my_agent.state.sqlite_checkpoint_store import SQLiteCheckpointStore
from my_agent.web.app import create_app
from my_agent.web.session_store import InMemorySessionStore
from tests.test_runtime_checkpoint_resume import HistoryPlanner, StopAfterAPlanner, build_runtime


class CheckpointHardeningTest(unittest.TestCase):
    def setUp(self):
        self.database_path = Path.cwd() / f"checkpoint-hardening-{uuid4().hex}.db"

    def tearDown(self):
        for path in (self.database_path, Path(f"{self.database_path}-wal"), Path(f"{self.database_path}-shm")):
            if path.exists():
                path.unlink()

    def make_state(self, run_id="run-1", **changes):
        values = {
            "run_id": run_id,
            "session_id": "session-1",
            "workflow_id": "workflow-1",
            "status": RunStatus.RUNNING,
            "user_input": "hello",
            "cursor": ExecutionCursor(next_node_id="begin"),
        }
        values.update(changes)
        return RunState(**values)

    def test_sqlite_persists_recorder_metadata_and_creates_parent_directory(self):
        store = SQLiteCheckpointStore(self.database_path)
        state = self.make_state()
        checkpoint = CheckpointRecorder(SessionState("session-1"), state, store).record({"reason": "before_tool_execution"})
        store.close()

        restored_store = SQLiteCheckpointStore(self.database_path)
        restored = restored_store.get_latest("run-1")
        self.assertTrue(self.database_path.exists())
        self.assertEqual(restored.metadata, {"reason": "before_tool_execution"})
        self.assertEqual(checkpoint.metadata, {"reason": "before_tool_execution"})
        restored_store.close()

    def test_run_state_rejects_negative_tool_trace_start_index(self):
        with self.assertRaises(ValueError):
            self.make_state(tool_trace_start_index=-1)

    def test_old_run_state_payload_defaults_trace_start_index_to_zero(self):
        payload = self.make_state().to_dict()
        payload.pop("tool_trace_start_index")
        self.assertEqual(RunState.from_dict(payload).tool_trace_start_index, 0)

    def test_get_run_returns_sanitized_summary_and_completed_resume_is_conflict(self):
        store = SQLiteCheckpointStore(self.database_path)
        state = self.make_state(status=RunStatus.COMPLETED, error={"type": "RuntimeError", "message": "secret internal detail"})
        store.save(Checkpoint.create(state))
        client = TestClient(create_app(session_store=InMemorySessionStore(), checkpoint_store=store))

        summary = client.get("/runs/run-1")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()["status"], "completed")
        self.assertEqual(summary.json()["error"], {"code": "runtime_failed", "message": "Runtime execution failed"})
        self.assertNotIn("secret internal detail", str(summary.json()))
        resume = client.post("/runs/run-1/resume")
        self.assertEqual(resume.status_code, 409)
        self.assertEqual(resume.json()["error"]["code"], "run_already_completed")
        store.close()

    def test_completed_resume_rejects_before_runtime_factory(self):
        store = SQLiteCheckpointStore(self.database_path)
        store.save(Checkpoint.create(self.make_state(status=RunStatus.COMPLETED)))
        client = TestClient(create_app(lambda _session: (_ for _ in ()).throw(RuntimeError("factory must not run")), InMemorySessionStore(), store))
        response = client.post("/runs/run-1/resume")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "run_already_completed")
        store.close()

    def test_old_sqlite_table_migrates_metadata_column_idempotently(self):
        import sqlite3
        connection = sqlite3.connect(self.database_path)
        connection.execute("CREATE TABLE checkpoints (checkpoint_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, sequence_no INTEGER NOT NULL, schema_version INTEGER NOT NULL, created_at_utc TEXT NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL, UNIQUE(run_id, sequence_no))")
        connection.commit(); connection.close()
        first = SQLiteCheckpointStore(self.database_path)
        first.close()
        second = SQLiteCheckpointStore(self.database_path)
        columns = {row[1] for row in second._connection.execute("PRAGMA table_info(checkpoints)")}
        self.assertIn("metadata_json", columns)
        second.close()

    def test_closed_store_raises_runtime_error(self):
        store = SQLiteCheckpointStore(self.database_path)
        store.close()
        with self.assertRaises(RuntimeError):
            store.get_latest("run-1")

    def test_cursor_none_round_trips_and_resume_does_not_execute_nodes(self):
        state = self.make_state(cursor=ExecutionCursor(next_node_id=None, completed_node_ids=["begin"]))
        restored = RunState.from_dict(state.to_dict())
        self.assertIsNone(restored.cursor.next_node_id)

    def test_bind_failure_after_run_creation_returns_recovery_contract_once(self):
        store = SQLiteCheckpointStore(self.database_path)
        def factory(session):
            runtime = build_runtime(session, store, HistoryPlanner({"tool_a": 0, "tool_b": 0}), {"tool_a": 0, "tool_b": 0})
            runtime._executor.bind_run_state = lambda *_args: (_ for _ in ()).throw(RuntimeError("bind failed"))
            return runtime
        client = TestClient(create_app(factory, InMemorySessionStore(), store))
        session_id = client.post("/sessions").json()["session_id"]
        response = client.post(f"/sessions/{session_id}/messages", json={"user_input": "go"})
        self.assertEqual(response.status_code, 500)
        body = response.json(); self.assertEqual(body["session_id"], session_id); self.assertEqual(body["status"], "failed")
        latest = store.get_latest(body["run_id"])
        self.assertEqual(latest.run_state.status, RunStatus.FAILED)
        self.assertEqual(store._connection.execute("SELECT COUNT(*) FROM checkpoints WHERE run_id = ? AND metadata_json LIKE '%run_failed%'", (body["run_id"],)).fetchone()[0], 1)
        store.close()

    def test_runtime_context_failure_after_run_creation_returns_recovery_contract_once(self):
        store = SQLiteCheckpointStore(self.database_path)
        client = TestClient(create_app(lambda session: build_runtime(session, store, HistoryPlanner({"tool_a": 0, "tool_b": 0}), {"tool_a": 0, "tool_b": 0}), InMemorySessionStore(), store))
        session_id = client.post("/sessions").json()["session_id"]
        with patch("my_agent.runtime.conversation.RuntimeContext", side_effect=RuntimeError("context failed")):
            response = client.post(f"/sessions/{session_id}/messages", json={"user_input": "go"})
        body = response.json(); self.assertEqual(response.status_code, 500); self.assertEqual(body["session_id"], session_id); self.assertEqual(body["status"], "failed")
        self.assertEqual(store.get_latest(body["run_id"]).run_state.status, RunStatus.FAILED)
        self.assertEqual(store._connection.execute("SELECT COUNT(*) FROM checkpoints WHERE run_id = ? AND metadata_json LIKE '%run_failed%'", (body["run_id"],)).fetchone()[0], 1)
        store.close()

    def test_output_contract_failure_never_saves_completed_checkpoint(self):
        store = SQLiteCheckpointStore(self.database_path)
        counts = {"tool_a": 0, "tool_b": 0}
        client = TestClient(create_app(lambda session: build_runtime(session, store, HistoryPlanner(counts), counts), InMemorySessionStore(), store))
        session_id = client.post("/sessions").json()["session_id"]
        with patch.object(ConversationRuntime, "_read_last_message", side_effect=ValueError("last_message missing")):
            response = client.post(f"/sessions/{session_id}/messages", json={"user_input": "go"})
        body = response.json(); self.assertEqual(response.status_code, 500); self.assertEqual(body["status"], "failed")
        self.assertEqual(store.get_latest(body["run_id"]).run_state.status, RunStatus.FAILED)
        self.assertEqual(store._connection.execute("SELECT COUNT(*) FROM checkpoints WHERE run_id = ? AND status = 'completed'", (body["run_id"],)).fetchone()[0], 0)
        self.assertEqual(store._connection.execute("SELECT COUNT(*) FROM checkpoints WHERE run_id = ? AND metadata_json LIKE '%run_failed%'", (body["run_id"],)).fetchone()[0], 1)
        store.close()

    def test_lifespan_closes_owned_store_but_preserves_injected_store(self):
        previous = os.environ.get("MYAGENT_CHECKPOINT_DB_PATH")
        os.environ["MYAGENT_CHECKPOINT_DB_PATH"] = str(self.database_path)
        try:
            owned = create_app()
            with TestClient(owned):
                pass
            with self.assertRaises(RuntimeError):
                owned.state.checkpoint_store.get_latest("run-1")
        finally:
            if previous is None: os.environ.pop("MYAGENT_CHECKPOINT_DB_PATH", None)
            else: os.environ["MYAGENT_CHECKPOINT_DB_PATH"] = previous
        external = SQLiteCheckpointStore(self.database_path)
        with TestClient(create_app(session_store=InMemorySessionStore(), checkpoint_store=external)):
            pass
        self.assertIsNone(external.get_latest("run-1"))
        external.close(); external.close()

    def test_resume_result_filters_prior_run_tool_traces(self):
        class OneToolPlanner(Planner):
            def __init__(self, tool_name, fail_after_tool=False): self.tool_name = tool_name; self.fail_after_tool = fail_after_tool
            def plan(self, _user_input, session):
                if session.list_messages()[-1].role == "user": return ToolAction(self.tool_name, {})
                if self.fail_after_tool: raise RuntimeError("pause after tool")
                return FinalAnswerAction("done")
        counts = {"tool_a": 0, "tool_b": 0}
        store = SQLiteCheckpointStore(self.database_path); session = SessionState("trace-session")
        run_a = build_runtime(session, store, OneToolPlanner("tool_a"), counts).start("run-a")
        self.assertEqual([trace.tool_name for trace in run_a.tool_traces], ["tool_a"])
        with self.assertRaises(RunExecutionFailedError):
            build_runtime(session, store, OneToolPlanner("tool_b", fail_after_tool=True), counts).start("run-b")
        run_b_id = store._connection.execute("SELECT run_id FROM checkpoints WHERE run_id != ? ORDER BY rowid DESC LIMIT 1", (run_a.run_id,)).fetchone()[0]
        persisted = store.get_latest(run_b_id).run_state
        self.assertEqual(persisted.tool_trace_start_index, 1)
        store.close()
        resumed_store = SQLiteCheckpointStore(self.database_path)
        resumed = build_runtime(SessionState("trace-session"), resumed_store, OneToolPlanner("tool_b"), counts).resume(run_b_id)
        self.assertEqual([trace.tool_name for trace in resumed.tool_traces], ["tool_b"])
        self.assertEqual(len(resumed.tool_traces), 1)
        self.assertEqual(resumed_store.get_latest(run_b_id).run_state.tool_trace_start_index, 1)
        resumed_store.close()

    def test_default_web_app_uses_configured_sqlite_path(self):
        previous = os.environ.get("MYAGENT_CHECKPOINT_DB_PATH")
        os.environ["MYAGENT_CHECKPOINT_DB_PATH"] = str(self.database_path)
        try:
            app = create_app()
            self.assertTrue(self.database_path.exists())
            app.state.checkpoint_store.close()
        finally:
            if previous is None:
                os.environ.pop("MYAGENT_CHECKPOINT_DB_PATH", None)
            else:
                os.environ["MYAGENT_CHECKPOINT_DB_PATH"] = previous

    def test_web_cross_app_resume_preserves_session_and_does_not_repeat_saved_tool(self):
        class HistoryAwarePlanner(Planner):
            def plan(self, _user_input, session):
                last_message = session.list_messages()[-1]
                if last_message.metadata.get("message_type") == "tool_observation":
                    return FinalAnswerAction("resumed")
                if last_message.content == "follow-up":
                    answer = "history-seen" if any(item.content == "history-marker" for item in session.list_messages()) else "history-missing"
                    return FinalAnswerAction(answer)
                raise AssertionError("unexpected session history")
        counts = {"tool_a": 0, "tool_b": 0}
        store_a = SQLiteCheckpointStore(self.database_path)
        sessions_a = InMemorySessionStore()
        app_a = create_app(lambda session: build_runtime(session, store_a, StopAfterAPlanner(counts), counts), sessions_a, store_a)
        client_a = TestClient(app_a)
        session_id = client_a.post("/sessions").json()["session_id"]
        failed = client_a.post(f"/sessions/{session_id}/messages", json={"user_input": "history-marker"})
        self.assertEqual(failed.status_code, 500)
        run_id = failed.json()["run_id"]
        self.assertEqual(failed.json()["status"], "failed")
        store_a.close()
        del app_a, client_a, sessions_a

        store_b = SQLiteCheckpointStore(self.database_path)
        sessions_b = InMemorySessionStore()
        app_b = create_app(lambda session: build_runtime(session, store_b, HistoryAwarePlanner(), counts), sessions_b, store_b)
        client_b = TestClient(app_b)
        self.assertEqual(client_b.get(f"/runs/{run_id}").json()["status"], "failed")
        resumed = client_b.post(f"/runs/{run_id}/resume")
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(counts, {"tool_a": 1, "tool_b": 0})
        self.assertEqual(client_b.get(f"/runs/{run_id}").json()["error"], None)
        self.assertEqual(client_b.post(f"/runs/{run_id}/resume").status_code, 409)
        follow_up = client_b.post(f"/sessions/{session_id}/messages", json={"user_input": "follow-up"})
        self.assertEqual(follow_up.status_code, 200)
        self.assertEqual(follow_up.json()["output_text"], "history-seen")
        self.assertIsNotNone(sessions_b.get(session_id))
        store_b.close()


if __name__ == "__main__":
    unittest.main()

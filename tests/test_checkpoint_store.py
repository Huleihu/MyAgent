"""本文件负责验证 CheckpointStore 的内存与 SQLite 持久化行为。"""
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from my_agent.state.checkpoint import Checkpoint
from my_agent.state.checkpoint_store import InMemoryCheckpointStore
from my_agent.state.run_state import ExecutionCursor, RunState, RunStatus
from my_agent.state.sqlite_checkpoint_store import SQLiteCheckpointStore


def build_checkpoint(run_id="run-1"):
    return Checkpoint.create(RunState(run_id=run_id, session_id="session-1", workflow_id="wf", status=RunStatus.RUNNING, user_input="你好", cursor=ExecutionCursor(next_node_id="begin")))


class CheckpointStoreTest(unittest.TestCase):
    def test_in_memory_returns_latest_checkpoint(self):
        store = InMemoryCheckpointStore()
        first, second = build_checkpoint(), build_checkpoint()
        store.save(first); store.save(second)
        self.assertEqual(store.get_latest("run-1").checkpoint_id, second.checkpoint_id)

    def test_sqlite_persists_and_increments_sequence_after_rebuild(self):
        path = Path.cwd() / f"checkpoint-store-{uuid4().hex}.db"
        try:
            first_store = SQLiteCheckpointStore(path)
            first = build_checkpoint(); first_store.save(first)
            first_store.close()
            second_store = SQLiteCheckpointStore(path)
            second = build_checkpoint(); second_store.save(second)
            latest = second_store.get_latest("run-1")
            self.assertEqual(latest.sequence_no, 2)
            self.assertEqual(latest.checkpoint_id, second.checkpoint_id)
            second_store.close()
        finally:
            if path.exists():
                path.unlink()


if __name__ == "__main__":
    unittest.main()

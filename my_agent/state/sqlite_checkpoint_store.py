"""本文件负责以 SQLite 追加保存与读取 Runtime Checkpoint。"""
import json
import sqlite3
from pathlib import Path
from my_agent.state.checkpoint import Checkpoint
from my_agent.state.run_state import RunState

class SQLiteCheckpointStore:
    """SQLite CheckpointStore 实现；序号生成与插入处于同一立即事务。"""
    def __init__(self, database_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(database_path), timeout=5, check_same_thread=False)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA busy_timeout=5000")
        self._connection.execute("CREATE TABLE IF NOT EXISTS checkpoints (checkpoint_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, sequence_no INTEGER NOT NULL, schema_version INTEGER NOT NULL, created_at_utc TEXT NOT NULL, status TEXT NOT NULL, payload_json TEXT NOT NULL, UNIQUE(run_id, sequence_no))")
        self._connection.execute("CREATE INDEX IF NOT EXISTS idx_checkpoints_latest ON checkpoints(run_id, sequence_no DESC)")
        self._connection.commit()
    def save(self, checkpoint: Checkpoint) -> Checkpoint:
        if checkpoint.run_state is None: raise ValueError("checkpoint must contain run_state")
        state = checkpoint.run_state
        cursor = self._connection.cursor(); cursor.execute("BEGIN IMMEDIATE")
        try:
            row = cursor.execute("SELECT COALESCE(MAX(sequence_no), 0) FROM checkpoints WHERE run_id = ?", (state.run_id,)).fetchone()
            saved = checkpoint.with_sequence_no(row[0] + 1)
            cursor.execute("INSERT INTO checkpoints VALUES (?, ?, ?, ?, ?, ?, ?)", (saved.checkpoint_id, state.run_id, saved.sequence_no, saved.schema_version, state.updated_at_utc, state.status.value, json.dumps(state.to_dict(), ensure_ascii=False, sort_keys=True)))
            self._connection.commit(); return saved
        except Exception:
            self._connection.rollback(); raise
    def get_latest(self, run_id: str) -> Checkpoint | None:
        row = self._connection.execute("SELECT checkpoint_id, sequence_no, schema_version, payload_json FROM checkpoints WHERE run_id = ? ORDER BY sequence_no DESC LIMIT 1", (run_id,)).fetchone()
        if row is None: return None
        state = RunState.from_dict(json.loads(row[3]))
        return Checkpoint(row[0], state.session_id, list(state.messages), list(state.tool_traces), {}, state, row[1], row[2])
    def close(self) -> None: self._connection.close()

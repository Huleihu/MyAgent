"""
本文件负责为 Agent 会话创建并保存内存 Checkpoint 快照。
本文件不负责文件持久化、数据库存储或从 Checkpoint 恢复会话。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from my_agent.state.checkpoint import Checkpoint
from my_agent.state.session import SessionState
from my_agent.state.checkpoint_store import CheckpointStore, InMemoryCheckpointStore
from my_agent.state.run_state import RunState


class CheckpointRecorder:
    """基于当前 SessionState 记录内存快照。"""

    def __init__(self, session_state: SessionState, run_state: RunState | None = None, store: CheckpointStore | None = None) -> None:
        if not isinstance(session_state, SessionState):
            raise TypeError("session_state must be a SessionState")

        self._session_state = session_state
        self._checkpoints: list[Checkpoint] = []
        self._run_state = run_state
        self._store = InMemoryCheckpointStore() if store is None else store

    def record(self, metadata: dict[str, Any] | None = None) -> Checkpoint:
        """创建一次会话快照，并返回实际写入的 Checkpoint。"""
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("metadata must be a dict or None")

        checkpoint = Checkpoint.from_session(
            checkpoint_id=str(uuid4()),
            session_state=self._session_state,
            metadata={} if metadata is None else dict(metadata),
        )
        if self._run_state is not None:
            checkpoint = Checkpoint.create(self._run_state)
            checkpoint = self._store.save(checkpoint)
        self._checkpoints.append(checkpoint)
        return checkpoint

    def list_checkpoints(self) -> list[Checkpoint]:
        """返回快照列表副本，避免调用方清空内部记录。"""
        return list(self._checkpoints)

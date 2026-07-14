"""本文件负责定义 Checkpoint 持久化边界及内存测试实现。"""
from typing import Protocol
from my_agent.state.checkpoint import Checkpoint

class CheckpointStore(Protocol):
    def save(self, checkpoint: Checkpoint) -> Checkpoint: ...
    def get_latest(self, run_id: str) -> Checkpoint | None: ...

class InMemoryCheckpointStore:
    """在进程内按运行标识追加保存 Checkpoint，供单元测试使用。"""
    def __init__(self) -> None:
        self._items: dict[str, list[Checkpoint]] = {}
    def save(self, checkpoint: Checkpoint) -> Checkpoint:
        if checkpoint.run_state is None:
            raise ValueError("checkpoint must contain run_state")
        items = self._items.setdefault(checkpoint.run_state.run_id, [])
        saved = checkpoint.with_sequence_no(len(items) + 1)
        items.append(saved)
        return saved
    def get_latest(self, run_id: str) -> Checkpoint | None:
        items = self._items.get(run_id, [])
        return items[-1] if items else None

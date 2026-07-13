"""
本文件负责定义 Web 演示入口使用的会话状态存储边界及其内存实现。
本文件只保存 SessionState 和同会话串行锁，不序列化或持久化 ConversationRuntime。
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Protocol

from my_agent.state.session import SessionState


@dataclass(frozen=True)
class SessionHandle:
    """保存一次会话的状态及同会话消息串行锁。"""

    session_state: SessionState
    lock: Lock

    def __post_init__(self) -> None:
        if not isinstance(self.session_state, SessionState):
            raise TypeError("session_state must be a SessionState")


class SessionStore(Protocol):
    """提供会话状态的创建和读取能力，供 HTTP 层替换持久化实现。"""

    def create(self, session_state: SessionState) -> None:
        """保存一个新会话状态。"""

    def get(self, session_id: str) -> SessionHandle | None:
        """按会话标识获取状态和串行锁。"""


class InMemorySessionStore:
    """在单进程内保存会话状态的第一版实现。"""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionHandle] = {}
        self._store_lock = Lock()

    def create(self, session_state: SessionState) -> None:
        """保存新会话，并拒绝重复的会话标识。"""
        if not isinstance(session_state, SessionState):
            raise TypeError("session_state must be a SessionState")

        with self._store_lock:
            if session_state.session_id in self._sessions:
                raise ValueError("session_id already exists")
            self._sessions[session_state.session_id] = SessionHandle(
                session_state=session_state,
                lock=Lock(),
            )

    def get(self, session_id: str) -> SessionHandle | None:
        """返回会话句柄；调用方必须使用句柄锁串行处理消息。"""
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")

        with self._store_lock:
            return self._sessions.get(session_id)

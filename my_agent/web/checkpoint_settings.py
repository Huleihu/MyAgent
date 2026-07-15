"""
本文件负责读取 Web 服务的 Checkpoint 数据库配置并创建默认 SQLite Store。
本文件不处理 HTTP 请求，也不参与 Runtime 执行。
"""

from __future__ import annotations

import os
from pathlib import Path

from my_agent.state.sqlite_checkpoint_store import SQLiteCheckpointStore


def create_default_checkpoint_store() -> SQLiteCheckpointStore:
    """按环境变量创建默认持久化 Store，并确保数据库目录存在。"""
    configured_path = os.getenv("MYAGENT_CHECKPOINT_DB_PATH")
    database_path = (
        Path(configured_path)
        if configured_path
        else Path.cwd() / ".myagent" / "checkpoints.sqlite3"
    )
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return SQLiteCheckpointStore(database_path)

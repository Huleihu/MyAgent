"""
本文件负责定义 RAG 检索过程的 Trace 数据模型。
本文件不负责执行检索、判断命中结果和生成评估结论。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RagTrace:
    """记录一次 RAG 检索的关键输入、输出和耗时。"""

    query: str
    retrieved_chunks: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    duration_ms: float

    def __post_init__(self) -> None:
        if not isinstance(self.query, str) or not self.query.strip():
            raise ValueError("query must be a non-empty string")
        if not isinstance(self.retrieved_chunks, list):
            raise ValueError("retrieved_chunks must be a list")
        if not all(
            isinstance(chunk, dict) for chunk in self.retrieved_chunks
        ):
            raise ValueError("retrieved_chunks must contain only dict")
        if not isinstance(self.citations, list):
            raise ValueError("citations must be a list")
        if not all(isinstance(citation, dict) for citation in self.citations):
            raise ValueError("citations must contain only dict")
        if not isinstance(self.duration_ms, (int, float)) or self.duration_ms < 0:
            raise ValueError("duration_ms must be a non-negative number")

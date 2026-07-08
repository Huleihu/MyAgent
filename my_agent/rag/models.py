"""
本文件负责定义 RAG 链路中的文档、切片、检索结果和引用数据模型。
本文件不负责文档切分、向量化、召回、重排和工具执行。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _validate_non_empty_text(field_name: str, field_value: str) -> None:
    """校验关键文本字段非空，避免产生无法追踪的数据对象。"""
    if not isinstance(field_value, str) or not field_value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _validate_metadata(metadata: dict[str, Any]) -> None:
    """校验 metadata 字段，后续解析器和引用构造都依赖该边界。"""
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a dict")


def _validate_non_negative_number(field_name: str, field_value: float) -> None:
    """校验检索分数非负，避免排序和评估阶段出现反直觉结果。"""
    if not isinstance(field_value, (int, float)) or field_value < 0:
        raise ValueError(f"{field_name} must be a non-negative number")


@dataclass(frozen=True)
class Document:
    """表示进入 RAG 链路的原始文档。"""

    doc_id: str
    title: str
    source: str
    content: str
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        _validate_non_empty_text("doc_id", self.doc_id)
        _validate_non_empty_text("title", self.title)
        _validate_non_empty_text("source", self.source)
        _validate_non_empty_text("content", self.content)
        _validate_metadata(self.metadata)


@dataclass(frozen=True)
class Chunk:
    """表示从文档中切分出的可检索片段。"""

    chunk_id: str
    doc_id: str
    content: str
    index: int
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        _validate_non_empty_text("chunk_id", self.chunk_id)
        _validate_non_empty_text("doc_id", self.doc_id)
        _validate_non_empty_text("content", self.content)
        if not isinstance(self.index, int) or self.index < 0:
            raise ValueError("index must be a non-negative integer")
        _validate_metadata(self.metadata)


@dataclass(frozen=True)
class RetrievedChunk:
    """表示召回后的 Chunk 及其各阶段得分。"""

    chunk: Chunk
    keyword_score: float
    vector_score: float
    final_score: float
    rerank_score: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.chunk, Chunk):
            raise ValueError("chunk must be a Chunk")
        _validate_non_negative_number("keyword_score", self.keyword_score)
        _validate_non_negative_number("vector_score", self.vector_score)
        _validate_non_negative_number("final_score", self.final_score)
        if self.rerank_score is not None:
            _validate_non_negative_number("rerank_score", self.rerank_score)


@dataclass(frozen=True)
class Citation:
    """表示最终返回给用户或评估模块的引用溯源信息。"""

    doc_id: str
    chunk_id: str
    source: str
    title: str
    snippet: str
    score: float
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        _validate_non_empty_text("doc_id", self.doc_id)
        _validate_non_empty_text("chunk_id", self.chunk_id)
        _validate_non_empty_text("source", self.source)
        _validate_non_empty_text("title", self.title)
        _validate_non_empty_text("snippet", self.snippet)
        _validate_non_negative_number("score", self.score)
        _validate_metadata(self.metadata)

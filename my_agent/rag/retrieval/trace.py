"""
本文件负责定义在线 retrieval.search 的三阶段结构化 Trace 数据模型。
本文件只描述 retrieve、rerank、citation 的遥测摘要，不负责执行检索或评估结论。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _validate_non_empty_text(field_name: str, field_value: str) -> None:
    """校验可稳定定位检索对象的文本标识。"""
    if not isinstance(field_value, str) or not field_value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _validate_non_negative_int(field_name: str, field_value: int) -> None:
    """校验阶段数量和排名，避免产生无意义的 Trace 摘要。"""
    if not isinstance(field_value, int) or field_value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _validate_non_negative_number(field_name: str, field_value: float) -> None:
    """校验阶段耗时与分数，统一采用非负数语义。"""
    if not isinstance(field_value, (int, float)) or field_value < 0:
        raise ValueError(f"{field_name} must be a non-negative number")


def _validate_optional_score(field_name: str, field_value: float | None) -> None:
    """校验阶段可用时才写入的分数。"""
    if field_value is not None:
        _validate_non_negative_number(field_name, field_value)


@dataclass(frozen=True)
class RetrievalChunkTrace:
    """记录一个 Chunk 在召回或重排阶段的轻量摘要。"""

    chunk_id: str
    doc_id: str
    rank: int
    keyword_score: float | None = None
    vector_score: float | None = None
    final_score: float | None = None
    rerank_score: float | None = None

    def __post_init__(self) -> None:
        _validate_non_empty_text("chunk_id", self.chunk_id)
        _validate_non_empty_text("doc_id", self.doc_id)
        if not isinstance(self.rank, int) or self.rank < 1:
            raise ValueError("rank must be a positive integer")
        _validate_optional_score("keyword_score", self.keyword_score)
        _validate_optional_score("vector_score", self.vector_score)
        _validate_optional_score("final_score", self.final_score)
        _validate_optional_score("rerank_score", self.rerank_score)

    def to_dict(self) -> dict[str, Any]:
        """转换为仅含稳定标识、排名和分数的 JSON 数据。"""
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "rank": self.rank,
            "keyword_score": self.keyword_score,
            "vector_score": self.vector_score,
            "final_score": self.final_score,
            "rerank_score": self.rerank_score,
        }

    @classmethod
    def from_dict(cls, trace_data: dict[str, Any]) -> "RetrievalChunkTrace":
        """从工具返回的 JSON 数据恢复 Chunk 阶段摘要。"""
        if not isinstance(trace_data, dict):
            raise ValueError("trace_data must be a dict")
        return cls(
            chunk_id=trace_data.get("chunk_id"),
            doc_id=trace_data.get("doc_id"),
            rank=trace_data.get("rank"),
            keyword_score=trace_data.get("keyword_score"),
            vector_score=trace_data.get("vector_score"),
            final_score=trace_data.get("final_score"),
            rerank_score=trace_data.get("rerank_score"),
        )


@dataclass(frozen=True)
class CitationTrace:
    """记录一个最终 Citation 的轻量摘要，不复制用户可见正文。"""

    chunk_id: str
    doc_id: str
    rank: int
    score: float

    def __post_init__(self) -> None:
        _validate_non_empty_text("chunk_id", self.chunk_id)
        _validate_non_empty_text("doc_id", self.doc_id)
        if not isinstance(self.rank, int) or self.rank < 1:
            raise ValueError("rank must be a positive integer")
        _validate_non_negative_number("score", self.score)

    def to_dict(self) -> dict[str, Any]:
        """转换为只含引用关联信息的 JSON 数据。"""
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "rank": self.rank,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, trace_data: dict[str, Any]) -> "CitationTrace":
        """从工具返回的 JSON 数据恢复 Citation 摘要。"""
        if not isinstance(trace_data, dict):
            raise ValueError("trace_data must be a dict")
        return cls(
            chunk_id=trace_data.get("chunk_id"),
            doc_id=trace_data.get("doc_id"),
            rank=trace_data.get("rank"),
            score=trace_data.get("score"),
        )


@dataclass(frozen=True)
class RetrievalTrace:
    """记录一次成功或无命中 retrieval.search 的三阶段遥测数据。"""

    query: str
    requested_top_k: int
    retrieved_chunks: list[RetrievalChunkTrace]
    reranked_chunks: list[RetrievalChunkTrace]
    citations: list[CitationTrace]
    retrieved_count: int
    reranked_count: int
    citation_count: int
    final_count: int
    retrieve_duration_ms: float
    rerank_duration_ms: float
    citation_duration_ms: float
    total_duration_ms: float

    def __post_init__(self) -> None:
        _validate_non_empty_text("query", self.query)
        if not isinstance(self.requested_top_k, int) or self.requested_top_k < 1:
            raise ValueError("requested_top_k must be a positive integer")
        self._validate_trace_list("retrieved_chunks", self.retrieved_chunks, RetrievalChunkTrace)
        self._validate_trace_list("reranked_chunks", self.reranked_chunks, RetrievalChunkTrace)
        self._validate_trace_list("citations", self.citations, CitationTrace)
        _validate_non_negative_int("retrieved_count", self.retrieved_count)
        _validate_non_negative_int("reranked_count", self.reranked_count)
        _validate_non_negative_int("citation_count", self.citation_count)
        _validate_non_negative_int("final_count", self.final_count)
        self._validate_count("retrieved_count", self.retrieved_count, self.retrieved_chunks)
        self._validate_count("reranked_count", self.reranked_count, self.reranked_chunks)
        self._validate_count("citation_count", self.citation_count, self.citations)
        if self.final_count != self.reranked_count:
            raise ValueError("final_count must equal reranked_count")
        _validate_non_negative_number("retrieve_duration_ms", self.retrieve_duration_ms)
        _validate_non_negative_number("rerank_duration_ms", self.rerank_duration_ms)
        _validate_non_negative_number("citation_duration_ms", self.citation_duration_ms)
        _validate_non_negative_number("total_duration_ms", self.total_duration_ms)

    def to_dict(self) -> dict[str, Any]:
        """转换为可放入 ToolTraceRecord.result 的 JSON 数据。"""
        return {
            "query": self.query,
            "requested_top_k": self.requested_top_k,
            "retrieved_chunks": [chunk.to_dict() for chunk in self.retrieved_chunks],
            "reranked_chunks": [chunk.to_dict() for chunk in self.reranked_chunks],
            "citations": [citation.to_dict() for citation in self.citations],
            "retrieved_count": self.retrieved_count,
            "reranked_count": self.reranked_count,
            "citation_count": self.citation_count,
            "final_count": self.final_count,
            "retrieve_duration_ms": self.retrieve_duration_ms,
            "rerank_duration_ms": self.rerank_duration_ms,
            "citation_duration_ms": self.citation_duration_ms,
            "total_duration_ms": self.total_duration_ms,
        }

    @classmethod
    def from_dict(cls, trace_data: dict[str, Any]) -> "RetrievalTrace":
        """从 RetrievalTool 的结构化返回恢复同一份 Trace。"""
        if not isinstance(trace_data, dict):
            raise ValueError("trace_data must be a dict")
        return cls(
            query=trace_data.get("query"),
            requested_top_k=trace_data.get("requested_top_k"),
            retrieved_chunks=[
                RetrievalChunkTrace.from_dict(chunk)
                for chunk in trace_data.get("retrieved_chunks", [])
            ],
            reranked_chunks=[
                RetrievalChunkTrace.from_dict(chunk)
                for chunk in trace_data.get("reranked_chunks", [])
            ],
            citations=[
                CitationTrace.from_dict(citation)
                for citation in trace_data.get("citations", [])
            ],
            retrieved_count=trace_data.get("retrieved_count"),
            reranked_count=trace_data.get("reranked_count"),
            citation_count=trace_data.get("citation_count"),
            final_count=trace_data.get("final_count"),
            retrieve_duration_ms=trace_data.get("retrieve_duration_ms"),
            rerank_duration_ms=trace_data.get("rerank_duration_ms"),
            citation_duration_ms=trace_data.get("citation_duration_ms"),
            total_duration_ms=trace_data.get("total_duration_ms"),
        )

    @staticmethod
    def _validate_trace_list(field_name: str, values: list[Any], item_type: type) -> None:
        """校验阶段列表及其元素类型，保持数据模型边界明确。"""
        if not isinstance(values, list) or not all(isinstance(value, item_type) for value in values):
            raise ValueError(f"{field_name} must contain only {item_type.__name__}")

    @staticmethod
    def _validate_count(field_name: str, count: int, values: list[Any]) -> None:
        """确保记录数量和实际摘要数量一致。"""
        if count != len(values):
            raise ValueError(f"{field_name} must equal the trace list length")

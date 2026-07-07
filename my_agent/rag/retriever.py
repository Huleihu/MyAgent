"""
本文件负责 RAG 链路中的关键词与向量混合召回。
本文件不负责 Chunk 索引写入、重排、引用构造和 Tool 调用。
"""

from __future__ import annotations

from my_agent.rag.document import RetrievedChunk
from my_agent.rag.index import InMemoryChunkIndex


class HybridRetriever:
    """融合关键词召回和向量召回结果，并计算统一 final_score。"""

    def __init__(
        self,
        index: InMemoryChunkIndex,
        keyword_weight: float = 0.4,
        vector_weight: float = 0.6,
    ) -> None:
        if not isinstance(index, InMemoryChunkIndex):
            raise ValueError("index must be an InMemoryChunkIndex")
        self._validate_weight("keyword_weight", keyword_weight)
        self._validate_weight("vector_weight", vector_weight)

        self._index = index
        self._keyword_weight = keyword_weight
        self._vector_weight = vector_weight

    def retrieve(self, query: str, top_k: int) -> list[RetrievedChunk]:
        """召回并融合 Chunk，按融合分数返回前 top_k 个结果。"""
        keyword_results = self._index.keyword_search(query, top_k)
        vector_results = self._index.vector_search(query, top_k)

        merged_results: dict[str, dict] = {}
        for result in keyword_results:
            merged_results[result.chunk.chunk_id] = {
                "chunk": result.chunk,
                "keyword_score": result.keyword_score,
                "vector_score": 0.0,
            }

        for result in vector_results:
            existing_result = merged_results.setdefault(
                result.chunk.chunk_id,
                {
                    "chunk": result.chunk,
                    "keyword_score": 0.0,
                    "vector_score": 0.0,
                },
            )
            existing_result["vector_score"] = result.vector_score

        fused_results = [
            self._build_retrieved_chunk(
                item["chunk"],
                item["keyword_score"],
                item["vector_score"],
            )
            for item in merged_results.values()
        ]

        return self._sort_results(fused_results)[:top_k]

    def _build_retrieved_chunk(
        self,
        chunk,
        keyword_score: float,
        vector_score: float,
    ) -> RetrievedChunk:
        """根据两路召回分数构造统一召回结果。"""
        final_score = (
            self._keyword_weight * keyword_score
            + self._vector_weight * vector_score
        )
        return RetrievedChunk(
            chunk=chunk,
            keyword_score=keyword_score,
            vector_score=vector_score,
            final_score=final_score,
        )

    def _sort_results(
        self,
        results: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        """按融合分数降序排序，分数相同时保持切片顺序稳定。"""
        return sorted(
            results,
            key=lambda result: (
                -result.final_score,
                result.chunk.doc_id,
                result.chunk.index,
            ),
        )

    def _validate_weight(self, field_name: str, field_value: float) -> None:
        """校验融合权重，避免负分数破坏排序语义。"""
        if not isinstance(field_value, (int, float)) or field_value < 0:
            raise ValueError(f"{field_name} must be a non-negative number")

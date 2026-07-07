"""
本文件负责将 Chunk 及其向量保存在内存中，并提供基础召回能力。
本文件不负责文档解析、Chunk 切分、混合召回融合、重排和引用构造。
"""

from __future__ import annotations

from dataclasses import dataclass

from my_agent.rag.document import Chunk, RetrievedChunk
from my_agent.rag.embedding import SimpleEmbeddingModel


@dataclass(frozen=True)
class _IndexedChunk:
    """保存 Chunk 与预计算向量，避免每次检索重复向量化文档内容。"""

    chunk: Chunk
    embedding: dict[str, float]


class InMemoryChunkIndex:
    """使用进程内列表保存 Chunk，适合第一版本地演示和单元测试。"""

    def __init__(self, embedding_model: SimpleEmbeddingModel) -> None:
        if not isinstance(embedding_model, SimpleEmbeddingModel):
            raise ValueError("embedding_model must be a SimpleEmbeddingModel")

        self._embedding_model = embedding_model
        self._items: list[_IndexedChunk] = []

    def add_chunks(self, chunks: list[Chunk]) -> None:
        """为 Chunk 生成 embedding 并追加写入内存索引。"""
        for chunk in chunks:
            if not isinstance(chunk, Chunk):
                raise ValueError("chunks must contain only Chunk")

            self._items.append(
                _IndexedChunk(
                    chunk=chunk,
                    embedding=self._embedding_model.embed(chunk.content),
                )
            )

    def keyword_search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        """按 query token 覆盖率执行关键词召回。"""
        self._validate_search_arguments(query, top_k)
        query_tokens = set(self._embedding_model.tokenize(query))
        if not query_tokens:
            return []

        results = []
        for item in self._items:
            chunk_tokens = set(self._embedding_model.tokenize(item.chunk.content))
            matched_count = len(query_tokens.intersection(chunk_tokens))
            if matched_count == 0:
                continue

            keyword_score = matched_count / len(query_tokens)
            results.append(
                RetrievedChunk(
                    chunk=item.chunk,
                    keyword_score=keyword_score,
                    vector_score=0.0,
                    final_score=keyword_score,
                )
            )

        return self._sort_results(results)[:top_k]

    def vector_search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        """按 query embedding 与 Chunk embedding 的余弦相似度召回。"""
        self._validate_search_arguments(query, top_k)
        query_embedding = self._embedding_model.embed(query)
        if not query_embedding:
            return []

        results = []
        for item in self._items:
            vector_score = self._embedding_model.cosine_similarity(
                query_embedding,
                item.embedding,
            )
            if vector_score == 0.0:
                continue

            results.append(
                RetrievedChunk(
                    chunk=item.chunk,
                    keyword_score=0.0,
                    vector_score=vector_score,
                    final_score=vector_score,
                )
            )

        return self._sort_results(results)[:top_k]

    def _validate_search_arguments(self, query: str, top_k: int) -> None:
        """校验检索入参，保持后续 RetrievalTool 的参数边界一致。"""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        if not isinstance(top_k, int) or top_k <= 0:
            raise ValueError("top_k must be a positive integer")

    def _sort_results(self, results: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """按分数降序排序，分数相同时保持文档切片顺序稳定。"""
        return sorted(
            results,
            key=lambda result: (
                -result.final_score,
                result.chunk.doc_id,
                result.chunk.index,
            ),
        )

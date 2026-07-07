"""
本文件负责 RAG 链路中的简单重排。
本文件不负责召回、索引访问、引用构造和 Tool 调用。
"""

from __future__ import annotations

from dataclasses import replace

from my_agent.rag.document import RetrievedChunk


class SimpleReranker:
    """基于已有 final_score 做稳定重排，并写入 rerank_score。"""

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        """按 final_score 重排召回结果。"""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")

        reranked_chunks = []
        for chunk in chunks:
            if not isinstance(chunk, RetrievedChunk):
                raise ValueError("chunks must contain only RetrievedChunk")
            reranked_chunks.append(
                replace(chunk, rerank_score=chunk.final_score)
            )

        return sorted(
            reranked_chunks,
            key=lambda result: (
                -result.rerank_score,
                result.chunk.doc_id,
                result.chunk.index,
            ),
        )

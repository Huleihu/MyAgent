"""
本文件负责把 RAG 检索链路适配为标准 Tool。
本文件不负责文档解析、Chunk 切分、索引写入和 ToolExecutor 执行包装。
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from my_agent.core.interfaces import Tool
from my_agent.rag.retrieval.citation import CitationBuilder
from my_agent.rag.models import Citation, RetrievedChunk
from my_agent.rag.retrieval.reranker import SimpleReranker
from my_agent.rag.retrieval.retriever import HybridRetriever
from my_agent.rag.retrieval.trace import (
    CitationTrace,
    RetrievalChunkTrace,
    RetrievalTrace,
)
from my_agent.tools.schema import ToolDefinition


class RetrievalTool(Tool):
    """将混合召回、重排和引用构造封装为 retrieval.search 工具。"""

    def __init__(
        self,
        retriever: HybridRetriever,
        reranker: SimpleReranker,
        citation_builder: CitationBuilder,
    ) -> None:
        if not isinstance(retriever, HybridRetriever):
            raise ValueError("retriever must be a HybridRetriever")
        if not isinstance(reranker, SimpleReranker):
            raise ValueError("reranker must be a SimpleReranker")
        if not isinstance(citation_builder, CitationBuilder):
            raise ValueError("citation_builder must be a CitationBuilder")

        self._retriever = retriever
        self._reranker = reranker
        self._citation_builder = citation_builder
        self._definition = ToolDefinition(
            name="retrieval.search",
            description="检索知识库中的相关文档片段，并返回引用溯源信息。",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "用户检索问题",
                    },
                    "top_k": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 20,
                    },
                },
                "required": ["query"],
            },
            tags=("rag", "retrieval"),
        )

    @property
    def definition(self) -> ToolDefinition:
        """返回 retrieval.search 的工具定义。"""
        return self._definition

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """执行检索工具调用，并返回结构化 Chunk 与 Citation 数据。"""
        query = self._get_query(arguments)
        top_k = self._get_top_k(arguments)

        total_started_at = perf_counter()
        retrieved_chunks, retrieve_duration_ms = self._retrieve(query, top_k)
        reranked_chunks, rerank_duration_ms = self._rerank(query, retrieved_chunks)
        citations, citation_duration_ms = self._build_citations(reranked_chunks)
        retrieval_trace = RetrievalTrace(
            query=query,
            requested_top_k=top_k,
            retrieved_chunks=self._build_chunk_traces(retrieved_chunks),
            reranked_chunks=self._build_chunk_traces(reranked_chunks),
            citations=self._build_citation_traces(citations),
            retrieved_count=len(retrieved_chunks),
            reranked_count=len(reranked_chunks),
            citation_count=len(citations),
            final_count=len(reranked_chunks),
            retrieve_duration_ms=retrieve_duration_ms,
            rerank_duration_ms=rerank_duration_ms,
            citation_duration_ms=citation_duration_ms,
            total_duration_ms=(perf_counter() - total_started_at) * 1000,
        )

        return {
            "query": query,
            "chunks": [
                self._format_retrieved_chunk(chunk)
                for chunk in reranked_chunks
            ],
            "citations": [
                self._format_citation(citation)
                for citation in citations
            ],
            "retrieval_trace": retrieval_trace.to_dict(),
        }

    def _retrieve(
        self,
        query: str,
        top_k: int,
    ) -> tuple[list[RetrievedChunk], float]:
        """执行混合召回，并在异常中标注失败所属阶段。"""
        started_at = perf_counter()
        try:
            chunks = self._retriever.retrieve(query=query, top_k=top_k)
        except Exception as error:
            raise RuntimeError("retrieval.search retrieve stage failed") from error
        return chunks, (perf_counter() - started_at) * 1000

    def _rerank(
        self,
        query: str,
        retrieved_chunks: list[RetrievedChunk],
    ) -> tuple[list[RetrievedChunk], float]:
        """执行稳定重排，并在异常中标注失败所属阶段。"""
        started_at = perf_counter()
        try:
            chunks = self._reranker.rerank(query, retrieved_chunks)
        except Exception as error:
            raise RuntimeError("retrieval.search rerank stage failed") from error
        return chunks, (perf_counter() - started_at) * 1000

    def _build_citations(
        self,
        reranked_chunks: list[RetrievedChunk],
    ) -> tuple[list[Citation], float]:
        """构造最终引用，并在异常中标注失败所属阶段。"""
        started_at = perf_counter()
        try:
            citations = self._citation_builder.build(reranked_chunks)
        except Exception as error:
            raise RuntimeError("retrieval.search citation stage failed") from error
        return citations, (perf_counter() - started_at) * 1000

    def _build_chunk_traces(
        self,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievalChunkTrace]:
        """按阶段输出顺序生成仅包含标识、排名和分数的摘要。"""
        return [
            RetrievalChunkTrace(
                chunk_id=retrieved_chunk.chunk.chunk_id,
                doc_id=retrieved_chunk.chunk.doc_id,
                rank=rank,
                keyword_score=retrieved_chunk.keyword_score,
                vector_score=retrieved_chunk.vector_score,
                final_score=retrieved_chunk.final_score,
                rerank_score=retrieved_chunk.rerank_score,
            )
            for rank, retrieved_chunk in enumerate(chunks, start=1)
        ]

    def _build_citation_traces(
        self,
        citations: list[Citation],
    ) -> list[CitationTrace]:
        """按 Citation 输出顺序生成轻量引用摘要。"""
        return [
            CitationTrace(
                chunk_id=citation.chunk_id,
                doc_id=citation.doc_id,
                rank=rank,
                score=citation.score,
            )
            for rank, citation in enumerate(citations, start=1)
        ]

    def _get_query(self, arguments: dict[str, Any]) -> str:
        """读取并校验 query 参数。"""
        query = arguments.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")
        return query

    def _get_top_k(self, arguments: dict[str, Any]) -> int:
        """读取并校验 top_k 参数，默认返回 5。"""
        top_k = arguments.get("top_k", 5)
        if not isinstance(top_k, int):
            raise ValueError("top_k must be an integer")
        if top_k < 1 or top_k > 20:
            raise ValueError("top_k must be between 1 and 20")
        return top_k

    def _format_retrieved_chunk(
        self,
        retrieved_chunk: RetrievedChunk,
    ) -> dict[str, Any]:
        """将 RetrievedChunk 转为工具返回的 dict。"""
        chunk = retrieved_chunk.chunk
        return {
            "chunk_id": chunk.chunk_id,
            "doc_id": chunk.doc_id,
            "content": chunk.content,
            "keyword_score": retrieved_chunk.keyword_score,
            "vector_score": retrieved_chunk.vector_score,
            "final_score": retrieved_chunk.final_score,
            "rerank_score": retrieved_chunk.rerank_score,
            "metadata": dict(chunk.metadata),
        }

    def _format_citation(self, citation: Citation) -> dict[str, Any]:
        """将 Citation 转为工具返回的 dict。"""
        return {
            "doc_id": citation.doc_id,
            "chunk_id": citation.chunk_id,
            "source": citation.source,
            "title": citation.title,
            "snippet": citation.snippet,
            "score": citation.score,
            "metadata": dict(citation.metadata),
        }

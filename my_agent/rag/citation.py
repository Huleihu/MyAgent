"""
本文件负责把召回结果转换为可返回给用户的引用信息。
本文件不负责召回、重排、答案生成和 Tool 调用。
"""

from __future__ import annotations

from my_agent.rag.document import Citation, RetrievedChunk


class CitationBuilder:
    """从 RetrievedChunk 构造 Citation，保留 Chunk 的溯源 metadata。"""

    def build(
        self,
        retrieved_chunks: list[RetrievedChunk],
    ) -> list[Citation]:
        """按输入顺序生成引用列表。"""
        citations = []
        for retrieved_chunk in retrieved_chunks:
            if not isinstance(retrieved_chunk, RetrievedChunk):
                raise ValueError(
                    "retrieved_chunks must contain only RetrievedChunk"
                )
            citations.append(self._build_citation(retrieved_chunk))
        return citations

    def _build_citation(
        self,
        retrieved_chunk: RetrievedChunk,
    ) -> Citation:
        """从单个召回结果中提取引用字段。"""
        chunk = retrieved_chunk.chunk
        metadata = dict(chunk.metadata)
        source = metadata.get("source") or chunk.doc_id
        title = metadata.get("title") or chunk.doc_id
        score = (
            retrieved_chunk.rerank_score
            if retrieved_chunk.rerank_score is not None
            else retrieved_chunk.final_score
        )

        return Citation(
            doc_id=chunk.doc_id,
            chunk_id=chunk.chunk_id,
            source=source,
            title=title,
            snippet=chunk.content,
            score=score,
            metadata=metadata,
        )

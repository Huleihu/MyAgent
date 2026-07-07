"""
本文件负责把标准 Document 切分为可检索 Chunk。
本文件不负责文件解析、Embedding、索引写入和检索召回。
"""

from __future__ import annotations

from my_agent.rag.document import Chunk, Document


class TextChunker:
    """按固定字符长度切分文档，并保留溯源 metadata。"""

    def __init__(self, chunk_size: int, overlap: int = 0) -> None:
        if not isinstance(chunk_size, int) or chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer")
        if not isinstance(overlap, int) or overlap < 0:
            raise ValueError("overlap must be a non-negative integer")
        if overlap >= chunk_size:
            raise ValueError("overlap must be less than chunk_size")

        self._chunk_size = chunk_size
        self._overlap = overlap

    def split(self, document: Document) -> list[Chunk]:
        """将单篇 Document 切分为 Chunk 列表。"""
        if not isinstance(document, Document):
            raise ValueError("document must be a Document")

        chunks = []
        start = 0
        chunk_index = 0
        step_size = self._chunk_size - self._overlap

        while start < len(document.content):
            end = start + self._chunk_size
            chunk_content = document.content[start:end]
            chunks.append(
                Chunk(
                    chunk_id=f"{document.doc_id}:{chunk_index}",
                    doc_id=document.doc_id,
                    content=chunk_content,
                    index=chunk_index,
                    metadata=self._build_chunk_metadata(document, chunk_index),
                )
            )
            start += step_size
            chunk_index += 1

        return chunks

    def split_many(self, documents: list[Document]) -> list[Chunk]:
        """按输入顺序切分多篇 Document。"""
        chunks = []
        for document in documents:
            chunks.extend(self.split(document))
        return chunks

    def _build_chunk_metadata(
        self,
        document: Document,
        chunk_index: int,
    ) -> dict:
        """构造 Chunk metadata，保留文档来源并补充切片序号。"""
        metadata = dict(document.metadata)
        metadata.update(
            {
                "source": document.source,
                "title": document.title,
                "chunk_index": chunk_index,
            }
        )
        return metadata

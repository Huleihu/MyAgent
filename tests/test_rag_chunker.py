"""
本文件负责验证 RAG 文本切分器的切片边界与 metadata 传递。
本文件不测试文档解析、Embedding 和检索流程。
"""

import unittest

from my_agent.rag.indexing.chunker import TextChunker
from my_agent.rag.models import Chunk, Document


def build_document(content):
    return Document(
        doc_id="doc-1",
        title="Agentic RAG 介绍",
        source="local://agentic-rag.md",
        content=content,
        metadata={
            "filename": "agentic-rag.md",
            "tags": ["rag", "agent"],
        },
    )


class TextChunkerTest(unittest.TestCase):
    def test_split_short_document_returns_single_chunk(self):
        document = build_document("Agentic RAG 会把检索能力封装为工具。")
        chunker = TextChunker(chunk_size=100, overlap=20)

        chunks = chunker.split(document)

        self.assertEqual(len(chunks), 1)
        self.assertIsInstance(chunks[0], Chunk)
        self.assertEqual(chunks[0].chunk_id, "doc-1:0")
        self.assertEqual(chunks[0].doc_id, "doc-1")
        self.assertEqual(chunks[0].index, 0)
        self.assertEqual(chunks[0].content, document.content)

    def test_split_long_document_uses_overlap(self):
        document = build_document("abcdefghijklmnopqrstuvwxyz")
        chunker = TextChunker(chunk_size=10, overlap=3)

        chunks = chunker.split(document)

        self.assertEqual([chunk.content for chunk in chunks], [
            "abcdefghij",
            "hijklmnopq",
            "opqrstuvwx",
            "vwxyz",
        ])
        self.assertEqual([chunk.chunk_id for chunk in chunks], [
            "doc-1:0",
            "doc-1:1",
            "doc-1:2",
            "doc-1:3",
        ])

    def test_chunk_metadata_inherits_document_metadata_and_adds_chunk_fields(self):
        document = build_document("abcdefghijklmnopqrstuvwxyz")
        chunker = TextChunker(chunk_size=10, overlap=0)

        chunk = chunker.split(document)[0]

        self.assertEqual(chunk.metadata["filename"], "agentic-rag.md")
        self.assertEqual(chunk.metadata["tags"], ["rag", "agent"])
        self.assertEqual(chunk.metadata["source"], "local://agentic-rag.md")
        self.assertEqual(chunk.metadata["title"], "Agentic RAG 介绍")
        self.assertEqual(chunk.metadata["chunk_index"], 0)

    def test_split_many_preserves_document_order(self):
        first = build_document("first document")
        second = Document(
            doc_id="doc-2",
            title="第二篇文档",
            source="local://second.md",
            content="second document",
            metadata={"filename": "second.md"},
        )
        chunker = TextChunker(chunk_size=100, overlap=0)

        chunks = chunker.split_many([first, second])

        self.assertEqual([chunk.doc_id for chunk in chunks], ["doc-1", "doc-2"])

    def test_rejects_invalid_chunk_size(self):
        with self.assertRaises(ValueError):
            TextChunker(chunk_size=0, overlap=0)

    def test_rejects_overlap_greater_than_or_equal_to_chunk_size(self):
        with self.assertRaises(ValueError):
            TextChunker(chunk_size=10, overlap=10)


if __name__ == "__main__":
    unittest.main()

"""
本文件负责验证 RAG 数据模型的字段契约和基础校验。
本文件不测试文档切分、检索和引用构造流程。
"""

import unittest

from my_agent.rag.models import Citation, Chunk, Document, RetrievedChunk


class RagDocumentModelTest(unittest.TestCase):
    def test_document_preserves_metadata(self):
        document = Document(
            doc_id="doc-1",
            title="Agentic RAG 介绍",
            source="local://agentic-rag.txt",
            content="Agentic RAG 会把检索能力封装为工具。",
            metadata={
                "filename": "agentic-rag.txt",
                "tags": ["rag", "agent"],
            },
        )

        self.assertEqual(document.doc_id, "doc-1")
        self.assertEqual(document.metadata["filename"], "agentic-rag.txt")

    def test_chunk_preserves_document_metadata_boundary(self):
        chunk = Chunk(
            chunk_id="doc-1:0",
            doc_id="doc-1",
            content="Agentic RAG 会把检索能力封装为工具。",
            index=0,
            metadata={
                "source": "local://agentic-rag.txt",
                "page": 1,
                "section": "intro",
            },
        )

        self.assertEqual(chunk.chunk_id, "doc-1:0")
        self.assertEqual(chunk.index, 0)
        self.assertEqual(chunk.metadata["section"], "intro")

    def test_retrieved_chunk_keeps_all_retrieval_scores(self):
        chunk = Chunk(
            chunk_id="doc-1:0",
            doc_id="doc-1",
            content="Agentic RAG 使用混合召回。",
            index=0,
            metadata={"source": "local://agentic-rag.txt"},
        )

        retrieved = RetrievedChunk(
            chunk=chunk,
            keyword_score=0.4,
            vector_score=0.8,
            final_score=0.64,
            rerank_score=None,
        )

        self.assertIs(retrieved.chunk, chunk)
        self.assertEqual(retrieved.keyword_score, 0.4)
        self.assertEqual(retrieved.vector_score, 0.8)
        self.assertEqual(retrieved.final_score, 0.64)
        self.assertIsNone(retrieved.rerank_score)

    def test_citation_keeps_source_snippet_score_and_metadata(self):
        citation = Citation(
            doc_id="doc-1",
            chunk_id="doc-1:0",
            source="local://agentic-rag.txt",
            title="Agentic RAG 介绍",
            snippet="Agentic RAG 会把检索能力封装为工具。",
            score=0.91,
            metadata={"filename": "agentic-rag.txt"},
        )

        self.assertEqual(citation.source, "local://agentic-rag.txt")
        self.assertEqual(citation.score, 0.91)
        self.assertEqual(citation.metadata["filename"], "agentic-rag.txt")

    def test_document_rejects_non_dict_metadata(self):
        with self.assertRaises(ValueError):
            Document(
                doc_id="doc-1",
                title="Agentic RAG 介绍",
                source="local://agentic-rag.txt",
                content="Agentic RAG 会把检索能力封装为工具。",
                metadata=["not", "dict"],
            )

    def test_retrieved_chunk_rejects_negative_score(self):
        chunk = Chunk(
            chunk_id="doc-1:0",
            doc_id="doc-1",
            content="Agentic RAG 使用混合召回。",
            index=0,
            metadata={},
        )

        with self.assertRaises(ValueError):
            RetrievedChunk(
                chunk=chunk,
                keyword_score=-0.1,
                vector_score=0.8,
                final_score=0.64,
            )


if __name__ == "__main__":
    unittest.main()

"""
本文件负责验证 RAG 混合召回、简单重排和引用构造行为。
本文件不测试文档解析、Chunk 切分、索引内部实现和 Tool 调用链。
"""

import unittest

from my_agent.rag.citation import CitationBuilder
from my_agent.rag.document import Chunk, RetrievedChunk
from my_agent.rag.embedding import SimpleEmbeddingModel
from my_agent.rag.index import InMemoryChunkIndex
from my_agent.rag.reranker import SimpleReranker
from my_agent.rag.retriever import HybridRetriever


def build_chunk(chunk_id, content, index=0, title="测试文档"):
    return Chunk(
        chunk_id=chunk_id,
        doc_id=chunk_id.split(":")[0],
        content=content,
        index=index,
        metadata={
            "source": f"local://{chunk_id}.md",
            "title": title,
            "filename": f"{chunk_id}.md",
        },
    )


class HybridRetrieverTest(unittest.TestCase):
    def test_retrieve_merges_keyword_and_vector_scores(self):
        chunks = [
            build_chunk("doc-1:0", "Agentic RAG 支持检索工具和向量召回", 0),
            build_chunk("doc-2:0", "Checkpoint 保存 Agent 运行状态", 0),
        ]
        index = InMemoryChunkIndex(SimpleEmbeddingModel())
        index.add_chunks(chunks)
        retriever = HybridRetriever(
            index=index,
            keyword_weight=0.4,
            vector_weight=0.6,
        )

        results = retriever.retrieve("RAG 检索工具", top_k=2)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chunk.chunk_id, "doc-1:0")
        self.assertGreater(results[0].keyword_score, 0.0)
        self.assertGreater(results[0].vector_score, 0.0)
        expected_score = (
            0.4 * results[0].keyword_score
            + 0.6 * results[0].vector_score
        )
        self.assertAlmostEqual(results[0].final_score, expected_score)

    def test_retrieve_keeps_best_chunks_after_fusion_sorting(self):
        chunks = [
            build_chunk("doc-1:0", "Agentic RAG 支持检索工具", 0),
            build_chunk("doc-2:0", "RAG RAG RAG 检索", 0),
            build_chunk("doc-3:0", "完全无关的运行状态", 0),
        ]
        index = InMemoryChunkIndex(SimpleEmbeddingModel())
        index.add_chunks(chunks)
        retriever = HybridRetriever(index=index)

        results = retriever.retrieve("RAG 检索", top_k=1)

        self.assertEqual(len(results), 1)
        self.assertIn(results[0].chunk.chunk_id, {"doc-1:0", "doc-2:0"})
        self.assertGreater(results[0].final_score, 0.0)

    def test_retrieve_rejects_invalid_weight(self):
        index = InMemoryChunkIndex(SimpleEmbeddingModel())

        with self.assertRaises(ValueError):
            HybridRetriever(index=index, keyword_weight=-0.1)


class SimpleRerankerTest(unittest.TestCase):
    def test_rerank_orders_by_final_score_and_sets_rerank_score(self):
        lower = RetrievedChunk(
            chunk=build_chunk("doc-1:0", "低分片段", 0),
            keyword_score=0.2,
            vector_score=0.2,
            final_score=0.2,
        )
        higher = RetrievedChunk(
            chunk=build_chunk("doc-2:0", "高分片段", 0),
            keyword_score=0.8,
            vector_score=0.8,
            final_score=0.8,
        )

        results = SimpleReranker().rerank("RAG", [lower, higher])

        self.assertEqual([item.chunk.chunk_id for item in results], [
            "doc-2:0",
            "doc-1:0",
        ])
        self.assertEqual(results[0].rerank_score, 0.8)
        self.assertEqual(results[1].rerank_score, 0.2)

    def test_rerank_rejects_non_retrieved_chunk(self):
        with self.assertRaises(ValueError):
            SimpleReranker().rerank("RAG", ["not retrieved chunk"])


class CitationBuilderTest(unittest.TestCase):
    def test_build_converts_retrieved_chunks_to_citations(self):
        retrieved = RetrievedChunk(
            chunk=build_chunk(
                "doc-1:0",
                "Agentic RAG 会把检索能力封装为工具。",
                0,
                title="Agentic RAG 介绍",
            ),
            keyword_score=0.5,
            vector_score=0.7,
            final_score=0.62,
            rerank_score=0.62,
        )

        citations = CitationBuilder().build([retrieved])

        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0].doc_id, "doc-1")
        self.assertEqual(citations[0].chunk_id, "doc-1:0")
        self.assertEqual(citations[0].source, "local://doc-1:0.md")
        self.assertEqual(citations[0].title, "Agentic RAG 介绍")
        self.assertEqual(citations[0].snippet, retrieved.chunk.content)
        self.assertEqual(citations[0].score, 0.62)
        self.assertEqual(citations[0].metadata["filename"], "doc-1:0.md")

    def test_build_uses_final_score_when_rerank_score_missing(self):
        retrieved = RetrievedChunk(
            chunk=build_chunk("doc-1:0", "Agentic RAG 使用混合召回", 0),
            keyword_score=0.4,
            vector_score=0.6,
            final_score=0.52,
        )

        citation = CitationBuilder().build([retrieved])[0]

        self.assertEqual(citation.score, 0.52)


if __name__ == "__main__":
    unittest.main()

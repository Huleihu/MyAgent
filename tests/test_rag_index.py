"""
本文件负责验证 RAG 确定性向量化和内存 Chunk 索引的检索行为。
本文件不测试文档解析、Chunk 切分和 Tool 调用链。
"""

import unittest

from my_agent.rag.models import Chunk, RetrievedChunk
from my_agent.rag.indexing.embedding import SimpleEmbeddingModel
from my_agent.rag.indexing.index import InMemoryChunkIndex


def build_chunk(chunk_id, content, index=0):
    return Chunk(
        chunk_id=chunk_id,
        doc_id=chunk_id.split(":")[0],
        content=content,
        index=index,
        metadata={
            "source": f"local://{chunk_id}.md",
            "title": "测试文档",
        },
    )


class SimpleEmbeddingModelTest(unittest.TestCase):
    def test_embed_uses_deterministic_token_frequency(self):
        model = SimpleEmbeddingModel()

        first = model.embed("Agentic RAG rag 检索")
        second = model.embed("agentic rag RAG 检索")

        self.assertEqual(first, second)
        self.assertEqual(first["agentic"], 1.0)
        self.assertEqual(first["rag"], 2.0)
        self.assertGreater(first["检"], 0.0)

    def test_cosine_similarity_returns_zero_for_empty_vectors(self):
        model = SimpleEmbeddingModel()

        self.assertEqual(model.cosine_similarity({}, {"rag": 1.0}), 0.0)


class InMemoryChunkIndexTest(unittest.TestCase):
    def test_keyword_search_returns_matching_chunks_by_overlap_score(self):
        chunks = [
            build_chunk("doc-1:0", "Agentic RAG 会把检索能力封装为工具", 0),
            build_chunk("doc-2:0", "Checkpoint 负责保存运行状态", 0),
        ]
        index = InMemoryChunkIndex(SimpleEmbeddingModel())
        index.add_chunks(chunks)

        results = index.keyword_search("RAG 检索工具", top_k=2)

        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], RetrievedChunk)
        self.assertEqual(results[0].chunk.chunk_id, "doc-1:0")
        self.assertGreater(results[0].keyword_score, 0.0)
        self.assertEqual(results[0].vector_score, 0.0)
        self.assertEqual(results[0].final_score, results[0].keyword_score)

    def test_vector_search_returns_chunks_by_cosine_similarity(self):
        chunks = [
            build_chunk("doc-1:0", "Agentic RAG 支持向量检索", 0),
            build_chunk("doc-2:0", "ToolExecutor 执行工具调用", 0),
        ]
        index = InMemoryChunkIndex(SimpleEmbeddingModel())
        index.add_chunks(chunks)

        results = index.vector_search("RAG 向量召回", top_k=1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].chunk.chunk_id, "doc-1:0")
        self.assertEqual(results[0].keyword_score, 0.0)
        self.assertGreater(results[0].vector_score, 0.0)
        self.assertEqual(results[0].final_score, results[0].vector_score)

    def test_add_chunks_rejects_non_chunk_item(self):
        index = InMemoryChunkIndex(SimpleEmbeddingModel())

        with self.assertRaises(ValueError):
            index.add_chunks(["not chunk"])

    def test_search_rejects_invalid_query_and_top_k(self):
        index = InMemoryChunkIndex(SimpleEmbeddingModel())

        with self.assertRaises(ValueError):
            index.keyword_search("", top_k=1)

        with self.assertRaises(ValueError):
            index.vector_search("rag", top_k=0)


if __name__ == "__main__":
    unittest.main()

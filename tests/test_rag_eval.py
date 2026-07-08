"""
本文件负责验证 RAG Trace 与 Retrieval Test 的评估行为。
本文件不测试文档解析、Chunk 切分、索引排序和 ToolExecutor 包装。
"""

import unittest

from my_agent.rag.citation import CitationBuilder
from my_agent.rag.document import Chunk
from my_agent.rag.embedding import SimpleEmbeddingModel
from my_agent.rag.eval import (
    RetrievalEvaluator,
    RetrievalEvalResult,
    RetrievalTestCase,
)
from my_agent.rag.index import InMemoryChunkIndex
from my_agent.rag.reranker import SimpleReranker
from my_agent.rag.retrieval_tool import RetrievalTool
from my_agent.rag.retriever import HybridRetriever
from my_agent.rag.trace import RagTrace


def build_tool():
    index = InMemoryChunkIndex(SimpleEmbeddingModel())
    index.add_chunks(
        [
            Chunk(
                chunk_id="doc-1:0",
                doc_id="doc-1",
                content="Agentic RAG 会把检索能力封装为工具。",
                index=0,
                metadata={
                    "source": "local://agentic-rag.md",
                    "title": "Agentic RAG 介绍",
                },
            ),
            Chunk(
                chunk_id="doc-2:0",
                doc_id="doc-2",
                content="Checkpoint 负责保存 Agent 运行状态。",
                index=0,
                metadata={
                    "source": "local://checkpoint.md",
                    "title": "Checkpoint 介绍",
                },
            ),
        ]
    )
    return RetrievalTool(
        retriever=HybridRetriever(index),
        reranker=SimpleReranker(),
        citation_builder=CitationBuilder(),
    )


class RagTraceTest(unittest.TestCase):
    def test_trace_keeps_query_chunks_citations_and_duration(self):
        trace = RagTrace(
            query="RAG 检索工具",
            retrieved_chunks=[
                {
                    "chunk_id": "doc-1:0",
                    "keyword_score": 0.5,
                    "vector_score": 0.7,
                    "final_score": 0.62,
                    "rerank_score": 0.62,
                }
            ],
            citations=[
                {
                    "doc_id": "doc-1",
                    "chunk_id": "doc-1:0",
                    "source": "local://agentic-rag.md",
                }
            ],
            duration_ms=1.5,
        )

        self.assertEqual(trace.query, "RAG 检索工具")
        self.assertEqual(trace.retrieved_chunks[0]["chunk_id"], "doc-1:0")
        self.assertEqual(trace.citations[0]["doc_id"], "doc-1")
        self.assertEqual(trace.duration_ms, 1.5)


class RetrievalEvaluatorTest(unittest.TestCase):
    def test_evaluate_returns_hit_with_trace_when_expected_doc_and_keyword_match(self):
        evaluator = RetrievalEvaluator(build_tool())
        test_case = RetrievalTestCase(
            query="RAG 检索工具",
            expected_doc_ids=["doc-1"],
            expected_chunk_keywords=["检索能力"],
            top_k=1,
        )

        result = evaluator.evaluate(test_case)

        self.assertIsInstance(result, RetrievalEvalResult)
        self.assertTrue(result.hit)
        self.assertEqual(result.matched_doc_ids, ["doc-1"])
        self.assertEqual(result.missing_doc_ids, [])
        self.assertEqual(result.top_chunks[0]["chunk_id"], "doc-1:0")
        self.assertIsInstance(result.trace, RagTrace)
        self.assertEqual(result.trace.query, "RAG 检索工具")
        self.assertGreaterEqual(result.trace.duration_ms, 0.0)
        self.assertEqual(result.failure_reasons, [])

    def test_evaluate_reports_missing_doc_and_failure_reason(self):
        evaluator = RetrievalEvaluator(build_tool())
        test_case = RetrievalTestCase(
            query="RAG 检索工具",
            expected_doc_ids=["doc-2"],
            expected_chunk_keywords=["运行状态"],
            top_k=1,
        )

        result = evaluator.evaluate(test_case)

        self.assertFalse(result.hit)
        self.assertEqual(result.missing_doc_ids, ["doc-2"])
        self.assertIn("missing_doc_ids: doc-2", result.failure_reasons)
        self.assertIn(
            "missing_chunk_keywords: 运行状态",
            result.failure_reasons,
        )

    def test_test_case_rejects_invalid_top_k(self):
        with self.assertRaises(ValueError):
            RetrievalTestCase(
                query="RAG",
                expected_doc_ids=["doc-1"],
                expected_chunk_keywords=[],
                top_k=0,
            )


if __name__ == "__main__":
    unittest.main()

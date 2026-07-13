"""
本文件负责验证 RAG Trace 与 Retrieval Test 的评估行为。
本文件不测试文档解析、Chunk 切分、索引排序和 ToolExecutor 包装。
"""

import unittest

from my_agent.rag.retrieval.citation import CitationBuilder
from my_agent.rag.models import Chunk
from my_agent.rag.indexing.embedding import SimpleEmbeddingModel
from my_agent.rag.evaluation.eval import (
    RetrievalEvaluator,
    RetrievalEvalResult,
    RetrievalTestCase,
)
from my_agent.rag.indexing.index import InMemoryChunkIndex
from my_agent.rag.retrieval.reranker import SimpleReranker
from my_agent.rag.retrieval.retrieval_tool import RetrievalTool
from my_agent.rag.retrieval.retriever import HybridRetriever
from my_agent.rag.evaluation.trace import RagTrace
from my_agent.rag.retrieval.trace import RetrievalTrace


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
    def test_rag_trace_is_compatible_retrieval_trace_export(self):
        self.assertIs(RagTrace, RetrievalTrace)


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
        self.assertEqual(result.trace.requested_top_k, 1)
        self.assertGreaterEqual(result.trace.total_duration_ms, 0.0)
        self.assertEqual(result.failure_reasons, [])

    def test_evaluate_restores_trace_returned_by_retrieval_tool(self):
        tool = build_tool()
        evaluator = RetrievalEvaluator(tool)
        test_case = RetrievalTestCase(
            query="RAG 检索工具",
            expected_doc_ids=["doc-1"],
            expected_chunk_keywords=["检索能力"],
            top_k=1,
        )

        result = evaluator.evaluate(test_case)
        tool_trace = RetrievalTrace.from_dict(
            tool.run({"query": test_case.query, "top_k": test_case.top_k})[
                "retrieval_trace"
            ]
        )

        self.assertEqual(result.trace.query, tool_trace.query)
        self.assertEqual(result.trace.requested_top_k, tool_trace.requested_top_k)
        self.assertEqual(result.trace.retrieved_chunks, tool_trace.retrieved_chunks)
        self.assertEqual(result.trace.reranked_chunks, tool_trace.reranked_chunks)
        self.assertEqual(result.trace.citations, tool_trace.citations)

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

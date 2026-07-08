"""
本文件负责验证 RetrievalTool 的工具定义、参数处理和结构化返回。
本文件不测试文档解析、Chunk 切分和索引内部排序细节。
"""

import unittest

from my_agent.rag.citation import CitationBuilder
from my_agent.rag.document import Chunk
from my_agent.rag.embedding import SimpleEmbeddingModel
from my_agent.rag.index import InMemoryChunkIndex
from my_agent.rag.reranker import SimpleReranker
from my_agent.rag.retrieval_tool import RetrievalTool
from my_agent.rag.retriever import HybridRetriever
from my_agent.tools.executor import ToolExecutor
from my_agent.tools.registry import ToolRegistry
from my_agent.tools.schema import ToolCallRequest


def build_index():
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
                    "filename": "agentic-rag.md",
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
                    "filename": "checkpoint.md",
                },
            ),
        ]
    )
    return index


def build_tool():
    return RetrievalTool(
        retriever=HybridRetriever(build_index()),
        reranker=SimpleReranker(),
        citation_builder=CitationBuilder(),
    )


class RetrievalToolTest(unittest.TestCase):
    def test_definition_exposes_retrieval_search_schema(self):
        tool = build_tool()

        definition = tool.definition

        self.assertEqual(definition.name, "retrieval.search")
        self.assertIn("rag", definition.tags)
        self.assertEqual(definition.parameters["type"], "object")
        self.assertEqual(definition.parameters["required"], ["query"])
        self.assertEqual(
            definition.parameters["properties"]["top_k"]["type"],
            "integer",
        )
        self.assertEqual(
            definition.parameters["properties"]["top_k"]["default"],
            5,
        )

    def test_run_returns_chunks_and_citations(self):
        tool = build_tool()

        result = tool.run({"query": "RAG 检索工具", "top_k": 1})

        self.assertEqual(result["query"], "RAG 检索工具")
        self.assertEqual(len(result["chunks"]), 1)
        self.assertEqual(result["chunks"][0]["chunk_id"], "doc-1:0")
        self.assertEqual(result["chunks"][0]["doc_id"], "doc-1")
        self.assertEqual(
            result["chunks"][0]["content"],
            "Agentic RAG 会把检索能力封装为工具。",
        )
        self.assertGreater(result["chunks"][0]["final_score"], 0.0)
        self.assertIsNotNone(result["chunks"][0]["rerank_score"])
        self.assertEqual(len(result["citations"]), 1)
        self.assertEqual(result["citations"][0]["chunk_id"], "doc-1:0")
        self.assertEqual(
            result["citations"][0]["source"],
            "local://agentic-rag.md",
        )

    def test_run_uses_default_top_k(self):
        tool = build_tool()

        result = tool.run({"query": "Agent"})

        self.assertLessEqual(len(result["chunks"]), 5)

    def test_run_rejects_invalid_top_k(self):
        tool = build_tool()

        with self.assertRaises(ValueError):
            tool.run({"query": "RAG", "top_k": 21})

    def test_tool_executor_can_execute_retrieval_search(self):
        registry = ToolRegistry()
        registry.register(build_tool())
        executor = ToolExecutor(registry)

        result = executor.execute(
            ToolCallRequest(
                name="retrieval.search",
                arguments={"query": "RAG 检索工具", "top_k": 1},
                call_id="call-1",
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.call_id, "call-1")
        self.assertEqual(result.data["chunks"][0]["chunk_id"], "doc-1:0")


if __name__ == "__main__":
    unittest.main()

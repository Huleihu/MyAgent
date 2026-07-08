"""
本文件负责执行 RAG 检索测试用例，并输出可解释的评估结果。
本文件不负责文档解析、Chunk 切分、索引构建和检索工具注册。
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from my_agent.rag.retrieval_tool import RetrievalTool
from my_agent.rag.trace import RagTrace


@dataclass(frozen=True)
class RetrievalTestCase:
    """描述一条检索评估用例及其期望命中条件。"""

    query: str
    expected_doc_ids: list[str]
    expected_chunk_keywords: list[str]
    top_k: int = 5

    def __post_init__(self) -> None:
        if not isinstance(self.query, str) or not self.query.strip():
            raise ValueError("query must be a non-empty string")
        if not isinstance(self.expected_doc_ids, list) or not all(
            isinstance(doc_id, str) and doc_id.strip()
            for doc_id in self.expected_doc_ids
        ):
            raise ValueError("expected_doc_ids must be a list of non-empty string")
        if not isinstance(self.expected_chunk_keywords, list) or not all(
            isinstance(keyword, str) and keyword.strip()
            for keyword in self.expected_chunk_keywords
        ):
            raise ValueError(
                "expected_chunk_keywords must be a list of non-empty string"
            )
        if not isinstance(self.top_k, int) or self.top_k <= 0:
            raise ValueError("top_k must be a positive integer")


@dataclass(frozen=True)
class RetrievalEvalResult:
    """表示一次检索测试的命中状态、缺失项、Trace 和失败原因。"""

    hit: bool
    matched_doc_ids: list[str]
    missing_doc_ids: list[str]
    top_chunks: list[dict[str, Any]]
    trace: RagTrace
    failure_reasons: list[str]

    def __post_init__(self) -> None:
        if not isinstance(self.hit, bool):
            raise ValueError("hit must be a bool")
        if not isinstance(self.matched_doc_ids, list):
            raise ValueError("matched_doc_ids must be a list")
        if not isinstance(self.missing_doc_ids, list):
            raise ValueError("missing_doc_ids must be a list")
        if not isinstance(self.top_chunks, list):
            raise ValueError("top_chunks must be a list")
        if not isinstance(self.trace, RagTrace):
            raise ValueError("trace must be a RagTrace")
        if not isinstance(self.failure_reasons, list):
            raise ValueError("failure_reasons must be a list")


class RetrievalEvaluator:
    """通过 RetrievalTool 执行检索用例，并生成可解释评估结果。"""

    def __init__(self, retrieval_tool: RetrievalTool) -> None:
        if not isinstance(retrieval_tool, RetrievalTool):
            raise ValueError("retrieval_tool must be a RetrievalTool")
        self._retrieval_tool = retrieval_tool

    def evaluate(self, test_case: RetrievalTestCase) -> RetrievalEvalResult:
        """执行一条检索测试用例并判断命中结果。"""
        if not isinstance(test_case, RetrievalTestCase):
            raise ValueError("test_case must be a RetrievalTestCase")

        started_at = perf_counter()
        tool_result = self._retrieval_tool.run(
            {
                "query": test_case.query,
                "top_k": test_case.top_k,
            }
        )
        duration_ms = (perf_counter() - started_at) * 1000
        top_chunks = tool_result["chunks"]
        trace = RagTrace(
            query=test_case.query,
            retrieved_chunks=top_chunks,
            citations=tool_result["citations"],
            duration_ms=duration_ms,
        )

        matched_doc_ids = self._find_matched_doc_ids(
            expected_doc_ids=test_case.expected_doc_ids,
            top_chunks=top_chunks,
        )
        missing_doc_ids = [
            doc_id
            for doc_id in test_case.expected_doc_ids
            if doc_id not in matched_doc_ids
        ]
        missing_keywords = self._find_missing_keywords(
            expected_keywords=test_case.expected_chunk_keywords,
            top_chunks=top_chunks,
        )
        failure_reasons = self._build_failure_reasons(
            missing_doc_ids=missing_doc_ids,
            missing_keywords=missing_keywords,
            top_chunks=top_chunks,
            citations=tool_result["citations"],
        )

        return RetrievalEvalResult(
            hit=not failure_reasons,
            matched_doc_ids=matched_doc_ids,
            missing_doc_ids=missing_doc_ids,
            top_chunks=top_chunks,
            trace=trace,
            failure_reasons=failure_reasons,
        )

    def _find_matched_doc_ids(
        self,
        expected_doc_ids: list[str],
        top_chunks: list[dict[str, Any]],
    ) -> list[str]:
        """按期望顺序找出已经命中的 doc_id。"""
        returned_doc_ids = {
            chunk.get("doc_id")
            for chunk in top_chunks
        }
        return [
            doc_id
            for doc_id in expected_doc_ids
            if doc_id in returned_doc_ids
        ]

    def _find_missing_keywords(
        self,
        expected_keywords: list[str],
        top_chunks: list[dict[str, Any]],
    ) -> list[str]:
        """检查期望关键词是否出现在任一召回 Chunk 内容中。"""
        combined_content = "\n".join(
            str(chunk.get("content", ""))
            for chunk in top_chunks
        )
        return [
            keyword
            for keyword in expected_keywords
            if keyword not in combined_content
        ]

    def _build_failure_reasons(
        self,
        missing_doc_ids: list[str],
        missing_keywords: list[str],
        top_chunks: list[dict[str, Any]],
        citations: list[dict[str, Any]],
    ) -> list[str]:
        """根据缺失信息生成排查提示。"""
        reasons = []
        if missing_doc_ids:
            reasons.append(f"missing_doc_ids: {', '.join(missing_doc_ids)}")
        if missing_keywords:
            reasons.append(
                f"missing_chunk_keywords: {', '.join(missing_keywords)}"
            )
        if top_chunks and self._all_scores_zero(top_chunks, "keyword_score"):
            reasons.append("keyword_score 全低：关键词召回可能失败")
        if top_chunks and self._all_scores_zero(top_chunks, "vector_score"):
            reasons.append("vector_score 全低：Embedding 表达可能不足")
        if top_chunks and self._all_scores_zero(top_chunks, "final_score"):
            reasons.append("final_score 全低：融合分数可能异常")
        if top_chunks and not citations:
            reasons.append("citations 缺失：引用构造可能失败")
        if not top_chunks:
            reasons.append("未召回任何 Chunk：知识库可能没有答案")
        return reasons

    def _all_scores_zero(
        self,
        top_chunks: list[dict[str, Any]],
        score_field: str,
    ) -> bool:
        """判断某一类分数是否全部为 0。"""
        return all(
            float(chunk.get(score_field, 0.0)) == 0.0
            for chunk in top_chunks
        )

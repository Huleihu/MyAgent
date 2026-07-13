"""
本文件负责兼容导出 RAG 检索 Trace 数据模型。
运行期 Trace 属于 retrieval 子包，评估层只消费该模型而不反向被查询链路依赖。
"""

from my_agent.rag.retrieval.trace import RetrievalTrace

# 保留既有评估层导入路径和 isinstance 契约。
RagTrace = RetrievalTrace

__all__ = ["RagTrace"]

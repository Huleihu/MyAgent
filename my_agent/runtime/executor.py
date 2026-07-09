"""
本文件负责按 RuntimeGraph 的线性拓扑调度节点执行器。
本文件不直接依赖 ToolExecutor、RAG、LLM SDK 或具体 Agent Loop 实现。
"""

from __future__ import annotations

from typing import Any

from my_agent.runtime.context import RuntimeContext
from my_agent.runtime.graph import RuntimeGraph


class RuntimeExecutor:
    """按线性拓扑执行 Runtime 节点。"""

    def __init__(
        self,
        graph: RuntimeGraph,
        node_runners: dict[str, Any],
    ) -> None:
        if not isinstance(graph, RuntimeGraph):
            raise TypeError("graph must be a RuntimeGraph")
        if not isinstance(node_runners, dict):
            raise ValueError("node_runners must be a dict")

        self._graph = graph
        self._node_runners = dict(node_runners)

    def run(self, context: RuntimeContext) -> RuntimeContext:
        """按节点顺序执行工作流，并把每个节点输出写入上下文。"""
        if not isinstance(context, RuntimeContext):
            raise TypeError("context must be a RuntimeContext")

        for node in self._graph.linear_nodes():
            runner = self._node_runners.get(node.node_type)
            if runner is None:
                raise ValueError(f"missing node runner for type: {node.node_type}")
            output = runner.run(node, context)
            if not isinstance(output, dict):
                raise ValueError("node runner must return a dict")
            context.node_outputs[node.node_id] = output

        return context

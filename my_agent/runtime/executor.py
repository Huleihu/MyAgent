"""
本文件负责按 RuntimeGraph 的线性拓扑调度节点执行器。
本文件不直接依赖 ToolExecutor、RAG、LLM SDK 或具体 Agent Loop 实现。
"""

from __future__ import annotations

from time import perf_counter
from typing import Any

from my_agent.runtime.context import RuntimeContext
from my_agent.runtime.graph import RuntimeGraph
from my_agent.runtime.resolver import resolve_node_inputs
from my_agent.runtime.trace import NodeExecutionRecord


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
            inputs = resolve_node_inputs(node, context)
            started_at = perf_counter()
            try:
                output = runner.run(node, context, inputs)
                if not isinstance(output, dict):
                    raise ValueError("node runner must return a dict")
                context.node_outputs[node.node_id] = output
                context.add_node_trace(
                    self._build_success_trace(node, inputs, output, started_at)
                )
            except Exception as exc:
                context.add_node_trace(
                    self._build_failure_trace(node, inputs, exc, started_at)
                )
                raise

        return context

    def _build_success_trace(
        self,
        node: Any,
        inputs: dict[str, Any],
        output: dict[str, Any],
        started_at: float,
    ) -> NodeExecutionRecord:
        """构造节点成功执行记录。"""
        return NodeExecutionRecord(
            node_id=node.node_id,
            node_type=node.node_type,
            inputs=inputs,
            output=output,
            success=True,
            error=None,
            duration_ms=self._elapsed_ms(started_at),
        )

    def _build_failure_trace(
        self,
        node: Any,
        inputs: dict[str, Any],
        error: Exception,
        started_at: float,
    ) -> NodeExecutionRecord:
        """构造节点失败执行记录，并保留异常继续向外传播。"""
        return NodeExecutionRecord(
            node_id=node.node_id,
            node_type=node.node_type,
            inputs=inputs,
            output=None,
            success=False,
            error={
                "type": error.__class__.__name__,
                "message": str(error),
            },
            duration_ms=self._elapsed_ms(started_at),
        )

    def _elapsed_ms(self, started_at: float) -> float:
        """计算节点执行耗时，单位为毫秒。"""
        return (perf_counter() - started_at) * 1000

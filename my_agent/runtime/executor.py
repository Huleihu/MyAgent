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
from my_agent.state.checkpoint_recorder import CheckpointRecorder


class RuntimeExecutor:
    """按线性拓扑执行 Runtime 节点。"""

    def __init__(
        self,
        graph: RuntimeGraph,
        node_runners: dict[str, Any],
        checkpoint_recorder: CheckpointRecorder | None = None,
    ) -> None:
        if not isinstance(graph, RuntimeGraph):
            raise TypeError("graph must be a RuntimeGraph")
        if not isinstance(node_runners, dict):
            raise ValueError("node_runners must be a dict")

        self._graph = graph
        self._node_runners = dict(node_runners)
        self._checkpoint_recorder = checkpoint_recorder

    def bind_checkpoint_recorder(self, checkpoint_recorder: CheckpointRecorder) -> None:
        """为一次运行绑定状态保存器并传递给支持绑定的节点执行器。"""
        self._checkpoint_recorder = checkpoint_recorder
        for runner in self._node_runners.values():
            if hasattr(runner, "bind_run_state"):
                runner.bind_run_state(None, checkpoint_recorder)

    def first_node_id(self) -> str:
        """返回当前线性工作流首节点标识，供创建运行游标使用。"""
        return self._graph.linear_nodes()[0].node_id

    def bind_run_state(self, run_state, checkpoint_recorder: CheckpointRecorder) -> None:
        """为恢复运行绑定同一 RunState 与保存器。"""
        self._checkpoint_recorder = checkpoint_recorder
        for runner in self._node_runners.values():
            if hasattr(runner, "bind_run_state"):
                runner.bind_run_state(run_state, checkpoint_recorder)

    def run(self, context: RuntimeContext) -> RuntimeContext:
        """按节点顺序执行工作流，并把每个节点输出写入上下文。"""
        if not isinstance(context, RuntimeContext):
            raise TypeError("context must be a RuntimeContext")

        nodes = self._graph.linear_nodes()
        start_index = 0
        if context.run_state is not None:
            ids = [node.node_id for node in nodes]
            start_index = ids.index(context.run_state.cursor.next_node_id)
        for node in nodes[start_index:]:
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
                self._checkpoint_node_success(context, nodes, node)
            except Exception as exc:
                context.add_node_trace(
                    self._build_failure_trace(node, inputs, exc, started_at)
                )
                if context.run_state is not None:
                    context.run_state.status = __import__("my_agent.state.run_state", fromlist=["RunStatus"]).RunStatus.FAILED
                    context.run_state.error = {"type": exc.__class__.__name__, "message": str(exc)}
                    self._sync_run_state(context)
                    if self._checkpoint_recorder is not None:
                        self._checkpoint_recorder.record({"reason": "run_failed"})
                raise

        return context

    def _checkpoint_node_success(self, context, nodes, node) -> None:
        """节点输出与游标同步后再写入快照，保证恢复时可跳过成功节点。"""
        if context.run_state is None:
            return
        cursor = context.run_state.cursor
        if node.node_id not in cursor.completed_node_ids:
            cursor.completed_node_ids.append(node.node_id)
        current = [item.node_id for item in nodes].index(node.node_id)
        cursor.next_node_id = nodes[current + 1].node_id if current + 1 < len(nodes) else node.node_id
        self._sync_run_state(context)
        if self._checkpoint_recorder is not None:
            self._checkpoint_recorder.record({"reason": "after_node_success", "node_id": node.node_id})

    def _sync_run_state(self, context) -> None:
        context.run_state.variables = dict(context.variables)
        context.run_state.node_outputs = {key: dict(value) for key, value in context.node_outputs.items()}
        context.run_state.node_traces = context.list_node_traces()

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

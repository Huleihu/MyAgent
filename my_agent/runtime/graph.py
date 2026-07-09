"""
本文件负责根据工作流定义计算线性节点拓扑顺序。
本文件不执行节点，也不解析 DSL 原始输入。
"""

from __future__ import annotations

from my_agent.dsl.schema import NodeDefinition, WorkflowDefinition


class RuntimeGraph:
    """提供 JSON DSL v0.1 的线性拓扑访问能力。"""

    def __init__(self, workflow: WorkflowDefinition) -> None:
        if not isinstance(workflow, WorkflowDefinition):
            raise TypeError("workflow must be a WorkflowDefinition")
        self._workflow = workflow

    def linear_nodes(self) -> list[NodeDefinition]:
        """按 begin 到末尾节点的顺序返回节点列表。"""
        node_by_id = {node.node_id: node for node in self._workflow.nodes}
        target_ids = {edge.target for edge in self._workflow.edges}
        start_nodes = [
            node for node in self._workflow.nodes if node.node_id not in target_ids
        ]
        if len(start_nodes) != 1:
            raise ValueError("workflow must have exactly one start node")

        next_node_by_id = {
            edge.source: edge.target for edge in self._workflow.edges
        }
        ordered_nodes = [start_nodes[0]]
        visited_node_ids = {start_nodes[0].node_id}

        current_node_id = start_nodes[0].node_id
        while current_node_id in next_node_by_id:
            current_node_id = next_node_by_id[current_node_id]
            if current_node_id in visited_node_ids:
                raise ValueError("workflow contains a cycle")
            ordered_nodes.append(node_by_id[current_node_id])
            visited_node_ids.add(current_node_id)

        if len(ordered_nodes) != len(self._workflow.nodes):
            raise ValueError("workflow must be connected and linear")
        return ordered_nodes

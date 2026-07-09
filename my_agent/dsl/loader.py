"""
本文件负责把 JSON DSL 加载并校验为项目内部工作流定义。
本文件不负责执行节点，也不创建 Agent Loop、ToolExecutor 或模型客户端。
"""

from __future__ import annotations

import json
from typing import Any

from my_agent.dsl.schema import EdgeDefinition, NodeDefinition, WorkflowDefinition


SUPPORTED_NODE_TYPES = {"begin", "agent_loop", "message"}


class WorkflowLoader:
    """加载并校验 JSON DSL v0.1 工作流。"""

    def load_dict(self, workflow_data: dict[str, Any]) -> WorkflowDefinition:
        """从普通 dict 加载工作流定义。"""
        if not isinstance(workflow_data, dict):
            raise ValueError("workflow_data must be a dict")

        nodes = self._load_nodes(workflow_data.get("nodes"))
        edges = self._load_edges(workflow_data.get("edges"))
        workflow = WorkflowDefinition(
            workflow_id=workflow_data.get("workflow_id"),
            nodes=nodes,
            edges=edges,
        )
        self._validate_workflow(workflow)
        return workflow

    def load_json(self, workflow_json: str) -> WorkflowDefinition:
        """从 JSON 字符串加载工作流定义。"""
        if not isinstance(workflow_json, str) or not workflow_json.strip():
            raise ValueError("workflow_json must be a non-empty string")
        return self.load_dict(json.loads(workflow_json))

    def _load_nodes(self, nodes_data: Any) -> list[NodeDefinition]:
        """加载节点定义，并限制 v0.1 仅支持三类节点。"""
        if not isinstance(nodes_data, list):
            raise ValueError("nodes must be a list")

        nodes: list[NodeDefinition] = []
        for node_data in nodes_data:
            if not isinstance(node_data, dict):
                raise ValueError("node must be a dict")
            node = NodeDefinition(
                node_id=node_data.get("node_id"),
                node_type=node_data.get("node_type"),
                inputs=node_data.get("inputs", {}),
            )
            if node.node_type not in SUPPORTED_NODE_TYPES:
                raise ValueError(f"unsupported node_type: {node.node_type}")
            nodes.append(node)
        return nodes

    def _load_edges(self, edges_data: Any) -> list[EdgeDefinition]:
        """加载边定义。"""
        if not isinstance(edges_data, list):
            raise ValueError("edges must be a list")

        edges: list[EdgeDefinition] = []
        for edge_data in edges_data:
            if not isinstance(edge_data, dict):
                raise ValueError("edge must be a dict")
            edges.append(
                EdgeDefinition(
                    source=edge_data.get("source"),
                    target=edge_data.get("target"),
                )
            )
        return edges

    def _validate_workflow(self, workflow: WorkflowDefinition) -> None:
        """校验节点唯一性、边引用和 v0.1 线性拓扑约束。"""
        node_ids = [node.node_id for node in workflow.nodes]
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("node_id must be unique")

        node_id_set = set(node_ids)
        for edge in workflow.edges:
            if edge.source not in node_id_set or edge.target not in node_id_set:
                raise ValueError("edge must reference existing nodes")

        self._validate_linear_edges(workflow)

    def _validate_linear_edges(self, workflow: WorkflowDefinition) -> None:
        """校验 v0.1 只允许单入口、单出口、无分支的线性流程。"""
        if len(workflow.nodes) == 1:
            if workflow.edges:
                raise ValueError("single-node workflow must not contain edges")
            return

        if len(workflow.edges) != len(workflow.nodes) - 1:
            raise ValueError("workflow must be a linear graph")

        incoming_count = {node.node_id: 0 for node in workflow.nodes}
        outgoing_count = {node.node_id: 0 for node in workflow.nodes}
        for edge in workflow.edges:
            outgoing_count[edge.source] += 1
            incoming_count[edge.target] += 1
            if outgoing_count[edge.source] > 1 or incoming_count[edge.target] > 1:
                raise ValueError("workflow must be a linear graph")

        start_nodes = [
            node_id for node_id, count in incoming_count.items() if count == 0
        ]
        end_nodes = [node_id for node_id, count in outgoing_count.items() if count == 0]
        if len(start_nodes) != 1 or len(end_nodes) != 1:
            raise ValueError("workflow must have one start node and one end node")

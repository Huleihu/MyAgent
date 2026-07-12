"""
本文件负责把 JSON DSL 加载并校验为项目内部工作流定义。
本文件不负责执行节点，也不创建 Agent Loop、ToolExecutor 或模型客户端。
"""

from __future__ import annotations

import json
import re
from typing import Any

from my_agent.dsl.schema import (
    NODE_CONTRACTS,
    EdgeDefinition,
    NodeDefinition,
    WorkflowDefinition,
)


SUPPORTED_NODE_TYPES = {"begin", "agent_loop", "message"}
_NODE_OUTPUT_REFERENCE_PATTERN = re.compile(
    r"^\{\{(?P<node_id>[^.\s{}]+)\.(?P<output_key>[^.\s{}]+)\}\}$"
)


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
                inputs=self._normalize_reference_inputs(node_data.get("inputs", {})),
            )
            if node.node_type not in SUPPORTED_NODE_TYPES:
                raise ValueError(f"unsupported node_type: {node.node_type}")
            nodes.append(node)
        return nodes

    def _normalize_reference_inputs(self, inputs: Any) -> Any:
        """只规范化完整引用的外围空白，普通字符串保持原样。"""
        if not isinstance(inputs, dict):
            return inputs
        return {
            input_name: self._normalize_reference_value(input_value)
            for input_name, input_value in inputs.items()
        }

    def _normalize_reference_value(self, input_value: Any) -> Any:
        """去除候选精确引用外围空白，避免加载期与执行期语义不一致。"""
        if not isinstance(input_value, str):
            return input_value
        stripped_value = input_value.strip()
        if stripped_value.startswith("{{") and stripped_value.endswith("}}"):
            return stripped_value
        return input_value

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

        linear_nodes = self._validate_linear_edges(workflow)
        self._validate_node_contracts(linear_nodes)
        self._validate_input_references(linear_nodes)

    def _validate_linear_edges(self, workflow: WorkflowDefinition) -> list[NodeDefinition]:
        """校验 v0.1 只允许单入口、单出口、无分支的线性流程。"""
        if len(workflow.nodes) == 1:
            if workflow.edges:
                raise ValueError("single-node workflow must not contain edges")
            return list(workflow.nodes)

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
            if not start_nodes or not end_nodes:
                raise ValueError(
                    "workflow contains a cycle and must have one start and one end node"
                )
            raise ValueError("workflow must have one start node and one end node")

        node_by_id = {node.node_id: node for node in workflow.nodes}
        next_node_by_id = {edge.source: edge.target for edge in workflow.edges}
        linear_nodes: list[NodeDefinition] = []
        visited_node_ids: set[str] = set()
        current_node_id = start_nodes[0]
        while True:
            if current_node_id in visited_node_ids:
                raise ValueError("workflow contains a cycle")
            linear_nodes.append(node_by_id[current_node_id])
            visited_node_ids.add(current_node_id)
            if current_node_id not in next_node_by_id:
                break
            current_node_id = next_node_by_id[current_node_id]

        if len(linear_nodes) != len(workflow.nodes):
            raise ValueError("workflow must be connected and must not contain isolated nodes")
        return linear_nodes

    def _validate_node_contracts(self, linear_nodes: list[NodeDefinition]) -> None:
        """校验节点输入是否符合 v0.1 的静态契约。"""
        for node in linear_nodes:
            contract = NODE_CONTRACTS[node.node_type]
            for input_name in sorted(contract.required_inputs - node.inputs.keys()):
                raise self._node_error(
                    node,
                    f"input={input_name}: missing required input",
                )
            for input_name in sorted(set(node.inputs) - contract.allowed_inputs):
                raise self._node_error(
                    node,
                    f"input={input_name}: undeclared input",
                )

    def _validate_input_references(self, linear_nodes: list[NodeDefinition]) -> None:
        """校验精确引用指向已执行节点声明的固定输出。"""
        node_index_by_id = {
            node.node_id: index for index, node in enumerate(linear_nodes)
        }
        node_by_id = {node.node_id: node for node in linear_nodes}

        for current_index, node in enumerate(linear_nodes):
            for input_name, input_value in node.inputs.items():
                self._validate_input_reference(
                    node=node,
                    current_index=current_index,
                    input_name=input_name,
                    input_value=input_value,
                    node_index_by_id=node_index_by_id,
                    node_by_id=node_by_id,
                )

    def _validate_input_reference(
        self,
        node: NodeDefinition,
        current_index: int,
        input_name: str,
        input_value: Any,
        node_index_by_id: dict[str, int],
        node_by_id: dict[str, NodeDefinition],
    ) -> None:
        """校验单个输入值；只识别完整的 v0.1 引用表达式。"""
        if not isinstance(input_value, str):
            return
        reference = input_value.strip()
        if not (reference.startswith("{{") and reference.endswith("}}")):
            return
        if reference == "{{user_input}}":
            return

        reference_match = _NODE_OUTPUT_REFERENCE_PATTERN.fullmatch(reference)
        if reference_match is None:
            raise self._node_error(
                node,
                f"input={input_name}, reference={reference}: unsupported reference format",
            )

        referenced_node_id = reference_match.group("node_id")
        output_key = reference_match.group("output_key")
        if referenced_node_id not in node_by_id:
            raise self._node_error(
                node,
                f"input={input_name}, reference={reference}: referenced node does not exist",
            )
        if node_index_by_id[referenced_node_id] >= current_index:
            raise self._node_error(
                node,
                f"input={input_name}, reference={reference}: referenced node is a later node or current node",
            )

        referenced_node = node_by_id[referenced_node_id]
        if output_key not in NODE_CONTRACTS[referenced_node.node_type].fixed_outputs:
            raise self._node_error(
                node,
                f"input={input_name}, reference={reference}: output field does not exist",
            )

    def _node_error(self, node: NodeDefinition, reason: str) -> ValueError:
        """构造可定位到节点和输入字段的 DSL 校验异常。"""
        return ValueError(
            f"node_id={node.node_id}, node_type={node.node_type}, {reason}"
        )

"""
本文件负责定义 JSON DSL 的工作流、节点和边数据模型。
本文件不负责加载 DSL，也不执行 Runtime 节点。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


def _validate_non_empty_text(field_name: str, field_value: str) -> None:
    """校验 DSL 标识字段，避免生成不可追踪的工作流结构。"""
    if not isinstance(field_value, str) or not field_value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True)
class NodeContract:
    """描述一种 DSL 节点的静态输入输出契约。"""

    required_inputs: frozenset[str]
    allowed_inputs: frozenset[str]
    fixed_outputs: frozenset[str]

    def __post_init__(self) -> None:
        """校验契约字段，确保 Loader 可安全进行静态校验。"""
        contract_fields = {
            "required_inputs": self.required_inputs,
            "allowed_inputs": self.allowed_inputs,
            "fixed_outputs": self.fixed_outputs,
        }
        for field_name, field_value in contract_fields.items():
            if not isinstance(field_value, frozenset) or not all(
                isinstance(item, str) and item.strip() for item in field_value
            ):
                raise ValueError(f"{field_name} must be a frozenset of non-empty strings")
        if not self.required_inputs.issubset(self.allowed_inputs):
            raise ValueError("required_inputs must be included in allowed_inputs")


# 契约只表达 DSL 静态接口，不依赖 Runtime Runner 或执行对象。
NODE_CONTRACTS: Mapping[str, NodeContract] = MappingProxyType(
    {
        "begin": NodeContract(frozenset(), frozenset(), frozenset({"user_input"})),
        "agent_loop": NodeContract(
            frozenset({"user_input"}),
            frozenset({"user_input"}),
            frozenset({"output"}),
        ),
        "message": NodeContract(
            frozenset({"content"}),
            frozenset({"content"}),
            frozenset({"content"}),
        ),
    }
)


@dataclass(frozen=True)
class NodeDefinition:
    """描述 JSON DSL 中的一个运行节点。"""

    node_id: str
    node_type: str
    inputs: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _validate_non_empty_text("node_id", self.node_id)
        _validate_non_empty_text("node_type", self.node_type)
        if not isinstance(self.inputs, dict):
            raise ValueError("inputs must be a dict")


@dataclass(frozen=True)
class EdgeDefinition:
    """描述 JSON DSL 中两个节点之间的有向边。"""

    source: str
    target: str

    def __post_init__(self) -> None:
        _validate_non_empty_text("source", self.source)
        _validate_non_empty_text("target", self.target)
        if self.source == self.target:
            raise ValueError("edge source and target must be different")


@dataclass(frozen=True)
class WorkflowDefinition:
    """描述一个 JSON DSL 工作流的静态结构。"""

    workflow_id: str
    nodes: list[NodeDefinition]
    edges: list[EdgeDefinition]

    def __post_init__(self) -> None:
        _validate_non_empty_text("workflow_id", self.workflow_id)
        if not isinstance(self.nodes, list) or not all(
            isinstance(node, NodeDefinition) for node in self.nodes
        ):
            raise ValueError("nodes must be a list[NodeDefinition]")
        if not isinstance(self.edges, list) or not all(
            isinstance(edge, EdgeDefinition) for edge in self.edges
        ):
            raise ValueError("edges must be a list[EdgeDefinition]")
        if not self.nodes:
            raise ValueError("workflow must contain at least one node")

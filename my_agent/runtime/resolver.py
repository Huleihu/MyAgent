"""
本文件负责解析 Runtime v0.1 的节点输入引用。
本文件不执行节点，也不写入 RuntimeContext。
"""

from __future__ import annotations

from typing import Any

from my_agent.dsl.schema import NodeDefinition
from my_agent.runtime.context import RuntimeContext


def resolve_runtime_value(input_value: Any, context: RuntimeContext) -> Any:
    """解析 Runtime v0.1 的精确引用，不支持复杂表达式。"""
    if not isinstance(input_value, str):
        return input_value

    if input_value == "{{user_input}}":
        return context.user_input

    if input_value.startswith("{{") and input_value.endswith("}}"):
        reference = input_value[2:-2].strip()
        parts = reference.split(".")
        if len(parts) == 2:
            node_id, output_key = parts
            return context.node_outputs[node_id][output_key]
        raise ValueError(f"unsupported runtime reference: {input_value}")

    return input_value


def resolve_node_inputs(
    node: NodeDefinition,
    context: RuntimeContext,
) -> dict[str, Any]:
    """解析节点全部输入字段，返回执行时使用的真实输入快照。"""
    if not isinstance(node, NodeDefinition):
        raise TypeError("node must be a NodeDefinition")
    if not isinstance(context, RuntimeContext):
        raise TypeError("context must be a RuntimeContext")
    return {
        input_name: resolve_runtime_value(input_value, context)
        for input_name, input_value in node.inputs.items()
    }

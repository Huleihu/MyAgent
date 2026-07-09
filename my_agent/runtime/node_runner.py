"""
本文件负责实现 Runtime v0.1 支持的 begin、agent_loop 和 message 节点。
本文件不负责整体调度，也不直接依赖 ToolExecutor、RAG 或 LLM SDK。
"""

from __future__ import annotations

from typing import Any

from my_agent.dsl.schema import NodeDefinition
from my_agent.runtime.context import RuntimeContext


class BeginNodeRunner:
    """执行 begin 节点，把用户输入放入节点输出。"""

    def run(
        self,
        node: NodeDefinition,
        context: RuntimeContext,
    ) -> dict[str, Any]:
        """返回 Runtime 初始用户输入。"""
        return {"user_input": context.user_input}


class AgentLoopNodeRunner:
    """执行 agent_loop 节点，并通过构造参数注入已有 ReActAgentLoop。"""

    def __init__(self, agent_loop: Any) -> None:
        if not hasattr(agent_loop, "run"):
            raise TypeError("agent_loop must provide run(user_input)")
        self._agent_loop = agent_loop

    def run(
        self,
        node: NodeDefinition,
        context: RuntimeContext,
    ) -> dict[str, Any]:
        """调用已注入的 Agent Loop，并返回最终回答。"""
        user_input = self._resolve_input(node.inputs.get("user_input"), context)
        answer = self._agent_loop.run(user_input)
        return {"output": answer}

    def _resolve_input(self, input_value: Any, context: RuntimeContext) -> Any:
        """解析 v0.1 支持的最小输入引用表达式。"""
        if input_value is None:
            return context.user_input
        return resolve_runtime_value(input_value, context)


class MessageNodeRunner:
    """执行 message 节点，把最终消息写入 Runtime 变量。"""

    def run(
        self,
        node: NodeDefinition,
        context: RuntimeContext,
    ) -> dict[str, Any]:
        """解析消息内容，并记录为 last_message。"""
        content = resolve_runtime_value(node.inputs.get("content"), context)
        if not isinstance(content, str) or not content.strip():
            raise ValueError("message content must be a non-empty string")

        context.variables["last_message"] = content
        return {"content": content}


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

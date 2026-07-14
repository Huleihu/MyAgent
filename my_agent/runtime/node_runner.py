"""
本文件负责实现 Runtime v0.1 支持的 begin、agent_loop 和 message 节点。
本文件不负责整体调度、输入引用解析或 Trace 记录，也不直接依赖 ToolExecutor、RAG 或 LLM SDK。
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
        inputs: dict[str, Any],
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
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """调用已注入的 Agent Loop，并返回最终回答。"""
        user_input = inputs["user_input"]
        answer = self._agent_loop.run(user_input)
        return {"output": answer}

    def bind_run_state(self, run_state, checkpoint_recorder) -> None:
        """为当前回合绑定恢复状态；不会替换已注入的 Planner 或工具执行器。"""
        self._agent_loop._run_state = run_state
        self._agent_loop._checkpoint_recorder = checkpoint_recorder


class MessageNodeRunner:
    """执行 message 节点，把最终消息写入 Runtime 变量。"""

    def run(
        self,
        node: NodeDefinition,
        context: RuntimeContext,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        """解析消息内容，并记录为 last_message。"""
        content = inputs["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("message content must be a non-empty string")

        context.variables["last_message"] = content
        return {"content": content}

"""
本文件负责提供面向用户消息的 Runtime 对话触发入口与回合结果快照。
本文件不执行节点、不写入会话消息，也不负责持久化、并发或会话恢复。
"""

from __future__ import annotations

from dataclasses import dataclass

from my_agent.runtime.context import RuntimeContext
from my_agent.runtime.executor import RuntimeExecutor
from my_agent.runtime.trace import NodeExecutionRecord
from my_agent.state.session import SessionState
from my_agent.state.trace import ToolTraceRecord


@dataclass(frozen=True)
class ConversationTurnResult:
    """保存一次对话回合的最终文本、上下文及 Trace 快照。"""

    output_text: str
    runtime_context: RuntimeContext
    node_traces: tuple[NodeExecutionRecord, ...]
    tool_traces: tuple[ToolTraceRecord, ...]

    def __post_init__(self) -> None:
        """校验回合结果的公开字段，不把可变上下文误称为不可变。"""
        if not isinstance(self.output_text, str) or not self.output_text.strip():
            raise ValueError("output_text must be a non-empty string")
        if not isinstance(self.runtime_context, RuntimeContext):
            raise TypeError("runtime_context must be a RuntimeContext")
        if not isinstance(self.node_traces, tuple) or not all(
            isinstance(trace, NodeExecutionRecord) for trace in self.node_traces
        ):
            raise ValueError("node_traces must be a tuple[NodeExecutionRecord, ...]")
        if not isinstance(self.tool_traces, tuple) or not all(
            isinstance(trace, ToolTraceRecord) for trace in self.tool_traces
        ):
            raise ValueError("tool_traces must be a tuple[ToolTraceRecord, ...]")


class ConversationRuntime:
    """以复用会话状态和独立回合上下文触发 Runtime 执行。"""

    def __init__(self, executor: RuntimeExecutor, session_state: SessionState) -> None:
        if not isinstance(executor, RuntimeExecutor):
            raise TypeError("executor must be a RuntimeExecutor")
        if not isinstance(session_state, SessionState):
            raise TypeError("session_state must be a SessionState")

        self._executor = executor
        self._session_state = session_state

    def chat(self, user_input: str) -> ConversationTurnResult:
        """执行一轮串行对话并返回本轮独立上下文与 Trace 快照。"""
        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("user_input must be a non-empty string")

        tool_trace_start_index = len(self._session_state.list_tool_traces())
        runtime_context = RuntimeContext(
            user_input=user_input,
            session_state=self._session_state,
        )
        self._executor.run(runtime_context)

        output_text = self._read_last_message(runtime_context)
        node_traces = tuple(runtime_context.list_node_traces())
        tool_traces = tuple(
            self._session_state.list_tool_traces()[tool_trace_start_index:]
        )
        return ConversationTurnResult(
            output_text=output_text,
            runtime_context=runtime_context,
            node_traces=node_traces,
            tool_traces=tool_traces,
        )

    def _read_last_message(self, runtime_context: RuntimeContext) -> str:
        """读取 message 节点约定写入的最终文本，并转换为明确错误。"""
        if "last_message" not in runtime_context.variables:
            raise ValueError(
                "ConversationRuntime output contract failed: last_message is missing"
            )

        output_text = runtime_context.variables["last_message"]
        if not isinstance(output_text, str) or not output_text.strip():
            raise ValueError(
                "ConversationRuntime output contract failed: "
                "last_message must be a non-empty string"
            )
        return output_text

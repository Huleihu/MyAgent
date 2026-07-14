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
from my_agent.state.checkpoint_recorder import CheckpointRecorder
from my_agent.state.checkpoint_store import CheckpointStore, InMemoryCheckpointStore
from my_agent.state.run_state import ExecutionCursor, RunState, RunStatus
from uuid import uuid4


class RunNotFoundError(ValueError):
    """表示指定运行不存在可恢复 Checkpoint。"""


class RunAlreadyCompletedError(ValueError):
    """表示已完成运行不能再次恢复。"""


@dataclass(frozen=True)
class ConversationTurnResult:
    """保存一次对话回合的最终文本、上下文及 Trace 快照。"""

    output_text: str
    runtime_context: RuntimeContext
    node_traces: tuple[NodeExecutionRecord, ...]
    tool_traces: tuple[ToolTraceRecord, ...]
    run_id: str | None = None

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

    def __init__(self, executor: RuntimeExecutor, session_state: SessionState, checkpoint_store: CheckpointStore | None = None, workflow_id: str = "runtime-workflow") -> None:
        if not isinstance(executor, RuntimeExecutor):
            raise TypeError("executor must be a RuntimeExecutor")
        if not isinstance(session_state, SessionState):
            raise TypeError("session_state must be a SessionState")

        self._executor = executor
        self._session_state = session_state
        self._checkpoint_store = InMemoryCheckpointStore() if checkpoint_store is None else checkpoint_store
        self._workflow_id = workflow_id

    def chat(self, user_input: str) -> ConversationTurnResult:
        """执行一轮串行对话并返回本轮独立上下文与 Trace 快照。"""
        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("user_input must be a non-empty string")

        return self.start(user_input)

    def start(self, user_input: str) -> ConversationTurnResult:
        """创建带唯一 run_id 的可持久化运行并执行当前回合。"""
        tool_trace_start_index = len(self._session_state.list_tool_traces())
        run_state = RunState(run_id=str(uuid4()), session_id=self._session_state.session_id, workflow_id=self._workflow_id, status=RunStatus.RUNNING, user_input=user_input, messages=self._session_state.list_messages(), tool_traces=self._session_state.list_tool_traces(), cursor=ExecutionCursor(next_node_id=self._executor.first_node_id()))
        recorder = CheckpointRecorder(self._session_state, run_state, self._checkpoint_store)
        self._executor.bind_run_state(run_state, recorder)
        runtime_context = RuntimeContext(
            user_input=user_input,
            session_state=self._session_state,
            run_state=run_state,
        )
        self._executor.run(runtime_context)
        run_state.status = RunStatus.COMPLETED
        run_state.cursor.agent_phase = "completed"
        run_state.messages = self._session_state.list_messages(); run_state.tool_traces = self._session_state.list_tool_traces()
        recorder.record({"reason": "run_completed"})

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
            run_id=run_state.run_id,
        )

    def resume(self, run_id: str) -> ConversationTurnResult:
        """从最新 Checkpoint 恢复未完成运行。"""
        checkpoint = self._checkpoint_store.get_latest(run_id)
        if checkpoint is None or checkpoint.run_state is None: raise RunNotFoundError("run_id not found")
        state = checkpoint.run_state
        if state.status is RunStatus.COMPLETED: raise RunAlreadyCompletedError("run is already completed")
        if state.session_id != self._session_state.session_id: raise ValueError("session_id does not match runtime")
        self._session_state.restore_snapshot(state.messages, state.tool_traces)
        recorder = CheckpointRecorder(self._session_state, state, self._checkpoint_store)
        self._executor.bind_run_state(state, recorder)
        context = RuntimeContext(state.user_input, dict(state.variables), dict(state.node_outputs), list(state.node_traces), self._session_state, state)
        self._executor.run(context)
        state.status = RunStatus.COMPLETED; state.cursor.agent_phase = "completed"; state.messages = self._session_state.list_messages(); state.tool_traces = self._session_state.list_tool_traces(); recorder.record({"reason": "run_completed"})
        return ConversationTurnResult(self._read_last_message(context), context, tuple(context.list_node_traces()), tuple(self._session_state.list_tool_traces()), run_id)

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

"""
本文件负责实现多轮 ReAct Agent Loop MVP。
本文件不实现真实 LLM 调用，也不直接依赖具体工具业务逻辑。
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from my_agent.agent_loop.planner import FinalAnswerAction, Planner, ToolAction
from my_agent.state.checkpoint_recorder import CheckpointRecorder
from my_agent.state.session import SessionState
from my_agent.state.run_state import PendingToolCall, RunState, RunStatus
from my_agent.tools.executor import ToolExecutor
from my_agent.tools.schema import ToolCallRequest, ToolCallResult


class ReActAgentLoop:
    """多轮 ReAct Agent Loop MVP。

    每一轮只支持一个 Planner 动作：
    - FinalAnswerAction：直接回答；
    - ToolAction：执行一次工具，把结果作为 observation 写回会话。

    后续支持并发 tool-calling 时，可把一轮扩展为多个 ToolAction。
    """

    def __init__(
        self,
        planner: Planner,
        tool_executor: ToolExecutor,
        session_state: SessionState,
        max_rounds: int = 5,
        checkpoint_recorder: CheckpointRecorder | None = None,
        run_state: RunState | None = None,
    ) -> None:
        if not isinstance(planner, Planner):
            raise TypeError("planner must be a Planner")
        if not isinstance(tool_executor, ToolExecutor):
            raise TypeError("tool_executor must be a ToolExecutor")
        if not isinstance(session_state, SessionState):
            raise TypeError("session_state must be a SessionState")
        if not isinstance(max_rounds, int) or max_rounds <= 0:
            raise ValueError("max_rounds must be a positive integer")
        if checkpoint_recorder is not None and not isinstance(
            checkpoint_recorder, CheckpointRecorder
        ):
            raise TypeError("checkpoint_recorder must be a CheckpointRecorder or None")

        self._planner = planner
        self._tool_executor = tool_executor
        self._session_state = session_state
        self._max_rounds = max_rounds
        self._checkpoint_recorder = checkpoint_recorder
        self._run_state = run_state

    def bind_run_state(
        self,
        run_state: RunState | None,
        checkpoint_recorder: CheckpointRecorder | None,
    ) -> None:
        """为当前 Runtime 回合绑定恢复状态，不替换 Planner 或工具执行器。"""
        if run_state is not None and not isinstance(run_state, RunState):
            raise TypeError("run_state must be a RunState or None")
        if checkpoint_recorder is not None and not isinstance(
            checkpoint_recorder, CheckpointRecorder
        ):
            raise TypeError(
                "checkpoint_recorder must be a CheckpointRecorder or None"
            )
        self._run_state = run_state
        self._checkpoint_recorder = checkpoint_recorder

    def run(self, user_input: str) -> str:
        """执行多轮 Agent Loop，并返回最终助手输出文本。"""
        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("user_input must be a non-empty string")

        if self._run_state is not None and self._run_state.cursor.agent_phase == "final_answer_written":
            return self._read_saved_final_answer()
        if self._run_state is None or self._run_state.cursor.agent_phase == "not_started":
            self._session_state.add_message("user", user_input)
            if self._run_state is not None:
                self._run_state.cursor.agent_phase = "planning"
                self._run_state.cursor.agent_round_index = 1
            self._record_checkpoint({"reason": "after_user_input", "round_index": 0})

        start_round = 1 if self._run_state is None else self._run_state.cursor.agent_round_index
        for round_index in range(start_round, self._max_rounds + 1):
            action = self._next_action(user_input)

            if isinstance(action, FinalAnswerAction):
                self._session_state.add_message("assistant", action.answer)
                if self._run_state is not None:
                    self._run_state.cursor.agent_phase = "final_answer_written"
                    self._run_state.cursor.agent_round_index = round_index
                self._record_checkpoint(
                    {"reason": "after_final_answer", "round_index": round_index}
                )
                return action.answer

            if isinstance(action, ToolAction):
                result = self._execute_tool_action(action)
                self._add_tool_observation(action, result)
                if self._run_state is not None:
                    self._run_state.pending_tool_call = None
                    self._run_state.cursor.agent_phase = "planning"
                    self._run_state.cursor.agent_round_index = round_index + 1
                self._record_checkpoint(
                    {
                        "reason": "after_tool_observation",
                        "round_index": round_index,
                        "tool_name": result.name,
                        "call_id": result.call_id,
                        "success": result.success,
                    }
                )
                continue

            raise ValueError("unsupported agent action")

        raise ValueError("Agent Loop exceeded max_rounds before final answer")

    def _execute_tool_action(self, action: ToolAction) -> ToolCallResult:
        """执行工具动作，并在缺少 call_id 时生成稳定可追踪的调用编号。"""
        call_id = action.call_id or str(uuid4())
        request = ToolCallRequest(
            name=action.tool_name,
            arguments=action.arguments,
            call_id=call_id,
        )
        if self._run_state is not None:
            self._run_state.pending_tool_call = PendingToolCall(action.tool_name, dict(action.arguments), call_id)
            self._run_state.cursor.agent_phase = "tool_pending"
            self._record_checkpoint({"reason": "before_tool_execution", "round_index": self._run_state.cursor.agent_round_index})
        return self._tool_executor.execute(request)

    def _next_action(self, user_input: str):
        """优先消费已持久化的待执行工具，避免恢复时再次规划。"""
        if self._run_state is not None and self._run_state.cursor.agent_phase == "tool_pending":
            pending = self._run_state.pending_tool_call
            if pending is None:
                raise ValueError("tool_pending phase requires pending_tool_call")
            return ToolAction(pending.tool_name, dict(pending.arguments), pending.call_id)
        return self._planner.plan(user_input, self._session_state)

    def _read_saved_final_answer(self) -> str:
        """从已持久化最终回答恢复 agent 节点输出。"""
        for message in reversed(self._session_state.list_messages()):
            if message.role == "assistant" and message.metadata.get("message_type") != "tool_observation":
                return message.content
        raise ValueError("final_answer_written phase requires an assistant answer")

    def _format_tool_result_message(self, result: ToolCallResult) -> str:
        """把工具结果压缩成可读摘要，避免把大块检索结果直接塞进消息。"""
        if result.success:
            data_text = json.dumps(result.data, ensure_ascii=False, sort_keys=True)
            return f"工具 {result.name} 执行成功，结果：{data_text}"

        error_text = json.dumps(result.error, ensure_ascii=False, sort_keys=True)
        return f"工具 {result.name} 执行失败，错误：{error_text}"

    def _add_tool_observation(self, action: ToolAction, result: ToolCallResult) -> None:
        """把工具执行结果作为 observation 写入会话，供下一轮 Planner 使用。"""
        self._session_state.add_message(
            "assistant",
            self._format_tool_result_message(result),
            metadata={
                "message_type": "tool_observation",
                "tool_name": result.name,
                "call_id": result.call_id,
                "arguments": dict(action.arguments),
                "success": result.success,
            },
        )

    def _record_checkpoint(self, metadata: dict[str, Any]) -> None:
        """在配置 Recorder 时记录会话快照。"""
        if self._run_state is not None:
            self._run_state.messages = self._session_state.list_messages()
            self._run_state.tool_traces = self._session_state.list_tool_traces()
            self._run_state.updated_at_utc = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        if self._checkpoint_recorder is None:
            return
        self._checkpoint_recorder.record(metadata)

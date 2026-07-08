"""
本文件负责实现单步 ReAct Agent Loop MVP。
本文件不实现真实 LLM 调用，也不直接依赖具体工具业务逻辑。
"""

from __future__ import annotations

import json
from uuid import uuid4

from my_agent.agent_loop.planner import FinalAnswerAction, Planner, ToolAction
from my_agent.state.session import SessionState
from my_agent.tools.executor import ToolExecutor
from my_agent.tools.schema import ToolCallRequest, ToolCallResult


class ReActAgentLoop:
    """单步 ReAct Agent Loop MVP。

    第一版只支持一次 Planner 决策：
    - FinalAnswerAction：直接回答；
    - ToolAction：执行一次工具并返回结果摘要。

    后续再扩展为多步 Thought-Action-Observation 循环。
    """

    def __init__(
        self,
        planner: Planner,
        tool_executor: ToolExecutor,
        session_state: SessionState,
    ) -> None:
        if not isinstance(planner, Planner):
            raise TypeError("planner must be a Planner")
        if not isinstance(tool_executor, ToolExecutor):
            raise TypeError("tool_executor must be a ToolExecutor")
        if not isinstance(session_state, SessionState):
            raise TypeError("session_state must be a SessionState")

        self._planner = planner
        self._tool_executor = tool_executor
        self._session_state = session_state

    def run(self, user_input: str) -> str:
        """执行一次单步 Agent Loop，并返回助手输出文本。"""
        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("user_input must be a non-empty string")

        self._session_state.add_message("user", user_input)
        action = self._planner.plan(user_input, self._session_state)

        if isinstance(action, FinalAnswerAction):
            self._session_state.add_message("assistant", action.answer)
            return action.answer

        if isinstance(action, ToolAction):
            result = self._execute_tool_action(action)
            message = self._format_tool_result_message(result)
            self._session_state.add_message(
                "assistant",
                message,
                metadata={
                    "tool_name": result.name,
                    "call_id": result.call_id,
                    "success": result.success,
                },
            )
            return message

        raise ValueError("unsupported agent action")

    def _execute_tool_action(self, action: ToolAction) -> ToolCallResult:
        """执行工具动作，并在缺少 call_id 时生成稳定可追踪的调用编号。"""
        call_id = action.call_id or str(uuid4())
        request = ToolCallRequest(
            name=action.tool_name,
            arguments=action.arguments,
            call_id=call_id,
        )
        return self._tool_executor.execute(request)

    def _format_tool_result_message(self, result: ToolCallResult) -> str:
        """把工具结果压缩成可读摘要，避免把大块检索结果直接塞进消息。"""
        if result.success:
            data_text = json.dumps(result.data, ensure_ascii=False, sort_keys=True)
            return f"工具 {result.name} 执行成功，结果：{data_text}"

        error_text = json.dumps(result.error, ensure_ascii=False, sort_keys=True)
        return f"工具 {result.name} 执行失败，错误：{error_text}"

"""
本文件负责把模型响应解析为 Agent Loop 可执行的规划动作。
本文件不直接调用具体模型供应商 SDK，也不读取模型配置。
"""

from __future__ import annotations

from typing import Any

from my_agent.agent_loop.planner import AgentAction, FinalAnswerAction, Planner, ToolAction
from my_agent.llm.client import ModelClient
from my_agent.state.session import SessionMessage, SessionState
from my_agent.tools.schema import ToolDefinition


class LLMPlanner(Planner):
    """通过模型客户端生成下一步 AgentAction。"""

    def __init__(
        self,
        model_client: ModelClient,
        tool_definitions: list[ToolDefinition],
    ) -> None:
        if not isinstance(model_client, ModelClient):
            raise TypeError("model_client must be a ModelClient")
        if not isinstance(tool_definitions, list) or not all(
            isinstance(tool_definition, ToolDefinition)
            for tool_definition in tool_definitions
        ):
            raise ValueError("tool_definitions must be a list[ToolDefinition]")

        self._model_client = model_client
        self._tool_definitions = list(tool_definitions)

    def plan(self, user_input: str, session: SessionState) -> AgentAction:
        """调用模型客户端，并把响应字典解析为下一步规划动作。"""
        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("user_input must be a non-empty string")
        if not isinstance(session, SessionState):
            raise TypeError("session must be a SessionState")

        response = self._model_client.chat(
            messages=self._build_model_messages(session.list_messages()),
            tool_definitions=self._build_tool_definitions(),
        )
        return self._parse_model_response(response)

    def _build_model_messages(
        self,
        messages: list[SessionMessage],
    ) -> list[dict[str, Any]]:
        """把会话消息转换为模型客户端可消费的普通字典。"""
        return [
            {
                "role": message.role,
                "content": message.content,
                "metadata": dict(message.metadata),
            }
            for message in messages
        ]

    def _build_tool_definitions(self) -> list[dict[str, Any]]:
        """把项目内部 ToolDefinition 转成模型客户端输入字典。"""
        return [
            {
                "name": tool_definition.name,
                "description": tool_definition.description,
                "parameters": dict(tool_definition.parameters),
                "tags": list(tool_definition.tags),
            }
            for tool_definition in self._tool_definitions
        ]

    def _parse_model_response(self, response: dict[str, Any]) -> AgentAction:
        """把模型响应字典解析为工具调用或最终回答动作。"""
        if not isinstance(response, dict):
            raise ValueError("model response must be a dict")

        response_type = response.get("type")
        if response_type == "tool_call":
            return self._parse_tool_call(response)
        if response_type == "final_answer":
            return self._parse_final_answer(response)
        raise ValueError("model response type must be tool_call or final_answer")

    def _parse_tool_call(self, response: dict[str, Any]) -> ToolAction:
        """解析模型工具调用响应，并保持工具参数为项目内置 dict。"""
        tool_name = response.get("tool_name")
        arguments = response.get("arguments")
        call_id = response.get("call_id")
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise ValueError("tool_call response requires non-empty tool_name")
        if not isinstance(arguments, dict):
            raise ValueError("tool_call response requires dict arguments")
        if call_id is not None and not isinstance(call_id, str):
            raise ValueError("tool_call response call_id must be a string or None")
        return ToolAction(tool_name=tool_name, arguments=arguments, call_id=call_id)

    def _parse_final_answer(self, response: dict[str, Any]) -> FinalAnswerAction:
        """解析模型最终回答响应。"""
        answer = response.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError("final_answer response requires non-empty answer")
        return FinalAnswerAction(answer=answer)

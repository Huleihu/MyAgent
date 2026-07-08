"""
本文件负责提供测试用 Fake 模型客户端。
本文件不解析 AgentAction，也不调用真实模型服务。
"""

from __future__ import annotations

from typing import Any


class FakeModelClient:
    """按预设顺序返回模型响应字典的离线客户端。"""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        if not isinstance(responses, list) or not all(
            isinstance(response, dict) for response in responses
        ):
            raise ValueError("responses must be a list[dict]")

        self._responses = list(responses)
        self._next_index = 0
        self.chat_calls: list[dict[str, Any]] = []

    def chat(
        self,
        messages: list[dict[str, Any]],
        tool_definitions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """记录模型请求并返回下一个预设响应。"""
        if not isinstance(messages, list):
            raise ValueError("messages must be a list")
        if not isinstance(tool_definitions, list):
            raise ValueError("tool_definitions must be a list")
        if self._next_index >= len(self._responses):
            raise ValueError("FakeModelClient has no remaining responses")

        self.chat_calls.append(
            {
                "messages": messages,
                "tool_definitions": tool_definitions,
            }
        )
        response = self._responses[self._next_index]
        self._next_index += 1
        return dict(response)

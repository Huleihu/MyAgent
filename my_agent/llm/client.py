"""
本文件负责定义模型调用客户端的最小协议。
本文件不解析 AgentAction，也不依赖具体模型供应商 SDK。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ModelClient(Protocol):
    """表示可接收会话消息和工具定义并返回模型响应字典的客户端。"""

    def chat(
        self,
        messages: list[dict[str, Any]],
        tool_definitions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """调用模型并返回原始或规范化后的模型响应字典。"""

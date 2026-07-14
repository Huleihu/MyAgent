"""
本文件负责把项目内部模型协议适配为 DeepSeek 官方 OpenAI 兼容 API。
本文件是唯一直接使用 OpenAI SDK 的模块，不向 Agent 核心泄漏 SDK 类型。
"""

from __future__ import annotations

import json
import re
from typing import Any

from my_agent.core.errors import ModelClientError, ModelResponseError
from my_agent.llm.config import ModelConfig


class DeepSeekModelClient:
    """调用 DeepSeek 并把响应转换为项目标准模型响应字典。"""

    def __init__(self, config: ModelConfig, sdk_client: Any = None) -> None:
        if not isinstance(config, ModelConfig):
            raise TypeError("config must be a ModelConfig")
        if config.provider.lower() != "deepseek":
            raise ValueError("config.provider must be deepseek")
        if not isinstance(config.api_key, str) or not config.api_key.strip():
            raise ValueError("DeepSeek api_key must be configured")
        if not isinstance(config.base_url, str) or not config.base_url.strip():
            raise ValueError("DeepSeek base_url must be configured")
        self._config = config
        self._sdk_client = sdk_client or self._create_sdk_client()

    def chat(self, messages: list[dict[str, Any]], tool_definitions: list[dict[str, Any]]) -> dict[str, Any]:
        """发送非流式请求，并返回项目规范化的单工具或最终回答响应。"""
        tool_name_map = self._build_tool_name_map(tool_definitions)
        provider_tools = self._build_provider_tools(tool_definitions, tool_name_map)
        provider_messages = self._build_provider_messages(messages, tool_name_map)
        request = {
            "model": self._config.model_name,
            "messages": provider_messages,
            "tools": provider_tools,
            "tool_choice": "auto",
            "stream": False,
            "extra_body": {"thinking": {"type": "disabled"}},
            "temperature": self._config.temperature,
        }
        if self._config.max_tokens is not None:
            request["max_tokens"] = self._config.max_tokens
        try:
            response = self._sdk_client.chat.completions.create(**request)
        except Exception as error:
            raise self._convert_sdk_error(error) from error
        return self._normalize_response(response, tool_name_map)

    def _create_sdk_client(self) -> Any:
        """仅在未注入测试客户端时创建 OpenAI SDK 客户端。"""
        try:
            from openai import OpenAI
        except ImportError as error:
            raise ModelClientError("未安装 DeepSeek 所需的 OpenAI SDK") from error
        return OpenAI(api_key=self._config.api_key, base_url=self._config.base_url, timeout=self._config.timeout_seconds)

    def _build_tool_name_map(self, definitions: list[dict[str, Any]]) -> dict[str, str]:
        """建立内部工具名到 Provider 安全名称的稳定映射并检测冲突。"""
        if not isinstance(definitions, list):
            raise ValueError("tool_definitions must be a list")
        mappings: dict[str, str] = {}
        provider_names: set[str] = set()
        for definition in definitions:
            if not isinstance(definition, dict):
                raise ValueError("tool definition must be a dict")
            internal_name = definition.get("name")
            if not isinstance(internal_name, str) or not internal_name.strip():
                raise ValueError("tool definition name must be a non-empty string")
            provider_name = re.sub(r"[^A-Za-z0-9_-]", "_", internal_name)
            if not provider_name or provider_name in provider_names:
                raise ModelResponseError("工具名称映射冲突")
            mappings[internal_name] = provider_name
            provider_names.add(provider_name)
        return mappings

    def _build_provider_tools(self, definitions: list[dict[str, Any]], name_map: dict[str, str]) -> list[dict[str, Any]]:
        """移除内部 tags 并转换为 DeepSeek Function Calling 工具定义。"""
        provider_tools = []
        for definition in definitions:
            name = definition["name"]
            description = definition.get("description")
            parameters = definition.get("parameters")
            if not isinstance(description, str) or not description.strip() or not isinstance(parameters, dict):
                raise ValueError("tool definition must include description and parameters")
            provider_tools.append({"type": "function", "function": {"name": name_map[name], "description": description, "parameters": parameters}})
        return provider_tools

    def _build_provider_messages(self, messages: list[dict[str, Any]], name_map: dict[str, str]) -> list[dict[str, Any]]:
        """把内部 observation 重建为 assistant tool_calls 与 role=tool 消息。"""
        if not isinstance(messages, list):
            raise ValueError("messages must be a list")
        provider_messages = []
        for message in messages:
            if not isinstance(message, dict):
                raise ValueError("message must be a dict")
            metadata = message.get("metadata", {})
            if isinstance(metadata, dict) and metadata.get("message_type") == "tool_observation":
                provider_messages.extend(self._build_tool_observation_messages(message, metadata, name_map))
                continue
            role = message.get("role")
            content = message.get("content")
            if role not in {"user", "assistant"} or not isinstance(content, str) or not content.strip():
                raise ModelResponseError("模型消息格式无效")
            provider_messages.append({"role": role, "content": content})
        return provider_messages

    def _build_tool_observation_messages(self, message: dict[str, Any], metadata: dict[str, Any], name_map: dict[str, str]) -> list[dict[str, Any]]:
        """将单条内部工具 observation 转换为 DeepSeek 标准的两条消息。"""
        tool_name = metadata.get("tool_name")
        call_id = metadata.get("call_id")
        arguments = metadata.get("arguments")
        content = message.get("content")
        if tool_name not in name_map or not isinstance(call_id, str) or not call_id.strip() or not isinstance(arguments, dict) or not isinstance(content, str) or not content.strip():
            raise ModelResponseError("工具 observation 缺少重建所需字段")
        return [{"role": "assistant", "content": None, "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name_map[tool_name], "arguments": json.dumps(arguments, ensure_ascii=False, sort_keys=True)}}]}, {"role": "tool", "tool_call_id": call_id, "content": content}]

    def _normalize_response(self, response: Any, name_map: dict[str, str]) -> dict[str, Any]:
        """验证 SDK 响应边界，并转换为项目内部字典。"""
        choices = getattr(response, "choices", None)
        if not isinstance(choices, list) or not choices:
            raise ModelResponseError("模型响应缺少 choices")
        message = getattr(choices[0], "message", None)
        if message is None:
            raise ModelResponseError("模型响应缺少 message")
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            if not isinstance(tool_calls, list) or len(tool_calls) != 1:
                raise ModelResponseError("当前 MVP 不支持一次返回多个工具调用")
            return self._normalize_tool_call(tool_calls[0], name_map)
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise ModelResponseError("模型响应缺少有效文本内容")
        return {"type": "final_answer", "answer": content}

    def _normalize_tool_call(self, tool_call: Any, name_map: dict[str, str]) -> dict[str, Any]:
        """反向映射 Provider 工具名并解析 JSON object 参数。"""
        call_id = getattr(tool_call, "id", None)
        function = getattr(tool_call, "function", None)
        provider_name = getattr(function, "name", None)
        arguments_text = getattr(function, "arguments", None)
        inverse_name_map = {provider_name: internal_name for internal_name, provider_name in name_map.items()}
        if not isinstance(call_id, str) or not call_id.strip() or provider_name not in inverse_name_map or not isinstance(arguments_text, str):
            raise ModelResponseError("模型工具调用格式无效")
        try:
            arguments = json.loads(arguments_text)
        except json.JSONDecodeError as error:
            raise ModelResponseError("模型工具参数不是合法 JSON") from error
        if not isinstance(arguments, dict):
            raise ModelResponseError("模型工具参数必须是 JSON object")
        return {"type": "tool_call", "tool_name": inverse_name_map[provider_name], "arguments": arguments, "call_id": call_id}

    def _convert_sdk_error(self, error: Exception) -> ModelClientError:
        """将 SDK 异常压缩为不含请求和密钥的项目错误。"""
        error_name = error.__class__.__name__
        if error_name == "AuthenticationError":
            return ModelClientError("DeepSeek 鉴权失败，请检查 API Key")
        if error_name == "RateLimitError":
            return ModelClientError("DeepSeek 服务限流，请稍后重试")
        if error_name == "APITimeoutError":
            return ModelClientError("DeepSeek 请求超时，请稍后重试")
        if error_name == "APIConnectionError":
            return ModelClientError("无法连接 DeepSeek 服务")
        if error_name == "APIStatusError":
            return ModelClientError("DeepSeek 服务返回异常状态")
        return ModelClientError("DeepSeek 模型调用失败")

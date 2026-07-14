"""
本文件负责读取模型 Provider 的环境变量并生成项目内部配置。
本文件不创建 SDK 客户端，也不参与 Agent 运行时执行。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from dotenv import load_dotenv

from my_agent.core.errors import ModelConfigurationError
from my_agent.llm.config import ModelConfig


@dataclass(frozen=True)
class DeepSeekSettings:
    """保存 DeepSeek 装配所需的通用模型配置与 Thinking 开关。"""

    model_config: ModelConfig
    thinking_enabled: bool


def load_model_settings(
    environment: Mapping[str, str] | None = None,
) -> DeepSeekSettings | None:
    """读取环境变量；未选择 Provider 时返回 None 以保持离线 Demo。"""
    if environment is None:
        # 部署环境优先于本地 .env，避免平台注入的密钥被开发文件覆盖。
        load_dotenv(override=False)
        environment = os.environ

    provider = _read_optional_text(environment, "MYAGENT_LLM_PROVIDER")
    if provider is None or provider.lower() == "demo":
        return None
    if provider.lower() != "deepseek":
        raise ModelConfigurationError("不支持的 MYAGENT_LLM_PROVIDER")

    api_key = _read_required_text(environment, "DEEPSEEK_API_KEY")
    thinking_enabled = _read_bool(environment, "MYAGENT_DEEPSEEK_THINKING_ENABLED", False)
    if thinking_enabled:
        raise ModelConfigurationError("当前 MVP 暂不支持 DeepSeek Thinking 模式")
    timeout_seconds = _read_positive_float(environment, "MYAGENT_LLM_TIMEOUT_SECONDS", 30.0)
    return DeepSeekSettings(
        model_config=ModelConfig(
            provider="deepseek",
            model_name=_read_text_with_default(environment, "MYAGENT_LLM_MODEL", "deepseek-v4-flash"),
            api_key=api_key,
            base_url=_read_text_with_default(environment, "MYAGENT_LLM_BASE_URL", "https://api.deepseek.com"),
            timeout_seconds=timeout_seconds,
        ),
        thinking_enabled=False,
    )


def _read_optional_text(environment: Mapping[str, str], name: str) -> str | None:
    """读取去除空白后的可选文本环境变量。"""
    raw_value = environment.get(name)
    if not isinstance(raw_value, str) or not raw_value.strip():
        return None
    return raw_value.strip()


def _read_required_text(environment: Mapping[str, str], name: str) -> str:
    """读取必填文本，错误信息只暴露变量名而不包含变量值。"""
    value = _read_optional_text(environment, name)
    if value is None:
        raise ModelConfigurationError(f"缺少必填环境变量 {name}")
    return value


def _read_text_with_default(environment: Mapping[str, str], name: str, default: str) -> str:
    """读取带默认值的非空文本；显式空值视为错误而非回退。"""
    raw_value = environment.get(name)
    if raw_value is None:
        return default
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ModelConfigurationError(f"{name} 不能为空")
    return raw_value.strip()


def _read_positive_float(environment: Mapping[str, str], name: str, default: float) -> float:
    """读取正数超时，拒绝无法转换或非正值。"""
    raw_value = _read_optional_text(environment, name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError as error:
        raise ModelConfigurationError(f"{name} 必须是正数") from error
    if value <= 0:
        raise ModelConfigurationError(f"{name} 必须是正数")
    return value


def _read_bool(environment: Mapping[str, str], name: str, default: bool) -> bool:
    """读取大小写不敏感的布尔环境变量。"""
    raw_value = _read_optional_text(environment, name)
    if raw_value is None:
        return default
    normalized_value = raw_value.lower()
    if normalized_value == "true":
        return True
    if normalized_value == "false":
        return False
    raise ModelConfigurationError(f"{name} 只能为 true 或 false")

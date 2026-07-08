"""
本文件负责保存模型调用所需的最小配置数据。
本文件不负责读取环境变量、加载配置文件或调用模型服务。
"""

from __future__ import annotations

from dataclasses import dataclass


def _validate_non_empty_text(field_name: str, field_value: str) -> None:
    """校验模型配置中的必填文本字段，避免后续适配器拿到空配置。"""
    if not isinstance(field_value, str) or not field_value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True)
class ModelConfig:
    """保存真实模型适配器未来可能需要的基础配置。"""

    provider: str
    model_name: str
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.0
    max_tokens: int | None = None
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        _validate_non_empty_text("provider", self.provider)
        _validate_non_empty_text("model_name", self.model_name)
        if self.api_key is not None and not isinstance(self.api_key, str):
            raise ValueError("api_key must be a string or None")
        if self.base_url is not None and not isinstance(self.base_url, str):
            raise ValueError("base_url must be a string or None")
        if not isinstance(self.temperature, (int, float)) or self.temperature < 0:
            raise ValueError("temperature must be a non-negative number")
        if self.max_tokens is not None and (
            not isinstance(self.max_tokens, int) or self.max_tokens <= 0
        ):
            raise ValueError("max_tokens must be a positive integer or None")
        if (
            not isinstance(self.timeout_seconds, (int, float))
            or self.timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a positive number")

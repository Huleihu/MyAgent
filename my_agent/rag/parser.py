"""
本文件负责定义 RAG 文档解析层的原始输入模型和解析器抽象接口。
本文件不负责具体文件格式解析，也不负责 Chunk 切分。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from my_agent.rag.document import Document


def _validate_non_empty_text(field_name: str, field_value: str) -> None:
    """校验解析输入的关键文本字段非空。"""
    if not isinstance(field_value, str) or not field_value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True)
class RawDocument:
    """表示尚未转换为标准 Document 的原始文档输入。"""

    source: str
    filename: str
    content: str | bytes
    metadata: dict[str, Any]

    def __post_init__(self) -> None:
        _validate_non_empty_text("source", self.source)
        _validate_non_empty_text("filename", self.filename)
        if not isinstance(self.content, (str, bytes)) or not self.content:
            raise ValueError("content must be a non-empty str or bytes")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dict")


class DocumentParser(ABC):
    """定义不同文件格式解析器必须实现的统一接口。"""

    supported_extensions: tuple[str, ...] = ()

    @abstractmethod
    def parse(self, raw_document: RawDocument) -> list[Document]:
        """将原始文档解析为一个或多个标准 Document。"""

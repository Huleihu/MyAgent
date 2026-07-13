"""
本文件负责定义 Markdown 结构块的内部数据模型和解析器协议。
本文件不依赖 markdown-it-py，也不负责将结构块组合为 RAG Chunk。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class BlockType(str, Enum):
    """表示第一版支持的 Markdown 正文结构类型。"""

    PARAGRAPH = "paragraph"
    LIST = "list"
    CODE = "code"
    OTHER = "other"


@dataclass(frozen=True)
class Heading:
    """表示 Markdown 标题的原始层级与文本。"""

    level: int
    title: str

    def __post_init__(self) -> None:
        if not isinstance(self.level, int) or not 1 <= self.level <= 6:
            raise ValueError("level must be an integer between 1 and 6")
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValueError("title must be a non-empty string")


@dataclass(frozen=True)
class MarkdownBlock:
    """表示从 Markdown 原文恢复出的一个可供 Chunker 组合的正文块。"""

    block_type: BlockType
    content: str
    heading_path: tuple[Heading, ...]
    start_offset: int
    end_offset: int

    def __post_init__(self) -> None:
        if not isinstance(self.block_type, BlockType):
            raise ValueError("block_type must be a BlockType")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("content must be a non-empty string")
        if not isinstance(self.heading_path, tuple) or not all(
            isinstance(heading, Heading) for heading in self.heading_path
        ):
            raise ValueError("heading_path must be a tuple[Heading, ...]")
        if not isinstance(self.start_offset, int) or self.start_offset < 0:
            raise ValueError("start_offset must be a non-negative integer")
        if not isinstance(self.end_offset, int) or self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")


class MarkdownBlockParser(Protocol):
    """定义 Markdown 原文到项目内部结构块的适配边界。"""

    def parse(self, content: str) -> list[MarkdownBlock]:
        """解析 Markdown 原文并返回有序正文结构块。"""

"""
本文件负责根据 MarkdownBlock 的章节结构组合可检索 Chunk。
本文件不依赖 markdown-it-py Token，也不负责 Markdown 语法解析、Embedding 或检索。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from my_agent.rag.indexing.markdown_blocks import (
    BlockType,
    Heading,
    MarkdownBlock,
    MarkdownBlockParser,
)
from my_agent.rag.models import Chunk, Document


@dataclass(frozen=True)
class _ChunkBody:
    """保存一个待输出 Chunk 的正文和其在源文档中的覆盖范围。"""

    content: str
    start_offset: int
    end_offset: int


class MarkdownStructureChunker:
    """按 Markdown 章节结构组合 Chunk，并仅对超长单块执行回退切分。"""

    def __init__(
        self,
        chunk_size: int,
        overlap: int = 0,
        block_parser: MarkdownBlockParser | None = None,
    ) -> None:
        if not isinstance(chunk_size, int) or chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer")
        if not isinstance(overlap, int) or overlap < 0:
            raise ValueError("overlap must be a non-negative integer")
        if overlap >= chunk_size:
            raise ValueError("overlap must be less than chunk_size")
        if block_parser is not None and not hasattr(block_parser, "parse"):
            raise TypeError("block_parser must provide parse(content)")

        self._chunk_size = chunk_size
        self._overlap = overlap
        if block_parser is None:
            # 默认实现仅在装配时引入，Chunker 的业务逻辑始终只面向内部 Parser 协议。
            from my_agent.rag.indexing.markdown_it_block_parser import (
                MarkdownItBlockParser,
            )

            block_parser = MarkdownItBlockParser()
        self._block_parser = block_parser

    def split(self, document: Document) -> list[Chunk]:
        """按章节路径组合单篇 Markdown 文档的正文块。"""
        if not isinstance(document, Document):
            raise ValueError("document must be a Document")

        blocks = self._block_parser.parse(document.content)
        if not isinstance(blocks, list) or not all(
            isinstance(block, MarkdownBlock) for block in blocks
        ):
            raise ValueError("block_parser must return a list[MarkdownBlock]")

        chunk_bodies: list[tuple[tuple[Heading, ...], _ChunkBody]] = []
        current_path: tuple[Heading, ...] | None = None
        current_blocks: list[MarkdownBlock] = []

        for block in blocks:
            if current_path is not None and block.heading_path != current_path:
                chunk_bodies.extend(self._flush_blocks(current_path, current_blocks))
                current_blocks = []
            current_path = block.heading_path
            current_blocks.append(block)

        if current_path is not None:
            chunk_bodies.extend(self._flush_blocks(current_path, current_blocks))

        return [
            self._build_chunk(document, chunk_index, heading_path, body)
            for chunk_index, (heading_path, body) in enumerate(chunk_bodies)
        ]

    def split_many(self, documents: Sequence[Document]) -> list[Chunk]:
        """按输入顺序切分多篇文档，并保持每篇文档独立编号。"""
        if isinstance(documents, (str, bytes)) or not isinstance(documents, Sequence):
            raise ValueError("documents must be a sequence of Document")
        chunks: list[Chunk] = []
        for document in documents:
            chunks.extend(self.split(document))
        return chunks

    def _flush_blocks(
        self,
        heading_path: tuple[Heading, ...],
        blocks: list[MarkdownBlock],
    ) -> list[tuple[tuple[Heading, ...], _ChunkBody]]:
        """在同一章节中优先装箱完整块，仅对放不下的单块回退切分。"""
        if not blocks:
            return []

        prefix = self._build_heading_prefix(heading_path)
        body_capacity = self._chunk_size - len(prefix)
        results: list[tuple[tuple[Heading, ...], _ChunkBody]] = []
        current_blocks: list[MarkdownBlock] = []

        for block in blocks:
            candidate_blocks = [*current_blocks, block]
            candidate_content = self._join_block_contents(candidate_blocks)
            if len(candidate_content) <= body_capacity:
                current_blocks.append(block)
                continue

            if current_blocks:
                results.append((heading_path, self._combine_blocks(current_blocks)))
                current_blocks = []

            if len(block.content) <= body_capacity:
                current_blocks.append(block)
                continue

            results.extend(
                (heading_path, body)
                for body in self._split_oversized_block(block, body_capacity)
            )

        if current_blocks:
            results.append((heading_path, self._combine_blocks(current_blocks)))
        return results

    def _build_heading_prefix(self, heading_path: tuple[Heading, ...]) -> str:
        """构造计入 chunk_size 的标题上下文，并为极长标题保留至少一个正文字符位。"""
        if not heading_path:
            return ""

        full_prefix = "\n".join(
            f"{'#' * heading.level} {heading.title}" for heading in heading_path
        ) + "\n\n"
        maximum_prefix_length = self._chunk_size - 1
        if len(full_prefix) <= maximum_prefix_length:
            return full_prefix

        # 标题上下文过长时仅保留最接近正文的标题，并截断标题文本以保证正文切分前进。
        nearest_heading = heading_path[-1]
        marker = f"{'#' * nearest_heading.level} "
        separator = "\n\n"
        title_capacity = maximum_prefix_length - len(marker) - len(separator)
        if title_capacity <= 0:
            return ""
        return marker + nearest_heading.title[:title_capacity] + separator

    def _join_block_contents(self, blocks: list[MarkdownBlock]) -> str:
        """使用固定空行分隔结构块，保留 Markdown 块之间的可读边界。"""
        return "\n\n".join(block.content for block in blocks)

    def _combine_blocks(self, blocks: list[MarkdownBlock]) -> _ChunkBody:
        """将连续结构块合并为一个正文范围，offset 覆盖首尾正文来源。"""
        return _ChunkBody(
            content=self._join_block_contents(blocks),
            start_offset=blocks[0].start_offset,
            end_offset=blocks[-1].end_offset,
        )

    def _split_oversized_block(
        self,
        block: MarkdownBlock,
        body_capacity: int,
    ) -> list[_ChunkBody]:
        """按类型回退切分超长块，确保每个循环都在源正文中前进。"""
        if body_capacity <= 0:
            raise ValueError("chunk_size leaves no room for block content")
        if block.block_type is BlockType.CODE:
            code_chunks = self._split_fenced_code(block, body_capacity)
            if code_chunks is not None:
                return code_chunks
        # 第一版尚未做列表项级装箱；超长列表按字符回退，但不会静默丢失列表原文。
        return self._split_text(block.content, block.start_offset, body_capacity)

    def _split_text(
        self,
        content: str,
        start_offset: int,
        body_capacity: int,
    ) -> list[_ChunkBody]:
        """按固定字符和安全有效 overlap 切分正文，避免标题前缀压缩空间后停滞。"""
        effective_overlap = min(self._overlap, body_capacity - 1)
        step_size = body_capacity - effective_overlap
        chunks: list[_ChunkBody] = []
        start = 0
        while start < len(content):
            piece = content[start:start + body_capacity]
            chunks.append(
                _ChunkBody(
                    content=piece,
                    start_offset=start_offset + start,
                    end_offset=start_offset + start + len(piece),
                )
            )
            start += step_size
        return chunks

    def _split_fenced_code(
        self,
        block: MarkdownBlock,
        body_capacity: int,
    ) -> list[_ChunkBody] | None:
        """按行拆分超长 fenced code，并为每个子块补全围栏以保持 Markdown 可读。"""
        opening_match = re.match(r"^(?P<fence>`{3,}|~{3,})[^\r\n]*(?:\r\n|\n)", block.content)
        if opening_match is None:
            return None
        opening = opening_match.group(0)
        closing_match = re.search(
            r"(?P<newline>\r\n|\n)(?P<fence>`{3,}|~{3,})[ \t]*$",
            block.content,
        )
        if closing_match is None:
            return None
        closing = closing_match.group("fence")
        code_start = len(opening)
        # 闭合围栏前的换行属于代码正文，保留它可使拆分后的围栏仍处于独立行。
        code_end = closing_match.start() + len(closing_match.group("newline"))
        code_body = block.content[code_start:code_end]
        inner_capacity = body_capacity - len(opening) - len(closing)
        if inner_capacity <= 0:
            return None

        pieces: list[_ChunkBody] = []
        source_offset = block.start_offset + code_start
        current = ""
        current_start = 0
        consumed = 0
        for line in code_body.splitlines(keepends=True):
            if current and len(current) + len(line) > inner_capacity:
                pieces.append(
                    _ChunkBody(
                        content=opening + current + closing,
                        start_offset=source_offset + current_start,
                        end_offset=source_offset + consumed,
                    )
                )
                current = ""
                current_start = consumed
            if len(line) > inner_capacity:
                if current:
                    pieces.append(
                        _ChunkBody(
                            content=opening + current + closing,
                            start_offset=source_offset + current_start,
                            end_offset=source_offset + consumed,
                        )
                    )
                    current = ""
                    current_start = consumed
                for fragment in self._split_text(line, source_offset + consumed, inner_capacity):
                    pieces.append(
                        _ChunkBody(
                            content=opening + fragment.content + closing,
                            start_offset=fragment.start_offset,
                            end_offset=fragment.end_offset,
                        )
                    )
                consumed += len(line)
                current_start = consumed
                continue
            current += line
            consumed += len(line)
        if current:
            pieces.append(
                _ChunkBody(
                    content=opening + current + closing,
                    start_offset=source_offset + current_start,
                    end_offset=source_offset + consumed,
                )
            )
        return pieces or None

    def _build_chunk(
        self,
        document: Document,
        chunk_index: int,
        heading_path: tuple[Heading, ...],
        body: _ChunkBody,
    ) -> Chunk:
        """构造带序列化标题路径和源正文 offset 的最终 Chunk。"""
        prefix = self._build_heading_prefix(heading_path)
        content = prefix + body.content
        metadata = dict(document.metadata)
        metadata.update(
            {
                "source": document.source,
                "title": document.title,
                "chunk_index": chunk_index,
                "heading_path": [
                    {"level": heading.level, "title": heading.title}
                    for heading in heading_path
                ],
                "start_offset": body.start_offset,
                "end_offset": body.end_offset,
            }
        )
        return Chunk(
            chunk_id=f"{document.doc_id}:{chunk_index}",
            doc_id=document.doc_id,
            content=content,
            index=chunk_index,
            metadata=metadata,
        )

"""
本文件负责把 markdown-it-py Token 转换为项目内部 MarkdownBlock。
本文件是 RAG 索引层中唯一直接依赖和理解 markdown-it-py Token 的模块。
"""

from __future__ import annotations

from markdown_it import MarkdownIt
from markdown_it.token import Token

from my_agent.rag.indexing.markdown_blocks import (
    BlockType,
    Heading,
    MarkdownBlock,
)


class MarkdownItBlockParser:
    """使用 markdown-it-py 解析 Markdown 并恢复保留原格式的正文块。"""

    def __init__(self) -> None:
        self._markdown = MarkdownIt("commonmark")

    def parse(self, content: str) -> list[MarkdownBlock]:
        """将 Markdown 原文转换为带标题路径和字符偏移的结构块。"""
        if not isinstance(content, str):
            raise ValueError("content must be a string")
        if not content.strip():
            return []

        tokens = self._markdown.parse(content)
        line_starts = self._build_line_starts(content)
        heading_stack: list[Heading] = []
        blocks: list[MarkdownBlock] = []
        token_index = 0

        while token_index < len(tokens):
            token = tokens[token_index]
            if token.type == "heading_open":
                self._update_heading_stack(tokens, token_index, heading_stack)
                token_index += 3
                continue

            if token.type in {"bullet_list_open", "ordered_list_open"}:
                block = self._build_block_from_token(
                    token,
                    BlockType.LIST,
                    heading_stack,
                    content,
                    line_starts,
                )
                if block is not None:
                    blocks.append(block)
                token_index = self._skip_container(tokens, token_index)
                continue

            if token.type in {"blockquote_open"}:
                block = self._build_block_from_token(
                    token,
                    BlockType.OTHER,
                    heading_stack,
                    content,
                    line_starts,
                )
                if block is not None:
                    blocks.append(block)
                token_index = self._skip_container(tokens, token_index)
                continue

            block_type = self._block_type_for_token(token)
            if block_type is not None:
                block = self._build_block_from_token(
                    token,
                    block_type,
                    heading_stack,
                    content,
                    line_starts,
                )
                if block is not None:
                    blocks.append(block)

            token_index += 1

        return blocks

    def _update_heading_stack(
        self,
        tokens: list[Token],
        token_index: int,
        heading_stack: list[Heading],
    ) -> None:
        """按原始标题级别更新路径，跳级标题不重新编号。"""
        token = tokens[token_index]
        if token_index + 1 >= len(tokens) or tokens[token_index + 1].type != "inline":
            return
        level = int(token.tag[1:])
        title = tokens[token_index + 1].content.strip()
        if not title:
            return
        heading_stack[:] = [heading for heading in heading_stack if heading.level < level]
        heading_stack.append(Heading(level=level, title=title))

    def _block_type_for_token(self, token: Token) -> BlockType | None:
        """将拥有顶层行范围的 Token 映射为第一版支持的正文块类型。"""
        if token.type == "paragraph_open":
            return BlockType.PARAGRAPH
        if token.type in {"fence", "code_block"}:
            return BlockType.CODE
        if token.type in {"html_block", "hr"}:
            return BlockType.OTHER
        return None

    def _build_block_from_token(
        self,
        token: Token,
        block_type: BlockType,
        heading_stack: list[Heading],
        content: str,
        line_starts: list[int],
    ) -> MarkdownBlock | None:
        """利用顶层 Token 的行范围从原文恢复 Markdown，避免使用渲染后的纯文本。"""
        if token.map is None:
            return None
        start_offset = self._line_offset(token.map[0], line_starts, len(content))
        end_offset = self._line_offset(token.map[1], line_starts, len(content))
        raw_content = content[start_offset:end_offset].rstrip("\r\n")
        end_offset = start_offset + len(raw_content)
        if not raw_content.strip():
            return None
        return MarkdownBlock(
            block_type=block_type,
            content=raw_content,
            heading_path=tuple(heading_stack),
            start_offset=start_offset,
            end_offset=end_offset,
        )

    def _skip_container(self, tokens: list[Token], token_index: int) -> int:
        """跳过已整体恢复原文的列表或引用容器，避免内部段落重复输出。"""
        opening_token = tokens[token_index]
        opening_type = opening_token.type
        closing_type = opening_type.replace("_open", "_close")
        depth = 1
        next_index = token_index + 1
        while next_index < len(tokens) and depth:
            token_type = tokens[next_index].type
            if token_type == opening_type:
                depth += 1
            elif token_type == closing_type:
                depth -= 1
            next_index += 1
        return next_index

    def _build_line_starts(self, content: str) -> list[int]:
        """记录每行起始字符位置，兼容 LF 和 CRLF 的 Token 行范围转换。"""
        starts = [0]
        current_offset = 0
        for line in content.splitlines(keepends=True):
            current_offset += len(line)
            starts.append(current_offset)
        return starts

    def _line_offset(
        self,
        line_index: int,
        line_starts: list[int],
        content_length: int,
    ) -> int:
        """将 markdown-it-py 的行索引转换为原文字符偏移。"""
        if line_index < 0:
            return 0
        if line_index >= len(line_starts):
            return content_length
        return line_starts[line_index]

"""
本文件负责将 Markdown 原始文档解析为标准 RAG Document。
本文件不负责 Chunk 切分、Embedding 和检索。
"""

from __future__ import annotations

import re
from pathlib import Path

from my_agent.rag.document import Document
from my_agent.rag.parser import DocumentParser, RawDocument


class MarkdownDocumentParser(DocumentParser):
    """解析 Markdown 文档，并保留后续溯源所需 metadata。"""

    supported_extensions = (".md", ".markdown")

    def parse(self, raw_document: RawDocument) -> list[Document]:
        """解析 Markdown 文档，第一版一个文件生成一个 Document。"""
        content = self._decode_content(raw_document.content)
        headings = self._extract_headings(content)
        title = headings[0] if headings else raw_document.filename
        extension = Path(raw_document.filename).suffix.lower()

        metadata = dict(raw_document.metadata)
        metadata.update(
            {
                "source": raw_document.source,
                "filename": raw_document.filename,
                "extension": extension,
                "parser": "markdown",
                "title": title,
                "headings": headings,
            }
        )

        return [
            Document(
                doc_id=str(metadata.get("doc_id") or raw_document.source),
                title=title,
                source=raw_document.source,
                content=self._to_searchable_text(content),
                metadata=metadata,
            )
        ]

    def _decode_content(self, content: str | bytes) -> str:
        """把 Markdown 内容统一转换为字符串。"""
        if isinstance(content, bytes):
            return content.decode("utf-8")
        return content

    def _extract_headings(self, content: str) -> list[str]:
        """提取 Markdown 标题，一级标题用于 Document.title。"""
        headings = []
        for line in content.splitlines():
            match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", line)
            if match:
                headings.append(match.group(1).strip())
        return headings

    def _to_searchable_text(self, content: str) -> str:
        """移除简单 Markdown 标题标记，保留可检索文本。"""
        lines = []
        for line in content.splitlines():
            lines.append(re.sub(r"^\s{0,3}#{1,6}\s+", "", line).strip())
        searchable_text = "\n".join(line for line in lines if line)
        if not searchable_text:
            raise ValueError("markdown content has no searchable text")
        return searchable_text

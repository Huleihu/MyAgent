"""
本文件负责根据文件扩展名选择合适的文档解析器。
本文件不负责具体解析逻辑，也不负责 Chunk 切分。
"""

from __future__ import annotations

from pathlib import Path

from my_agent.rag.models import Document
from my_agent.rag.parsing.parser import DocumentParser, RawDocument


class DocumentParserRegistry:
    """维护文件扩展名到解析器的映射关系。"""

    def __init__(self) -> None:
        self._parsers: dict[str, DocumentParser] = {}

    def register(self, parser: DocumentParser) -> None:
        """注册解析器，同一扩展名只能绑定一个解析器。"""
        if not isinstance(parser, DocumentParser):
            raise ValueError("parser must inherit from DocumentParser")

        for extension in parser.supported_extensions:
            normalized_extension = self._normalize_extension(extension)
            if normalized_extension in self._parsers:
                raise ValueError(f"parser already exists: {normalized_extension}")
            self._parsers[normalized_extension] = parser

    def get_parser(self, filename: str) -> DocumentParser:
        """根据文件名查找解析器。"""
        extension = self._extension_from_filename(filename)
        if extension not in self._parsers:
            raise ValueError(f"unsupported document extension: {extension}")
        return self._parsers[extension]

    def parse(self, raw_document: RawDocument) -> list[Document]:
        """根据 RawDocument 的文件名选择解析器并执行解析。"""
        return self.get_parser(raw_document.filename).parse(raw_document)

    def _extension_from_filename(self, filename: str) -> str:
        """从文件名提取标准化扩展名。"""
        extension = Path(filename).suffix
        return self._normalize_extension(extension)

    def _normalize_extension(self, extension: str) -> str:
        """统一扩展名格式，便于大小写无关匹配。"""
        if not isinstance(extension, str) or not extension.strip():
            raise ValueError("extension must be a non-empty string")
        normalized_extension = extension.lower()
        if not normalized_extension.startswith("."):
            normalized_extension = f".{normalized_extension}"
        return normalized_extension

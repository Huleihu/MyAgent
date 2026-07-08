"""
本文件负责验证 RAG 文档解析器的格式适配和注册分发能力。
本文件不测试 Chunk 切分、Embedding 和检索流程。
"""

import unittest

from my_agent.rag.models import Document
from my_agent.rag.parsing.markdown_parser import MarkdownDocumentParser
from my_agent.rag.parsing.parser import RawDocument
from my_agent.rag.parsing.parser_registry import DocumentParserRegistry


class RagParserTest(unittest.TestCase):
    def test_markdown_parser_extracts_title_from_first_h1(self):
        parser = MarkdownDocumentParser()
        raw_document = RawDocument(
            source="local://agentic-rag.md",
            filename="agentic-rag.md",
            content="# Agentic RAG 介绍\n\nAgentic RAG 会把检索能力封装为工具。",
            metadata={"tags": ["rag", "agent"]},
        )

        documents = parser.parse(raw_document)

        self.assertEqual(len(documents), 1)
        document = documents[0]
        self.assertIsInstance(document, Document)
        self.assertEqual(document.doc_id, "local://agentic-rag.md")
        self.assertEqual(document.title, "Agentic RAG 介绍")
        self.assertIn("Agentic RAG 会把检索能力封装为工具。", document.content)
        self.assertEqual(document.metadata["filename"], "agentic-rag.md")
        self.assertEqual(document.metadata["extension"], ".md")
        self.assertEqual(document.metadata["parser"], "markdown")
        self.assertEqual(document.metadata["headings"], ["Agentic RAG 介绍"])

    def test_markdown_parser_uses_filename_when_h1_missing(self):
        parser = MarkdownDocumentParser()
        raw_document = RawDocument(
            source="local://notes.markdown",
            filename="notes.markdown",
            content="没有一级标题，但仍然应该可以解析。",
            metadata={},
        )

        document = parser.parse(raw_document)[0]

        self.assertEqual(document.title, "notes.markdown")
        self.assertEqual(document.metadata["title"], "notes.markdown")
        self.assertEqual(document.metadata["headings"], [])

    def test_markdown_parser_decodes_bytes_content(self):
        parser = MarkdownDocumentParser()
        raw_document = RawDocument(
            source="local://bytes.md",
            filename="bytes.md",
            content="# 字节内容\n\n这是 UTF-8 字节内容。".encode("utf-8"),
            metadata={},
        )

        document = parser.parse(raw_document)[0]

        self.assertEqual(document.title, "字节内容")
        self.assertIn("UTF-8", document.content)

    def test_parser_registry_dispatches_by_markdown_extension(self):
        registry = DocumentParserRegistry()
        registry.register(MarkdownDocumentParser())
        raw_document = RawDocument(
            source="local://agentic-rag.MD",
            filename="agentic-rag.MD",
            content="# Agentic RAG\n\n正文",
            metadata={},
        )

        documents = registry.parse(raw_document)

        self.assertEqual(documents[0].title, "Agentic RAG")

    def test_parser_registry_rejects_unsupported_extension(self):
        registry = DocumentParserRegistry()
        registry.register(MarkdownDocumentParser())
        raw_document = RawDocument(
            source="local://paper.pdf",
            filename="paper.pdf",
            content=b"%PDF",
            metadata={},
        )

        with self.assertRaises(ValueError):
            registry.parse(raw_document)

    def test_raw_document_rejects_non_dict_metadata(self):
        with self.assertRaises(ValueError):
            RawDocument(
                source="local://agentic-rag.md",
                filename="agentic-rag.md",
                content="# Agentic RAG",
                metadata=["not", "dict"],
            )


if __name__ == "__main__":
    unittest.main()

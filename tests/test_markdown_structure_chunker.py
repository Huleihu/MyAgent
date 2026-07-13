"""
本文件负责验证 MarkdownStructureChunker 的结构组合、超长回退与 metadata 行为。
本文件使用假 BlockParser 隔离 markdown-it-py 适配器。
"""

import unittest

from my_agent.rag.indexing.markdown_blocks import (
    BlockType,
    Heading,
    MarkdownBlock,
)
from my_agent.rag.indexing.markdown_chunker import MarkdownStructureChunker
from my_agent.rag.models import Document


class FakeBlockParser:
    """按预设结构块返回结果，用于只验证 Chunker 策略。"""

    def __init__(self, blocks):
        self._blocks = list(blocks)

    def parse(self, content):
        return list(self._blocks)


def build_document(content="placeholder"):
    return Document(
        doc_id="doc-1",
        title="安装文档",
        source="local://install.md",
        content=content,
        metadata={"filename": "install.md", "tags": ["guide"]},
    )


def block(block_type, content, path=(), start=0):
    return MarkdownBlock(
        block_type=block_type,
        content=content,
        heading_path=path,
        start_offset=start,
        end_offset=start + len(content),
    )


class MarkdownStructureChunkerTest(unittest.TestCase):
    def test_split_combines_small_blocks_under_same_heading(self):
        path = (Heading(level=1, title="安装"),)
        parser = FakeBlockParser(
            [
                block(BlockType.PARAGRAPH, "第一段。", path, 3),
                block(BlockType.LIST, "- 选项", path, 8),
            ]
        )
        chunker = MarkdownStructureChunker(50, 0, parser)

        chunks = chunker.split(build_document())

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].content, "# 安装\n\n第一段。\n\n- 选项")
        self.assertEqual(chunks[0].metadata["heading_path"], [{"level": 1, "title": "安装"}])
        self.assertEqual(chunks[0].metadata["start_offset"], 3)
        self.assertEqual(chunks[0].metadata["end_offset"], 12)

    def test_split_ends_chunk_when_heading_path_changes(self):
        first_path = (Heading(level=1, title="A"),)
        second_path = (Heading(level=1, title="B"),)
        parser = FakeBlockParser(
            [
                block(BlockType.PARAGRAPH, "第一节正文。", first_path, 0),
                block(BlockType.PARAGRAPH, "第二节正文。", second_path, 10),
            ]
        )

        chunks = MarkdownStructureChunker(100, 0, parser).split(build_document())

        self.assertEqual([chunk.content for chunk in chunks], ["# A\n\n第一节正文。", "# B\n\n第二节正文。"])
        self.assertEqual([chunk.index for chunk in chunks], [0, 1])

    def test_split_counts_heading_prefix_in_chunk_size(self):
        path = (Heading(level=1, title="标题"),)
        parser = FakeBlockParser([block(BlockType.PARAGRAPH, "123456", path)])
        chunker = MarkdownStructureChunker(chunk_size=10, overlap=0, block_parser=parser)

        chunks = chunker.split(build_document())

        self.assertTrue(all(len(chunk.content) <= 10 for chunk in chunks))
        self.assertEqual("".join(chunk.content.replace("# 标题\n\n", "") for chunk in chunks), "123456")

    def test_split_keeps_short_code_block_complete(self):
        path = (Heading(level=2, title="命令"),)
        code = "```bash\npip install app\n```"
        parser = FakeBlockParser([block(BlockType.CODE, code, path)])

        chunks = MarkdownStructureChunker(100, 0, parser).split(build_document())

        self.assertEqual(chunks[0].content, "## 命令\n\n" + code)

    def test_split_falls_back_to_overlapped_text_for_long_paragraph(self):
        parser = FakeBlockParser([block(BlockType.PARAGRAPH, "abcdefghij", (), 0)])

        chunks = MarkdownStructureChunker(6, 2, parser).split(build_document())

        self.assertEqual([chunk.content for chunk in chunks], ["abcdef", "efghij", "ij"])
        self.assertEqual(
            [(chunk.metadata["start_offset"], chunk.metadata["end_offset"]) for chunk in chunks],
            [(0, 6), (4, 10), (8, 10)],
        )

    def test_split_long_fenced_code_keeps_each_piece_fenced_and_preserves_body(self):
        code = "```python\nalpha\nbeta\ngamma\n```"
        parser = FakeBlockParser([block(BlockType.CODE, code, (), 0)])

        chunks = MarkdownStructureChunker(22, 0, parser).split(build_document())

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.content.startswith("```python\n") for chunk in chunks))
        self.assertTrue(all(chunk.content.endswith("```") for chunk in chunks))
        combined_body = "".join(
            chunk.content[len("```python\n"):-len("```")]
            for chunk in chunks
        )
        self.assertEqual(combined_body, "alpha\nbeta\ngamma\n")

    def test_split_preserves_document_metadata_without_mutating_it(self):
        document = build_document()
        parser = FakeBlockParser([block(BlockType.PARAGRAPH, "正文", ())])

        chunk = MarkdownStructureChunker(20, 0, parser).split(document)[0]

        self.assertEqual(document.metadata, {"filename": "install.md", "tags": ["guide"]})
        self.assertEqual(chunk.metadata["filename"], "install.md")
        self.assertEqual(chunk.metadata["source"], "local://install.md")
        self.assertEqual(chunk.metadata["title"], "安装文档")

    def test_split_many_preserves_document_order(self):
        parser = FakeBlockParser([block(BlockType.PARAGRAPH, "正文", ())])
        chunker = MarkdownStructureChunker(20, 0, parser)
        first = build_document()
        second = Document("doc-2", "第二篇", "local://two.md", "placeholder", {})

        chunks = chunker.split_many([first, second])

        self.assertEqual([chunk.doc_id for chunk in chunks], ["doc-1", "doc-2"])

    def test_split_returns_no_chunk_when_parser_returns_no_body_blocks(self):
        self.assertEqual(
            MarkdownStructureChunker(20, 0, FakeBlockParser([])).split(build_document()),
            [],
        )

    def test_split_uses_default_markdown_it_adapter(self):
        document = build_document("# 安装\n\n第一段。\n\n第二段。")

        chunks = MarkdownStructureChunker(100).split(document)

        self.assertEqual(chunks[0].content, "# 安装\n\n第一段。\n\n第二段。")
        self.assertEqual(chunks[0].metadata["start_offset"], 6)
        self.assertEqual(chunks[0].metadata["end_offset"], len(document.content))

    def test_split_long_list_fallback_does_not_drop_original_content(self):
        list_content = "- 第一项\n- 第二项\n- 第三项"
        parser = FakeBlockParser([block(BlockType.LIST, list_content, ())])

        chunks = MarkdownStructureChunker(5, 0, parser).split(build_document())

        self.assertEqual("".join(chunk.content for chunk in chunks), list_content)
        self.assertTrue(all(chunk.content for chunk in chunks))

    def test_split_uses_safe_prefix_fallback_for_extremely_long_heading(self):
        path = (Heading(level=1, title="很长的标题" * 10),)
        parser = FakeBlockParser([block(BlockType.PARAGRAPH, "正文", path)])

        chunks = MarkdownStructureChunker(5, 0, parser).split(build_document())

        self.assertTrue(chunks)
        self.assertTrue(all(0 < len(chunk.content) <= 5 for chunk in chunks))
        self.assertIn("正文", "".join(chunk.content for chunk in chunks))

    def test_init_rejects_invalid_sizes(self):
        parser = FakeBlockParser([])
        with self.assertRaises(ValueError):
            MarkdownStructureChunker(0, 0, parser)
        with self.assertRaises(ValueError):
            MarkdownStructureChunker(5, -1, parser)
        with self.assertRaises(ValueError):
            MarkdownStructureChunker(5, 5, parser)


if __name__ == "__main__":
    unittest.main()

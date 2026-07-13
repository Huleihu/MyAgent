"""
本文件负责验证 markdown-it-py 适配器的结构块、标题路径与原文偏移转换。
本文件不测试 RAG Chunk 组合策略。
"""

import unittest

from my_agent.rag.indexing.markdown_blocks import BlockType, Heading, MarkdownBlock
from my_agent.rag.indexing.markdown_it_block_parser import MarkdownItBlockParser


class MarkdownItBlockParserTest(unittest.TestCase):
    def setUp(self):
        self.parser = MarkdownItBlockParser()

    def test_parse_assigns_heading_paths_for_nested_and_skipped_levels(self):
        content = "# A\n\n一级正文。\n\n### C\n\n三级正文。\n\n## B\n\n二级正文。"

        blocks = self.parser.parse(content)

        self.assertEqual([block.content for block in blocks], ["一级正文。", "三级正文。", "二级正文。"])
        self.assertEqual(
            blocks[0].heading_path,
            (Heading(level=1, title="A"),),
        )
        self.assertEqual(
            blocks[1].heading_path,
            (Heading(level=1, title="A"), Heading(level=3, title="C")),
        )
        self.assertEqual(
            blocks[2].heading_path,
            (Heading(level=1, title="A"), Heading(level=2, title="B")),
        )

    def test_parse_keeps_preamble_empty_path_and_does_not_emit_heading_block(self):
        content = "前言。\n\n# 标题\n\n正文。"

        blocks = self.parser.parse(content)

        self.assertEqual([block.block_type for block in blocks], [BlockType.PARAGRAPH, BlockType.PARAGRAPH])
        self.assertEqual(blocks[0].heading_path, ())
        self.assertEqual(blocks[1].heading_path, (Heading(level=1, title="标题"),))
        self.assertNotIn("标题", [block.content for block in blocks])

    def test_parse_keeps_code_fence_and_hash_without_creating_heading(self):
        content = "# 安装\n\n```python\n# 不是标题\nprint('ok')\n```\n"

        blocks = self.parser.parse(content)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].block_type, BlockType.CODE)
        self.assertEqual(blocks[0].content, "```python\n# 不是标题\nprint('ok')\n```")
        self.assertEqual(blocks[0].heading_path, (Heading(level=1, title="安装"),))

    def test_parse_treats_indented_code_as_code_block(self):
        content = "    print('ok')\n    print('again')\n"

        blocks = self.parser.parse(content)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].block_type, BlockType.CODE)
        self.assertEqual(blocks[0].content, content.rstrip("\n"))

    def test_parse_groups_complete_list_and_preserves_markers(self):
        content = "- 第一项\n- 第二项\n  - 嵌套项\n\n段落。"

        blocks = self.parser.parse(content)

        self.assertEqual([block.block_type for block in blocks], [BlockType.LIST, BlockType.PARAGRAPH])
        self.assertEqual(blocks[0].content, "- 第一项\n- 第二项\n  - 嵌套项")
        self.assertEqual(blocks[1].content, "段落。")

    def test_parse_converts_unhandled_block_to_other_without_losing_source(self):
        content = "> 引用内容\n> 第二行\n"

        blocks = self.parser.parse(content)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].block_type, BlockType.OTHER)
        self.assertEqual(blocks[0].content, content.rstrip("\n"))

    def test_parse_uses_source_offsets_for_lf_and_crlf(self):
        for content in ("# 标题\n\n正文。\n", "# 标题\r\n\r\n正文。\r\n"):
            with self.subTest(content=repr(content)):
                blocks = self.parser.parse(content)

                self.assertEqual(len(blocks), 1)
                block = blocks[0]
                self.assertEqual(
                    content[block.start_offset:block.end_offset],
                    block.content,
                )

    def test_parse_returns_internal_blocks_not_third_party_tokens(self):
        blocks = self.parser.parse("正文。")

        self.assertTrue(all(isinstance(block, MarkdownBlock) for block in blocks))
        self.assertFalse(any(hasattr(block, "children") for block in blocks))

    def test_parse_empty_heading_section_produces_no_empty_block(self):
        self.assertEqual(self.parser.parse("# 仅标题\n"), [])

    def test_parse_supports_commonmark_setext_heading(self):
        content = "安装说明\n========\n\n正文。"

        blocks = self.parser.parse(content)

        self.assertEqual(blocks[0].heading_path, (Heading(level=1, title="安装说明"),))
        self.assertEqual(blocks[0].content, "正文。")


if __name__ == "__main__":
    unittest.main()

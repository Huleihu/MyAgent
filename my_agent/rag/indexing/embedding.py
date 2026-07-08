"""
本文件负责提供 RAG 链路中的确定性文本向量化能力。
本文件不负责保存 Chunk、执行检索排序或调用真实 Embedding 服务。
"""

from __future__ import annotations

import math
import re


class SimpleEmbeddingModel:
    """使用确定性词袋构造稀疏向量，便于本地测试和演示。"""

    _ENGLISH_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

    def tokenize(self, text: str) -> list[str]:
        """将文本转换为稳定 token 列表，英文按词、中文按单字。"""
        if not isinstance(text, str):
            raise ValueError("text must be a string")

        normalized_text = text.lower()
        tokens = []
        position = 0

        while position < len(normalized_text):
            char = normalized_text[position]
            if self._is_chinese_char(char):
                tokens.append(char)
                position += 1
                continue

            match = self._ENGLISH_TOKEN_PATTERN.match(normalized_text, position)
            if match is not None:
                tokens.append(match.group())
                position = match.end()
                continue

            position += 1

        return tokens

    def embed(self, text: str) -> dict[str, float]:
        """用 token 词频构造稀疏向量，确保相同文本输入结果稳定。"""
        vector: dict[str, float] = {}
        for token in self.tokenize(text):
            vector[token] = vector.get(token, 0.0) + 1.0
        return vector

    def cosine_similarity(
        self,
        left: dict[str, float],
        right: dict[str, float],
    ) -> float:
        """计算两个稀疏向量的余弦相似度。"""
        if not left or not right:
            return 0.0

        left_norm = self._vector_norm(left)
        right_norm = self._vector_norm(right)
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0

        common_tokens = set(left).intersection(right)
        dot_product = sum(left[token] * right[token] for token in common_tokens)
        return dot_product / (left_norm * right_norm)

    def _vector_norm(self, vector: dict[str, float]) -> float:
        """计算稀疏向量长度。"""
        return math.sqrt(sum(value * value for value in vector.values()))

    def _is_chinese_char(self, char: str) -> bool:
        """判断字符是否属于常用 CJK 统一表意文字范围。"""
        return "\u4e00" <= char <= "\u9fff"

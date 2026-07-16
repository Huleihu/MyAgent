"""
本文件负责验证跨 Checkpoint Store 的 JSON 原生值精确类型契约。
本文件不测试具体 Store、Planner 或工具执行流程。
"""

from enum import IntEnum, StrEnum
import unittest

from my_agent.core.json_value import validate_json_native


class TextCode(StrEnum):
    """模拟会被 json 编码器当作字符串处理的业务枚举。"""

    VALUE = "value"


class NumberCode(IntEnum):
    """模拟会被 json 编码器当作整数处理的业务枚举。"""

    VALUE = 1


class CustomList(list):
    """模拟 SQLite roundtrip 后会丢失类型的列表子类。"""


class JsonValueTest(unittest.TestCase):
    def test_accepts_exact_json_native_types(self):
        validate_json_native(
            {"text": "value", "flag": True, "count": 1, "ratio": 1.5, "items": []}
        )

    def test_rejects_scalar_and_container_subclasses(self):
        for value in (TextCode.VALUE, NumberCode.VALUE, CustomList([1])):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_json_native(value)


if __name__ == "__main__":
    unittest.main()

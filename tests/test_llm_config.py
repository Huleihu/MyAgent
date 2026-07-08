"""
本文件负责验证模型配置数据结构的基础约束。
本文件不测试环境变量读取，也不测试真实模型调用。
"""

import unittest

from my_agent.llm.config import ModelConfig


class ModelConfigTest(unittest.TestCase):
    def test_model_config_keeps_minimal_model_settings(self):
        config = ModelConfig(
            provider="fake",
            model_name="fake-model",
            api_key="test-key",
            base_url="https://example.test",
            temperature=0.2,
            max_tokens=128,
            timeout_seconds=10.0,
        )

        self.assertEqual(config.provider, "fake")
        self.assertEqual(config.model_name, "fake-model")
        self.assertEqual(config.api_key, "test-key")
        self.assertEqual(config.base_url, "https://example.test")
        self.assertEqual(config.temperature, 0.2)
        self.assertEqual(config.max_tokens, 128)
        self.assertEqual(config.timeout_seconds, 10.0)

    def test_model_config_rejects_invalid_required_fields(self):
        with self.assertRaises(ValueError):
            ModelConfig(provider="", model_name="fake-model")

        with self.assertRaises(ValueError):
            ModelConfig(provider="fake", model_name="")

    def test_model_config_rejects_invalid_optional_numbers(self):
        with self.assertRaises(ValueError):
            ModelConfig(provider="fake", model_name="fake-model", temperature=-0.1)

        with self.assertRaises(ValueError):
            ModelConfig(provider="fake", model_name="fake-model", max_tokens=0)

        with self.assertRaises(ValueError):
            ModelConfig(provider="fake", model_name="fake-model", timeout_seconds=0)


if __name__ == "__main__":
    unittest.main()

"""本文件负责验证模型 Provider 环境变量的读取与安全校验。"""

import unittest
from unittest.mock import patch

from my_agent.core.errors import ModelConfigurationError
from my_agent.llm.settings import load_model_settings


class LlmEnvironmentConfigTest(unittest.TestCase):
    def test_missing_provider_uses_demo(self):
        self.assertIsNone(load_model_settings({}))
        self.assertIsNone(load_model_settings({"MYAGENT_LLM_PROVIDER": "demo"}))

    def test_process_configuration_loads_dotenv_without_overriding_environment(self):
        with patch("my_agent.llm.settings.load_dotenv") as load_dotenv:
            with patch.dict("os.environ", {"MYAGENT_LLM_PROVIDER": ""}, clear=True):
                self.assertIsNone(load_model_settings())
        load_dotenv.assert_called_once_with(override=False)

    def test_deepseek_uses_documented_defaults(self):
        settings = load_model_settings({"MYAGENT_LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "secret"})
        self.assertEqual(settings.model_config.provider, "deepseek")
        self.assertEqual(settings.model_config.model_name, "deepseek-v4-flash")
        self.assertEqual(settings.model_config.base_url, "https://api.deepseek.com")
        self.assertFalse(settings.thinking_enabled)
        self.assertNotIn("secret", repr(settings.model_config))

    def test_deepseek_requires_api_key_and_rejects_thinking(self):
        with self.assertRaises(ModelConfigurationError):
            load_model_settings({"MYAGENT_LLM_PROVIDER": "deepseek"})
        with self.assertRaises(ModelConfigurationError):
            load_model_settings({"MYAGENT_LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "secret", "MYAGENT_DEEPSEEK_THINKING_ENABLED": "true"})

    def test_rejects_unknown_provider_and_invalid_timeout(self):
        with self.assertRaises(ModelConfigurationError):
            load_model_settings({"MYAGENT_LLM_PROVIDER": "unknown"})
        with self.assertRaises(ModelConfigurationError):
            load_model_settings({"MYAGENT_LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "secret", "MYAGENT_LLM_TIMEOUT_SECONDS": "zero"})
        with self.assertRaises(ModelConfigurationError):
            load_model_settings({"MYAGENT_LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "secret", "MYAGENT_LLM_MODEL": ""})

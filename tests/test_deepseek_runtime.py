"""本文件负责验证 DeepSeek Runtime 装配仍保留离线 Demo 路径。"""

import unittest
from unittest.mock import patch

from my_agent.core.errors import ModelConfigurationError
from my_agent.state.session import SessionState
from my_agent.web.demo_runtime import build_runtime


class DeepSeekRuntimeTest(unittest.TestCase):
    def test_missing_provider_uses_demo_runtime(self):
        with patch("my_agent.web.demo_runtime.load_model_settings", return_value=None):
            runtime = build_runtime(SessionState(session_id="demo"))
        self.assertEqual(runtime.chat("zzzxqv_unique_no_match_98765").output_text, "演示知识库中未找到与该问题相关的内容。")

    def test_configuration_error_is_not_silently_replaced_by_demo(self):
        with patch("my_agent.web.demo_runtime.load_model_settings", side_effect=ModelConfigurationError("missing key")):
            with self.assertRaises(ModelConfigurationError):
                build_runtime(SessionState(session_id="deepseek"))

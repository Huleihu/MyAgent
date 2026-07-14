"""
本文件负责导出模型调用抽象与测试用模型客户端。
本文件不负责读取环境变量，也不直接调用真实模型供应商。
"""

from my_agent.llm.client import ModelClient
from my_agent.llm.config import ModelConfig
from my_agent.llm.fake import FakeModelClient
from my_agent.llm.deepseek import DeepSeekModelClient

__all__ = [
    "FakeModelClient",
    "DeepSeekModelClient",
    "ModelClient",
    "ModelConfig",
]

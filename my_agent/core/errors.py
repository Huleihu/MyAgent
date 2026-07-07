"""
本文件负责定义 Agent 核心模块使用的统一异常类型。
本文件不负责异常捕获和错误结果转换。
"""


class ToolError(Exception):
    """工具框架异常基类。"""


class ToolNotFoundError(ToolError):
    """表示请求的工具不存在。"""


class ToolAlreadyExistsError(ToolError):
    """表示注册了重复名称的工具。"""


class ToolValidationError(ToolError):
    """表示工具定义、调用参数或调用结果不符合框架契约。"""


class ToolExecutionError(ToolError):
    """表示工具执行过程失败。"""

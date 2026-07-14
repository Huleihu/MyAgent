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


class ModelError(Exception):
    """表示模型配置、调用或响应转换中的安全错误。"""


class ModelConfigurationError(ModelError):
    """表示模型 Provider 配置缺失或不符合约束。"""


class ModelClientError(ModelError):
    """表示调用模型服务时发生的可安全展示错误。"""


class ModelResponseError(ModelClientError):
    """表示模型响应不符合项目内部协议。"""

"""
本文件负责执行标准化工具调用请求，并返回统一工具调用结果。
本文件不负责工具注册，也不实现具体工具业务逻辑。
"""

from __future__ import annotations

from time import perf_counter

from my_agent.core.errors import (
    ToolExecutionError,
    ToolNotFoundError,
    ToolValidationError,
)
from my_agent.core.interfaces import Tool
from my_agent.tools.registry import ToolRegistry
from my_agent.tools.schema import ToolCallRequest, ToolCallResult


class ToolExecutor:
    """工具执行边界，统一处理查找、轻量校验、异常包装和耗时记录。"""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def execute(self, request: ToolCallRequest) -> ToolCallResult:
        """执行一次工具调用，并把成功或失败都包装为 ToolCallResult。"""
        started_at = perf_counter()
        try:
            tool = self._registry.get(request.name)
            self._validate_required_arguments(tool, request)
            data = tool.run(request.arguments)
            if not isinstance(data, dict):
                raise ToolExecutionError("tool must return a dict")

            return ToolCallResult.success_result(
                name=request.name,
                data=data,
                duration_ms=self._elapsed_ms(started_at),
                call_id=request.call_id,
            )
        except (ToolNotFoundError, ToolValidationError) as exc:
            return self._build_failure_result(request, exc, started_at)
        except Exception as exc:
            wrapped_error = ToolExecutionError(str(exc))
            return self._build_failure_result(request, wrapped_error, started_at)

    def _validate_required_arguments(
        self,
        tool: Tool,
        request: ToolCallRequest,
    ) -> None:
        """只校验 required 字段，完整 JSON Schema 校验留给后续扩展。"""
        required_fields = tool.definition.parameters.get("required", [])
        missing_fields = sorted(
            field_name
            for field_name in required_fields
            if field_name not in request.arguments
        )
        if missing_fields:
            joined_fields = ", ".join(missing_fields)
            raise ToolValidationError(
                f"Missing required arguments: {joined_fields}"
            )

    def _build_failure_result(
        self,
        request: ToolCallRequest,
        error: Exception,
        started_at: float,
    ) -> ToolCallResult:
        """把内部异常转换成结构化错误结果，避免异常泄漏到 Agent Loop。"""
        return ToolCallResult.failure_result(
            name=request.name,
            error_type=error.__class__.__name__,
            error_message=str(error),
            duration_ms=self._elapsed_ms(started_at),
            call_id=request.call_id,
        )

    def _elapsed_ms(self, started_at: float) -> float:
        """计算本次工具调用耗时，单位为毫秒。"""
        return (perf_counter() - started_at) * 1000

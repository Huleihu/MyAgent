"""
本文件负责执行固定 Runtime Eval 用例，并按输出、节点路径和工具调用分别报告结果。
本文件不修改 Runtime 执行逻辑，也不评估真实 LLM 的语义等价性。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from my_agent.runtime.conversation import ConversationRuntime
from my_agent.runtime.eval_models import (
    ExpectedToolCall,
    RuntimeEvalCase,
    RuntimeEvalFailure,
    RuntimeEvalResult,
)


class RuntimeEvaluator:
    """基于独立 ConversationRuntime 实例执行确定性 Runtime 回归评估。"""

    def __init__(
        self,
        runtime_factory: Callable[[], ConversationRuntime],
    ) -> None:
        if not callable(runtime_factory):
            raise TypeError("runtime_factory must be callable")
        self._runtime_factory = runtime_factory

    def evaluate(self, case: RuntimeEvalCase) -> RuntimeEvalResult:
        """执行一个用例，并收集所有完成运行后可检查的不匹配项。"""
        if not isinstance(case, RuntimeEvalCase):
            raise TypeError("case must be a RuntimeEvalCase")

        try:
            runtime = self._runtime_factory()
            if not isinstance(runtime, ConversationRuntime):
                raise TypeError("runtime_factory must return a ConversationRuntime")
            turn_result = runtime.chat(case.user_input)
        except Exception as exc:
            root_error = exc.__cause__ if exc.__cause__ is not None else exc
            return self._build_execution_failure_result(case, root_error)

        actual_node_ids = tuple(trace.node_id for trace in turn_result.node_traces)
        actual_tool_calls = tuple(
            ExpectedToolCall(tool_name=trace.tool_name, success=trace.success)
            for trace in turn_result.tool_traces
        )
        failures = self._check_completed_run(
            case=case,
            output_text=turn_result.output_text,
            actual_node_ids=actual_node_ids,
            actual_tool_calls=actual_tool_calls,
        )
        return RuntimeEvalResult(
            case_id=case.case_id,
            passed=not failures,
            failures=failures,
            actual_node_ids=actual_node_ids,
            actual_tool_calls=actual_tool_calls,
            turn_result=turn_result,
        )

    def evaluate_many(
        self,
        cases: Iterable[RuntimeEvalCase],
    ) -> tuple[RuntimeEvalResult, ...]:
        """按输入顺序评估多个用例，单个运行失败不会中断后续用例。"""
        if isinstance(cases, (str, bytes)):
            raise ValueError("cases must be an iterable of RuntimeEvalCase")
        try:
            case_snapshot = tuple(cases)
        except TypeError as exc:
            raise ValueError("cases must be an iterable of RuntimeEvalCase") from exc
        if not all(isinstance(case, RuntimeEvalCase) for case in case_snapshot):
            raise ValueError("cases must contain RuntimeEvalCase instances")
        return tuple(self.evaluate(case) for case in case_snapshot)

    def _check_completed_run(
        self,
        case: RuntimeEvalCase,
        output_text: str,
        actual_node_ids: tuple[str, ...],
        actual_tool_calls: tuple[ExpectedToolCall, ...],
    ) -> tuple[RuntimeEvalFailure, ...]:
        """独立检查已完成运行的三个固定断言，避免首项失败遮蔽其余差异。"""
        failures: list[RuntimeEvalFailure] = []
        if output_text != case.expected_output_text:
            failures.append(
                RuntimeEvalFailure(
                    check_name="output_text",
                    expected=case.expected_output_text,
                    actual=output_text,
                    message="最终输出文本与严格期望不一致",
                )
            )
        if actual_node_ids != case.expected_node_ids:
            failures.append(
                RuntimeEvalFailure(
                    check_name="node_path",
                    expected=case.expected_node_ids,
                    actual=actual_node_ids,
                    message="节点执行路径与严格期望不一致",
                )
            )
        if actual_tool_calls != case.expected_tool_calls:
            failures.append(
                RuntimeEvalFailure(
                    check_name="tool_calls",
                    expected=case.expected_tool_calls,
                    actual=actual_tool_calls,
                    message="工具调用顺序、名称或成功状态与严格期望不一致",
                )
            )
        return tuple(failures)

    def _build_execution_failure_result(
        self,
        case: RuntimeEvalCase,
        error: Exception,
    ) -> RuntimeEvalResult:
        """把 Runtime 创建或执行异常转换为单个明确失败项。"""
        failure = RuntimeEvalFailure(
            check_name="runtime_execution",
            expected=None,
            actual={
                "type": error.__class__.__name__,
                "message": str(error),
            },
            message="Runtime 创建或执行过程中抛出异常",
        )
        return RuntimeEvalResult(
            case_id=case.case_id,
            passed=False,
            failures=(failure,),
            actual_node_ids=(),
            actual_tool_calls=(),
            turn_result=None,
        )

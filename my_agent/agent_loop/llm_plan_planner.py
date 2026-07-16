"""
本文件负责通过项目 ModelClient 实现任务规划、步骤决策和计划最终回答。
本文件不直接依赖模型供应商 SDK，也不修改 PlanState 或 RunState。
"""

from __future__ import annotations

from copy import deepcopy
import json
from typing import Any

from my_agent.agent_loop.plan_actions import (
    AbortPlanAction,
    CompleteStepAction,
    PlannerProtocolError,
    SkipStepAction,
    StepDecision,
)
from my_agent.agent_loop.plan_planner import (
    CreatePlanRequest,
    FinalizePlanRequest,
    PlanDefinition,
    PlanStepDefinition,
    StepDecisionRequest,
)
from my_agent.agent_loop.planner import FinalAnswerAction, ToolAction
from my_agent.llm.client import ModelClient
from my_agent.core.json_value import validate_json_native


def _read_text_response(response: dict[str, Any]) -> str:
    """读取 ModelClient 的普通文本响应并转换为稳定协议错误。"""
    if not isinstance(response, dict) or response.get("type") != "final_answer":
        raise PlannerProtocolError("model response must be a final_answer")
    answer = response.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise PlannerProtocolError("model final_answer must contain text")
    return answer


def _parse_json_object(text: str) -> dict[str, Any]:
    """解析 Planner JSON 文本并保留原始解析异常上下文。"""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise PlannerProtocolError("model response must be valid JSON") from error
    if not isinstance(payload, dict):
        raise PlannerProtocolError("model JSON response must be an object")
    return payload


def _reject_unknown_fields(
    payload: dict[str, Any],
    allowed_fields: set[str],
    context: str,
) -> None:
    """拒绝模型越过当前动作协议写入状态或控制字段。"""
    if set(payload) - allowed_fields:
        raise PlannerProtocolError(f"{context} contains unsupported fields")


class LLMTaskPlanner:
    """使用 ModelClient 创建任务计划并生成整个计划的最终回答。"""

    def __init__(self, model_client: ModelClient) -> None:
        if not isinstance(model_client, ModelClient):
            raise TypeError("model_client must be a ModelClient")
        self._model_client = model_client

    def create_plan(self, request: CreatePlanRequest) -> PlanDefinition:
        """要求模型返回只包含目标和有序步骤的 JSON 计划。"""
        if not isinstance(request, CreatePlanRequest):
            raise TypeError("request must be a CreatePlanRequest")
        prompt = {
            "instruction": (
                "为用户任务创建顺序执行计划。只返回 JSON object，格式为 "
                '{"goal":"目标","steps":["步骤一","步骤二"]}。'
                "不要返回 ID、状态、计数、限制或 Markdown。"
            ),
            "user_input": request.user_input,
            "session_messages": request.messages,
            "available_tools": list(request.tool_definitions),
            "max_plan_steps": request.max_plan_steps,
        }
        response = self._model_client.chat(
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(prompt, ensure_ascii=False, sort_keys=True),
                }
            ],
            tool_definitions=[],
        )
        payload = _parse_json_object(_read_text_response(response))
        _reject_unknown_fields(payload, {"goal", "steps"}, "plan response")
        goal = payload.get("goal")
        steps = payload.get("steps")
        if not isinstance(goal, str) or not goal.strip():
            raise PlannerProtocolError("plan goal must be a non-empty string")
        if not isinstance(steps, list) or not steps or not all(
            isinstance(step, str) and step.strip() for step in steps
        ):
            raise PlannerProtocolError(
                "plan steps must be a non-empty list of strings"
            )
        if len(steps) > request.max_plan_steps:
            raise PlannerProtocolError("plan exceeds max_plan_steps")
        return PlanDefinition(
            goal=goal,
            steps=tuple(PlanStepDefinition(step) for step in steps),
        )

    def finalize_plan(self, request: FinalizePlanRequest) -> FinalAnswerAction:
        """根据已确定的计划结果生成用户可读的最终回答。"""
        if not isinstance(request, FinalizePlanRequest):
            raise TypeError("request must be a FinalizePlanRequest")
        prompt = {
            "instruction": (
                "根据已确定的计划结果生成最终回答。不得改变 outcome，"
                "不要调用工具，只返回最终回答文本。"
            ),
            "user_input": request.user_input,
            "session_messages": request.messages,
            "plan": request.plan,
            "outcome": request.outcome,
            "abort_reason": request.abort_reason,
        }
        response = self._model_client.chat(
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(prompt, ensure_ascii=False, sort_keys=True),
                }
            ],
            tool_definitions=[],
        )
        return FinalAnswerAction(_read_text_response(response))


class LLMStepPlanner:
    """使用 ModelClient 为当前计划步骤生成工具或终态决策。"""

    def __init__(self, model_client: ModelClient) -> None:
        if not isinstance(model_client, ModelClient):
            raise TypeError("model_client must be a ModelClient")
        self._model_client = model_client

    def decide(self, request: StepDecisionRequest) -> StepDecision:
        """解析标准 tool calling 或步骤级 JSON 终态动作。"""
        if not isinstance(request, StepDecisionRequest):
            raise TypeError("request must be a StepDecisionRequest")
        prompt = {
            "instruction": (
                "决定当前步骤的下一步。如果需要工具，使用提供的标准工具。"
                "否则只返回 JSON object："
                '{"action":"complete_step","result_summary":"摘要","reflection":"可选反思"}，'
                '{"action":"skip_step","reason":"原因","result_summary":"可选摘要","reflection":"可选反思"}，'
                "或 "
                '{"action":"abort_plan","reason":"原因","reflection":"可选反思"}。'
            ),
            "user_input": request.user_input,
            "session_messages": request.messages,
            "plan": request.plan,
            "current_step": request.current_step,
            "previous_step_summaries": request.previous_step_summaries,
            "observations": request.observations,
            "recent_observation": request.recent_observation,
            "remaining_step_tool_calls": request.remaining_step_tool_calls,
            "remaining_total_tool_calls": request.remaining_total_tool_calls,
            "can_call_tool": request.can_call_tool,
        }
        decision_message = {
            "role": "user",
            "content": json.dumps(prompt, ensure_ascii=False, sort_keys=True),
        }
        # 有工具可用时保留标准 tool history；限额耗尽后只传嵌入式快照，避免暴露工具。
        messages = (
            [deepcopy(message) for message in request.messages]
            + [decision_message]
            if request.can_call_tool
            else [decision_message]
        )
        response = self._model_client.chat(
            messages=messages,
            tool_definitions=[
                deepcopy(definition) for definition in request.tool_definitions
            ]
            if request.can_call_tool
            else [],
        )
        if isinstance(response, dict) and response.get("type") == "tool_call":
            return self._parse_tool_action(response, request.can_call_tool)
        payload = _parse_json_object(_read_text_response(response))
        return self._parse_terminal_decision(payload)

    def _parse_tool_action(
        self, response: dict[str, Any], can_call_tool: bool
    ) -> StepDecision:
        """丢弃供应商 call ID，仅保留工具名称和参数。"""
        if not can_call_tool:
            raise PlannerProtocolError("tool call is not allowed by execution limits")
        _reject_unknown_fields(
            response,
            {"type", "tool_name", "arguments", "call_id"},
            "tool_call response",
        )
        tool_name = response.get("tool_name")
        arguments = response.get("arguments")
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise PlannerProtocolError("tool_call requires tool_name")
        if not isinstance(arguments, dict):
            raise PlannerProtocolError("tool_call requires dict arguments")
        try:
            validate_json_native(arguments)
        except ValueError as error:
            raise PlannerProtocolError(
                "tool_call arguments must be JSON-serializable"
            ) from error
        return StepDecision(
            ToolAction(
                tool_name=tool_name,
                arguments=deepcopy(arguments),
                call_id=None,
            )
        )

    def _parse_terminal_decision(self, payload: dict[str, Any]) -> StepDecision:
        """把模型 JSON 转换为步骤完成、跳过或计划终止动作。"""
        action_type = payload.get("action")
        allowed_fields_by_action = {
            "complete_step": {"action", "result_summary", "reflection"},
            "skip_step": {"action", "reason", "result_summary", "reflection"},
            "abort_plan": {"action", "reason", "reflection"},
        }
        allowed_fields = allowed_fields_by_action.get(action_type)
        if allowed_fields is None:
            raise PlannerProtocolError("unsupported step action from model")
        _reject_unknown_fields(payload, allowed_fields, "step action response")
        reflection = payload.get("reflection")
        if reflection is not None and not isinstance(reflection, str):
            raise PlannerProtocolError("reflection must be a string or None")
        if action_type == "complete_step":
            action = CompleteStepAction(payload.get("result_summary"))
        elif action_type == "skip_step":
            action = SkipStepAction(
                reason=payload.get("reason"),
                result_summary=payload.get("result_summary"),
            )
        elif action_type == "abort_plan":
            action = AbortPlanAction(reason=payload.get("reason"))
        return StepDecision(action=action, reflection=reflection)

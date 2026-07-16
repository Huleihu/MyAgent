"""
本文件负责验证基于 ModelClient 的真实任务规划、步骤决策和最终回答解析。
本文件使用 FakeModelClient，不访问真实模型服务。
"""

from __future__ import annotations

import json
import unittest
from dataclasses import replace

from my_agent.agent_loop.llm_plan_planner import LLMTaskPlanner, LLMStepPlanner
from my_agent.agent_loop.plan_actions import (
    CompleteStepAction,
    PlannerProtocolError,
)
from my_agent.agent_loop.plan_planner import (
    CreatePlanRequest,
    FinalizePlanRequest,
    StepDecisionRequest,
)
from my_agent.agent_loop.planner import ToolAction
from my_agent.llm.fake import FakeModelClient


def build_create_request() -> CreatePlanRequest:
    """构造真实任务 Planner 的最小输入。"""
    return CreatePlanRequest(
        user_input="查询 checkpoint 并总结",
        messages=[{"role": "user", "content": "查询 checkpoint 并总结"}],
        tool_definitions=[
            {
                "name": "retrieval.search",
                "description": "查询资料",
                "parameters": {"type": "object"},
            }
        ],
        max_plan_steps=3,
    )


def build_step_request() -> StepDecisionRequest:
    """构造真实步骤 Planner 的最小输入。"""
    tools = [
        {
            "name": "retrieval.search",
            "description": "查询资料",
            "parameters": {"type": "object"},
        }
    ]
    return StepDecisionRequest(
        user_input="查询 checkpoint 并总结",
        plan={"goal": "查询并总结", "steps": [{"step_id": "step-1"}]},
        current_step={"step_id": "step-1", "instruction": "查询资料"},
        previous_step_summaries=(),
        observations=[],
        recent_observation=None,
        messages=[{"role": "user", "content": "查询 checkpoint 并总结"}],
        tool_definitions=tools,
        remaining_step_tool_calls=2,
        remaining_total_tool_calls=4,
        can_call_tool=True,
    )


class LLMPlanPlannerTest(unittest.TestCase):
    def test_task_planner_parses_plan_json(self):
        model_client = FakeModelClient(
            [
                {
                    "type": "final_answer",
                    "answer": (
                        '{"goal":"查询并总结","steps":'
                        '["检索 checkpoint 资料","整理结果"]}'
                    ),
                }
            ]
        )
        planner = LLMTaskPlanner(model_client)

        plan = planner.create_plan(build_create_request())

        self.assertEqual(plan.goal, "查询并总结")
        self.assertEqual(
            [step.instruction for step in plan.steps],
            ["检索 checkpoint 资料", "整理结果"],
        )
        self.assertEqual(model_client.chat_calls[0]["tool_definitions"], [])
        prompt = json.loads(model_client.chat_calls[0]["messages"][0]["content"])
        self.assertEqual(
            prompt["session_messages"][0]["content"],
            "查询 checkpoint 并总结",
        )

    def test_step_planner_discards_provider_call_id(self):
        model_client = FakeModelClient(
            [
                {
                    "type": "tool_call",
                    "tool_name": "retrieval.search",
                    "arguments": {"query": "checkpoint"},
                    "call_id": "provider-call-1",
                }
            ]
        )
        planner = LLMStepPlanner(model_client)

        decision = planner.decide(build_step_request())

        self.assertIsInstance(decision.action, ToolAction)
        self.assertIsNone(decision.action.call_id)
        self.assertEqual(decision.action.arguments, {"query": "checkpoint"})

    def test_step_planner_rejects_non_serializable_tool_arguments(self):
        model_client = FakeModelClient(
            [
                {
                    "type": "tool_call",
                    "tool_name": "retrieval.search",
                    "arguments": {"query": {"not-json"}},
                    "call_id": "provider-call-1",
                }
            ]
        )

        with self.assertRaises(PlannerProtocolError):
            LLMStepPlanner(model_client).decide(build_step_request())

    def test_step_planner_rejects_json_coercing_tool_arguments(self):
        for arguments in ({"items": (1, 2)}, {7: "integer-key"}):
            with self.subTest(arguments=arguments):
                model_client = FakeModelClient(
                    [
                        {
                            "type": "tool_call",
                            "tool_name": "retrieval.search",
                            "arguments": arguments,
                            "call_id": "provider-call-1",
                        }
                    ]
                )
                with self.assertRaises(PlannerProtocolError):
                    LLMStepPlanner(model_client).decide(build_step_request())

    def test_step_planner_passes_standard_tool_history_when_tools_are_allowed(self):
        request = replace(
            build_step_request(),
            messages=(
                {"role": "user", "content": "查询 checkpoint"},
                {
                    "role": "assistant",
                    "content": '{"items":["doc-1"]}',
                    "metadata": {
                        "message_type": "tool_observation",
                        "tool_name": "retrieval.search",
                        "call_id": "loop-call-1",
                        "arguments": {"query": "checkpoint"},
                        "success": True,
                    },
                },
            ),
        )
        model_client = FakeModelClient(
            [{"type": "final_answer", "answer": '{"action":"complete_step","result_summary":"done"}'}]
        )

        LLMStepPlanner(model_client).decide(request)

        sent_messages = model_client.chat_calls[0]["messages"]
        self.assertEqual(sent_messages[:-1], list(request.messages))
        self.assertEqual(sent_messages[-1]["role"], "user")

    def test_step_planner_embeds_history_when_tool_calls_are_disallowed(self):
        request = replace(
            build_step_request(),
            can_call_tool=False,
            messages=(
                {
                    "role": "assistant",
                    "content": "tool failed",
                    "metadata": {
                        "message_type": "tool_observation",
                        "tool_name": "retrieval.search",
                        "call_id": "loop-call-1",
                        "arguments": {"query": "checkpoint"},
                        "success": False,
                    },
                },
            ),
        )
        model_client = FakeModelClient(
            [{"type": "final_answer", "answer": '{"action":"abort_plan","reason":"limit"}'}]
        )

        LLMStepPlanner(model_client).decide(request)

        call = model_client.chat_calls[0]
        self.assertEqual(call["tool_definitions"], [])
        self.assertEqual(len(call["messages"]), 1)
        prompt = json.loads(call["messages"][0]["content"])
        self.assertEqual(prompt["session_messages"], list(request.messages))

    def test_step_planner_parses_complete_action_json(self):
        model_client = FakeModelClient(
            [
                {
                    "type": "final_answer",
                    "answer": (
                        '{"action":"complete_step",'
                        '"result_summary":"资料已获得",'
                        '"reflection":"结果足够"}'
                    ),
                }
            ]
        )

        decision = LLMStepPlanner(model_client).decide(build_step_request())

        self.assertIsInstance(decision.action, CompleteStepAction)
        self.assertEqual(decision.action.result_summary, "资料已获得")
        self.assertEqual(decision.reflection, "结果足够")

    def test_task_planner_rejects_invalid_json(self):
        model_client = FakeModelClient(
            [{"type": "final_answer", "answer": "not-json"}]
        )

        with self.assertRaises(PlannerProtocolError):
            LLMTaskPlanner(model_client).create_plan(build_create_request())

    def test_task_planner_rejects_unknown_persisted_state_fields(self):
        model_client = FakeModelClient(
            [
                {
                    "type": "final_answer",
                    "answer": (
                        '{"goal":"查询","steps":["检索"],'
                        '"status":"completed","plan_id":"model-plan"}'
                    ),
                }
            ]
        )

        with self.assertRaises(PlannerProtocolError):
            LLMTaskPlanner(model_client).create_plan(build_create_request())

    def test_step_planner_rejects_fields_outside_selected_action_schema(self):
        model_client = FakeModelClient(
            [
                {
                    "type": "final_answer",
                    "answer": (
                        '{"action":"complete_step","result_summary":"done",'
                        '"call_id":"model-call","status":"completed"}'
                    ),
                }
            ]
        )

        with self.assertRaises(PlannerProtocolError):
            LLMStepPlanner(model_client).decide(build_step_request())

    def test_task_planner_finalizes_with_model_answer(self):
        model_client = FakeModelClient(
            [{"type": "final_answer", "answer": "计划已完成，结果如下。"}]
        )
        request = FinalizePlanRequest(
            user_input="查询",
            plan={"goal": "查询", "steps": []},
            outcome="succeeded",
            abort_reason=None,
            messages=[],
        )

        action = LLMTaskPlanner(model_client).finalize_plan(request)

        self.assertEqual(action.answer, "计划已完成，结果如下。")


if __name__ == "__main__":
    unittest.main()

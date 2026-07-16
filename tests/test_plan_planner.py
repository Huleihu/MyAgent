"""
本文件负责验证 Plan-and-Execute Planner 协议、动作层级和输入快照隔离。
本文件不调用真实模型、工具或 Checkpoint Store。
"""

from __future__ import annotations

import unittest

from my_agent.agent_loop.plan_actions import (
    AbortPlanAction,
    CompleteStepAction,
    PlannerProtocolError,
    SkipStepAction,
    StepDecision,
)
from my_agent.agent_loop.plan_planner import (
    CreatePlanRequest,
    PlanDefinition,
    PlanStepDefinition,
    StepDecisionRequest,
)
from my_agent.agent_loop.planner import FinalAnswerAction, ToolAction


class PlanPlannerTest(unittest.TestCase):
    def test_package_exports_plan_and_execute_public_api(self):
        from my_agent import agent_loop

        exported_names = {
            "AbortPlanAction",
            "CompleteStepAction",
            "LLMStepPlanner",
            "LLMTaskPlanner",
            "PlanAndExecuteAgentLoop",
            "SkipStepAction",
            "StepPlanner",
            "TaskPlanner",
        }

        self.assertTrue(exported_names.issubset(set(agent_loop.__all__)))
        for name in exported_names:
            self.assertTrue(hasattr(agent_loop, name))

    def test_plan_definition_requires_at_least_one_step(self):
        with self.assertRaises(PlannerProtocolError):
            PlanDefinition(goal="查询资料", steps=())

    def test_step_decision_accepts_only_step_level_actions(self):
        actions = (
            ToolAction("retrieval.search", {"query": "checkpoint"}),
            CompleteStepAction("资料查询完成"),
            SkipStepAction("当前没有可用资料"),
            AbortPlanAction("无法继续执行"),
        )

        for action in actions:
            self.assertIs(StepDecision(action).action, action)

        with self.assertRaises(PlannerProtocolError):
            StepDecision(FinalAnswerAction("错误层级"))

    def test_create_plan_request_deep_copies_nested_inputs(self):
        messages = [{"role": "user", "content": "查询", "metadata": {"x": 1}}]
        tools = [{"name": "retrieval.search", "parameters": {"type": "object"}}]

        request = CreatePlanRequest(
            user_input="查询",
            messages=messages,
            tool_definitions=tools,
            max_plan_steps=3,
        )
        request.messages[0]["metadata"]["x"] = 2
        request.tool_definitions[0]["parameters"]["type"] = "string"

        self.assertEqual(messages[0]["metadata"]["x"], 1)
        self.assertEqual(tools[0]["parameters"]["type"], "object")

    def test_step_request_deep_copies_plan_and_observations(self):
        plan = {"plan_id": "plan-1", "steps": [{"step_id": "step-1"}]}
        observations = [
            {
                "call_id": "call-1",
                "success": True,
                "result": {"items": ["doc-1"]},
            }
        ]

        request = StepDecisionRequest(
            user_input="查询",
            plan=plan,
            current_step={"step_id": "step-1"},
            previous_step_summaries=(),
            observations=observations,
            recent_observation=observations[-1],
            messages=[],
            tool_definitions=[],
            remaining_step_tool_calls=2,
            remaining_total_tool_calls=4,
            can_call_tool=True,
        )
        request.plan["steps"][0]["step_id"] = "mutated"
        request.observations[0]["result"]["items"].append("doc-2")

        self.assertEqual(plan["steps"][0]["step_id"], "step-1")
        self.assertEqual(observations[0]["result"]["items"], ["doc-1"])

    def test_plan_step_definition_rejects_empty_instruction(self):
        with self.assertRaises(PlannerProtocolError):
            PlanStepDefinition("")


if __name__ == "__main__":
    unittest.main()

"""
本文件负责验证 JSON DSL Runtime v0.1 的加载、线性拓扑和节点调度行为。
本文件不测试 ToolExecutor、RAG 或真实 LLM SDK。
"""

import unittest

from my_agent.agent_loop.planner import FakePlanner, FinalAnswerAction
from my_agent.agent_loop.react import ReActAgentLoop
from my_agent.dsl.loader import WorkflowLoader
from my_agent.runtime.context import RuntimeContext
from my_agent.runtime.executor import RuntimeExecutor
from my_agent.runtime.graph import RuntimeGraph
from my_agent.runtime.node_runner import (
    AgentLoopNodeRunner,
    BeginNodeRunner,
    MessageNodeRunner,
)
from my_agent.state.session import SessionState
from my_agent.tools.executor import ToolExecutor
from my_agent.tools.registry import ToolRegistry


def build_agent_loop(session):
    planner = FakePlanner([FinalAnswerAction(answer="Agent 已完成回答")])
    return ReActAgentLoop(
        planner=planner,
        tool_executor=ToolExecutor(ToolRegistry()),
        session_state=session,
    )


def build_workflow_dict():
    return {
        "workflow_id": "workflow-1",
        "nodes": [
            {"node_id": "begin", "node_type": "begin"},
            {
                "node_id": "agent",
                "node_type": "agent_loop",
                "inputs": {"user_input": "{{user_input}}"},
            },
            {
                "node_id": "message",
                "node_type": "message",
                "inputs": {"content": "{{agent.output}}"},
            },
        ],
        "edges": [
            {"source": "begin", "target": "agent"},
            {"source": "agent", "target": "message"},
        ],
    }


class DslRuntimeTest(unittest.TestCase):
    def test_loader_builds_workflow_definition_from_dict(self):
        workflow = WorkflowLoader().load_dict(build_workflow_dict())

        self.assertEqual(workflow.workflow_id, "workflow-1")
        self.assertEqual([node.node_id for node in workflow.nodes], ["begin", "agent", "message"])
        self.assertEqual(workflow.nodes[1].node_type, "agent_loop")
        self.assertEqual(workflow.nodes[1].inputs["user_input"], "{{user_input}}")
        self.assertEqual(workflow.edges[0].source, "begin")
        self.assertEqual(workflow.edges[0].target, "agent")

    def test_loader_rejects_unsupported_tool_call_node(self):
        workflow_dict = build_workflow_dict()
        workflow_dict["nodes"].append({"node_id": "tool", "node_type": "tool_call"})

        with self.assertRaises(ValueError):
            WorkflowLoader().load_dict(workflow_dict)

    def test_loader_rejects_non_linear_graph(self):
        workflow_dict = build_workflow_dict()
        workflow_dict["edges"].append({"source": "begin", "target": "message"})

        with self.assertRaises(ValueError):
            WorkflowLoader().load_dict(workflow_dict)

    def test_graph_returns_linear_topology(self):
        workflow = WorkflowLoader().load_dict(build_workflow_dict())
        graph = RuntimeGraph(workflow)

        ordered_nodes = graph.linear_nodes()

        self.assertEqual(
            [node.node_id for node in ordered_nodes],
            ["begin", "agent", "message"],
        )

    def test_runtime_executor_runs_begin_agent_loop_and_message_nodes(self):
        session = SessionState(session_id="session-1")
        context = RuntimeContext(user_input="请回答问题", session_state=session)
        workflow = WorkflowLoader().load_dict(build_workflow_dict())
        agent_loop = build_agent_loop(session)
        executor = RuntimeExecutor(
            graph=RuntimeGraph(workflow),
            node_runners={
                "begin": BeginNodeRunner(),
                "agent_loop": AgentLoopNodeRunner(agent_loop),
                "message": MessageNodeRunner(),
            },
        )

        result_context = executor.run(context)

        self.assertIs(result_context, context)
        self.assertEqual(context.node_outputs["begin"], {"user_input": "请回答问题"})
        self.assertEqual(context.node_outputs["agent"], {"output": "Agent 已完成回答"})
        self.assertEqual(context.node_outputs["message"], {"content": "Agent 已完成回答"})
        self.assertEqual(context.variables["last_message"], "Agent 已完成回答")
        self.assertEqual(session.list_messages()[-1].content, "Agent 已完成回答")


if __name__ == "__main__":
    unittest.main()

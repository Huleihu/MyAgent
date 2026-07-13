"""
本文件负责为 Web 演示基于既有 SessionState 装配确定性 ConversationRuntime。
本文件不读取 HTTP 请求、不保存会话，也不接入真实模型或 RAG 知识库。
"""

from __future__ import annotations

from my_agent.agent_loop.planner import FinalAnswerAction, Planner
from my_agent.agent_loop.react import ReActAgentLoop
from my_agent.dsl.loader import WorkflowLoader
from my_agent.runtime.conversation import ConversationRuntime
from my_agent.runtime.executor import RuntimeExecutor
from my_agent.runtime.graph import RuntimeGraph
from my_agent.runtime.node_runner import (
    AgentLoopNodeRunner,
    BeginNodeRunner,
    MessageNodeRunner,
)
from my_agent.state.recorder import TraceRecorder
from my_agent.state.session import SessionState
from my_agent.tools.executor import ToolExecutor
from my_agent.tools.registry import ToolRegistry


class DemoPlanner(Planner):
    """根据当前会话中的用户消息数返回可复现的演示回答。"""

    def plan(self, user_input: str, session: SessionState) -> FinalAnswerAction:
        """返回包含回合序号的确定性最终回答。"""
        user_turn_count = sum(
            message.role == "user" for message in session.list_messages()
        )
        return FinalAnswerAction(answer=f"演示回答（第{user_turn_count}轮）：{user_input}")


def build_demo_runtime(session_state: SessionState) -> ConversationRuntime:
    """基于既有会话状态创建本次消息处理独占的演示 Runtime。"""
    if not isinstance(session_state, SessionState):
        raise TypeError("session_state must be a SessionState")

    workflow = WorkflowLoader().load_dict(_build_workflow_dict())
    tool_executor = ToolExecutor(
        ToolRegistry(),
        trace_recorder=TraceRecorder(session_state),
    )
    agent_loop = ReActAgentLoop(
        planner=DemoPlanner(),
        tool_executor=tool_executor,
        session_state=session_state,
    )
    executor = RuntimeExecutor(
        graph=RuntimeGraph(workflow),
        node_runners={
            "begin": BeginNodeRunner(),
            "agent_loop": AgentLoopNodeRunner(agent_loop),
            "message": MessageNodeRunner(),
        },
    )
    return ConversationRuntime(executor=executor, session_state=session_state)


def _build_workflow_dict() -> dict:
    """返回 Web 演示使用的最小线性 DSL 工作流。"""
    return {
        "workflow_id": "web-demo-workflow",
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

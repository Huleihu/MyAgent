"""
本文件负责为 Web 演示初始化固定知识库，并基于既有 SessionState 装配确定性 ConversationRuntime。
本文件不读取 HTTP 请求、不保存会话，也不接入真实模型或外部知识库。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from my_agent.agent_loop.planner import FinalAnswerAction, Planner, ToolAction
from my_agent.agent_loop.llm_planner import LLMPlanner
from my_agent.agent_loop.react import ReActAgentLoop
from my_agent.dsl.loader import WorkflowLoader
from my_agent.rag.indexing.chunker import TextChunker
from my_agent.rag.indexing.embedding import SimpleEmbeddingModel
from my_agent.rag.indexing.index import InMemoryChunkIndex
from my_agent.rag.parsing.markdown_parser import MarkdownDocumentParser
from my_agent.rag.parsing.parser import RawDocument
from my_agent.rag.retrieval.citation import CitationBuilder
from my_agent.rag.retrieval.reranker import SimpleReranker
from my_agent.rag.retrieval.retrieval_tool import RetrievalTool
from my_agent.rag.retrieval.retriever import HybridRetriever
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
from my_agent.llm.deepseek import DeepSeekModelClient
from my_agent.llm.settings import load_model_settings
from my_agent.tools.executor import ToolExecutor
from my_agent.tools.registry import ToolRegistry


class DemoRagPlanner(Planner):
    """根据会话最后消息驱动确定性检索与回答的演示 Planner。"""

    def plan(self, user_input: str, session: SessionState) -> ToolAction | FinalAnswerAction:
        """在用户消息后检索，在对应 observation 后依据 Trace 生成回答。"""
        messages = session.list_messages()
        if not messages:
            raise ValueError("DemoRagPlanner state contract failed: session has no messages")

        last_message = messages[-1]
        if last_message.role == "user":
            return ToolAction(
                tool_name="retrieval.search",
                arguments={"query": user_input, "top_k": 3},
            )

        if self._is_retrieval_observation(last_message):
            return self._build_final_answer(last_message.metadata, session)

        raise ValueError("DemoRagPlanner state contract failed: unsupported last message")

    def _is_retrieval_observation(self, message) -> bool:
        """判断最后消息是否为 retrieval.search 产生的 observation。"""
        return (
            message.role == "assistant"
            and message.metadata.get("message_type") == "tool_observation"
            and message.metadata.get("tool_name") == "retrieval.search"
        )

    def _build_final_answer(
        self,
        observation_metadata: dict,
        session: SessionState,
    ) -> FinalAnswerAction:
        """通过 observation 的 call_id 精确定位本次检索 Trace。"""
        call_id = observation_metadata.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            raise ValueError(
                "DemoRagPlanner state contract failed: retrieval observation has no call_id"
            )

        trace = next(
            (
                item
                for item in reversed(session.list_tool_traces())
                if item.call_id == call_id
            ),
            None,
        )
        if trace is None:
            raise ValueError(
                "DemoRagPlanner state contract failed: retrieval trace not found for call_id"
            )
        if not trace.success:
            return FinalAnswerAction(answer="知识库检索失败，暂时无法根据演示资料回答。")
        if not isinstance(trace.result, dict):
            raise ValueError(
                "DemoRagPlanner state contract failed: successful retrieval trace has no result"
            )

        chunks = trace.result.get("chunks")
        if not isinstance(chunks, list):
            raise ValueError(
                "DemoRagPlanner state contract failed: retrieval result chunks must be a list"
            )
        contents = [
            chunk.get("content")
            for chunk in chunks[:2]
            if isinstance(chunk, dict)
            and isinstance(chunk.get("content"), str)
            and chunk["content"].strip()
        ]
        if not contents:
            return FinalAnswerAction(answer="演示知识库中未找到与该问题相关的内容。")
        return FinalAnswerAction(answer="\n\n".join(contents))


def build_demo_runtime(session_state: SessionState) -> ConversationRuntime:
    """基于既有会话状态创建本次消息处理独占的演示 Runtime。"""
    if not isinstance(session_state, SessionState):
        raise TypeError("session_state must be a SessionState")

    registry = _build_demo_tool_registry()
    return _assemble_runtime(session_state, registry, DemoRagPlanner())


def build_runtime(session_state: SessionState) -> ConversationRuntime:
    """按环境变量选择离线 Demo 或 DeepSeek Runtime，不静默降级配置错误。"""
    if not isinstance(session_state, SessionState):
        raise TypeError("session_state must be a SessionState")

    settings = load_model_settings()
    if settings is None:
        return build_demo_runtime(session_state)

    registry = _build_demo_tool_registry()
    planner = LLMPlanner(
        model_client=DeepSeekModelClient(settings.model_config),
        tool_definitions=registry.list_definitions(),
    )
    return _assemble_runtime(session_state, registry, planner)


def _build_demo_tool_registry() -> ToolRegistry:
    """创建只读演示知识库对应的工具注册表。"""
    registry = ToolRegistry()
    registry.register(_get_demo_retrieval_tool())
    return registry


def _assemble_runtime(
    session_state: SessionState,
    registry: ToolRegistry,
    planner: Planner,
) -> ConversationRuntime:
    """复用既有 DSL、工具与会话状态装配单个 ConversationRuntime。"""
    workflow = WorkflowLoader().load_dict(_build_workflow_dict())
    tool_executor = ToolExecutor(registry, trace_recorder=TraceRecorder(session_state))
    agent_loop = ReActAgentLoop(planner=planner, tool_executor=tool_executor, session_state=session_state)
    executor = RuntimeExecutor(
        graph=RuntimeGraph(workflow),
        node_runners={
            "begin": BeginNodeRunner(),
            "agent_loop": AgentLoopNodeRunner(agent_loop),
            "message": MessageNodeRunner(),
        },
    )
    return ConversationRuntime(executor=executor, session_state=session_state)


@lru_cache(maxsize=1)
def _get_demo_retrieval_tool() -> RetrievalTool:
    """一次性完成 Demo 文档入库，并返回可跨会话共享的只读检索工具。"""
    parser = MarkdownDocumentParser()
    documents = []
    for document_path in sorted(_demo_docs_directory().glob("*.md")):
        documents.extend(
            parser.parse(
                RawDocument(
                    source=f"demo://{document_path.name}",
                    filename=document_path.name,
                    content=document_path.read_text(encoding="utf-8"),
                    metadata={"doc_id": f"demo-{document_path.stem}"},
                )
            )
        )

    chunker = TextChunker(chunk_size=400)
    index = InMemoryChunkIndex(SimpleEmbeddingModel())
    index.add_chunks(chunker.split_many(documents))

    # 索引构建完成后不再写入，因此 RetrievalTool 可安全跨 session 共享。
    return RetrievalTool(
        retriever=HybridRetriever(index),
        reranker=SimpleReranker(),
        citation_builder=CitationBuilder(),
    )


def _demo_docs_directory() -> Path:
    """基于当前模块位置返回稳定的演示知识库目录。"""
    return Path(__file__).resolve().parents[2] / "demo_docs"


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

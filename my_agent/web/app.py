"""
本文件负责提供 ConversationRuntime 的 HTTP 适配与稳定 API 契约。
本文件只依赖 SessionStore 和 RuntimeFactory，不直接管理 Runtime 全局字典或持久化细节。
"""

from __future__ import annotations

from copy import deepcopy
import logging
from collections.abc import Callable
from dataclasses import asdict
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from my_agent.runtime.conversation import ConversationRuntime, ConversationTurnResult
from my_agent.state.session import SessionState
from my_agent.web.demo_runtime import build_runtime
from my_agent.web.session_store import InMemorySessionStore, SessionStore
from my_agent.state.checkpoint_store import CheckpointStore, InMemoryCheckpointStore

logger = logging.getLogger(__name__)

RuntimeFactory = Callable[[SessionState], ConversationRuntime]


class MessageRequest(BaseModel):
    """定义发送给指定会话的用户消息请求。"""

    user_input: str

    @field_validator("user_input")
    @classmethod
    def validate_user_input(cls, user_input: str) -> str:
        """拒绝空白消息，避免无效请求进入 Runtime。"""
        if not isinstance(user_input, str) or not user_input.strip():
            raise ValueError("user_input must be a non-empty string")
        return user_input


def create_app(
    runtime_factory: RuntimeFactory = build_runtime,
    session_store: SessionStore | None = None,
    checkpoint_store: CheckpointStore | None = None,
) -> FastAPI:
    """创建具备独立会话 store 的最小 Runtime Web API。"""
    if not callable(runtime_factory):
        raise TypeError("runtime_factory must be callable")

    store = InMemorySessionStore() if session_store is None else session_store
    checkpoints = InMemoryCheckpointStore() if checkpoint_store is None else checkpoint_store
    if runtime_factory is build_runtime:
        runtime_factory = lambda session: build_runtime(session, checkpoints)
    app = FastAPI(title="myAgent Runtime Demo", version="0.1.0")

    @app.get("/health")
    def get_health() -> dict[str, str]:
        """返回服务存活状态。"""
        return {"status": "ok"}

    @app.post("/sessions", status_code=status.HTTP_201_CREATED)
    def create_session() -> dict[str, str]:
        """创建一个仅保存内存状态的新会话。"""
        session_state = SessionState(session_id=str(uuid4()))
        store.create(session_state)
        return {"session_id": session_state.session_id}

    @app.post("/sessions/{session_id}/messages")
    def send_message(session_id: str, request: MessageRequest) -> dict:
        """串行执行同一会话的一条消息，并返回本轮结果与 Trace。"""
        session_handle = store.get(session_id)
        if session_handle is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="session not found")

        try:
            with session_handle.lock:
                runtime = runtime_factory(session_handle.session_state)
                turn_result = runtime.chat(request.user_input)
        except Exception:
            logger.exception("会话 %s 的 Runtime 执行失败", session_id)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content=_runtime_failure_response(),
            )

        return _serialize_turn_result(session_id, turn_result)

    @app.post("/runs/{run_id}/resume")
    def resume_run(run_id: str) -> dict:
        """将 Checkpoint 恢复到 Store 中唯一的 SessionState 后继续执行。"""
        checkpoint = checkpoints.get_latest(run_id)
        if checkpoint is None or checkpoint.run_state is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
        handle = store.get_or_create(checkpoint.run_state.session_id)
        with handle.lock:
            handle.session_state.restore_snapshot(checkpoint.run_state.messages, checkpoint.run_state.tool_traces)
            result = runtime_factory(handle.session_state).resume(run_id)
        return _serialize_turn_result(handle.session_state.session_id, result)

    return app


def _serialize_turn_result(
    session_id: str,
    turn_result: ConversationTurnResult,
) -> dict:
    """将 Runtime 回合结果转换为对外稳定 JSON 数据。"""
    return {
        "session_id": session_id,
        "run_id": turn_result.run_id,
        "output_text": turn_result.output_text,
        "citations": _extract_turn_citations(turn_result.tool_traces),
        "node_traces": [asdict(trace) for trace in turn_result.node_traces],
        "tool_traces": [asdict(trace) for trace in turn_result.tool_traces],
    }


def _extract_turn_citations(tool_traces) -> list[dict]:
    """从当前回合成功检索 Trace 提取、去重并复制 Citation。"""
    citations = []
    seen_citation_keys = set()
    for trace in tool_traces:
        if (
            trace.tool_name != "retrieval.search"
            or not trace.success
            or not isinstance(trace.result, dict)
        ):
            continue
        trace_citations = trace.result.get("citations")
        if not isinstance(trace_citations, list):
            continue
        for citation in trace_citations:
            if not isinstance(citation, dict):
                continue
            citation_key = (citation.get("doc_id"), citation.get("chunk_id"))
            if citation_key in seen_citation_keys:
                continue
            seen_citation_keys.add(citation_key)
            citations.append(deepcopy(citation))
    return citations


def _runtime_failure_response() -> dict:
    """返回不泄漏异常细节的稳定 Runtime 执行失败响应。"""
    return {
        "error": {
            "code": "runtime_execution_failed",
            "message": "Runtime execution failed",
        }
    }


app = create_app()

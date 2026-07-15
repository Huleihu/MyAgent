"""
本文件负责提供 ConversationRuntime 的 HTTP 适配与稳定 API 契约。
本文件只依赖 SessionStore 和 RuntimeFactory，不直接管理 Runtime 全局字典或持久化细节。
"""

from __future__ import annotations

from copy import deepcopy
import logging
from contextlib import asynccontextmanager
from collections.abc import Callable
from dataclasses import asdict
from uuid import uuid4

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from my_agent.runtime.conversation import ConversationRuntime, ConversationTurnResult, RunAlreadyCompletedError, RunExecutionFailedError
from my_agent.state.session import SessionState
from my_agent.web.demo_runtime import build_runtime
from my_agent.web.session_store import InMemorySessionStore, SessionStore
from my_agent.state.checkpoint_store import CheckpointStore, InMemoryCheckpointStore
from my_agent.state.run_state import RunStatus
from my_agent.web.checkpoint_settings import create_default_checkpoint_store

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
    owns_checkpoint_store = checkpoint_store is None
    checkpoints = create_default_checkpoint_store() if owns_checkpoint_store else checkpoint_store
    if runtime_factory is build_runtime:
        runtime_factory = lambda session: build_runtime(session, checkpoints)
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            if owns_checkpoint_store and hasattr(checkpoints, "close"):
                checkpoints.close()

    app = FastAPI(title="myAgent Runtime Demo", version="0.1.0", lifespan=lifespan)
    app.state.checkpoint_store = checkpoints

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
            runtime = runtime_factory(session_handle.session_state)
        except Exception:
            logger.exception("会话 %s 的 Runtime 初始化失败", session_id)
            return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=_runtime_initialization_failure_response())
        try:
            with session_handle.lock:
                turn_result = runtime.chat(request.user_input)
        except RunExecutionFailedError as exc:
            logger.exception("会话 %s 的 Runtime 执行失败", session_id)
            return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=_run_failure_response(exc))
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
        if checkpoint.run_state.status is RunStatus.COMPLETED:
            return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"error": {"code": "run_already_completed", "message": "Run is already completed"}})
        handle = store.get_or_create(checkpoint.run_state.session_id)
        try:
            runtime = runtime_factory(handle.session_state)
        except Exception:
            logger.exception("运行 %s 的 Runtime 初始化失败", run_id)
            return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=_runtime_initialization_failure_response())
        try:
            with handle.lock:
                handle.session_state.restore_snapshot(checkpoint.run_state.messages, checkpoint.run_state.tool_traces)
                result = runtime.resume(run_id)
        except RunAlreadyCompletedError:
            return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"error": {"code": "run_already_completed", "message": "Run is already completed"}})
        except RunExecutionFailedError as exc:
            logger.exception("运行 %s 的恢复执行失败", run_id)
            return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=_run_failure_response(exc))
        return _serialize_turn_result(handle.session_state.session_id, result)

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        """返回最新 Checkpoint 的稳定运行摘要，不公开内部异常详情。"""
        checkpoint = checkpoints.get_latest(run_id)
        if checkpoint is None or checkpoint.run_state is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
        state = checkpoint.run_state
        return {"run_id": state.run_id, "session_id": state.session_id, "workflow_id": state.workflow_id, "status": state.status.value, "sequence_no": checkpoint.sequence_no, "created_at_utc": state.created_at_utc, "updated_at_utc": state.updated_at_utc, "cursor": {"next_node_id": state.cursor.next_node_id, "completed_node_ids": list(state.cursor.completed_node_ids), "agent_round_index": state.cursor.agent_round_index, "agent_phase": state.cursor.agent_phase}, "pending_tool_call": None if state.pending_tool_call is None else {"tool_name": state.pending_tool_call.tool_name, "call_id": state.pending_tool_call.call_id}, "error": _public_run_error(state.error)}

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


def _runtime_initialization_failure_response() -> dict:
    """返回 Runtime 创建失败时不伪造运行标识的稳定响应。"""
    return {"error": {"code": "runtime_initialization_failed", "message": "Runtime initialization failed"}}


def _run_failure_response(error: RunExecutionFailedError) -> dict:
    """返回已创建运行的失败响应，供客户端查询并恢复。"""
    return {"run_id": error.run_id, "session_id": error.session_id, "status": "failed", **_runtime_failure_response()}


def _public_run_error(error: dict | None) -> dict | None:
    """将内部异常详情收敛为公开 API 的稳定错误结构。"""
    if error is None:
        return None
    return {"code": "runtime_failed", "message": "Runtime execution failed"}


app = create_app()

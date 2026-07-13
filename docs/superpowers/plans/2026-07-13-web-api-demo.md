# 最小 Web API 演示入口实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 为现有 `ConversationRuntime` 提供带会话隔离、回合 Trace 返回和确定性演示装配的最小 FastAPI 入口。

**架构：** HTTP 层只负责请求校验、会话查找、串行保护、结果序列化和稳定错误响应，并且只依赖 `SessionStore` 抽象。`demo_runtime.py` 只负责基于既有 `SessionState` 独立装配 Planner、`TraceRecorder`、`ReActAgentLoop` 和 `ConversationRuntime`，不改动现有 Runtime、Agent Loop、RAG 或 DSL 调度实现。

**技术栈：** Python 3.11、FastAPI、Uvicorn、unittest、FastAPI TestClient。

## 全局约束

- 所有新建 Python 文件顶部使用中文模块职责说明，公共对象使用简洁中文文档字符串。
- `create_app(runtime_factory=...)` 不使用全局 session store；每个应用实例注入独立 `SessionStore`。
- `RuntimeFactory` 接收已存在的 `SessionState`；每次消息处理基于该状态独立装配 Runtime 关联对象，不跨 session 共享。
- `SessionStore` 负责会话状态及 session 级锁；未来持久化保存 `SessionState` 的消息和 Trace，而不是序列化 `ConversationRuntime`。
- 同一 session 的消息使用 session 级锁串行执行；不承诺持久化、跨进程共享或同 session 并发吞吐。
- 成功响应固定包含 `session_id`、`output_text`、`node_traces`、`tool_traces`；执行异常统一返回 `runtime_execution_failed`。
- 不接入数据库、鉴权、流式输出或真实模型；演示 Planner 必须确定性。

---

### Task 1: API 契约测试与依赖

**文件：**
- 创建：`tests/test_web_api.py`
- 修改：`requirements.txt`

**接口：**
- 消费：待实现的 `my_agent.web.app.create_app(runtime_factory)`。
- 产出：覆盖 health、创建会话、422、404、连续上下文、会话隔离、500 和本轮 Trace 的 API 契约测试。

- [ ] **步骤 1：编写失败的 API 测试**

```python
app = create_app(runtime_factory=factory)
client = TestClient(app)
session_id = client.post("/sessions").json()["session_id"]
response = client.post(f"/sessions/{session_id}/messages", json={"user_input": "问题"})
self.assertEqual(response.json()["session_id"], session_id)
```

测试分别断言 `/health`、`POST /sessions`、未知 session 的 404、空白与缺失 `user_input` 的 422、同 session 历史、两个 session 隔离、运行时异常的稳定 500 响应及 Trace 回合快照。

- [ ] **步骤 2：运行测试确认失败**

运行：`conda run -n myagent-py311 python -m unittest tests.test_web_api -v`

预期：因 `my_agent.web` 尚不存在而失败。

- [ ] **步骤 3：声明运行依赖**

在 `requirements.txt` 增加受限版本的 `fastapi`、`uvicorn` 和 HTTP 测试客户端依赖，保持现有依赖不变。

### Task 2: 会话状态仓储与确定性演示 Runtime 装配

**文件：**
- 创建：`my_agent/web/demo_runtime.py`
- 创建：`my_agent/web/session_store.py`
- 测试：`tests/test_web_api.py`

**接口：**
- 产出：`SessionStore`、`InMemorySessionStore` 和 `build_demo_runtime(session_state: SessionState) -> ConversationRuntime`。
- 消费：现有 WorkflowLoader、RuntimeExecutor、节点执行器、SessionState、ToolRegistry、ToolExecutor、TraceRecorder、ReActAgentLoop。

- [ ] **步骤 1：实现最小确定性 Planner 和装配函数**

```python
class DemoPlanner(Planner):
    def plan(self, user_input: str, session: SessionState) -> FinalAnswerAction:
        return FinalAnswerAction(answer=f"演示回答：{user_input}")

def build_demo_runtime(session_state: SessionState) -> ConversationRuntime:
    """为既有会话状态创建互不共享的演示 Runtime。"""
```

`InMemorySessionStore` 保存 `SessionState` 与 session 级锁；装配函数每次调用只使用传入的既有状态，并创建新的 `DemoPlanner`、`TraceRecorder`、`ToolExecutor`、`ReActAgentLoop` 和 `ConversationRuntime`。未来持久化实现只需替换 Store 的状态读取与保存。

- [ ] **步骤 2：运行 API 测试确认仍只缺 HTTP 适配**

运行：`conda run -n myagent-py311 python -m unittest tests.test_web_api -v`

预期：测试仍因 `create_app` 未实现失败。

### Task 3: FastAPI 应用工厂与 session store

**文件：**
- 创建：`my_agent/web/app.py`
- 创建：`my_agent/web/__init__.py`
- 测试：`tests/test_web_api.py`

**接口：**
- 消费：`SessionStore`、`Callable[[SessionState], ConversationRuntime]` 与 `ConversationRuntime.chat(user_input)`。
- 产出：`create_app(runtime_factory=build_demo_runtime) -> FastAPI` 与模块级 `app`。

- [ ] **步骤 1：实现会话记录和 API 路由**

```python
def create_app(
    runtime_factory: Callable[[str], ConversationRuntime] = build_demo_runtime,
) -> FastAPI:
    """创建持有独立内存会话 store 的 Web API 应用。"""
```

创建 session 时 Store 保存新的 `SessionState`；发送消息时路由从 Store 查找状态与锁，在锁内通过工厂装配 Runtime 并调用 `chat`。路由不持有或操作 `dict[str, ConversationRuntime]`。将 dataclass Trace 显式转换为 JSON dict，不暴露 `RuntimeContext`。记录异常日志，并以固定错误 JSON 和 500 返回。

- [ ] **步骤 2：运行 API 测试确认通过**

运行：`conda run -n myagent-py311 python -m unittest tests.test_web_api -v`

预期：所有 Web API 测试通过。

### Task 4: 启动说明与回归验证

**文件：**
- 修改：`docs/project-handoff.md`

**接口：**
- 产出：启动命令、端点、内存会话和并发限制的最小交接说明。

- [ ] **步骤 1：补充交接文档**

加入启动命令：

```bash
conda run -n myagent-py311 uvicorn my_agent.web.app:app --reload
```

说明 `POST /sessions` 与 `POST /sessions/{session_id}/messages`，以及内存 session、单 session 串行保护、无真实模型和无持久化的限制。

- [ ] **步骤 2：运行完整回归**

运行：`conda run -n myagent-py311 python -m unittest discover -s tests -v`

预期：所有既有测试与新增 Web API 测试通过。

## 自检

- 覆盖了 session 独立实例、session 级锁、应用工厂、规定成功与失败响应、确定性 Planner 和全部指定测试场景。
- 未引入 Runtime、Agent Loop、RAG、DSL 调度的职责修改。
- 无未定义接口、占位实现或待定范围。

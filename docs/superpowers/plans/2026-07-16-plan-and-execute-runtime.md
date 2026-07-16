# Plan-and-Execute Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现本地标准 Tool 的 Plan -> Execute -> Observe -> Retry/Reflect -> Final Answer 闭环，并支持真实 LLM Planner、步骤级多工具历史和 SQLite Checkpoint 恢复。

**Architecture:** 新增独立 `PlanAndExecuteAgentLoop`，通过 `TaskPlanner` 和 `StepPlanner` 获取只读决策，由 Loop 独占状态、计数、call ID 和 Checkpoint 推进。`PlanState` 只保存可序列化控制数据，完整工具结果继续来自 RunState Tool Trace；现有 ReAct 和 Runtime DSL 接口保持兼容。

**Tech Stack:** Python 3.11、dataclasses、Protocol、FastAPI Runtime 装配、SQLite Checkpoint、pytest、unittest。

**Implementation Status:** 已完成实现并经过独立 Code Review；审查确认的 Important 状态顺序、恢复状态、Trace 重放、Planner 字段边界和 JSON 持久化问题均已补回归测试并修复。保留原始任务复选框作为执行过程模板，本文件不代表 Git 提交状态。

## Global Constraints

- 严格遵守根目录 `AGENTS.md`：新增 Python 文件顶部写中文职责说明，公共接口和关键逻辑使用简洁中文文档字符串。
- 每项实现先补失败测试，再运行定向测试确认失败，最后写最小实现。
- 保持 `Planner`、`LLMPlanner`、`FakePlanner`、`ConversationRuntime.chat()` 和现有 Web API 兼容。
- Planner 不得控制 call ID、计数、状态、限制或 Plan outcome。
- 恢复已有计划时使用 Checkpoint 中的限制，不使用新 Runtime 配置覆盖。
- `pending_tool_call` 是待执行完整工具调用的唯一恢复来源。
- 当前工具恢复语义为 at-least-once，不承诺 exactly-once。
- 不接真实 MCP；未来 MCP 仅通过 ToolRegistry 适配。
- 不访问真实 LLM 服务；LLM Planner 自动化测试注入 `FakeModelClient`。
- 不自动 commit 或 push；计划中的每个任务以测试通过和工作区检查结束。

---

### Task 1: PlanState、RunState 序列化与一致性矩阵

**Files:**
- Create: `my_agent/state/plan_state.py`
- Modify: `my_agent/state/run_state.py`
- Test: `tests/test_plan_state.py`

**Interfaces:**
- Produces: `PlanStatus`、`PlanOutcome`、`PlanStepStatus`、`PlanStep`、`PlanState`。
- Produces: `RunState.plan_state: PlanState | None`、`RunState.validate_consistency()`。
- Consumes: 现有 `ExecutionCursor`、`PendingToolCall`、`ToolTraceRecord` 和 SessionMessage。

- [ ] **Step 1: 写 PlanState 基本模型失败测试**

```python
def test_plan_state_round_trip_preserves_steps_limits_and_call_ids():
    state = build_running_plan_state(tool_call_ids=["call-1"])
    restored = PlanState.from_dict(state.to_dict())
    assert restored == state
    assert restored.steps[0].attempt_count == 1
    assert restored.max_total_tool_calls == 5
```

- [ ] **Step 2: 运行模型测试确认失败**

Run: `pytest tests/test_plan_state.py -q`

Expected: FAIL，提示 `my_agent.state.plan_state` 不存在。

- [ ] **Step 3: 实现最小状态模型和 JSON round-trip**

```python
class PlanStatus(str, Enum):
    RUNNING = "running"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    ABORTED = "aborted"


@dataclass
class PlanStep:
    step_id: str
    instruction: str
    status: PlanStepStatus
    attempt_count: int = 0
    retry_count: int = 0
    tool_call_ids: list[str] = field(default_factory=list)
    last_observation_summary: str | None = None
    reflection: str | None = None
    result_summary: str | None = None
    failure_reason: str | None = None
```

`PlanState.to_dict()` 和 `from_dict()` 必须深拷贝列表，并校验计数、限制、唯一 ID、当前 running 步骤和 outcome。

- [ ] **Step 4: 补 RunState 向后兼容与一致性失败测试**

```python
def test_old_run_state_payload_defaults_plan_state_to_none():
    payload = build_run_state().to_dict()
    payload.pop("plan_state", None)
    assert RunState.from_dict(payload).plan_state is None


def test_plan_tool_pending_requires_matching_pending_call():
    run_state = build_plan_run_state(agent_phase="plan_tool_pending")
    run_state.pending_tool_call = None
    with pytest.raises(PlanStateConsistencyError):
        run_state.validate_consistency()
```

逐项覆盖设计中的 phase 矩阵，包括 `plan_creating`、`plan_step_deciding`、`plan_tool_pending`、`plan_finalizing`、`plan_final_answer_written` 和 Runtime `completed`。

- [ ] **Step 5: 实现 RunState 可选字段和统一校验**

```python
def validate_consistency(self) -> None:
    if self.plan_state is None:
        if self.cursor.agent_phase.startswith("plan_") and self.cursor.agent_phase != "plan_creating":
            raise PlanStateConsistencyError("plan phase requires plan_state")
        return
    self.plan_state.validate()
    _validate_plan_runtime_links(self)
```

`RunState.to_dict()`、`RunState.from_dict()` 和 `Checkpoint.create()` 在持久化边界调用该校验。旧 ReAct 状态不进入 Plan 校验分支。

- [ ] **Step 6: 运行定向测试**

Run: `pytest tests/test_plan_state.py tests/test_run_state.py tests/test_checkpoint_store.py -q`

Expected: PASS。

---

### Task 2: Planner 动作、协议与深拷贝快照

**Files:**
- Create: `my_agent/agent_loop/plan_actions.py`
- Create: `my_agent/agent_loop/plan_planner.py`
- Test: `tests/test_plan_planner.py`

**Interfaces:**
- Produces: `CompleteStepAction`、`SkipStepAction`、`AbortPlanAction`、`StepDecision`。
- Produces: `PlanDefinition`、`PlanStepDefinition`、`CreatePlanRequest`、`StepDecisionRequest`、`FinalizePlanRequest`。
- Produces: `TaskPlanner` 和 `StepPlanner` Protocol。
- Produces: `PlannerProtocolError(code="planner_protocol_error")`。

- [ ] **Step 1: 写协议和动作失败测试**

```python
def test_step_decision_rejects_final_answer_action():
    with pytest.raises(PlannerProtocolError):
        StepDecision(action=FinalAnswerAction("wrong level"))


def test_plan_definition_rejects_empty_steps():
    with pytest.raises(PlannerProtocolError):
        PlanDefinition(goal="goal", steps=())
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_plan_planner.py -q`

Expected: FAIL，提示新模块不存在。

- [ ] **Step 3: 实现动作、请求 DTO 和 Protocol**

```python
@dataclass(frozen=True)
class StepDecision:
    action: ToolAction | CompleteStepAction | SkipStepAction | AbortPlanAction
    reflection: str | None = None


class TaskPlanner(Protocol):
    def create_plan(self, request: CreatePlanRequest) -> PlanDefinition: ...
    def finalize_plan(self, request: FinalizePlanRequest) -> FinalAnswerAction: ...


class StepPlanner(Protocol):
    def decide(self, request: StepDecisionRequest) -> StepDecision: ...
```

- [ ] **Step 4: 写 Planner 输入引用隔离失败测试**

构造会修改消息 metadata、计划快照、工具 schema 和 observation result 的恶意 Planner，断言真实 Session、PlanState、ToolDefinition 和 ToolTraceRecord 均不变化。

- [ ] **Step 5: 实现快照构造函数**

在 `plan_planner.py` 提供只接收深拷贝值的 DTO。顺序集合转 tuple；嵌套 dict 使用 `deepcopy()`。Loop 后续只能通过这些构造函数创建 request。

- [ ] **Step 6: 运行定向测试**

Run: `pytest tests/test_plan_planner.py -q`

Expected: PASS。

---

### Task 3: 基于 ModelClient 的真实 LLM Planner

**Files:**
- Create: `my_agent/agent_loop/llm_plan_planner.py`
- Test: `tests/test_llm_plan_planner.py`

**Interfaces:**
- Consumes: Task 2 的 Planner Protocol 和请求/动作模型。
- Consumes: `my_agent.llm.client.ModelClient`、`FakeModelClient`、`ToolDefinition`。
- Produces: `LLMTaskPlanner`、`LLMStepPlanner`。

- [ ] **Step 1: 写 LLMTaskPlanner 失败测试**

```python
def test_llm_task_planner_parses_plan_json():
    client = FakeModelClient([{
        "type": "final_answer",
        "answer": '{"goal":"查资料并总结","steps":["检索资料","整理答案"]}',
    }])
    planner = LLMTaskPlanner(client)
    plan = planner.create_plan(build_create_request())
    assert [step.instruction for step in plan.steps] == ["检索资料", "整理答案"]
    assert client.chat_calls[0]["tool_definitions"] == []
```

- [ ] **Step 2: 写 LLMStepPlanner 失败测试**

```python
def test_llm_step_planner_discards_provider_call_id():
    client = FakeModelClient([{
        "type": "tool_call",
        "tool_name": "retrieval.search",
        "arguments": {"query": "checkpoint"},
        "call_id": "provider-call",
    }])
    decision = LLMStepPlanner(client).decide(build_step_request())
    assert isinstance(decision.action, ToolAction)
    assert decision.action.call_id is None
```

另写 Complete、Skip、Abort JSON、非法 JSON、非法 response type 和 finalization 测试。

- [ ] **Step 3: 运行测试确认失败**

Run: `pytest tests/test_llm_plan_planner.py -q`

Expected: FAIL，提示 `llm_plan_planner` 不存在。

- [ ] **Step 4: 实现真实 LLM Planner**

```python
class LLMTaskPlanner:
    def create_plan(self, request):
        response = self._model_client.chat(
            messages=[{"role": "user", "content": _build_plan_prompt(request)}],
            tool_definitions=[],
        )
        return _parse_plan_definition(response)


class LLMStepPlanner:
    def decide(self, request):
        response = self._model_client.chat(
            messages=_build_step_messages(request),
            tool_definitions=_copy_tool_definitions(request.tool_definitions),
        )
        if response.get("type") == "tool_call":
            return StepDecision(ToolAction(response["tool_name"], deepcopy(response["arguments"]), None))
        return _parse_step_terminal_action(response)
```

JSON 解析器只接受明确 schema；错误包装为 `PlannerProtocolError` 并保留原异常上下文。

- [ ] **Step 5: 运行定向和现有 LLM 回归测试**

Run: `pytest tests/test_llm_plan_planner.py tests/test_llm_planner.py tests/test_deepseek_model_client.py -q`

Expected: PASS。

---

### Task 4: PlanAndExecuteAgentLoop 正常闭环与多工具历史

**Files:**
- Create: `my_agent/agent_loop/plan_execute.py`
- Modify: `my_agent/agent_loop/__init__.py`
- Test: `tests/test_plan_execute_agent_loop.py`

**Interfaces:**
- Consumes: Tasks 1-3 的状态、Planner 和动作类型。
- Consumes: 现有 `ToolExecutor`、`SessionState`、`CheckpointRecorder`、`RunState.pending_tool_call`。
- Produces: `PlanAndExecuteAgentLoop.run()` 和 `bind_run_state()`。

- [ ] **Step 1: 写创建计划、工具成功后继续决策和显式完成的失败测试**

测试动作序列：创建一条步骤；StepPlanner 返回 ToolAction；工具成功；StepPlanner 收到 observation 后返回 CompleteStepAction；TaskPlanner 返回最终回答。断言工具成功时步骤仍为 RUNNING，Complete 后才终态化。

- [ ] **Step 2: 写同一步骤多工具历史失败测试**

连续返回两个 ToolAction，再完成步骤。第二次和第三次 StepPlanner request 应分别包含一条和两条 observation，顺序与 `tool_call_ids` 一致。

- [ ] **Step 3: 运行测试确认失败**

Run: `pytest tests/test_plan_execute_agent_loop.py -q`

Expected: FAIL，提示 `PlanAndExecuteAgentLoop` 不存在。

- [ ] **Step 4: 实现最小状态机**

实现 phase 分派方法：

```python
def run(self, user_input: str) -> str:
    self._ensure_user_message_and_plan(user_input)
    while True:
        phase = self._run_state.cursor.agent_phase
        if phase == "plan_step_deciding":
            self._decide_current_step()
        elif phase == "plan_tool_pending":
            self._execute_pending_tool()
        elif phase == "plan_finalizing":
            return self._finalize_plan()
        elif phase == "plan_final_answer_written":
            return self._read_saved_final_answer()
        else:
            raise PlanStateConsistencyError("unsupported plan phase")
```

Loop 接受新 ToolAction 时拒绝非空 provider call ID，生成 UUID，追加 `tool_call_ids`，增加 attempt/retry，创建 pending 并在执行前保存 Checkpoint。

- [ ] **Step 5: 实现 observation 历史重建**

按 `tool_call_ids` 查找 Tool Trace；同一 call ID 选择列表中最后一条；返回深拷贝 tuple。若非 pending call 缺少 Trace，抛 `PlanStateConsistencyError`。

- [ ] **Step 6: 实现 Complete、Skip、Abort 和 outcome**

步骤终态与下一步骤 RUNNING、current ID 和 phase 在一次状态变更后写入同一 Checkpoint。Abort 保持剩余步骤 PENDING；最终回答后 PlanStatus 仍为 ABORTED。

- [ ] **Step 7: 运行定向测试**

Run: `pytest tests/test_plan_execute_agent_loop.py -q`

Expected: PASS。

---

### Task 5: Checkpoint 恢复、at-least-once 与失败持久化

**Files:**
- Modify: `my_agent/agent_loop/plan_execute.py`
- Modify: `my_agent/runtime/executor.py`
- Test: `tests/test_plan_execute_checkpoint_resume.py`

**Interfaces:**
- Consumes: Task 4 状态机。
- Produces: 所有 Plan phase 的恢复行为和稳定 `planner_protocol_error` 持久化。

- [ ] **Step 1: 写 phase 恢复失败测试**

逐项构造 `plan_creating`、`plan_step_deciding`、`plan_tool_pending`、`plan_finalizing` 和 `plan_final_answer_written` Checkpoint，断言恢复调用的 Planner/Tool 次数符合规格。

- [ ] **Step 2: 写 at-least-once 故障注入测试**

工具第一次产生共享计数效果后，在 observation Checkpoint 前抛异常。新 Runtime 恢复后断言相同 Loop call ID 再次执行、共享计数变为 2，而 attempt/retry 不重复增加。

- [ ] **Step 3: 写 Planner 协议错误持久化测试**

在 `can_call_tool=False` 时让 StepPlanner 返回 ToolAction，断言工具未执行，最新 RunState 为 FAILED，error code 为 `planner_protocol_error`，PlanState 和计数保持一致。

- [ ] **Step 4: 运行测试确认失败**

Run: `pytest tests/test_plan_execute_checkpoint_resume.py -q`

Expected: FAIL 于尚未实现的恢复或稳定错误契约。

- [ ] **Step 5: 实现恢复和稳定失败记录**

`plan_tool_pending` 只从 `pending_tool_call` 恢复，不重新调用 StepPlanner、不增加计数。Planner 协议错误先同步 RunState 并记录 `planner_protocol_failed`，再抛出带 `code` 的异常；RuntimeExecutor 后续 `run_failed` 保留该 code。

- [ ] **Step 6: 运行恢复与现有 Checkpoint 回归测试**

Run: `pytest tests/test_plan_execute_checkpoint_resume.py tests/test_runtime_checkpoint_resume.py tests/test_checkpoint_hardening.py -q`

Expected: PASS。

---

### Task 6: 统一绑定接口与 ConversationRuntime 集成

**Files:**
- Modify: `my_agent/agent_loop/react.py`
- Modify: `my_agent/runtime/node_runner.py`
- Modify: `my_agent/runtime/executor.py`
- Test: `tests/test_agent_loop.py`
- Test: `tests/test_dsl_runtime.py`
- Test: `tests/test_runtime_checkpoint_resume.py`

**Interfaces:**
- Produces: ReAct 和 Plan-and-Execute 一致的 `bind_run_state(run_state, checkpoint_recorder)`。
- Preserves: `AgentLoopNodeRunner.run()` 和 DSL `agent_loop` 节点输入输出。

- [ ] **Step 1: 写禁止私有字段绑定的失败测试**

使用只提供 `run()` 和公开 `bind_run_state()` 的 Spy Loop，断言 AgentLoopNodeRunner 调用公开方法并传入原对象。

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/test_agent_loop.py tests/test_dsl_runtime.py -q`

Expected: FAIL，当前 NodeRunner 仍直接写 `_run_state`。

- [ ] **Step 3: 实现公开绑定**

```python
def bind_run_state(self, run_state, checkpoint_recorder) -> None:
    self._run_state = run_state
    self._checkpoint_recorder = checkpoint_recorder
```

AgentLoopNodeRunner 仅委托 `self._agent_loop.bind_run_state(...)`，不访问私有字段。

- [ ] **Step 4: 写跨 ConversationRuntime 实例恢复测试**

Runtime A 使用 SQLite 执行到失败边界并释放；Runtime B 使用相同 session ID、workflow 和数据库恢复，断言计划历史、步骤位置和最终 Session 连续。

- [ ] **Step 5: 运行集成回归测试**

Run: `pytest tests/test_agent_loop.py tests/test_dsl_runtime.py tests/test_runtime_checkpoint_resume.py tests/test_plan_execute_checkpoint_resume.py -q`

Expected: PASS。

---

### Task 7: 文档、全量验证和工作区自检

**Files:**
- Modify: `README.md`
- Modify: `docs/project-handoff.md`
- Verify: all files changed by Tasks 1-6

**Interfaces:**
- Documents: Plan-and-Execute 模块边界、Planner 选择、恢复限制和 at-least-once 语义。

- [ ] **Step 1: 更新 README**

说明 ReAct 与 Plan-and-Execute 是并列 Loop；真实 LLM Planner 通过 `ModelClient` 注入；MCP 后续只作为 ToolRegistry 适配器；恢复复用持久化限制和 Loop call ID。

- [ ] **Step 2: 更新 project-handoff**

把 Plan-and-Execute 从缺口移到已完成能力，记录剩余限制：无并行步骤、无 exactly-once、无真实 MCP、真实 LLM 冒烟测试需本地密钥手动执行。

- [ ] **Step 3: 运行定向新增测试**

Run: `pytest tests/test_plan_state.py tests/test_plan_planner.py tests/test_llm_plan_planner.py tests/test_plan_execute_agent_loop.py tests/test_plan_execute_checkpoint_resume.py -q`

Expected: PASS。

- [ ] **Step 4: 运行全量测试**

Run: `pytest tests -q`

Expected: 全部通过；允许保留已知 TestClient 弃用与 pytest cache 权限警告，但不得出现新失败。

- [ ] **Step 5: 检查结构、注释和工作区**

Run: `git diff --check`

Expected: 无空白错误。

Run: `git status --short`

Expected: 只包含本功能的代码、测试和文档；不包含 commit 或 push 产生的状态变化。

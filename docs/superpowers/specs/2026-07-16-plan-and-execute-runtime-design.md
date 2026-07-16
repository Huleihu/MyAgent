# Plan-and-Execute Runtime 闭环设计

## 1. 目标

在现有 ReAct、标准 Tool、Runtime、RunState 和 Checkpoint 能力之上，实现本地标准 Tool 的以下闭环：

```text
Plan -> Execute -> Observe -> Retry / Reflect -> Step Decision -> Final Answer
```

本期完成后，系统应具备：

- 显式任务计划和步骤状态；
- 工具 observation 后的步骤级再次决策；
- 由 Loop 强制控制的调用次数和重试次数；
- 步骤完成、跳过和计划终止语义；
- 计划结果与 Runtime 执行状态分离；
- 计划、步骤、限制和重试信息随 RunState 持久化；
- 基于现有 SQLite Checkpoint 的跨 Runtime 实例恢复；
- 明确的 at-least-once 工具执行语义；
- ReAct 和 Plan-and-Execute 统一的公开状态绑定接口。

## 2. 范围与非目标

### 2.1 本期范围

- 仅执行已注册到现有 `ToolRegistry` 的标准 Tool；
- 新增独立的 `PlanAndExecuteAgentLoop`；
- 新增 `TaskPlanner` 和 `StepPlanner`，不复用 `Planner.plan()`；
- 提供基于现有 `ModelClient` 的 `LLMTaskPlanner` 和 `LLMStepPlanner` 真实实现；
- 新增可序列化的 `PlanState` 和步骤状态；
- 将计划状态接入现有 `RunState.to_dict()`、`RunState.from_dict()` 和 Checkpoint；
- 保持 `ConversationRuntime.chat()`、Runtime DSL `agent_loop` 节点和现有 Web 成功响应兼容；
- 使用 FakeModelClient、Fake Planner 和 Fake Tool 完成不访问外部服务的确定性自动化测试。

### 2.2 非目标

- 不接入真实 MCP Client 或 Server；
- 不让 Plan-and-Execute 感知工具来自本地实现还是 MCP；
- 不实现并行步骤、条件图、动态 DAG 或计划版本树；
- 不提供 exactly-once 工具执行保证；
- 不将现有 ReAct 默认替换为 Plan-and-Execute；
- 不修改现有 `Planner`、`LLMPlanner` 和 `FakePlanner` 的职责与公开行为；
- 不允许 Planner 直接修改持久化状态、计数或执行限制。

后续接入 MCP 时，由 Tool 适配器把 MCP 能力注册为标准 Tool。`PlanAndExecuteAgentLoop` 仍只依赖 `ToolExecutor`、`ToolAction` 和 `ToolCallResult`。

## 3. 总体职责

### 3.1 PlanAndExecuteAgentLoop

`PlanAndExecuteAgentLoop` 负责：

- 调用 TaskPlanner 创建计划；
- 校验计划定义并创建持久化 PlanState；
- 选择和推进当前步骤；
- 调用 StepPlanner 获取步骤决策；
- 校验 Planner 决策协议；
- 生成稳定的 `call_id`；
- 控制步骤和全局工具调用上限；
- 维护 attempt、retry 和 Plan outcome；
- 调用 ToolExecutor；
- 写入 observation、状态和 Checkpoint；
- 恢复 pending 工具调用和计划执行位置；
- 调用 TaskPlanner 生成整个计划的最终回答。

Loop 是执行状态的唯一写入者。Planner 返回的对象只表示建议，不具备修改状态的权限。

### 3.2 TaskPlanner

`TaskPlanner` 负责两个任务级决策：

- 根据用户目标创建计划定义；
- 根据已由 Loop 确定的计划结果生成最终回答。

TaskPlanner 不生成持久化 ID，不控制步骤状态、计数、限制或 Plan outcome。

### 3.3 StepPlanner

`StepPlanner` 只负责当前步骤的下一步决策：

- 调用一个工具；
- 完成当前步骤；
- 跳过当前步骤；
- 终止整个计划。

工具执行成功不代表步骤完成。每次工具 observation 写入后，Loop 必须再次调用 StepPlanner，直到其返回步骤终态或计划终止动作。

### 3.4 ToolExecutor

`ToolExecutor` 继续负责标准 Tool 的参数校验、执行和 Tool Trace，不承担计划状态推进、重试决策或 Checkpoint 恢复职责。

## 4. 模块划分

建议新增以下文件：

```text
my_agent/agent_loop/plan_actions.py
  步骤级动作和 Planner 决策信封；不保存运行状态。

my_agent/agent_loop/plan_planner.py
  TaskPlanner、StepPlanner 协议及其输入输出快照模型。

my_agent/agent_loop/llm_plan_planner.py
  基于 ModelClient 的任务规划、步骤决策和最终回答实现。

my_agent/agent_loop/plan_execute.py
  PlanAndExecuteAgentLoop 状态机、限制校验和 Checkpoint 时序。

my_agent/state/plan_state.py
  可持久化的计划、步骤、状态、结果和限制模型。
```

现有文件仅做必要扩展：

```text
my_agent/state/run_state.py
  增加可选 plan_state 字段及向后兼容序列化。

my_agent/agent_loop/react.py
  增加公开 bind_run_state()，不改变 ReAct 决策行为。

my_agent/runtime/node_runner.py
  通过公开接口绑定状态，不再直接修改 Loop 私有字段。

my_agent/runtime/executor.py
  保留稳定 Planner 协议错误信息并写入失败 Checkpoint。
```

每个新增 Python 文件顶部必须使用中文模块文档字符串说明职责和边界。

## 5. Planner 协议

### 5.1 TaskPlanner

```python
class TaskPlanner(Protocol):
    def create_plan(self, request: CreatePlanRequest) -> PlanDefinition:
        """根据用户目标生成计划定义。"""

    def finalize_plan(self, request: FinalizePlanRequest) -> FinalAnswerAction:
        """根据已确定的计划结果生成整个计划的最终回答。"""
```

`create_plan()` 返回瞬态定义，不直接返回 `PlanState`：

```python
@dataclass(frozen=True)
class PlanDefinition:
    goal: str
    steps: tuple[PlanStepDefinition, ...]


@dataclass(frozen=True)
class PlanStepDefinition:
    instruction: str
```

Loop 负责生成：

- `plan_id`；
- 顺序稳定的 `step_id`；
- 初始步骤状态；
- 执行限制；
- 所有计数和结果字段。

计划必须至少包含一个步骤。步骤数量不得超过新计划配置的最大步骤数，目标和步骤指令必须为非空字符串。

### 5.2 StepPlanner

```python
class StepPlanner(Protocol):
    def decide(self, request: StepDecisionRequest) -> StepDecision:
        """根据当前步骤和已有 observation 决定下一步动作。"""
```

决策信封为：

```python
@dataclass(frozen=True)
class StepDecision:
    action: StepAction
    reflection: str | None = None
```

允许的步骤动作：

```python
StepAction = ToolAction | CompleteStepAction | SkipStepAction | AbortPlanAction
```

新增动作模型：

```python
@dataclass(frozen=True)
class CompleteStepAction:
    result_summary: str


@dataclass(frozen=True)
class SkipStepAction:
    reason: str
    result_summary: str | None = None


@dataclass(frozen=True)
class AbortPlanAction:
    reason: str
```

动作规则：

- `ToolAction` 仅表示工具名称和参数；
- `CompleteStepAction` 是把当前步骤标记为 `completed` 的唯一动作；
- `SkipStepAction` 把当前步骤标记为 `skipped`；
- `AbortPlanAction` 终止整个计划；
- `FinalAnswerAction` 不能作为步骤动作；
- `FinalAnswerAction` 只允许由 `TaskPlanner.finalize_plan()` 返回；
- `reflection` 可由 Loop 保存到当前步骤，但不能携带状态变更、计数或限制。

### 5.3 call_id 所有权

现有 `ToolAction` 为兼容 ReAct 仍保留可选 `call_id` 字段。Plan-and-Execute 对该字段采用更严格的协议：

- StepPlanner 返回的 `ToolAction.call_id` 必须为 `None`；
- 若 StepPlanner 提供非空 `call_id`，Loop 将其视为 Planner 协议错误；
- 新工具调用的 `call_id` 始终由 `PlanAndExecuteAgentLoop` 生成；
- Loop 校验 ToolAction 后必须深拷贝工具参数，再创建待执行调用；
- Loop 在工具执行前把生成的完整调用写入 `RunState.pending_tool_call`；
- 恢复 pending 工具调用时，只复用 Checkpoint 中已经持久化的原 `call_id`；
- Planner 不能读取后再指定、覆盖或复用 `call_id`。

这保证 ReAct 的现有行为不变，同时确保 Plan-and-Execute 的恢复标识由执行层统一控制。

### 5.4 Planner 输入快照

传入 Planner 的所有数据必须与真实运行状态隔离，包括：

- Session 消息；
- 完整计划和步骤；
- 工具定义及其参数 schema；
- 最近 observation；
- 前序步骤结果摘要；
- 当前限制和剩余次数。

`frozen=True` 只能禁止字段重新赋值，不能保护内部 `list` 和 `dict`。因此 Loop 构造 Planner request 时必须：

- 对来自 RunState、SessionState、ToolRegistry 和 Tool Trace 的对象执行深拷贝；
- 对顺序集合优先使用 tuple；
- 不把真实 `PlanState`、`PlanStep`、Session 内部列表或工具 schema dict 的引用交给 Planner；
- Planner 调用结束后只解析返回动作，不接收 Planner 对 request 的任何原地修改。

即使自定义 Planner 修改 request 内部的嵌套 dict，该修改也不得影响 RunState、SessionState、ToolRegistry 或 Checkpoint 内容。

### 5.5 Planner 请求内容

`CreatePlanRequest` 至少包含：

- `user_input`；
- Session 消息快照；
- 工具定义快照；
- `max_plan_steps`。

`StepDecisionRequest` 至少包含：

- 用户目标；
- 完整计划快照；
- 当前步骤快照；
- 前序步骤的 result summary；
- 根据当前步骤 `tool_call_ids` 从 Tool Trace 重建的有序 observation 历史；
- observation 历史中的最近一项；
- Session 消息快照；
- 工具定义快照；
- 本步骤剩余调用次数；
- 全局剩余调用次数；
- `can_call_tool`。

`FinalizePlanRequest` 至少包含：

- 用户目标；
- 完整计划快照；
- 已由 Loop 计算并持久化的 Plan outcome；
- abort reason；
- Session 消息快照。

`finalize_plan()` 只能读取 outcome，不能修改或重新判定 outcome。

### 5.6 真实 LLM Planner 实现

本期不仅提供 Planner 协议和 Fake，还必须实现可由现有 DeepSeek `ModelClient` 驱动的真实 Planner：

```python
class LLMTaskPlanner(TaskPlanner):
    ...


class LLMStepPlanner(StepPlanner):
    ...
```

两者只依赖项目内的 `ModelClient` 协议，不直接依赖 DeepSeek SDK。具体模型客户端仍由装配层注入，因此未来可替换其他模型供应商。

`LLMTaskPlanner.create_plan()` 使用空工具列表调用 `ModelClient.chat()`，要求模型返回包含 `goal` 和有序 `steps` 的 JSON 文本。它只解析计划定义，不接受模型提供的持久化 ID、状态、计数或限制。

`LLMTaskPlanner.finalize_plan()` 使用空工具列表调用 `ModelClient.chat()`，输入已确定的 Plan outcome、步骤终态和结果摘要，并把模型文本转换为 `FinalAnswerAction`。模型不能覆盖 Plan outcome。

`LLMStepPlanner.decide()`：

- 把当前步骤、前序结果、完整 observation 历史、最近 observation 和剩余限制写入模型消息；
- `can_call_tool=True` 时，把 Session 中已有的用户消息和 `tool_observation` 消息作为标准消息历史传给 `ModelClient`，再追加本轮步骤决策指令；DeepSeek 适配器据此重建 `assistant.tool_calls -> tool` 消息对；
- `can_call_tool=False` 时，不向模型暴露 ToolDefinition，也不直接传递需要工具名称映射的 observation 消息；历史只作为决策指令中的深拷贝 JSON 快照提供；
- 把标准 ToolDefinition 传给 `ModelClient.chat()`；
- 模型返回 `tool_call` 时，只读取工具名称和参数，丢弃供应商生成的 call ID，并构造 `call_id=None` 的 ToolAction；
- 模型返回普通文本时，要求其为步骤动作 JSON，并解析为 CompleteStepAction、SkipStepAction 或 AbortPlanAction；
- 从步骤动作 JSON 解析可选 reflection；
- 非法 JSON、非法动作或非法字段按稳定 Planner 协议错误处理。
- 计划 JSON 和每种步骤动作 JSON 使用精确字段白名单，模型不得附带 plan ID、状态、call ID、计数或其他未声明字段；
- tool call 参数必须只包含跨 Store 类型稳定的 JSON 原生值：object 键只能是字符串，容器只能是 dict/list，数字必须有限；循环引用、tuple、集合和自定义对象按稳定 Planner 协议错误拒绝。

DeepSeek 返回的 provider call ID 仅属于该次模型响应，不进入 PlanState。Loop 接受 ToolAction 后生成自己的稳定 call ID；后续 observation 消息使用 Loop call ID 重建标准 tool calling 上下文。

自动化测试使用 `FakeModelClient` 验证真实 LLM Planner 的模型输入和响应解析，不访问真实模型服务、不要求真实密钥。可选人工冒烟测试不作为 `pytest tests -q` 的组成部分。

## 6. 持久化状态模型

### 6.1 PlanState

`my_agent/state/plan_state.py` 定义：

```text
PlanState
├── plan_id
├── goal
├── status
├── outcome
├── current_step_id
├── steps
├── total_tool_call_count
├── total_retry_count
├── max_tool_calls_per_step
├── max_total_tool_calls
└── abort_reason
```

计划状态：

```python
class PlanStatus(str, Enum):
    RUNNING = "running"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    ABORTED = "aborted"
```

计划结果：

```python
class PlanOutcome(str, Enum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
```

`outcome` 在计划执行中为 `None`，进入 finalization 前由 Loop 计算并持久化。

### 6.2 PlanStep

步骤状态：

```python
class PlanStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
```

`PlanStep` 保存：

```text
step_id
instruction
status
attempt_count
retry_count
tool_call_ids
last_observation_summary
reflection
result_summary
failure_reason
```

`PlanStep` 不保存：

- 完整 ToolAction；
- 工具名称和参数的待执行副本；
- 完整 ToolCallResult；
- PendingToolCall 副本。

`tool_call_ids` 是当前步骤已接受工具调用的有序关联索引，只保存 call ID，不重复保存工具名称、参数或结果。待执行工具调用的唯一恢复来源仍是 `RunState.pending_tool_call`，完整历史结果继续由现有 `RunState.tool_traces` 保存。

步骤字段还必须与状态一致：pending 步骤不得携带调用历史或执行结果；running 步骤不得提前保存终态结果；completed 必须有 `result_summary` 且没有 `failure_reason`；skipped 必须同时有结果摘要和跳过原因；failed 必须有失败原因。

StepPlanner 的 observation 历史按以下规则重建：

1. 按 `PlanStep.tool_call_ids` 的顺序遍历；
2. 在 `RunState.tool_traces` 中查找相同 call ID 的记录；
3. 同一 call ID 因 at-least-once 重放出现多条 Trace 时，只选择最新一条已持久化记录；
4. 对结果执行深拷贝后构造 Planner observation 快照；
5. 没有 Tool Trace 的 call ID 只能是当前 `pending_tool_call`，此时 phase 必须为 `plan_tool_pending`，不会调用 StepPlanner；
6. observation 历史最后一项作为最近 observation，并用于判断下一次 ToolAction 是否属于 retry。

这使同一步骤内连续多个工具调用的全部结果都可被 StepPlanner 使用，同时不在 PlanStep 中复制完整 action 或结果。

### 6.3 RunState 兼容扩展

`RunState` 只增加：

```python
plan_state: PlanState | None = None
```

序列化包含 `plan_state`。反序列化必须使用可选读取：

```python
plan_payload = payload.get("plan_state")
```

旧 Checkpoint 没有该字段时恢复为 `None`。现有 ReAct 恢复逻辑不得要求 `plan_state` 存在。

### 6.4 状态一致性约束

`PlanState` 负责计划内部约束，`RunState` 负责跨对象约束。由于状态会在运行中原地推进，校验不能只发生在 dataclass 构造时；`RunState.to_dict()`、`Checkpoint.create()` 和 `RunState.from_dict()` 都必须调用统一的状态一致性校验。

PlanState 内部必须满足：

- step ID 非空且在计划内唯一；
- `tool_call_ids` 在步骤内保持有序且不重复，并在整个计划中全局唯一；
- `attempt_count == len(tool_call_ids)`；
- `retry_count <= attempt_count`；
- `total_tool_call_count` 等于所有步骤 attempt 之和；
- `total_retry_count` 等于所有步骤 retry 之和；
- `PlanStatus.RUNNING` 时 outcome 必须为 None；
- `PlanStatus.FINALIZING`、`COMPLETED` 或 `ABORTED` 时 outcome 必须已确定；
- `PlanStatus.RUNNING` 时 `current_step_id` 必须指向唯一的 running 步骤；
- `PlanStatus.FINALIZING`、`COMPLETED` 或 `ABORTED` 时 `current_step_id` 必须为 None；
- 同一计划最多存在一个 running 步骤。
- RUNNING 计划必须保持“completed/skipped 前缀 + 当前 running 步骤 + pending 后缀”的顺序边界；
- FINALIZING 和 COMPLETED 计划的全部步骤必须为 completed 或 skipped；
- ABORTED 计划必须保持“completed/skipped 前缀 + 唯一 failed 终止步骤 + pending 后缀”；
- `abort_reason` 只允许出现在 ABORTED 计划中。

RunState 与 PlanState 的跨对象约束如下：

| agent_phase | plan_state | current_step_id | pending_tool_call | 额外约束 |
| --- | --- | --- | --- | --- |
| `plan_creating` | 必须为 None | 不适用 | 必须为 None | 允许恢复后重新创建计划 |
| `plan_step_deciding` | 必须存在且为 RUNNING | 必须指向 running 步骤 | 必须为 None | 所有已接受调用均已有可重建 observation |
| `plan_tool_pending` | 必须存在且为 RUNNING | 必须指向 running 步骤 | 必须存在 | pending call ID 必须等于当前步骤 `tool_call_ids` 最后一项，且此前 call ID 均已有 Trace |
| `plan_finalizing` | 必须存在且为 FINALIZING 或 ABORTED | 必须为 None | 必须为 None | outcome 必须已持久化 |
| `plan_final_answer_written` | 必须存在且为 COMPLETED 或 ABORTED | 必须为 None | 必须为 None | 必须存在当前 run 唯一的最终 assistant 消息 |
| `completed` | 必须存在且为 COMPLETED 或 ABORTED | 必须为 None | 必须为 None | RunStatus 必须为 COMPLETED |

其他约束：

- Plan-and-Execute phase 出现时不得缺少匹配的 PlanState；
- PlanState 存在时，agent phase 必须属于上表中的 Plan-and-Execute phase 或 Runtime 最终 `completed`；
- `pending_tool_call` 在 `plan_tool_pending` 之外必须为 None；
- `completed` 之外的 Plan-and-Execute phase 不得搭配 `RunStatus.COMPLETED`；`completed` phase 也必须存在当前 run 和 plan 唯一的 tagged final message；
- pending call ID 必须已计入当前步骤 `tool_call_ids`，因此恢复执行不再增加 attempt；
- `plan_tool_pending` 时，仅允许最后一个 call ID 尚无 Trace；此前全部 call ID 都必须能重建 observation，否则拒绝持久化或恢复；
- `plan_step_deciding` 时，当前步骤每个 call ID 都必须能从持久化 Tool Trace 重建 observation；
- Planner 协议失败或执行异常可以把 RunStatus 设为 FAILED，但不能破坏 phase、PlanState、current step 和 pending 调用的结构一致性；
- 没有 PlanState 的旧 ReAct RunState 继续按现有 ReAct phase 规则运行，不套用 Plan-and-Execute 约束。

任何不一致状态在写入 Checkpoint 前必须被拒绝，并以稳定的状态一致性错误失败，避免把不可恢复快照保存到 SQLite。

### 6.5 Runtime 状态与计划结果

两者语义独立：

- `RunStatus.COMPLETED`：Runtime 已成功写入最终 assistant 消息并满足输出契约；
- `RunStatus.FAILED`：运行发生未处理异常、Planner 协议错误或输出契约失败；
- `PlanOutcome.SUCCEEDED`：全部步骤显式完成；
- `PlanOutcome.PARTIAL`：至少一个步骤完成，同时存在显式跳过、失败或 Abort；
- `PlanOutcome.FAILED`：没有任何步骤完成。

即使 Plan outcome 为 `FAILED`，只要解释性最终回答成功写入，Runtime 仍可以是 `RunStatus.COMPLETED`。

## 7. 执行限制与 Retry 定义

### 7.1 限制的创建与恢复

新 Runtime 配置只用于新计划。计划创建时，Loop 把以下限制写入 `PlanState`：

- `max_tool_calls_per_step`；
- `max_total_tool_calls`；
- 其他本期实际引入的计划执行上限。

恢复已有计划时必须使用 Checkpoint 中持久化的限制。即使新 Runtime 构造配置发生变化，也不得覆盖、收紧或放宽已有 PlanState 的限制。

只有 `plan_state is None`、即创建全新计划时，Loop 才读取当前 Runtime 配置。

### 7.2 attempt_count

`attempt_count` 表示当前步骤已经接受并准备执行的 ToolAction 数量。Loop 在新工具调用执行前统一增加：

```text
校验限制
  -> 判断是否为 retry
  -> 增加 attempt_count 和 total_tool_call_count
  -> 必要时增加 retry_count 和 total_retry_count
  -> 生成 call_id
  -> 创建 pending_tool_call
  -> 写入 before_tool_execution Checkpoint
  -> 执行工具
```

恢复 `pending_tool_call` 时，以上计数已经持久化，因此不得再次增加。

### 7.3 retry_count

Retry 精确定义为：

- 最近一次 `ToolCallResult.success == false`，表示最近 observation 失败；
- 在该失败 observation 已写入后，StepPlanner 再次返回合法 `ToolAction`；
- Loop 接受该 ToolAction 时，才增加当前步骤和计划全局的 `retry_count`；
- 成功工具调用后继续调用另一个工具，只增加 attempt 和工具调用总数，不增加 retry；
- Planner 协议错误不计入工具 retry；
- Planner 自身异常不计入工具 retry；
- ToolAction 尚未通过限制或协议校验时不增加 attempt 或 retry；
- 恢复已持久化的 pending 调用不增加 attempt 或 retry。

Retry 判断依据来自当前步骤 observation 历史中的最后一条 Tool Trace，不由 Planner 声明。

### 7.4 达到限制后的行为

达到单步或全局工具调用上限后：

- `StepDecisionRequest.can_call_tool` 为 `False`；
- StepPlanner 仍有一次步骤决策机会；
- 只允许返回 `CompleteStepAction`、`SkipStepAction` 或 `AbortPlanAction`；
- 若仍返回 `ToolAction`，Loop 不执行工具、不增加计数、不创建 pending 调用，并按稳定 Planner 协议错误失败。

## 8. 状态推进与 Checkpoint 精确时序

Plan-and-Execute 使用以下 `ExecutionCursor.agent_phase`：

```text
plan_creating
plan_step_deciding
plan_tool_pending
plan_finalizing
plan_final_answer_written
```

### 8.1 创建计划

```text
写入用户消息
  -> agent_phase = plan_creating
  -> Checkpoint(after_user_input)
  -> TaskPlanner.create_plan()
  -> 校验 PlanDefinition
  -> 创建 PlanState
  -> 首步骤设为 running
  -> current_step_id = 首步骤 ID
  -> agent_phase = plan_step_deciding
  -> Checkpoint(after_plan_created)
```

TaskPlanner 返回后、`after_plan_created` 前崩溃时，恢复允许重新调用 `create_plan()`。计划只有进入 Checkpoint 后才成为可恢复事实。

### 8.2 StepPlanner 决策

在 `plan_step_deciding` 阶段，Loop 从持久化状态构建深拷贝 request，再调用 StepPlanner。

若 StepPlanner 返回 ToolAction：

```text
校验 action 类型、参数、call_id=None 和执行限制
  -> Loop 判断 retry
  -> Loop 增加计数
  -> Loop 生成 call_id
  -> 把 call_id 追加到 step.tool_call_ids
  -> run_state.pending_tool_call = 完整调用
  -> agent_phase = plan_tool_pending
  -> Checkpoint(before_tool_execution)
  -> ToolExecutor.execute()
```

StepPlanner 的 ToolAction 在 `before_tool_execution` 落盘前不是恢复来源。若此时崩溃，恢复后重新调用 StepPlanner；由于工具尚未执行，不产生工具重复执行问题。

### 8.3 工具 observation

工具返回后按以下顺序更新内存状态：

```text
ToolExecutor 返回 ToolCallResult
  -> 校验 result.name 和 result.call_id 与 pending 完全一致
  -> 非 JSON 原生工具结果转换为失败 ToolCallResult，避免 SQLite 隐式改变类型
  -> 若当前 Session 本次执行未新增同 call_id Trace，则由 Loop 补写本次 Trace
  -> 写入工具 observation 消息
  -> 更新 step.last_observation_summary
  -> 保留 step.tool_call_ids 的完整有序关联
  -> 清空 pending_tool_call
  -> agent_phase = plan_step_deciding
  -> 同步 RunState messages 和 tool_traces
  -> Checkpoint(after_tool_observation)
```

清空 pending 调用、保存 observation、同步 Tool Trace 和切换 phase 必须进入同一个 Checkpoint 快照。工具成功后步骤仍为 `running`，必须再次调用 StepPlanner。

### 8.4 完成或跳过步骤

收到 `CompleteStepAction` 或 `SkipStepAction` 后，Loop 必须在一次内存状态变更中完成以下工作，再写一个 Checkpoint：

1. 写入当前步骤的终态、reflection、result summary 或 reason；
2. 查找下一个 `pending` 步骤；
3. 若存在下一步骤，将其设为 `running`；
4. 将 `current_step_id` 更新为下一步骤 ID；
5. 设置 `agent_phase = plan_step_deciding`；
6. 写入 `after_step_completed` 或 `after_step_skipped` Checkpoint。

同一个持久化快照中不得出现 `current_step_id` 已指向下一步骤但该步骤仍为 `pending` 的中间状态。

若不存在下一步骤，则在同一次状态变更中：

- 计算并设置 Plan outcome；
- 设置 `PlanStatus.FINALIZING`；
- 清空 `current_step_id`；
- 设置 `agent_phase = plan_finalizing`；
- 写入步骤终态和进入 finalization 的同一个 Checkpoint。

### 8.5 AbortPlanAction

收到 AbortPlanAction 后，Loop 原子更新：

- 当前步骤设为 `failed`；
- 保存 `failure_reason` 和 reflection；
- `PlanStatus` 设为 `ABORTED`；
- 保存 `abort_reason`；
- 清空 `current_step_id`；
- 由 Loop 计算并设置 Plan outcome；
- 设置 `agent_phase = plan_finalizing`；
- 写入 `after_plan_aborted` Checkpoint。

Abort 后剩余尚未执行的步骤保持 `pending`。其语义是“因计划终止而未执行”，不是显式跳过：

- 不把这些步骤改为 `skipped`；
- 不把它们计入显式 Skip；
- 当 `PlanStatus.ABORTED` 时，恢复逻辑不得继续选择这些 pending 步骤。

### 8.6 Plan outcome 计算

Plan outcome 只能由 Loop 在进入 finalization 前计算：

- 所有步骤均为 `completed`：`SUCCEEDED`；
- 至少一个步骤为 `completed`，且存在 `skipped`、`failed` 或 Abort：`PARTIAL`；
- 没有任何步骤为 `completed`：`FAILED`。

TaskPlanner 只能读取已持久化 outcome，不能覆盖或重新计算。

### 8.7 最终回答

正常计划进入 finalization：

```text
PlanStatus = finalizing
PlanOutcome 已确定
agent_phase = plan_finalizing
  -> TaskPlanner.finalize_plan()
  -> 校验返回 FinalAnswerAction
  -> 追加带 run_id、plan_id 和 message_type=plan_final_answer 元数据的最终 assistant 消息
  -> PlanStatus = completed
  -> agent_phase = plan_final_answer_written
  -> Checkpoint(after_final_answer)
```

Abort 计划进入 finalization：

```text
PlanStatus = aborted
PlanOutcome 已确定
agent_phase = plan_finalizing
  -> TaskPlanner.finalize_plan()
  -> 校验返回 FinalAnswerAction
  -> 追加带 run_id、plan_id 和 message_type=plan_final_answer 元数据的最终 assistant 消息
  -> PlanStatus 仍为 aborted
  -> agent_phase = plan_final_answer_written
  -> Checkpoint(after_final_answer)
```

最终 assistant 消息、最终 PlanStatus 和 `plan_final_answer_written` 必须进入同一个 Checkpoint 快照。恢复和一致性校验通过 `run_id + plan_id + message_type` 定位当前计划的最终消息，不能把同一 Session 的历史 assistant 回答误认为当前结果。

若最终回答成功写入，正常和 Abort 两种计划都允许 Runtime 最终进入 `RunStatus.COMPLETED`。

## 9. 恢复规则

### 9.1 通用规则

- 恢复时使用 Checkpoint 中的 PlanState、步骤状态、计数和限制；
- 新 Runtime 配置不能覆盖已有计划限制；
- 已经终态化的步骤不得重新执行；
- `PlanStatus.ABORTED` 时不得选择剩余 pending 步骤；
- Planner request 每次均从恢复后的状态重新构造深拷贝快照。

### 9.2 各 phase 恢复行为

| agent_phase | 恢复行为 |
| --- | --- |
| `plan_creating` | 重新调用 TaskPlanner 创建计划 |
| `plan_step_deciding` | 对当前 `running` 步骤重新调用 StepPlanner |
| `plan_tool_pending` | 从 `pending_tool_call` 恢复并执行，不调用 StepPlanner，不增加计数 |
| `plan_finalizing` | 重新调用 TaskPlanner.finalize_plan() |
| `plan_final_answer_written` | 读取已有最终 assistant 消息，不再调用 Planner，不重复追加消息 |

恢复到 `plan_finalizing` 时，`finalize_plan()` 可能被重复调用。该方法必须被定义为无业务副作用的纯生成操作：

- 不修改外部业务状态；
- 不执行工具；
- 不写入 RunState 或 Session；
- 除模型请求本身外，不产生不可重放的外部效果；
- 只有 Loop 可以把最终回答写入 Session 和 Checkpoint。

## 10. At-least-once 工具执行语义

本期不提供 exactly-once。关键崩溃窗口为：

```text
before_tool_execution 已落盘
  -> 工具执行成功并产生外部效果
  -> 进程在 after_tool_observation 前崩溃
  -> 最新 Checkpoint 仍为 plan_tool_pending
  -> 恢复后使用同一个 call_id 再次执行工具
```

因此：

- 工具可能被执行多次；
- 恢复调用必须复用持久化的 `call_id`；
- 恢复 pending 调用不得增加 attempt 或 retry；
- 当前本地 Tool 应优先保持无副作用；
- 后续有副作用的 MCP Tool 应在适配器或下游服务中以 `call_id` 实现幂等；
- 若下游已保存该 `call_id` 的成功结果，重复请求应返回原结果。

Planner 调用也可能因“返回后、决策 Checkpoint 前崩溃”而重复，但 Planner 不得直接产生业务副作用，因此不属于工具 exactly-once 范围。

## 11. Planner 错误与失败持久化

新增稳定的 Planner 协议错误，例如：

```python
class PlannerProtocolError(ValueError):
    code = "planner_protocol_error"
```

以下情况属于协议错误：

- TaskPlanner 返回空计划、超量步骤或非法字段；
- StepPlanner 返回不支持的动作；
- StepPlanner 返回 FinalAnswerAction；
- StepPlanner 返回带非空 `call_id` 的 ToolAction；
- `can_call_tool=False` 时仍返回 ToolAction；
- `finalize_plan()` 未返回 FinalAnswerAction；
- Planner 返回的数据类型或必要文本不符合契约。

发生 Planner 协议错误时，Loop 必须：

1. 不执行工具；
2. 不增加 attempt 或 retry；
3. 不创建或覆盖 pending 调用；
4. 将 Runtime 标记为 `FAILED`；
5. 保存稳定 `error.type`、`error.code` 和安全错误信息；
6. 同步最新 PlanState、Session 和 Tool Trace；
7. 写入 `planner_protocol_failed` Checkpoint；
8. 向上抛出带稳定 code 的异常，由现有 Runtime 失败契约继续处理。

Runtime 执行器写入后续 `run_failed` Checkpoint 时必须保留稳定 code，不得用普通 `str(exc)` 覆盖为无结构文本。最新 Checkpoint 因此仍可定位原始协议错误。

Planner 自身抛出的运行异常不计入工具 retry，由现有 Runtime 失败契约记录。恢复失败 Run 时，会从最近已持久化 phase 重新调用对应 Planner；替换或修复 Planner 后可继续恢复。

## 12. 统一状态绑定接口

ReAct 和 Plan-and-Execute 共同提供：

```python
class BindableAgentLoop(Protocol):
    def run(self, user_input: str) -> str:
        ...

    def bind_run_state(
        self,
        run_state: RunState | None,
        checkpoint_recorder: CheckpointRecorder | None,
    ) -> None:
        ...
```

实现要求：

- `ReActAgentLoop` 新增公开 `bind_run_state()`；
- `PlanAndExecuteAgentLoop` 实现相同方法；
- `AgentLoopNodeRunner.bind_run_state()` 仅调用 Loop 的公开方法；
- Runtime 模块不得直接修改 Loop 的 `_run_state` 或 `_checkpoint_recorder`；
- `run(user_input) -> str` 保持不变，因此现有 DSL `agent_loop` 节点不需要感知具体 Loop 类型。

## 13. 端到端数据流

```text
ConversationRuntime.start()
  -> 创建 RunState
  -> RuntimeExecutor.bind_run_state()
  -> AgentLoopNodeRunner.bind_run_state()
  -> PlanAndExecuteAgentLoop.bind_run_state()
  -> PlanAndExecuteAgentLoop.run()
       -> TaskPlanner.create_plan()
       -> StepPlanner.decide()
       -> ToolExecutor.execute()
       -> observation + Checkpoint
       -> StepPlanner.decide()
       -> Complete / Skip / Abort
       -> TaskPlanner.finalize_plan()
       -> final assistant message
  -> Runtime 节点完成
  -> RunStatus.COMPLETED
```

`ConversationRuntime.resume()` 使用相同装配路径，只是 Plan-and-Execute 从 `RunState.plan_state`、`ExecutionCursor.agent_phase` 和 `pending_tool_call` 继续执行。

## 14. 测试验收矩阵

### 14.1 PlanState 与兼容性

新增 `tests/test_plan_state.py`，覆盖：

- PlanState 完整 JSON round-trip；
- 所有枚举、计数、限制和标识字段校验；
- `current_step_id` 必须指向已有步骤；
- `retry_count` 不得大于 `attempt_count`；
- 计数与限制不得为负数；
- RunState 包含 PlanState 时可序列化和恢复；
- 旧 RunState payload 没有 `plan_state` 时恢复为 `None`；
- SQLite Store 关闭重建后，计划状态、步骤状态、计数、限制和 outcome 保持一致；
- 恢复时新 Runtime 配置不能覆盖持久化限制；
- `tool_call_ids` 与 attempt 计数保持一致；
- 每种 Plan-and-Execute phase 的 PlanStatus、current step 和 pending 调用组合均通过校验；
- 非法 phase 组合在写入 Checkpoint 前被拒绝。

### 14.2 Planner 契约与快照隔离

新增 `tests/test_plan_planner.py`，覆盖：

- TaskPlanner 生成合法多步骤计划；
- 空计划、空指令和超量步骤被拒绝；
- StepPlanner 可返回四种步骤动作；
- FinalAnswerAction 不能用于步骤决策；
- finalize_plan() 只能返回 FinalAnswerAction；
- Plan-and-Execute 拒绝 Planner 指定 call_id；
- Planner 不能控制计数、状态和执行限制；
- Planner 修改 request 内嵌消息 metadata 不影响 Session；
- Planner 修改计划快照不影响 PlanState；
- Planner 修改工具 schema 不影响 ToolRegistry；
- Planner 修改 observation 不影响 Tool Trace；
- LLMTaskPlanner 能解析模型生成的计划 JSON；
- LLMTaskPlanner 能根据已确定 outcome 生成最终回答；
- LLMStepPlanner 能把模型 tool_call 转为 `call_id=None` 的 ToolAction；
- LLMStepPlanner 能解析 Complete、Skip 和 Abort JSON；
- LLM Planner 的非法模型响应产生稳定协议错误；
- LLM Planner 自动化测试只使用 FakeModelClient，不访问真实服务。

### 14.3 正常执行闭环

新增 `tests/test_plan_execute_agent_loop.py`，覆盖：

- 创建计划并按顺序执行多个步骤；
- 工具成功后再次调用 StepPlanner；
- 工具成功不会自动完成步骤；
- 同一步骤可连续执行多个成功工具调用；
- 同一步骤全部工具 observation 按 `tool_call_ids` 顺序传给 StepPlanner；
- 同一 call ID 的 at-least-once 重复 Trace 只取最新持久化记录；
- Trace 物理顺序与 call ID 顺序不同时，仍按 `tool_call_ids` 重建 observation；
- pending 恢复前已有旧 Trace 时，本次重放结果仍成为最新 Trace，并据此判断 retry；
- CompleteStepAction 完成当前步骤；
- SkipStepAction 产生 `skipped`；
- AbortPlanAction 停止后续步骤；
- Abort 后剩余步骤保持 `pending` 且不再执行；
- 全部步骤完成产生 `SUCCEEDED`；
- 部分完成加 Skip 或 Abort 产生 `PARTIAL`；
- 没有任何完成步骤产生 `FAILED`；
- Plan outcome 为 FAILED 时仍可生成解释性最终回答；
- 正常最终回答后 PlanStatus 为 COMPLETED；
- Abort 最终回答后 PlanStatus 仍为 ABORTED；
- 两种情况下 Runtime 均可为 COMPLETED。

### 14.4 Attempt、Retry 与限制

- 每个新 ToolAction 执行前 attempt 恰好增加一次；
- 工具失败后的下一次 ToolAction 增加 retry；
- 工具成功后的下一次 ToolAction 不增加 retry；
- Planner 协议错误不增加 retry；
- Planner 运行异常不增加 retry；
- pending 调用恢复不重复增加 attempt 或 retry；
- 达到步骤上限后 `can_call_tool=False`；
- 达到全局上限后所有步骤均不可继续调用工具；
- 超限时返回 ToolAction 不执行工具、不改变计数并写入稳定失败；
- 恢复使用 Checkpoint 限制，不使用新 Runtime 限制。

### 14.5 Checkpoint 精确恢复

新增 `tests/test_plan_execute_checkpoint_resume.py`，覆盖：

- `after_user_input` 恢复时重新创建计划；
- `after_plan_created` 恢复时不重新创建计划；
- `plan_step_deciding` 恢复当前 running 步骤；
- `before_tool_execution` 恢复完整 pending 调用；
- pending 恢复使用相同 call_id；
- pending 恢复不调用 StepPlanner；
- observation 已落盘后恢复不重复执行工具；
- 步骤完成和下一步骤 running 状态在同一快照；
- 步骤跳过和下一步骤 running 状态在同一快照；
- 无下一步骤时同一快照进入 finalizing；
- Abort 后恢复不选择剩余 pending 步骤；
- `plan_finalizing` 恢复允许再次调用 finalize_plan()；
- `plan_final_answer_written` 恢复直接读取已有回答；
- 最终回答不会重复追加；
- 正常和 Abort 的最终 PlanStatus 均符合契约；
- SQLite 跨 ConversationRuntime 实例恢复完整计划。

### 14.6 At-least-once 故障注入

故障测试模拟：

1. `before_tool_execution` 已持久化；
2. 工具外部效果已经发生；
3. observation 写入 Checkpoint 前注入崩溃；
4. 新 Runtime 从 SQLite 恢复；
5. 同一 `call_id` 被再次执行；
6. attempt 和 retry 不重复增加；
7. 外部效果允许发生两次。

该测试用于证明当前语义是 at-least-once，而不是把重复执行误判为缺陷。

### 14.7 Planner 失败持久化

- `can_call_tool=False` 时返回 ToolAction 不执行工具；
- 错误以稳定 type、code 和安全 message 写入 Checkpoint；
- 最新 `run_failed` Checkpoint 保留 Planner 错误 code；
- PlanState、计数、Session 和 Tool Trace 与失败前一致；
- 从失败 Checkpoint 查询时能够定位协议错误；
- Planner 异常和 Planner 协议错误均不计入工具 retry。

### 14.8 状态绑定与回归

- AgentLoopNodeRunner 通过公开 `bind_run_state()` 绑定 ReAct；
- AgentLoopNodeRunner 通过相同接口绑定 Plan-and-Execute；
- Runtime 不再跨模块修改 Loop 私有字段；
- 现有 ReAct 行为和恢复测试保持通过；
- 现有 LLMPlanner 和 FakePlanner 测试保持通过；
- 现有 Web API、SQLite Checkpoint 和 `ConversationRuntime.chat()` 保持兼容。

最终验证命令：

```powershell
pytest tests/test_plan_state.py -q
pytest tests/test_plan_planner.py -q
pytest tests/test_plan_execute_agent_loop.py -q
pytest tests/test_plan_execute_checkpoint_resume.py -q
pytest tests -q
```

## 15. 实施顺序

1. 先用失败测试固定 PlanState、RunState 向后兼容和 SQLite round-trip；
2. 用失败测试固定 PlanStatus、agent phase、current step 和 pending 调用的一致性矩阵；
3. 实现 Planner 协议、动作模型和深拷贝输入快照；
4. 实现并测试 LLMTaskPlanner 与 LLMStepPlanner；
5. 用失败测试固定正常 Plan -> Execute -> Observe -> Complete 闭环；
6. 实现步骤级 `tool_call_ids` 历史重建、Retry、Skip、Abort、outcome 和执行限制；
7. 用故障注入测试固定 Checkpoint 时序和 at-least-once 语义；
8. 接入 ConversationRuntime 跨实例恢复；
9. 增加 ReAct 公共状态绑定接口并完成回归；
10. 更新 README 和 project-handoff；
11. 运行全部 Python 测试并检查工作区差异。

## 16. 完成标准

本期仅在以下条件全部满足时视为完成：

- Plan-and-Execute 可通过标准 Tool 完成完整状态机；
- 工具成功后由 StepPlanner 显式决定步骤是否完成；
- call_id、计数、状态和限制均由 Loop 控制；
- pending_tool_call 是待执行完整调用的唯一恢复来源；
- 同一步骤的全部工具结果可通过有序 `tool_call_ids` 重建；
- Retry 定义和计数符合本规格；
- LLMTaskPlanner 和 LLMStepPlanner 可通过真实 ModelClient 协议工作；
- Planner 无法通过输入引用修改真实状态；
- PlanStatus、agent phase、current step 和 pending 调用组合始终满足一致性矩阵；
- 恢复使用持久化限制；
- 步骤终态与下一步骤推进原子进入同一 Checkpoint；
- Abort 状态、剩余 pending 步骤和 Plan outcome 语义稳定；
- Planner 协议错误可查询、可诊断且不执行工具；
- finalization 可重复调用，但最终回答只追加一次；
- at-least-once 边界有明确测试；
- 旧 Checkpoint 和现有 ReAct 接口保持兼容；
- `pytest tests -q` 实际通过。

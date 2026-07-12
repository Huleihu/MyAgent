# ConversationRuntime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 提供可复用会话状态、隔离回合上下文并返回 Trace 快照的最小对话触发入口。

**Architecture:** 新模块只编排 `RuntimeExecutor` 和 `SessionState`，不修改既有 Executor、Agent Loop 或 Trace 模型。每轮创建 `RuntimeContext`，返回冻结的回合结果数据类。

**Tech Stack:** Python 3.11、dataclass、unittest。

## Global Constraints

- 新建 Python 文件必须有中文职责说明和中文文档字符串。
- 只支持串行同实例多轮，不增加并发、Memory、持久化或新 DSL 节点。
- 每轮工具 Trace 用会话级列表的起始长度截取，节点 Trace 使用当前 Context 的快照。

---

### Task 1: 回合结果与对话入口

**Files:**
- Create: `my_agent/runtime/conversation.py`
- Test: `tests/test_runtime_conversation.py`

**Interfaces:**
- Consumes: `RuntimeExecutor`、`SessionState`、`RuntimeContext`。
- Produces: `ConversationRuntime.chat(user_input) -> ConversationTurnResult`。

- [x] **Step 1: 写入失败测试**
- [x] **Step 2: 运行定向测试，确认缺少模块而失败**
- [x] **Step 3: 实现最小回合编排与 Trace 快照**
- [x] **Step 4: 运行定向测试，确认通过**

### Task 2: 连续多轮与异常约束

**Files:**
- Modify: `tests/test_runtime_conversation.py`
- Modify: `my_agent/runtime/conversation.py`

**Interfaces:**
- Consumes: Task 1 的 `ConversationRuntime` 与 `ConversationTurnResult`。
- Produces: 连续多轮历史可见、工具 Trace 隔离、输入与输出约定错误处理。

- [x] **Step 1: 写入连续多轮、工具 Trace、空输入与缺失输出失败测试**
- [x] **Step 2: 运行定向测试，确认失败**
- [x] **Step 3: 补充最小实现**
- [x] **Step 4: 运行完整 unittest 测试集**

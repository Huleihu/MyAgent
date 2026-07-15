# Persistent Runtime Checkpoint Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Runtime Checkpoint 扩展为默认 Web SQLite 持久化、可查询并可跨服务实例恢复的闭环。

**Architecture:** 保持现有 State、Runtime 和 Web 适配层边界。SQLite Store 负责连接安全和 metadata 持久化；ConversationRuntime 负责运行状态与失败包装；Web 层负责装配和稳定 HTTP 契约。

**Tech Stack:** Python、FastAPI、sqlite3、pytest、unittest。

## Global Constraints

- 保持 `ConversationRuntime.chat()` 与现有成功响应兼容。
- 新增 Python 文件使用中文职责说明；不做无关重构。
- 测试先行；不自动提交或推送。

---

### Task 1: 状态模型和 Checkpoint metadata

**Files:** `my_agent/state/run_state.py`、`my_agent/state/checkpoint.py`、`my_agent/state/checkpoint_recorder.py`、`my_agent/state/sqlite_checkpoint_store.py`、相关 state 测试。

- [ ] 先写 metadata SQLite 重启后仍存在、旧表可迁移、Trace 起点校验和 Cursor 终止语义的失败测试。
- [ ] 运行定向测试并确认因缺少新行为失败。
- [ ] 最小实现状态字段、metadata 传递、SQLite 显式列 SQL、`metadata_json` 迁移与 RLock。
- [ ] 运行定向 state 测试。

### Task 2: Runtime 完成、失败与 Trace 语义

**Files:** `my_agent/runtime/conversation.py`、`my_agent/runtime/executor.py`、`tests/test_runtime_checkpoint_resume.py`。

- [ ] 先写输出契约失败不完成、恢复成功清除 error、恢复结果过滤历史 Trace 的失败测试。
- [ ] 运行定向测试并确认失败。
- [ ] 最小实现 `RunExecutionFailedError`、完成顺序、恢复状态重置、Cursor None 与 Trace 切片。
- [ ] 运行定向 Runtime 测试。

### Task 3: Web 默认装配、查询和错误契约

**Files:** `my_agent/web/checkpoint_settings.py`、`my_agent/web/app.py`、`tests/test_web_api.py`。

- [ ] 先写默认路径、GET run 摘要、失败响应和 completed resume 409 的失败测试。
- [ ] 运行定向 Web 测试并确认失败。
- [ ] 最小实现 Web Store 装配/lifespan、稳定错误响应与端点。
- [ ] 运行定向 Web 测试。

### Task 4: 跨 App 恢复和文档

**Files:** `tests/test_web_api.py`、`README.md`、`docs/project-handoff.md`。

- [ ] 先写 App A 失败、丢弃实例、App B 查询恢复、工具不重复、后续消息连续性的端到端失败测试。
- [ ] 运行该测试并确认失败。
- [ ] 完成最小修复并更新使用文档与交接文档。
- [ ] 运行 `pytest tests -q` 并检查工作区差异。

# Persistent Runtime Checkpoint Hardening 设计

## 目标

让默认 Web 服务使用 SQLite Checkpoint，并在服务实例完全重建后查询失败运行、恢复运行和继续会话。

## 边界

保留 `RunState`、`CheckpointStore` 与 `ConversationRuntime` 的现有分层，不引入 RunRepository、后台任务或严格 exactly-once 语义。

## 装配与连接安全

Web 配置模块读取 `MYAGENT_CHECKPOINT_DB_PATH`，未设置时使用稳定的默认 SQLite 文件路径，并创建其父目录。`create_app()` 未注入 Store 时创建 `SQLiteCheckpointStore`；显式注入的 Store 仍用于测试。App 仅关闭自己创建的 Store。

`SQLiteCheckpointStore` 以进程内 `RLock` 串行化同一个 `sqlite3.Connection` 的 `save()`、`get_latest()` 和 `close()`。WAL 与 `busy_timeout` 继续处理不同连接或不同进程的竞争。表增加 `metadata_json`；建表兼容已有数据库，SQL 一律显式列名。

## 运行与恢复语义

`RunState` 增加非负整数 `tool_trace_start_index`，用于从同一 Session 的 Trace 中筛出本次运行的 Trace。旧 Checkpoint 缺失该字段时默认 `0`，因此旧运行可能包含历史 Trace，这是向后兼容行为。

`ExecutionCursor.next_node_id` 改为 `str | None`，`None` 表示所有节点完成。最后一个节点成功后写入 `None`；恢复到 `None` 时 Executor 不再重新执行节点。

`start()` 与 `resume()` 必须在 Runtime 成功执行且 `_read_last_message()` 验证成功后，才设置 `COMPLETED` 并写入 `run_completed` Checkpoint。恢复前设置 `RUNNING` 并清空旧 error；恢复成功最终状态必须为 `COMPLETED` 且 error 为 `None`。

已创建 RunState 后的执行失败由 `RunExecutionFailedError` 包装，保留异常链供日志使用。执行器仍保存内部失败详情到 Checkpoint。RuntimeFactory 创建 Runtime 之前的失败没有 run_id，HTTP 层使用独立通用初始化失败响应且不伪造标识。

## Web 契约

消息或恢复执行失败返回 HTTP 500，包含 `run_id`、`session_id`、`status: "failed"` 与稳定的 `error.code/message`，不返回堆栈。RuntimeFactory 初始化失败只返回通用初始化错误。

增加 `GET /runs/{run_id}`，返回最新 Checkpoint 的运行摘要。error 使用稳定公开的 code/message，不直接暴露 `str(exc)`；原始详情仅保存在 Checkpoint 与服务日志。已完成运行允许查询；再次 `POST /runs/{run_id}/resume` 返回 HTTP 409 和 `run_already_completed`。

## 测试

测试覆盖 metadata 的 SQLite 持久化与列迁移、Connection RLock、输出契约失败不得落库 completed、Cursor 终止、恢复后 error 清空、本 run Trace 过滤、错误 API 契约、运行摘要端点和跨 App SQLite 恢复。跨 App 测试在 App B 恢复完成后继续发送普通消息，验证恢复出的 SessionState 被 Store 保留。

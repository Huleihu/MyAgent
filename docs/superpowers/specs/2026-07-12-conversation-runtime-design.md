# ConversationRuntime 设计

## 目标

为现有线性 JSON DSL Runtime 增加面向用户消息的最小对话触发入口，并支持同一进程内的串行连续多轮。

## 设计

`ConversationRuntime` 通过构造参数接收 `RuntimeExecutor` 和 `SessionState`。每次 `chat(user_input)` 创建新的 `RuntimeContext`，把复用的 `SessionState` 注入其中，再调用 Executor。

`ReActAgentLoop` 仍是唯一写入 user、assistant 消息及工具 Trace 的组件。`ConversationRuntime` 只在执行前记录会话工具 Trace 数量，并在成功后截取本轮新增记录。

`ConversationTurnResult` 是冻结数据类，包含最终文本、本轮 `RuntimeContext`、节点 Trace 快照和工具 Trace 快照。Trace 使用 tuple 快照；`RuntimeContext` 保持可变，仅表示当前回合上下文。

## 输出与错误

最终文本来自 `RuntimeContext.variables["last_message"]`，这是 `ConversationRuntime` 对现有 `message` 节点的明确前置约定。若字段不存在、不是非空字符串，则抛出说明原因的 `ValueError`。

执行失败时保持原异常向外传播，不回滚已经写入的会话消息或工具 Trace，也不构造失败结果对象。

## 边界

第一版只支持同一实例的串行调用，不保证线程安全，不支持并发、持久化恢复、Memory、多用户会话、Human-in-the-loop 或 Checkpoint 恢复。

# Runtime 与 Agent Loop

JSON DSL Runtime 按 `begin`、`agent_loop`、`message` 的线性顺序执行节点。Agent Loop 负责
把用户消息写入 SessionState，调用 Planner 决定工具调用或最终回答，并把工具结果作为
observation 写回会话。节点 Trace 记录解析后的输入、输出、异常和耗时。

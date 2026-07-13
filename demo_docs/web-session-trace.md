# Web Session、Trace 与 Citation

Web API 为每个 session 保存独立的 SessionState，并用 session 级锁串行处理同一会话的消息。
每轮消息响应返回本轮 node_traces、tool_traces 和顶层 citations。前端应使用顶层 citations
展示参考来源，tool_traces 用于调试工具调用的参数、结果、错误和耗时。

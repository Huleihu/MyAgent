# 确定性 Agentic RAG Web 闭环实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标：** 让默认 Web Demo 通过 `retrieval.search` 生成确定性回答，并在成功消息响应顶层返回当前回合的 `citations`。

**架构：** `demo_runtime.py` 在模块内缓存只读 Demo RetrievalTool，并在每次会话消息时创建独立 Planner、TraceRecorder、ToolExecutor 和 Runtime。Web 序列化层只从 `ConversationTurnResult.tool_traces` 投影 Citation，不让 RAG 概念进入通用 Runtime。

**技术栈：** Python 3.11、FastAPI、unittest、现有 Markdown Parser、TextChunker、内存索引与 RetrievalTool。

## 全局约束

- 不修改 Runtime DSL、ConversationRuntime、Agent Loop、ToolExecutor 或 RAG 的公开接口。
- 成功响应固定含 `session_id`、`output_text`、`citations`、`node_traces`、`tool_traces`；失败响应保持现有结构。
- Demo 索引通过 `@lru_cache(maxsize=1)` 初始化一次，索引完成后只读并可跨 session 共享。
- SessionState、Planner、TraceRecorder、Tool Trace、ToolExecutor 与 Runtime 均按当前 session、当前请求独立创建。
- Planner 必须用 observation metadata 的 `call_id` 精确查找 Tool Trace，不能解析 observation 文本或读取“最新 Trace”。

---

### Task 1: 固定 Demo 知识库与端到端失败测试

**文件：**
- 创建：`demo_docs/agentic-rag.md`
- 创建：`demo_docs/runtime-agent-loop.md`
- 创建：`demo_docs/web-session-trace.md`
- 创建：`tests/test_demo_rag_web_api.py`
- 修改：`tests/test_web_api.py`

**接口：**
- 产出：默认 `create_app()` 的消息响应中存在顶层 `citations`。

- [ ] 编写失败测试，断言检索问题仅产生一次 `retrieval.search`、query 等于用户输入、Citation 顶层字段与本轮 Tool Trace 一致；断言无命中返回 `[]` 和稳定回答；断言多轮与多 session 不串扰。
- [ ] 运行 `conda run -n myagent-py311 python -m unittest tests.test_demo_rag_web_api -v`，预期因默认 Demo 仍为固定回答且无顶层 `citations` 而失败。

### Task 2: Demo 入库初始化与无状态 Planner

**文件：**
- 修改：`my_agent/web/demo_runtime.py`

**接口：**
- 产出：`_get_demo_retrieval_tool() -> RetrievalTool`、`DemoRagPlanner.plan(user_input, session)`。

- [ ] 以 `Path(__file__)` 定位、按文件名排序加载 `demo_docs`，使用 `RawDocument`、`MarkdownDocumentParser`、`TextChunker`、`SimpleEmbeddingModel`、`InMemoryChunkIndex`、`HybridRetriever`、`SimpleReranker`、`CitationBuilder` 创建 RetrievalTool。
- [ ] 使用 `@lru_cache(maxsize=1)` 缓存只读 Tool；每次 Runtime 仍用当前 SessionState 新建 TraceRecorder、Registry、ToolExecutor、Planner 与 ReActAgentLoop。
- [ ] Planner 在最后消息为用户时返回 `ToolAction("retrieval.search", {"query": user_input, "top_k": 3})`；在符合 retrieval observation 契约时按 call_id 找 Trace，并按成功/空结果/失败生成确定性 FinalAnswerAction。
- [ ] 运行端到端测试，预期 RAG 执行路径通过，Citation 顶层字段测试仍因 Web 投影未实现失败。

### Task 3: 顶层 Citation 投影

**文件：**
- 修改：`my_agent/web/app.py`
- 测试：`tests/test_web_api.py`、`tests/test_demo_rag_web_api.py`

**接口：**
- 产出：`_extract_turn_citations(tool_traces) -> list[dict]`。

- [ ] 遍历当前回合 Trace，仅合并成功 `retrieval.search` 的 dict `result.citations`；验证每项为 dict，按 `(doc_id, chunk_id)` 去重并深拷贝返回。
- [ ] 在 `_serialize_turn_result` 中按约定顺序加入 `citations`，无合法 Citation 时返回空列表。
- [ ] 运行两份 Web 测试，预期通过。

### Task 4: 文档与完整回归

**文件：**
- 修改：`docs/project-handoff.md`

- [ ] 说明 Demo 入库链路与聊天查询链路分离、惰性缓存只读前提、顶层 Citation 契约、用户知识库与授权尚未实现。
- [ ] 运行 `conda run -n myagent-py311 python -m unittest discover -s tests -v` 与 `git diff --check`；记录实际结果。

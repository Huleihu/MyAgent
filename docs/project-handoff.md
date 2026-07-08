# 项目交接文档

## 1. 项目目标

本项目用于实现一个简化版 Agent Runtime 与 Agentic RAG 能力，帮助面试时说明以下经历：

```text
1. 基于 JSON DSL 的轻量级 Agent Runtime；
2. Agentic RAG 链路，Retrieval 作为 Agent 可调用 Tool；
3. ReAct / Plan-and-Execute 风格 Agent Loop 与标准 Tool Calling；
4. State、Memory、Checkpoint、Trace 与 Agent Eval 数据基础。
```

当前已经完成：

```text
1. Tool Calling 框架 MVP；
2. Agentic RAG 设计文档；
3. RAG 数据模型；
4. Markdown 文档解析与 ParserRegistry；
5. TextChunker 文档切分；
6. Chunk 向量化与内存向量索引；
7. 混合召回、简单重排与引用构造；
8. RetrievalTool 工具适配；
9. RAG Trace 与 Retrieval Test；
10. State + Trace MVP；
11. ToolExecutor 可选写入全局工具调用 Trace；
12. Checkpoint MVP；
13. 多轮 ReAct Agent Loop MVP。
14. CheckpointRecorder 与 Agent Loop Checkpoint 接入 MVP。
15. LLMPlanner 与模型调用抽象 MVP。
```

### 1.1 最终五阶段路线图与当前进度

用户确认的最终目标按五个阶段推进：

```text
第一阶段：核心数据模型与 Tool 框架
core/models.py
core/interfaces.py
tools/schema.py
tools/registry.py
tools/executor.py
目标：能注册一个工具、校验参数、执行工具、返回标准化 ToolCallResult。

第二阶段：Agentic RAG Tool
rag/models.py
rag/indexing/chunker.py
rag/indexing/embedding.py
rag/indexing/index.py
rag/retrieval/retriever.py
rag/retrieval/retrieval_tool.py
目标：把文档切 chunk，建内存索引，然后通过 retrieval.search 这个 Tool 被 Agent 调用，并返回答案相关片段和引用来源。

第三阶段：Trace / State
state/trace.py
state/session.py
目标：每次工具调用都能记录耗时、输入、输出、异常，并能把消息与工具调用记录保存到会话状态中。这个对面试讲“可信执行链路”和“Agent Eval 数据基础”很加分。

第四阶段：Agent Loop
agent_loop/react.py
agent_loop/planner.py
目标：基于已有 Tool 框架做 ReAct 循环，不需要真实大模型，先用 Fake Planner/Fake LLM 模拟决策。

第五阶段：JSON DSL Runtime
dsl/schema.py
dsl/loader.py
runtime/graph.py
runtime/executor.py
目标：把前面的 Tool、RAG、Trace 包进节点编排里。
```

当前进度：

```text
第一阶段：基本完成
第二阶段：已完成，并额外补充了 RAG Trace 与 Retrieval Test
第三阶段：State / Trace / Checkpoint MVP 已完成
第四阶段：多轮 ReAct Agent Loop MVP 已完成，已接入可选 Checkpoint 与 LLMPlanner MVP，尚未接真实 LLM SDK
第五阶段：尚未开始
```

说明：

- 当前项目没有单独的 `core/models.py`，Tool 数据模型集中在 `tools/schema.py`，异常在 `core/errors.py`，抽象接口在 `core/interfaces.py`；
- 当前已经有 `my_agent/rag/evaluation/trace.py` 和 `my_agent/rag/evaluation/eval.py`，它们只服务于 RAG 检索评估；
- 第三阶段的 `state/trace.py` 和 `state/session.py` 应作为全局 Agent Runtime 的执行记录与会话状态模块，不应直接复用或混淆 RAG 专用 Trace；
- 下一步如果继续按最终目标推进，建议进入 JSON DSL Runtime，或在保持解耦的前提下新增真实模型适配器。

### 1.2 当前 RAG 目录结构

RAG 目录已按数据流阶段分组，便于阅读代码：

```text
my_agent/rag/
  models.py
    Document / Chunk / RetrievedChunk / Citation

  parsing/
    parser.py
    markdown_parser.py
    parser_registry.py
    负责 RawDocument -> Document

  indexing/
    chunker.py
    embedding.py
    index.py
    负责 Document -> Chunk -> embedding -> in-memory index

  retrieval/
    retriever.py
    reranker.py
    citation.py
    retrieval_tool.py
    负责召回、重排、引用构造和 retrieval.search Tool 适配

  evaluation/
    trace.py
    eval.py
    负责 RAG 专用 Trace 与检索评估
```

阅读顺序建议：

```text
models.py
-> parsing/
-> indexing/
-> retrieval/
-> evaluation/
```

## 2. 已完成内容

### 2.1 Tool 数据模型与异常

文件：

```text
my_agent/core/errors.py
my_agent/tools/schema.py
tests/test_tool_schema.py
```

完成：

- `ToolError`
- `ToolNotFoundError`
- `ToolAlreadyExistsError`
- `ToolValidationError`
- `ToolExecutionError`
- `ToolDefinition`
- `ToolCallRequest`
- `ToolCallResult`

关键约束：

- `ToolDefinition.parameters` 必须是 JSON Schema object schema；
- `ToolCallResult.error` 使用结构化 dict，不使用普通字符串；
- 成功结果必须有 dict 类型 `data`；
- 失败结果必须有 `{"type": "...", "message": "..."}`。

### 2.2 Tool 抽象接口

文件：

```text
my_agent/core/interfaces.py
tests/test_tool_interface.py
```

完成：

- `Tool` 抽象基类；
- 具体工具必须显式继承 `Tool`；
- 具体工具必须实现：

```text
definition -> ToolDefinition
run(arguments: dict) -> dict
```

### 2.3 ToolRegistry

文件：

```text
my_agent/tools/registry.py
tests/test_tool_registry.py
```

完成：

- `register(tool)`；
- `get(name)`；
- `list_definitions(tags=None)`；
- 重复工具名检测；
- 非 Tool 对象拒绝；
- 按 tag 导出工具定义。

边界：

- 只负责注册和查找；
- 不执行工具；
- 不校验具体调用参数。

### 2.4 FunctionTool

文件：

```text
my_agent/tools/function_tool.py
tests/test_function_tool.py
```

完成：

- 将普通 Python 函数包装为标准 Tool；
- 内部生成 `ToolDefinition`；
- `run(arguments)` 调用被包装函数；
- 非 callable 的 `func` 会被拒绝。

边界：

- 不负责异常包装；
- 不负责耗时记录；
- 工具返回值类型由 `ToolExecutor` 校验。

### 2.5 ToolExecutor

文件：

```text
my_agent/tools/executor.py
tests/test_tool_executor.py
```

完成：

- 接收 `ToolCallRequest`；
- 从 `ToolRegistry` 查找工具；
- 校验 required 参数；
- 调用 `tool.run(arguments)`；
- 成功返回 `ToolCallResult.success_result(...)`；
- 工具不存在、参数缺失、工具异常、返回非 dict 时返回结构化错误；
- 记录 `duration_ms`；
- 保留 `call_id`。

### 2.6 RAG 设计文档

文件：

```text
docs/agentic-rag-tool-design.md
```

完成：

- Agentic RAG 7 步开发方案；
- 插入文档解析 Parser 作为第 2 步；
- 明确 `RawDocument -> Parser -> Document -> Chunk -> RetrievalTool` 主链路；
- 明确 Document 和 Chunk 必须有 metadata；
- 明确 `top_k` 使用 integer；
- 明确 SimpleEmbeddingModel 不能使用随机向量；
- 明确需要 RAG Trace 和 Retrieval Test。

### 2.7 RAG 数据模型

文件：

```text
my_agent/rag/models.py
tests/test_rag_document.py
```

完成：

- `Document`
- `Chunk`
- `RetrievedChunk`
- `Citation`

关键字段：

```text
Document:
  doc_id
  title
  source
  content
  metadata

Chunk:
  chunk_id
  doc_id
  content
  index
  metadata

RetrievedChunk:
  chunk
  keyword_score
  vector_score
  final_score
  rerank_score

Citation:
  doc_id
  chunk_id
  source
  title
  snippet
  score
  metadata
```

边界：

- 数据模型不负责解析；
- 数据模型不负责切分；
- 数据模型不负责检索；
- 只做必要字段校验。

### 2.8 文档解析 Parser

文件：

```text
my_agent/rag/parsing/parser.py
my_agent/rag/parsing/markdown_parser.py
my_agent/rag/parsing/parser_registry.py
tests/test_rag_parser.py
```

完成：

- `RawDocument`
- `DocumentParser`
- `MarkdownDocumentParser`
- `DocumentParserRegistry`

Markdown 支持：

- 支持 `.md` / `.markdown`；
- 从第一个 Markdown 标题提取 `Document.title`；
- 没有标题时使用 filename 作为 title；
- 支持 `str` 和 UTF-8 `bytes` 内容；
- `Document.metadata` 会补充：
  - `source`
  - `filename`
  - `extension`
  - `parser`
  - `title`
  - `headings`

ParserRegistry 支持：

- 注册解析器；
- 按文件扩展名选择解析器；
- 扩展名大小写不敏感；
- 不支持扩展名时抛明确异常。

扩展方式：

```text
后续新增 PdfDocumentParser / WordDocumentParser 时，只需要实现 DocumentParser 并注册到 DocumentParserRegistry。
Chunker、Retriever、ToolExecutor 不需要知道原始文件格式。
```

### 2.9 TextChunker 文档切分

文件：

```text
my_agent/rag/indexing/chunker.py
tests/test_rag_chunker.py
```

完成：

- `TextChunker`
- `split(document)`
- `split_many(documents)`
- 支持 `chunk_size`
- 支持 `overlap`
- `chunk_id = {doc_id}:{index}`
- `Chunk.metadata` 继承 `Document.metadata`
- `Chunk.metadata` 补充：
  - `source`
  - `title`
  - `chunk_index`

overlap 实现方式：

```text
step_size = chunk_size - overlap
下一块起点 = 当前起点 + step_size
```

示例：

```text
content = abcdefghijklmnopqrstuvwxyz
chunk_size = 10
overlap = 3

chunks:
  abcdefghij
  hijklmnopq
  opqrstuvwx
  vwxyz
```

边界：

- Chunker 只接收标准 `Document`；
- Chunker 不读取文件；
- Chunker 不解析 Markdown / PDF / Word；
- Chunker 不做 Embedding；
- Chunker 不写索引。

### 2.10 Chunk 向量化与内存向量索引

文件：

```text
my_agent/rag/indexing/embedding.py
my_agent/rag/indexing/index.py
tests/test_rag_index.py
```

完成：

- `SimpleEmbeddingModel`
- `InMemoryChunkIndex`
- `keyword_search(query, top_k)`
- `vector_search(query, top_k)`

Embedding 规则：

- 使用确定性词袋，不使用随机向量；
- 英文按单词分词；
- 中文按单字分词；
- 统一转小写；
- 使用词频构造稀疏向量；
- 使用 cosine similarity 计算向量相似度。

Index 行为：

- `add_chunks(chunks)` 对每个 `Chunk` 生成 embedding 并存入内存；
- `keyword_search(query, top_k)` 按 query token 覆盖率返回 `RetrievedChunk`；
- `vector_search(query, top_k)` 按 query embedding 与 Chunk embedding 的余弦相似度返回 `RetrievedChunk`；
- `top_k` 必须是正整数；
- 空 query 会被拒绝；
- 返回结果会保留 `keyword_score`、`vector_score`、`final_score`。

边界：

- Embedding 模块只负责文本向量化和相似度计算；
- Index 模块只负责内存保存、基础召回和排序；
- Index 不负责混合召回融合、重排和引用构造；
- 不依赖真实 Embedding 服务；
- 不依赖外部向量数据库。

### 2.11 混合召回、简单重排与引用构造

文件：

```text
my_agent/rag/retrieval/retriever.py
my_agent/rag/retrieval/reranker.py
my_agent/rag/retrieval/citation.py
tests/test_rag_retriever.py
```

完成：

- `HybridRetriever`
- `SimpleReranker`
- `CitationBuilder`

HybridRetriever 行为：

- 调用 `InMemoryChunkIndex.keyword_search(query, top_k)` 获取关键词召回；
- 调用 `InMemoryChunkIndex.vector_search(query, top_k)` 获取向量召回；
- 按 `chunk_id` 合并两路召回结果；
- 使用 `final_score = keyword_weight * keyword_score + vector_weight * vector_score` 计算融合分数；
- 默认 `keyword_weight = 0.4`，`vector_weight = 0.6`；
- 按 `final_score` 降序返回前 `top_k` 个 `RetrievedChunk`。

SimpleReranker 行为：

- 只接收 `RetrievedChunk` 列表；
- 不访问索引，不重新召回；
- 第一版按已有 `final_score` 稳定排序；
- 将 `rerank_score` 设置为当前 `final_score`，为后续真实 Rerank 服务保留分数字段。

CitationBuilder 行为：

- 将 `RetrievedChunk` 转换为 `Citation`；
- 从 `Chunk.metadata` 读取 `source` 和 `title`；
- `snippet` 使用 Chunk 原文；
- 优先使用 `rerank_score` 作为引用分数，缺失时使用 `final_score`；
- 保留 Chunk metadata，便于后续展示 filename、page、section 等溯源字段。

边界：

- Retriever 只负责召回和融合；
- Reranker 只负责重排；
- CitationBuilder 只负责引用数据转换；
- 三者都不调用 ToolExecutor；
- 三者都不依赖具体文档解析器或文件格式。

### 2.12 RetrievalTool 工具适配

文件：

```text
my_agent/rag/retrieval/retrieval_tool.py
tests/test_retrieval_tool.py
```

完成：

- `RetrievalTool`
- `definition.name = "retrieval.search"`
- `run(arguments)`
- 通过 `ToolRegistry` 和 `ToolExecutor` 调用 `retrieval.search`

Tool Schema：

```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "用户检索问题"
    },
    "top_k": {
      "type": "integer",
      "default": 5,
      "minimum": 1,
      "maximum": 20
    }
  },
  "required": ["query"]
}
```

行为：

- `query` 必须是非空字符串；
- `top_k` 默认值为 5；
- `top_k` 必须是 1 到 20 之间的整数；
- 调用 `HybridRetriever.retrieve(query, top_k)` 获取召回结果；
- 调用 `SimpleReranker.rerank(query, retrieved_chunks)` 写入重排分数；
- 调用 `CitationBuilder.build(reranked_chunks)` 生成引用；
- 返回结构化 `query`、`chunks` 和 `citations`。

返回结构：

```text
{
  "query": "...",
  "chunks": [
    {
      "chunk_id": "...",
      "doc_id": "...",
      "content": "...",
      "keyword_score": 0.0,
      "vector_score": 0.0,
      "final_score": 0.0,
      "rerank_score": 0.0,
      "metadata": {...}
    }
  ],
  "citations": [
    {
      "doc_id": "...",
      "chunk_id": "...",
      "source": "...",
      "title": "...",
      "snippet": "...",
      "score": 0.0,
      "metadata": {...}
    }
  ]
}
```

边界：

- RetrievalTool 只做 Tool 适配；
- RetrievalTool 不负责文档解析；
- RetrievalTool 不负责 Chunk 切分；
- RetrievalTool 不负责索引写入；
- RetrievalTool 不直接管理 ToolRegistry 或 ToolExecutor。

### 2.13 RAG Trace 与 Retrieval Test

文件：

```text
my_agent/rag/evaluation/trace.py
my_agent/rag/evaluation/eval.py
tests/test_rag_eval.py
```

完成：

- `RagTrace`
- `RetrievalTestCase`
- `RetrievalEvalResult`
- `RetrievalEvaluator`

RagTrace 字段：

```text
query
retrieved_chunks
citations
duration_ms
```

RetrievalTestCase 字段：

```text
query
expected_doc_ids
expected_chunk_keywords
top_k
```

RetrievalEvalResult 字段：

```text
hit
matched_doc_ids
missing_doc_ids
top_chunks
trace
failure_reasons
```

RetrievalEvaluator 行为：

- 通过 `RetrievalTool.run({"query": ..., "top_k": ...})` 执行检索；
- 记录 `RagTrace`，包括 query、召回 chunks、citations 和 duration_ms；
- 按 `expected_doc_ids` 判断命中文档；
- 按 `expected_chunk_keywords` 判断召回内容是否包含期望关键词；
- 返回 `matched_doc_ids`、`missing_doc_ids` 和 `top_chunks`；
- 生成可读的 `failure_reasons`，用于定位召回失败原因。

当前 failure_reasons 支持：

- `missing_doc_ids: ...`
- `missing_chunk_keywords: ...`
- `keyword_score 全低：关键词召回可能失败`
- `vector_score 全低：Embedding 表达可能不足`
- `final_score 全低：融合分数可能异常`
- `citations 缺失：引用构造可能失败`
- `未召回任何 Chunk：知识库可能没有答案`

边界：

- Trace 只记录检索过程，不执行检索；
- Evaluator 只执行测试和生成评估结论；
- Evaluator 不负责构建索引；
- Evaluator 不直接调用 Parser 或 Chunker；
- 评估基于 RetrievalTool 的结构化返回，保证覆盖端到端工具链。

### 2.14 State + Trace MVP

文件：

```text
my_agent/state/trace.py
my_agent/state/session.py
my_agent/state/recorder.py
my_agent/state/checkpoint.py
my_agent/state/__init__.py
tests/test_state_trace.py
tests/test_state_session.py
tests/test_trace_recorder.py
tests/test_tool_executor_trace.py
tests/test_state_checkpoint.py
```

完成：

- `ToolTraceRecord`
- `SessionMessage`
- `SessionState`
- `TraceRecorder`
- `Checkpoint`

`ToolTraceRecord` 字段：

```text
trace_id
tool_name
call_id
arguments
success
result
error
duration_ms
token_usage
```

行为与约束：

- `trace_id` 和 `tool_name` 必须是非空字符串；
- `call_id` 可以为空，便于记录没有外部调用编号的工具调用；
- `arguments` 必须是 `dict`；
- `result`、`error`、`token_usage` 必须是 `dict` 或 `None`，便于后续 JSON 序列化；
- `duration_ms` 必须是非负数；
- 成功记录必须有 `result` 且不能有 `error`；
- 失败记录必须有结构化 `error`；
- Trace 只记录工具调用，不执行工具，也不依赖具体 Tool 或 RAG 类型。

`SessionMessage` 字段：

```text
role
content
metadata
```

`SessionState` 字段：

```text
session_id
messages
tool_traces
```

`SessionState` 最小 API：

```text
add_message(role, content, metadata=None)
add_tool_trace(trace)
list_messages()
list_tool_traces()
```

边界：

- Session 只保存一次 Agent 会话中的消息和工具调用记录；
- Session 不负责执行 Agent Loop；
- Session 不负责持久化、Checkpoint 恢复或 Memory 检索；
- `list_messages()` 和 `list_tool_traces()` 返回列表浅拷贝，避免调用方直接清空内部列表；
- `TraceRecorder` 接收 `SessionState`，只负责把 `ToolTraceRecord` 写入会话状态；
- `TraceRecorder` 初始化时会拒绝非 `SessionState`，`record_tool_call(trace)` 会拒绝非 `ToolTraceRecord`；
- `ToolExecutor` 已支持可选 `trace_recorder` 参数，未传入时保持原有行为，传入后会把每次 `ToolCallResult` 转换为 `ToolTraceRecord`；
- `ToolExecutor` 不直接 import 或依赖 `SessionState`，只在工具执行边界附近生成 Trace 数据；
- 当前 Trace 已覆盖成功调用、工具不存在、参数缺失、工具异常和返回非 dict 等路径。

`Checkpoint` 字段：

```text
checkpoint_id
session_id
messages
tool_traces
metadata
```

`Checkpoint` 最小 API：

```text
Checkpoint.from_session(checkpoint_id, session_state, metadata=None)
list_messages()
list_tool_traces()
```

边界：

- Checkpoint 只负责保存某一时刻的 `SessionState` 内存快照；
- Checkpoint 不负责文件持久化、数据库存储或 Agent Loop 恢复；
- 从 `SessionState` 创建快照后，后续继续修改 Session 不会改变已有 Checkpoint 的列表内容；
- `list_messages()` 和 `list_tool_traces()` 返回列表浅拷贝，避免调用方直接清空内部列表；
- 当前未做 `metadata` 深拷贝，后续如果需要严格不可变快照，可再升级为深拷贝或序列化快照。

### 2.15 多轮 ReAct Agent Loop MVP

文件：

```text
my_agent/agent_loop/planner.py
my_agent/agent_loop/react.py
my_agent/agent_loop/__init__.py
tests/test_agent_loop.py
```

完成：

- `AgentAction`
- `ToolAction`
- `FinalAnswerAction`
- `Planner`
- `FakePlanner`
- `ReActAgentLoop`

`ToolAction` 字段：

```text
tool_name
arguments
call_id
```

`FinalAnswerAction` 字段：

```text
answer
```

Planner 边界：

- `Planner.plan(user_input, session)` 只负责返回下一步动作；
- `FakePlanner` 只用于测试和离线演示，按预设动作顺序返回；
- 已新增 `LLMPlanner(Planner)`，后续接真实模型时应新增真实 `ModelClient` 适配器，避免修改 `ReActAgentLoop`。

`ReActAgentLoop` 行为：

- `run(user_input)` 会先写入 user message；
- 每轮调用一次 `Planner.plan(user_input, session)`，最多执行 `max_rounds` 轮 Planner 决策；
- 如果 Planner 返回 `FinalAnswerAction`，则写入 assistant message 并返回最终答案；
- 如果 Planner 返回 `ToolAction`，则通过 `ToolExecutor` 执行工具，并把工具结果作为 observation message 写回 `SessionState`；
- `ToolAction.call_id` 为空时，Agent Loop 会生成新的调用编号；
- 工具 observation 使用 `metadata["message_type"] = "tool_observation"` 标记，便于后续 Planner 区分普通助手消息与工具观测；
- 工具调用结果会被压缩为 observation 摘要，避免把完整 RAG chunks/citations 直接塞进对话；
- 工具调用 Trace 仍由 `ToolExecutor + TraceRecorder` 自动写入 `SessionState`。

边界：

- 当前每轮只支持一个 `ToolAction`，后续并发 tool-calling 可扩展为一轮返回多个工具动作；
- 当前只限制 `max_rounds`，暂不引入 `max_tool_calls`，等并发 tool-calling 实现时再补充工具总调用数限制；
- 当前不接真实 LLM；
- 当前仅在配置 `CheckpointRecorder` 时创建 Checkpoint；
- 当前不做 Memory、Human-in-the-loop 或 JSON DSL Runtime；
- Agent Loop 只依赖 `Planner`、`ToolExecutor` 和 `SessionState`，不直接依赖具体工具或 RAG 内部模块。

### 2.16 CheckpointRecorder 与 Agent Loop Checkpoint 接入

文件：

```text
my_agent/state/checkpoint_recorder.py
my_agent/state/__init__.py
my_agent/agent_loop/react.py
tests/test_checkpoint_recorder.py
tests/test_agent_loop.py
```

完成：

- `CheckpointRecorder`
- `record(metadata=None)`
- `list_checkpoints()`
- `ReActAgentLoop` 可选接收 `checkpoint_recorder`

`CheckpointRecorder` 行为：

- 初始化时接收 `SessionState`；
- `record(metadata=None)` 内部生成 `checkpoint_id`，并通过 `Checkpoint.from_session(...)` 创建内存快照；
- `list_checkpoints()` 返回列表副本，避免调用方清空内部 checkpoint 记录；
- 不负责文件持久化、数据库存储或从 checkpoint 恢复。

Agent Loop Checkpoint 行为：

- 未传入 `checkpoint_recorder` 时，Agent Loop 行为保持不变；
- 用户输入写入 session 后记录 checkpoint，metadata 使用 `reason="after_user_input"` 和 `round_index=0`；
- 工具调用完成后，先由 `ToolExecutor` 写入 trace，再由 Agent Loop 写入 observation message，最后记录 checkpoint；
- 工具 observation checkpoint 使用 `reason="after_tool_observation"`，并记录 `round_index`、`tool_name`、`call_id`、`success`；
- 最终回答写入 session 后记录 checkpoint，metadata 使用 `reason="after_final_answer"`；
- `round_index` 表示第几轮 Planner 决策完成后：直接最终回答为 1，第一轮工具后为 1，第二轮工具后为 2。

边界：

- Checkpoint 仍然是内存快照；
- 暂不做 Checkpoint 持久化；
- 暂不做从 Checkpoint 恢复 Agent Loop；
- 暂不做 checkpoint graph/tree。

### 2.17 LLMPlanner 与模型调用抽象 MVP

文件：

```text
my_agent/llm/__init__.py
my_agent/llm/config.py
my_agent/llm/client.py
my_agent/llm/fake.py
my_agent/agent_loop/llm_planner.py
my_agent/agent_loop/__init__.py
tests/test_llm_config.py
tests/test_fake_model_client.py
tests/test_llm_planner.py
```

完成：

- `ModelConfig`
- `ModelClient`
- `FakeModelClient`
- `LLMPlanner`

`ModelConfig` 行为：

- 只保存模型配置字段：`provider`、`model_name`、`api_key`、`base_url`、`temperature`、`max_tokens`、`timeout_seconds`；
- 不读取环境变量；
- 不读取配置文件；
- 不调用模型服务。

`ModelClient` 边界：

- 使用抽象接口定义 `chat(messages, tool_definitions) -> dict[str, Any]`；
- 只负责模型调用边界，不负责把响应解析为 `AgentAction`；
- 当前不绑定 OpenAI、Qwen、DeepSeek 等具体 SDK。

`FakeModelClient` 行为：

- 按预设顺序返回模型响应字典；
- 记录每次 chat 调用收到的 `messages` 和 `tool_definitions`；
- 用于单元测试和离线演示；
- 不依赖 Agent Loop 的动作模型。

`LLMPlanner` 行为：

- 只依赖 `ModelClient` 和 `ToolDefinition`；
- 从 `SessionState.messages` 构造模型输入消息；
- 将 `ToolDefinition` 转换为普通 dict 传给模型客户端；
- 如果模型响应为 `{"type": "tool_call", ...}`，转换为 `ToolAction`；
- 如果模型响应为 `{"type": "final_answer", ...}`，转换为 `FinalAnswerAction`；
- 如果模型响应结构非法，抛出明确 `ValueError`。

边界：

- `LLMPlanner` 不依赖 `ModelConfig`；
- `LLMPlanner` 不读取 `api_key`；
- `ReActAgentLoop`、`ToolExecutor`、`SessionState`、`CheckpointRecorder` 都不包含模型配置字段；
- 暂不实现真实模型调用、streaming、retry、token 统计或多模型路由。

## 3. 当前调用链

Tool 调用链：

```text
FunctionTool / 未来的 RetrievalTool
        |
        v
ToolRegistry.register(tool)
        |
        v
ToolCallRequest(name, arguments, call_id)
        |
        v
ToolExecutor.execute(request)
        |
        v
ToolCallResult(success, data, error, duration_ms)
        |
        v
ToolTraceRecord
        |
        v
TraceRecorder.record_tool_call(trace)
        |
        v
SessionState.tool_traces
```

RAG 当前链路：

```text
RawDocument
        |
        v
DocumentParserRegistry
        |
        v
MarkdownDocumentParser
        |
        v
list[Document]
        |
        v
TextChunker
        |
        v
list[Chunk]
        |
        v
SimpleEmbeddingModel
        |
        v
InMemoryChunkIndex
        |
        v
keyword_search / vector_search
        |
        v
HybridRetriever
        |
        v
SimpleReranker
        |
        v
CitationBuilder
        |
        v
RetrievalTool
        |
        v
ToolRegistry / ToolExecutor
        |
        v
RagTrace / RetrievalEvaluator
```

State 当前链路：

```text
SessionState
        |
        | add_message(role, content, metadata)
        v
list[SessionMessage]

ToolTraceRecord
        |
        | add_tool_trace(trace)
        v
SessionState.tool_traces
```

说明：

- `ToolExecutor` 通过可选 `trace_recorder` 写入全局工具调用 Trace；
- 未传入 `trace_recorder` 时，`ToolExecutor` 行为与原有测试保持一致；
- `ToolCallResult` 到 `ToolTraceRecord` 的转换放在工具执行边界附近，具体工具不需要关心 Trace；
- `token_usage` 当前保持 `None`，因为普通工具执行本身没有 LLM Token 来源。

## 4. 当前提交历史

```text
d8f2aef 新增工具调用数据模型与异常
081ce9e 新增工具抽象接口与开发环境配置
b2a4fa0 新增工具注册表
7dfcf0a 新增函数工具包装器
5005229 新增工具执行器
f6a77de 新增Agentic RAG设计文档与数据模型
cf589cc 新增Markdown文档解析器
7d90f10 新增文本切分器
ffb1abc 新增Chunk向量化与内存索引
3ee6074 新增混合召回重排与引用构造
ad5b934 新增RetrievalTool工具适配
cc32286 新增RAG Trace与检索评估
71761fc 重组RAG目录结构
1b7bfe3 新增State与工具调用Trace基础模型
9eb6d3e 新增ToolExecutor工具调用Trace记录
2ce3422 新增Checkpoint会话状态快照模型
d047bf3 新增单步ReAct Agent Loop
b4e4b74 新增多轮ReAct Agent Loop
6b544cb 新增Agent Loop Checkpoint记录器
```

当前建议提交信息：

```text
新增多轮ReAct Agent Loop
新增Agent Loop Checkpoint记录器
新增LLMPlanner模型规划器
```

## 5. 测试与环境

环境文件：

```text
environment.yml
requirements.txt
```

推荐环境：

```text
conda activate myagent-py311
pip install -r requirements.txt
```

当前测试命令：

```bash
python -m unittest discover -v
```

最近一次完整测试结果：

```text
Ran 114 tests in 0.006s
OK
```

说明：

- Codex 当前默认 `python` 曾显示为 Python 3.7.4；
- 用户已经在本地激活 `myagent-py311` 并确认 requirements 已安装；
- 后续建议用户在 `myagent-py311` 环境中运行测试。

## 6. 可维护性与后续增强建议

当前 Chunker 和 Embedding 都是第一版 MVP，实现刻意保持简单，便于测试和面试演示。后续增强时应继续保持“输入输出契约稳定、实现可替换”的方向，避免把语义切分、真实模型调用、索引存储和 Agent Tool 适配混在一起。

### 6.1 Chunker 增强

当前 `TextChunker` 使用固定字符长度切分，优点是确定、简单、容易测试；不足是不了解标题、段落、列表和代码块等文档结构。

后续增强建议：

- 保持 `split(document) -> list[Chunk]` 和 `split_many(documents) -> list[Chunk]` 这两个调用契约；
- 新增 `MarkdownStructureChunker` 或 `ParagraphChunker`，优先按标题、段落和列表边界切分；
- 过长段落再回退到固定长度切分和 overlap；
- Chunk metadata 中继续保留 `source`、`title`、`chunk_index`，后续可补充 `section`、`heading_path`、`start_offset`、`end_offset`；
- 不让 Chunker 直接调用 Embedding、Index 或 ToolExecutor。

### 6.2 Embedding 与 Index 增强

当前 `SimpleEmbeddingModel` 使用确定性词袋，适合作为测试实现；不足是语义表达能力弱，中文按单字分词也比较粗糙。

后续增强建议：

- 在接入真实 embedding 前，再抽轻量 `EmbeddingModel` 协议；
- 保留 `SimpleEmbeddingModel` 作为单元测试和离线演示实现；
- 新增真实模型适配器时，只负责把文本转成项目内部向量表示，不把第三方 SDK 类型扩散到核心 RAG 模块；
- 在接入外部向量库前，再抽轻量 `ChunkIndex` 协议；
- 让 `HybridRetriever` 依赖 `keyword_search(query, top_k)` 和 `vector_search(query, top_k)` 这样的索引能力，而不是依赖某个具体数据库 SDK；
- 避免提前创建没有调用方的复杂接口，等 RetrievalTool、Trace 或真实模型接入前再做小步抽象。

### 6.3 推荐演进顺序

建议先完成 `RetrievalTool`，形成端到端闭环，再回头增强 Chunker 和 Embedding。这样增强效果可以通过 Retrieval Test 和 Trace 直接观察，避免为了抽象而抽象。

推荐顺序：

```text
1. RetrievalTool
2. RAG Trace 与 Retrieval Test
3. 结构感知 Chunker
4. EmbeddingModel / ChunkIndex 轻量协议
5. 真实 Embedding 适配器或外部向量库适配器
```

## 7. 下一阶段计划

当前第四阶段的多轮 ReAct Agent Loop、Checkpoint 接入和 LLMPlanner MVP 已完成。下一步建议进入第五阶段 JSON DSL Runtime，或补充真实模型适配器。

建议新增或修改文件：

```text
my_agent/dsl/schema.py
my_agent/dsl/loader.py
my_agent/runtime/graph.py
my_agent/runtime/executor.py
tests/test_dsl_runtime.py
```

目标：

- 先实现最小 JSON DSL 数据模型和加载校验；
- 把 Tool、Agent Loop、Trace、Checkpoint 能力包装进可执行节点；
- Runtime 仍通过现有公开接口调用 Agent Loop 和 ToolExecutor；
- 不把具体 LLM SDK、RAG 内部实现或存储细节写进 DSL Runtime。

建议实现顺序：

```text
1. 先定义 JSON DSL 的最小 schema，只覆盖当前已有能力；
2. 实现 loader，把 dict / JSON 转成项目内部数据模型；
3. 实现最小 runtime graph，只支持顺序执行或单节点执行；
4. Runtime 节点通过依赖注入使用现有 ToolExecutor / ReActAgentLoop；
5. 后续再考虑真实模型适配器、Checkpoint 文件持久化、数据库存储或从 checkpoint 恢复；
6. 跑完整 unittest，确认已有 Tool/RAG/State/Checkpoint/Agent Loop 测试不回归。
```

暂缓事项：

- 暂不做 Memory；
- 暂不做 Checkpoint 持久化和自动恢复；
- 暂不做 Human-in-the-loop 暂停恢复；
- 暂不做复杂节点执行路径 Trace，等 Agent Loop MVP 跑通后再细化；
- 暂不把 RAG 专用 `RagTrace` 合并进全局 Trace，避免混淆评估 Trace 与 Runtime Trace。

RAG 后续增强建议：

- Chunker 从固定字符切分升级为 Markdown 结构感知切分；
- Embedding 从确定性词袋升级为可替换模型适配器；
- Index 从内存实现升级为可替换向量库适配器；
- RAG Trace 细化为 parse、chunk、embed、retrieve、rerank、citation 多阶段记录；
- Retrieval Test 支持批量用例、指标汇总和失败原因统计。

## 8. 开发约束

必须遵守项目 `AGENTS.md`：

- 新建 Python 文件顶部必须有中文职责说明；
- 公共类、公共函数、核心业务函数应添加简洁中文文档字符串；
- 每个模块保持单一职责；
- 修改范围尽量小；
- 不引入不必要抽象；
- 不声称未运行的检查通过；
- 不覆盖用户未提交修改。

RAG 阶段额外约束：

- Document 和 Chunk 必须有 metadata；
- Parser 只负责把原始文件转成标准 `Document`；
- Chunker 不关心原始文件格式；
- Chunker 不负责向量化和索引写入；
- `retrieval.search` 的 `top_k` 使用 integer，不使用 number；
- SimpleEmbeddingModel 不允许使用随机向量；
- Retrieval Test 必须能解释召回失败原因。

## 9. 面试主线

Tool 框架可这样讲：

> 我先实现了一套标准 Tool Calling 框架，把工具定义、注册、调用请求、执行结果和异常包装统一起来。Agent 不直接依赖具体工具，只依赖 ToolExecutor 和 Tool 接口。Retrieval、MCP、SQL、HTTP API 都可以作为 Tool 注册进来。

文档解析可这样讲：

> 我在 RAG 链路里单独抽象了 Parser 层，用 `RawDocument` 表示原始文件输入，用 `DocumentParser` 定义统一解析接口，再通过 `DocumentParserRegistry` 按扩展名分发到 Markdown、PDF 或 Word 解析器。这样 Chunker 和 Retriever 永远只处理标准 `Document`，不会和具体文件格式耦合。

Chunk 切分可这样讲：

> Parser 只负责把不同文件格式转成标准 Document，Chunker 只负责把 Document 切成带 metadata 的 Chunk。Chunker 支持 overlap，通过 `chunk_size - overlap` 控制下一块起点，避免答案跨 chunk 边界时丢上下文。

向量索引可这样讲：

> 我先实现了一个确定性的 `SimpleEmbeddingModel`，用词袋和词频构造稀疏向量，避免随机向量导致测试不可复现。`InMemoryChunkIndex` 只保存 Chunk 和预计算 embedding，并提供关键词召回与向量召回两种基础能力；混合融合、重排和引用构造会放在后续独立模块里，避免索引层承担过多职责。

混合召回可这样讲：

> `HybridRetriever` 负责把关键词召回和向量召回按 `chunk_id` 合并，再用可配置权重计算统一 `final_score`。`SimpleReranker` 第一版只按已有分数做稳定重排，并写入 `rerank_score` 字段；`CitationBuilder` 单独负责把召回结果转换为带 source、title、snippet 和 score 的引用数据。这样召回、重排和引用构造可以分别替换，不会互相耦合。

RetrievalTool 可这样讲：

> 最后我把检索链路封装成标准 `retrieval.search` Tool。Tool 层只负责参数 schema、默认值、边界校验和结果格式化，真正的召回、重排和引用构造仍然由 Retriever、Reranker、CitationBuilder 各自负责。这样 Agent 只需要通过 `ToolExecutor` 调用工具，不需要知道知识库内部是怎么检索和排序的。

RAG Trace 与评估可这样讲：

> 在检索闭环之后，我补了 `RagTrace` 和 `RetrievalEvaluator`。Trace 记录每次检索的 query、召回 chunks、citations 和耗时；Evaluator 用 `RetrievalTestCase` 表达期望命中的文档和关键词，再输出 hit、missing_doc_ids、top_chunks 和 failure_reasons。这样当 RAG 没召回对时，不只是知道失败，还能定位是文档没命中、关键词没覆盖、分数全低、引用缺失，还是知识库本身没有答案。

Agentic RAG 可这样讲：

> RAG 链路参考 RAGFlow 的分层思路，但做了轻量化实现。底层拆成 Parser、Document、Chunker、Embedding、Index、Retriever、Reranker、Citation 和 Eval。Retrieval 被封装成 `retrieval.search` Tool，因此 Agent 主流程不需要关心知识库内部怎么检索，后续替换解析器、向量库或模型也不会影响 Agent Runtime。

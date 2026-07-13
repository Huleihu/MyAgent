# 项目交接文档

## 1. 项目目标

本项目用于实现一个简化版 Agent Runtime 与 Agentic RAG 能力，帮助面试时说明以下经历：

```text
1. 基于 JSON DSL 的轻量级 Agent Runtime；
2. Agentic RAG 链路，Retrieval 作为 Agent 可调用 Tool；
3. ReAct / Plan-and-Execute 风格 Agent Loop 与标准 Tool Calling；
4. State、Memory、Checkpoint、Trace 与 Agent Eval 数据基础。
```

### 1.0 简历目标对齐与当前差距

当前开发应围绕以下四条简历描述推进。每一阶段都优先补齐真实可演示能力，避免为了简历关键词提前堆空架构。

#### 目标一：JSON DSL Agent Runtime

简历描述：

```text
参考 RAGFlow Agent Canvas 设计，实现基于 JSON DSL 的轻量级 Agent Runtime，
支持节点编排、变量引用、组件输入输出映射、多节点协同执行，以及对话触发模式。
```

当前完成：

- 已有 JSON DSL Runtime v0.1；
- 已支持 `begin -> agent_loop -> message` 线性节点编排；
- 已有最小变量引用：`{{user_input}}` 和 `{{node_id.output_key}}`；
- 已通过 `RuntimeContext.node_outputs` 保存组件输出；
- 已通过 `RuntimeContext.node_traces` 保存节点级执行 Trace；
- `agent_loop` 节点通过依赖注入调用已有 `ReActAgentLoop`。

主要缺口：

- 变量引用还很弱，只支持精确引用，不支持输入默认值、变量命名空间或错误定位；
- 对话触发模式已支持同一进程内复用会话状态的最小连续多轮，但不支持持久化恢复或并发；
- 多节点协同当前已有线性顺序执行和节点级执行记录，但还没有分支、循环或并发；
- 暂不支持分支、循环、并发和可视化 Canvas，但这些不是下一步优先级。

建议下一步：

- 后续可考虑把 `ConversationRuntime` 作为 CLI、Web API 或 Canvas 的统一触发入口；
- 暂不为单进程最小多轮引入 Memory、持久化恢复或并发会话管理。

#### 目标二：Agentic RAG Tool

简历描述：

```text
实现 Agentic RAG 链路，将 Retrieval 封装为 Agent 可调用 Tool，
支持文档 Chunk 切分、Embedding 建库、关键词与向量混合召回、Rerank 接口、
引用溯源和 Retrieval Test，提升知识库问答的相关性与可信度。
```

当前完成：

- 已实现 Markdown Parser、`TextChunker`、`MarkdownStructureChunker`、`SimpleEmbeddingModel`、`InMemoryChunkIndex`；
- 已实现关键词召回、向量召回、`HybridRetriever`、`SimpleReranker`、`CitationBuilder`；
- 已封装 `retrieval.search` 为标准 Tool；
- 已有 `RagTrace`、`RetrievalEvaluator` 和失败原因解释。

主要缺口：

- Markdown 结构切分已覆盖标题、段落、列表和代码块；表格、复杂 HTML、MDX 等扩展语法仍按原文 `OTHER` 块处理；
- Embedding 仍是确定性词袋模型，不是真实 embedding 适配器；
- Reranker 当前是接口占位式简单重排，还没有真实 rerank 服务适配；
- Index 仍是内存实现，还没有外部向量库适配；
- RAG Trace 还没有细化到 parse、chunk、embed、retrieve、rerank、citation 多阶段。

建议下一步：

- 在 Runtime Trace 后，再增强 RAG 多阶段 Trace 或真实 Embedding 适配器；
- 暂不急着接真实向量库，先保持测试稳定和链路可讲清楚。

#### 目标三：Agent Loop、Tool Calling 与 Plan-and-Execute

简历描述：

```text
设计 Agent Loop 与标准化 Tool Calling 框架，参考 ReAct 思想实现
“工具选择—工具调用—结果观察—下一步决策”的循环执行，并结合 Plan-and-Execute
支持任务拆解、步骤规划、失败重试、反思修正和 MCP 扩展。
```

当前完成：

- 已有标准化 Tool Calling 框架：ToolDefinition、ToolRegistry、ToolExecutor、ToolCallResult；
- 已有多轮 `ReActAgentLoop`，支持 ToolAction、工具执行、observation、FinalAnswerAction；
- 已有 `LLMPlanner` 与 `ModelClient` 抽象，真实模型 SDK 尚未接入；
- 工具调用 Trace 已由 `ToolExecutor + TraceRecorder` 写入 Session。

主要缺口：

- Plan-and-Execute 还没有独立计划模型，例如任务拆解、步骤列表、步骤状态；
- 失败重试当前没有策略对象，工具失败只作为 observation 返回；
- 反思修正还没有独立动作或 Planner 协议；
- MCP 扩展尚未实现，目前只有本地 Tool 抽象和 FunctionTool；
- 真实 LLM SDK 适配器尚未实现。

建议下一步：

- 在 Runtime Trace 稳住之后，新增轻量 Plan-and-Execute 数据模型与 Planner；
- 失败重试先做简单策略，例如最大重试次数和可重试错误类型；
- MCP 适配等本地 Tool + Runtime + Trace 跑通后再接。

#### 目标四：State、Memory、Checkpoint、Trace 与 Eval 数据

简历描述：

```text
构建 State、Memory、Checkpoint 与 Trace 追踪模块，记录节点执行路径、
工具调用结果、异常、耗时和 Token 消耗，支持上下文恢复、多轮连续对话
与 Human-in-the-loop，并为 Agent Eval 提供链路数据依据。
```

当前完成：

- 已有 `SessionState` 保存消息和工具调用 Trace；
- 已有 `ToolTraceRecord` 记录工具名、参数、结果、错误、耗时；
- 已有 `Checkpoint` 和 `CheckpointRecorder` 保存内存快照；
- Agent Loop 已可选接入 checkpoint；
- RAG Eval 已有检索测试与失败原因解释。
- 已有确定性 Runtime Eval MVP，可校验最终输出、节点路径和工具调用序列。

主要缺口：

- 已实现 Runtime 节点级 Trace，可记录节点执行路径、解析后的输入、输出、异常和耗时；
- `token_usage` 字段存在但当前没有真实 LLM token 来源；
- Memory 尚未实现；
- Checkpoint 仍是内存快照，不支持持久化和恢复；
- Human-in-the-loop 暂停、审批、恢复尚未实现；
- 已具备确定性 Runtime Eval MVP；尚未覆盖真实 LLM、语义等价判断、指标聚合和评估报告。

建议下一步：

- 第一优先级是把现有 `ConversationRuntime` 接入 CLI、Web API 或 Canvas 演示入口；
- 第二优先级是增强 RAG 的结构感知 Chunker 或多阶段 Trace；
- Memory、持久化恢复和 Human-in-the-loop 放到 Trace 基础稳定之后。

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
16. JSON DSL Runtime v0.1，支持 begin -> agent_loop -> message 线性流程。
17. Runtime 节点级 Trace，记录节点输入、输出、异常和耗时。
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
第五阶段：JSON DSL Runtime v0.1 已完成，当前支持 begin -> agent_loop -> message、节点级 Trace、输入输出映射校验和最小连续多轮对话触发
```

说明：

- 当前项目没有单独的 `core/models.py`，Tool 数据模型集中在 `tools/schema.py`，异常在 `core/errors.py`，抽象接口在 `core/interfaces.py`；
- 当前已经有 `my_agent/rag/evaluation/trace.py` 和 `my_agent/rag/evaluation/eval.py`，它们只服务于 RAG 检索评估；
- 第三阶段的 `state/trace.py` 和 `state/session.py` 应作为全局 Agent Runtime 的执行记录与会话状态模块，不应直接复用或混淆 RAG 专用 Trace；
- 下一步如果继续按最终目标推进，建议在 JSON DSL Runtime v0.1 基础上补充 Runtime Eval 数据结构或真实模型适配器。

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
    markdown_blocks.py
    markdown_it_block_parser.py
    markdown_chunker.py
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
- `TextChunker` 不解析 Markdown / PDF / Word；`MarkdownStructureChunker` 只通过可注入的块解析协议理解已标准化的 Markdown 内容，不负责原始文件格式识别；
- Chunker 不做 Embedding；
- Chunker 不写索引。

### 2.9.1 MarkdownStructureChunker 结构感知切分

文件：

```text
my_agent/rag/indexing/markdown_blocks.py
my_agent/rag/indexing/markdown_it_block_parser.py
my_agent/rag/indexing/markdown_chunker.py
tests/test_markdown_it_block_parser.py
tests/test_markdown_structure_chunker.py
```

实现链路：

```text
markdown-it-py
        |
        v
MarkdownItBlockParser
        |
        v
MarkdownBlock
        |
        v
MarkdownStructureChunker
        |
        v
Chunk
```

设计与边界：

- 使用 `markdown-it-py` 识别 CommonMark 块级语法；它只在 `MarkdownItBlockParser` 中出现，第三方 Token 不会扩散到 RAG 核心；
- `MarkdownBlock`、`Heading` 与 `MarkdownBlockParser` 是轻量内部模型和协议，适配器负责把 Token 与原文行范围转换为项目模型；
- `MarkdownStructureChunker` 只依赖 `MarkdownBlockParser` 协议，负责按标题路径组合和回退切分，不理解第三方 Token，也不负责 Embedding、索引或检索；
- 第一版支持标题路径、段落、完整列表、fenced / 缩进代码块；未专门支持的块保留原文并标记为 `OTHER`，不承诺表格、复杂 HTML 或 MDX 的语义切分；
- Parser 的 `start_offset` / `end_offset` 使用原始 `Document.content` 的左闭右开字符区间，块内容满足 `content[start_offset:end_offset] == block.content`；最终 Chunk 的 offset 仅描述正文来源，因为其内容可能额外带有标题前缀；
- `chunk_size` 限制最终 `Chunk.content`，包含标题前缀和分隔换行。常规块保持完整；仅超长块使用 overlap 回退。超长列表第一版按字符回退，超长 fenced code 尽量按行切分并为每块补全围栏；
- 当标题上下文过长时，只保留最靠近正文的标题并截断标题文本，至少留出一个正文字符，避免负容量、空 Chunk 和死循环；
- 原 `TextChunker` 保持不变，可继续用于纯文本或固定字符切分场景。

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

### 2.18 JSON DSL Runtime v0.1

文件：

```text
my_agent/dsl/__init__.py
my_agent/dsl/schema.py
my_agent/dsl/loader.py
my_agent/runtime/__init__.py
my_agent/runtime/context.py
my_agent/runtime/graph.py
my_agent/runtime/resolver.py
my_agent/runtime/trace.py
my_agent/runtime/node_runner.py
my_agent/runtime/executor.py
tests/test_dsl_runtime.py
```

完成：

- `WorkflowDefinition`
- `NodeDefinition`
- `EdgeDefinition`
- `NodeContract`
- `WorkflowLoader`
- `RuntimeGraph`
- `RuntimeContext`
- `NodeExecutionRecord`
- `BeginNodeRunner`
- `AgentLoopNodeRunner`
- `MessageNodeRunner`
- `RuntimeExecutor`

JSON DSL v0.1 支持：

- 只支持 `begin`、`agent_loop`、`message` 三类节点；
- 只支持单入口、单出口、无分支的线性拓扑；
- 支持 `{{user_input}}` 和 `{{node_id.output_key}}` 这种最小精确引用；
- 节点契约集中声明：`begin` 无 DSL 输入并输出 `user_input`，`agent_loop` 必填 `user_input` 并输出 `output`，`message` 必填 `content` 并输出 `content`；
- Loader 在加载阶段校验完整连通性、节点必填输入和未声明输入，并校验引用节点、引用输出字段及前序执行顺序；
- 完整引用允许去除外围空白；普通字符串中的花括号保持字面量，不支持模板插值；
- `agent_loop` 节点通过 `AgentLoopNodeRunner` 构造参数注入已有 `ReActAgentLoop`；
- `RuntimeExecutor` 只负责按 `RuntimeGraph.linear_nodes()` 调度节点执行器，并统一写入 `RuntimeContext.node_outputs` 和 `RuntimeContext.node_traces`；
- 节点级 Trace 记录解析后的 `inputs`、`output`、`success`、结构化 `error` 和 `duration_ms`；
- 节点失败时 Runtime 会先记录失败 Trace，再继续抛出原始异常。

边界：

- `dsl/schema.py` 只定义 DSL 数据模型和静态节点契约，不依赖 Runtime；
- `dsl/loader.py` 只负责加载、线性拓扑和静态 DSL 校验；
- `runtime/graph.py` 只负责线性拓扑；
- `runtime/context.py` 只保存 `user_input`、`variables`、`node_outputs`、`node_traces` 和 `session_state`；
- `runtime/resolver.py` 只负责解析运行时输入引用；
- `runtime/trace.py` 只定义 Runtime 节点级执行记录；
- `runtime/node_runner.py` 只实现 v0.1 三类节点的执行，不解析输入、不写 `node_outputs` 或 `node_traces`；
- `runtime/executor.py` 不直接依赖 `ToolExecutor`、RAG、LLM SDK 或具体 Agent Loop 实现，只负责解析输入、调度 runner、写输出和写 Trace；
- 当前不实现 `tool_call`、`switch`、`loop`、并发、恢复或复杂变量表达式；
- 当前 Runtime Trace 不包含 `token_usage`、`checkpoint_id`、`session_id`、`traceback`、`retry_count`、LLM 信息或 ToolTrace 信息；
- Tool Call 仍然发生在 `ReActAgentLoop` 内部，由 Planner / LLMPlanner 产生 `ToolAction`，再交给 `ToolExecutor` 执行。

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
TextChunker / MarkdownStructureChunker
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
conda run -n myagent-py311 python -m unittest discover -s tests -v
```

最近一次完整测试结果：

```text
Ran 138 tests in 0.006s
OK
```

说明：

- Codex 当前默认 `python` 曾显示为 Python 3.7.4，项目级 VS Code 配置已指向 `myagent-py311`；
- 用户已经在本地激活 `myagent-py311` 并确认 requirements 已安装；
- 后续建议直接使用 `myagent-py311` 的 `python.exe` 运行测试，避免 `conda run` 启动开销。

## 6. 可维护性与后续增强建议

当前 Chunker 和 Embedding 都是第一版 MVP，实现刻意保持简单，便于测试和面试演示。后续增强时应继续保持“输入输出契约稳定、实现可替换”的方向，避免把语义切分、真实模型调用、索引存储和 Agent Tool 适配混在一起。

### 6.1 Chunker 增强

`TextChunker` 继续提供固定字符切分，优点是确定、简单、容易测试。`MarkdownStructureChunker` 已补充标题、段落、列表和代码块感知切分，两者通过相同的 `Document -> Chunk` 调用契约并存。

后续增强建议：

- 保持 `split(document) -> list[Chunk]` 和 `split_many(documents) -> list[Chunk]` 这两个调用契约；
- 继续保持两种 Chunker 的职责独立，不让结构切分影响纯文本固定切分；
- 后续若需要表格、MDX 或 HTML 的语义边界，再为 `MarkdownItBlockParser` 小步增加块类型支持；
- `MarkdownStructureChunker` 的 Chunk metadata 已保留 `source`、`title`、`chunk_index`，并补充 `heading_path`、`start_offset`、`end_offset`；
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
3. MarkdownStructureChunker
4. EmbeddingModel / ChunkIndex 轻量协议
5. 真实 Embedding 适配器或外部向量库适配器
```

## 7. 下一阶段计划

当前第四阶段的多轮 ReAct Agent Loop、Checkpoint 接入和 LLMPlanner MVP 已完成。第五阶段 JSON DSL Runtime v0.1 已完成，当前只支持 `begin -> agent_loop -> message` 线性流程，并已具备节点级 Runtime Trace。

结合当前简历目标，Runtime 已具备节点级 Trace、输入输出映射、变量引用校验、最小连续多轮对话触发和 Runtime Eval MVP；RAG 已具备 Markdown 结构感知 Chunker。下一步不要急着扩展 `tool_call`、switch、loop 或并发，可优先把 `ConversationRuntime` 接入演示入口，或补充真实 Embedding 适配器与 RAG 多阶段 Trace。

### 7.1 已完成：Runtime 节点级 Trace

已新增或修改文件：

```text
my_agent/runtime/trace.py
my_agent/runtime/context.py
my_agent/runtime/resolver.py
my_agent/runtime/node_runner.py
my_agent/runtime/executor.py
tests/test_dsl_runtime.py
docs/project-handoff.md
```

完成内容：

- 新增 `NodeExecutionRecord`，记录 `node_id`、`node_type`、`inputs`、`output`、`error`、`success`、`duration_ms`；
- `RuntimeContext` 增加 `node_traces`，保存节点执行路径；
- `RuntimeExecutor` 在每个节点执行前后记录 trace；
- 节点成功和失败都要记录，失败时保留原始异常上下文；
- `RuntimeExecutor` 统一负责解析 inputs、调用 runner、写 `node_outputs` 和写 `node_traces`；
- `NodeRunner` 统一接收解析后的 inputs，只负责执行节点逻辑并返回 output；
- `runtime/resolver.py` 负责 `{{user_input}}` 和 `{{node_id.output_key}}` 的运行时引用解析；
- 不把 RAG 专用 `RagTrace` 混进 Runtime Trace；
- 不让 Runtime Trace 直接依赖 ToolExecutor、LLM SDK 或具体 RAG 类型。

已验证：

- `begin -> agent_loop -> message` 三个节点都会生成 `NodeExecutionRecord`；
- Trace 记录解析后的 inputs，而不是原始 DSL 表达式；
- 失败节点会记录 `success=False` 和结构化错误，并继续抛出原始异常；
- `RuntimeExecutor` 仍然只负责任务调度，不直接依赖 ToolExecutor、RAG、LLM SDK；
- 完整 unittest 通过。

### 7.2 已完成：输入输出映射与变量引用校验

推荐新增或修改文件：

```text
my_agent/dsl/schema.py
my_agent/dsl/loader.py
my_agent/runtime/node_runner.py
tests/test_dsl_runtime.py
docs/project-handoff.md
```

目标：

- 新增不可变 `NodeContract` 和只读节点契约表，声明每类节点的 `required_inputs`、`allowed_inputs`、`fixed_outputs`；
- Loader 先校验结构、唯一入口/出口和完整连通性，再取得线性执行顺序并校验节点契约和输入引用；
- 对缺失输入、未声明输入、引用不存在节点、引用不存在输出字段、引用后序节点和不支持引用格式给出可定位错误；
- 只支持完整的 `{{user_input}}` 和 `{{node_id.output_key}}`，不实现模板插值或通用表达式语言；
- Runner 删除必填输入的静默回退，合法 DSL 的执行行为保持不变；
- 新增 DSL Runtime 覆盖测试后，完整 unittest 通过（138 项）。

### 7.3 已完成：对话触发模式

推荐新增或修改文件：

```text
my_agent/runtime/conversation.py
tests/test_runtime_conversation.py
docs/project-handoff.md
```

目标：

- 新增 `ConversationRuntime`，持有并复用 `SessionState`，每轮创建独立 `RuntimeContext`；
- `chat(user_input)` 触发 `RuntimeExecutor.run(context)`，返回 `ConversationTurnResult`；
- 回合结果返回最终文本、当前 Context、节点 Trace 快照和当前轮新增工具 Trace 快照；
- 明确 `last_message` 是最终输出的前置约定，缺失或不是非空字符串时给出明确 `ValueError`；
- 连续多轮可复用消息历史，且第一版只支持同一实例串行调用，不保证线程安全；
- 不做持久化恢复、Memory、多用户会话、并发、Human-in-the-loop 或 Checkpoint 恢复。

### 7.4 已完成：Runtime Eval MVP

已新增文件：

```text
my_agent/runtime/eval_models.py
my_agent/runtime/evaluator.py
tests/test_runtime_eval.py
```

完成内容：

- `RuntimeEvalCase` 定义单轮固定用例的用户输入、严格最终文本、节点路径和工具调用期望；
- `RuntimeEvaluator.evaluate(case)` 通过工厂创建独立 `ConversationRuntime`，执行单个用例；
- `RuntimeEvaluator.evaluate_many(cases)` 保持输入顺序，且单个用例创建或执行失败不会中断后续用例；
- Runtime 正常完成后，分别检查最终输出、节点路径和工具调用序列，并收集全部不匹配项；
- 工具调用第一版只严格检查顺序、工具名和成功状态，不检查参数或完整返回结果；
- Runtime 创建或执行抛出普通 `Exception` 时，返回 `runtime_execution` 失败项，包含异常类型和消息；
- 期望路径、期望工具调用、失败项、实际路径和实际工具调用均保存为 tuple 快照；
- `ConversationTurnResult` 仅作为可选调试引用保留，其中包含可变 `RuntimeContext`，因此 `RuntimeEvalResult` 不承诺深度不可变。

评估定位与边界：

- Runtime Eval MVP 只用于基于 Fake Planner、Fake ModelClient 和确定性工具的执行回归评估；
- `output_text` 使用严格字符串相等，目的是验证确定性链路，不用于判断真实 LLM 的语义等价性；
- 不增加 Matcher DSL、关键词匹配、LLM-as-a-judge、真实 LLM 评估、多轮 Eval、报告落盘、CLI 或指标聚合；
- 不修改 `RuntimeExecutor`、`ConversationRuntime`、`ReActAgentLoop`、Tool、RAG 或现有 Trace 数据模型。

已验证：

- 通过用例会同时确认严格输出、节点路径和工具调用序列；
- 三项断言不匹配时会一次返回全部失败项；
- Runtime 异常会转换为明确的 `runtime_execution` 失败项；
- 多用例评估保持输入顺序，每个用例恰好调用一次工厂，并且 SessionState、Planner 状态和工具 Trace 不泄漏。

### 7.5 已完成：MarkdownStructureChunker MVP

已按 `markdown-it-py -> MarkdownItBlockParser -> MarkdownBlock -> MarkdownStructureChunker -> Chunk`
实现结构感知切分。适配器将第三方 Token 收敛为项目内部 `MarkdownBlock`，Chunker 只依赖
`MarkdownBlockParser` 协议，因此测试可注入 Fake Parser，未来替换解析实现也不影响 RAG 核心。

已支持标题路径、段落、完整列表、fenced / 缩进代码块和原文保留的 `OTHER` 块；正常块不跨章节且优先完整保留。
最终 `Chunk.content` 带 Markdown 标题上下文，`chunk_size` 包含该上下文；metadata 提供可序列化的
`heading_path`、`start_offset`、`end_offset` 和连续 `chunk_index`。超长段落与 `OTHER` 块按字符回退，
超长列表当前也按字符回退，超长 fenced code 尽量按行切分并补全围栏。

已知限制：第一版不提供表格、复杂 HTML、MDX 的语义切分；超长列表不保证按列表项边界切开；Chunk 的 offset
只描述源正文范围，不包含合成的标题前缀。

### 7.6 后续候选方向

- RAG 增强：真实 Embedding 适配器、真实 Rerank 适配器、RAG 多阶段 Trace；
- Plan-and-Execute：任务拆解模型、步骤状态、失败重试、反思修正；
- State 增强：Checkpoint 持久化、从 checkpoint 恢复；
- Memory：先做简单内存记忆接口，再考虑检索式 Memory；
- MCP 扩展：等本地 Tool、Runtime Trace 和 Plan-and-Execute 稳定后再接。

暂缓事项：

- 暂不做 Memory；
- 暂不做 Checkpoint 持久化和自动恢复；
- 暂不做 Human-in-the-loop 暂停恢复；
- 暂不做 `tool_call` 节点，工具调用仍由 ReActAgentLoop 内部处理；
- 暂不做 switch、loop、并发和复杂变量表达式；
- 暂不做复杂节点执行路径 Trace，等 Agent Loop MVP 跑通后再细化；
- 暂不把 RAG 专用 `RagTrace` 合并进全局 Trace，避免混淆评估 Trace 与 Runtime Trace。

RAG 后续增强建议：

- 继续使用 `TextChunker` 或 `MarkdownStructureChunker`，按文档类型选择固定字符或结构感知切分；
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

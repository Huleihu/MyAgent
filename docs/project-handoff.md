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
8. RetrievalTool 工具适配。
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
my_agent/rag/document.py
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
my_agent/rag/parser.py
my_agent/rag/markdown_parser.py
my_agent/rag/parser_registry.py
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
my_agent/rag/chunker.py
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
my_agent/rag/embedding.py
my_agent/rag/index.py
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
my_agent/rag/retriever.py
my_agent/rag/reranker.py
my_agent/rag/citation.py
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
my_agent/rag/retrieval_tool.py
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
```

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
```

当前 RetrievalTool 工具适配代码已完成，建议提交信息：

```text
新增RetrievalTool工具适配
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
Ran 59 tests in 0.003s
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

Agentic RAG 后续按以下粒度推进：

```text
1. RAG 数据模型：已完成
2. 文档解析 Parser：已完成
3. Chunk 切分：已完成
4. Chunk 向量化与内存向量索引：已完成
5. 混合召回、重排和引用构造：已完成
6. RetrievalTool：已完成
7. RAG Trace 与 Retrieval Test：下一步
```

下一步建议实现：

```text
my_agent/rag/trace.py
my_agent/rag/eval.py
tests/test_rag_eval.py
```

下一步目标：

- 定义 `RagTrace` 记录 query、retrieved_chunks、citations 和 duration_ms；
- 定义 `RetrievalTestCase` 表达 query、expected_doc_ids、expected_chunk_keywords 和 top_k；
- 定义 `RetrievalEvalResult` 返回 hit、matched_doc_ids、missing_doc_ids、top_chunks 和 trace；
- `RetrievalEvaluator` 通过 RetrievalTool 或 Retriever 执行测试；
- 评估失败时能解释关键词召回、向量召回、融合分数、重排和引用构造中的问题位置。

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

Agentic RAG 可这样讲：

> RAG 链路参考 RAGFlow 的分层思路，但做了轻量化实现。底层拆成 Parser、Document、Chunker、Embedding、Index、Retriever、Reranker、Citation 和 Eval。Retrieval 被封装成 `retrieval.search` Tool，因此 Agent 主流程不需要关心知识库内部怎么检索，后续替换解析器、向量库或模型也不会影响 Agent Runtime。

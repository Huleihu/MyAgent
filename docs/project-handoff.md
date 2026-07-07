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
4. Markdown 文档解析与 ParserRegistry。
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

RAG 解析链：

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
```

## 4. 当前提交历史

```text
d8f2aef 新增工具调用数据模型与异常
081ce9e 新增工具抽象接口与开发环境配置
b2a4fa0 新增工具注册表
7dfcf0a 新增函数工具包装器
5005229 新增工具执行器
f6a77de 新增Agentic RAG设计文档与数据模型
```

当前 Parser 代码还未提交，建议提交信息：

```text
新增Markdown文档解析器
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
Ran 35 tests in 0.002s
OK
```

说明：

- Codex 当前默认 `python` 曾显示为 Python 3.7.4；
- 用户已经在本地激活 `myagent-py311` 并确认 requirements 已安装；
- 后续建议用户在 `myagent-py311` 环境中运行测试。

## 6. 下一阶段计划

Agentic RAG 后续按以下粒度推进：

```text
1. RAG 数据模型：已完成
2. 文档解析 Parser：当前完成，待提交
3. Chunk 切分
4. 确定性 Embedding 与内存索引
5. 混合召回、重排和引用构造
6. RetrievalTool
7. RAG Trace 与 Retrieval Test
```

下一步建议实现：

```text
my_agent/rag/chunker.py
tests/test_rag_chunker.py
```

Chunker 目标：

- 输入 `Document`；
- 输出 `Chunk`；
- 支持 `chunk_size` 和 `overlap`；
- `Chunk.metadata` 继承 `Document.metadata`；
- 补充 `source`、`title`、`chunk_index`。

## 7. 开发约束

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
- `retrieval.search` 的 `top_k` 使用 integer，不使用 number；
- SimpleEmbeddingModel 不允许使用随机向量；
- Retrieval Test 必须能解释召回失败原因。

## 8. 面试主线

Tool 框架可这样讲：

> 我先实现了一套标准 Tool Calling 框架，把工具定义、注册、调用请求、执行结果和异常包装统一起来。Agent 不直接依赖具体工具，只依赖 ToolExecutor 和 Tool 接口。Retrieval、MCP、SQL、HTTP API 都可以作为 Tool 注册进来。

文档解析可这样讲：

> 我在 RAG 链路里单独抽象了 Parser 层，用 `RawDocument` 表示原始文件输入，用 `DocumentParser` 定义统一解析接口，再通过 `DocumentParserRegistry` 按扩展名分发到 Markdown、PDF 或 Word 解析器。这样 Chunker 和 Retriever 永远只处理标准 `Document`，不会和具体文件格式耦合。

Agentic RAG 可这样讲：

> RAG 链路参考 RAGFlow 的分层思路，但做了轻量化实现。底层拆成 Parser、Document、Chunker、Embedding、Index、Retriever、Reranker、Citation 和 Eval。Retrieval 被封装成 `retrieval.search` Tool，因此 Agent 主流程不需要关心知识库内部怎么检索，后续替换解析器、向量库或模型也不会影响 Agent Runtime。

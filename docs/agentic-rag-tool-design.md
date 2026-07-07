# Agentic RAG Tool 开发文档

## 1. 目标

本阶段实现一个轻量级 Agentic RAG 链路，并将 Retrieval 封装成现有 Tool Calling 框架可调用的标准工具。

第一版目标不是复刻完整 RAGFlow，而是参考其分层思路，完成一个可测试、可演示、可扩展的最小闭环：

```text
RawDocument -> Parser -> Document -> Chunk -> Embedding/Index -> Hybrid Retriever -> Rerank -> Citation -> RetrievalTool
```

核心要求：

- 文档和 Chunk 保留 metadata，便于后续接入 PDF、Word、Markdown；
- 文档解析先支持 Markdown，但解析器接口必须方便扩展 PDF、Word、HTML 等格式；
- Embedding 必须是确定性的，不能使用随机向量；
- 支持关键词与向量混合召回；
- 支持 Rerank 扩展接口；
- 支持引用溯源；
- 支持 Retrieval Test 和 RAG Trace，便于排查检索不准的问题；
- Retrieval 最终以 `retrieval.search` Tool 形式接入 `ToolRegistry` 和 `ToolExecutor`。

## 2. 参考 RAGFlow 的设计取舍

RAGFlow 的 RAG 链路大致分为：

```text
文档解析 / Chunk
        |
检索器 Retriever
        |
关键词 + 向量混合召回
        |
Rerank
        |
引用溯源 / 格式化
        |
Agent Tool
```

RAGFlow 中 `agent/tools/retrieval.py` 将 Retrieval 暴露为 Agent 可调用工具，参数包含 query、top_k、top_n、similarity_threshold、keywords_similarity_weight、rerank_id、metadata_filter、kb_ids 等。

本项目第一版只保留核心能力：

- Markdown 文档解析；
- 标准 Document 数据模型；
- 字符或词级 Chunk；
- 确定性词袋 Embedding；
- 内存索引；
- keyword_score + vector_score 融合；
- 简单 Rerank；
- Citation；
- RetrievalTool；
- RAG Trace 和 Retrieval Test。

暂不实现：

- PDF / Word / HTML 的真实解析；
- 真实 Embedding 模型；
- 外部向量数据库；
- 真实 Rerank 服务；
- 多知识库权限；
- metadata filter 的复杂表达式；
- KG 检索。

## 3. 模块划分

计划新增目录：

```text
my_agent/
  rag/
    __init__.py
    document.py
    parser.py
    markdown_parser.py
    parser_registry.py
    chunker.py
    embedding.py
    index.py
    retriever.py
    reranker.py
    citation.py
    retrieval_tool.py
    trace.py
    eval.py

tests/
  test_rag_document.py
  test_rag_parser.py
  test_rag_chunker.py
  test_rag_index.py
  test_rag_retriever.py
  test_retrieval_tool.py
  test_rag_eval.py
```

## 4. 分步实现计划

### 第 1 步：RAG 数据模型

文件：

```text
my_agent/rag/document.py
tests/test_rag_document.py
```

定义：

```text
Document
Chunk
RetrievedChunk
Citation
```

字段：

```text
Document:
  doc_id: str
  title: str
  source: str
  content: str
  metadata: dict[str, Any]

Chunk:
  chunk_id: str
  doc_id: str
  content: str
  index: int
  metadata: dict[str, Any]

RetrievedChunk:
  chunk: Chunk
  keyword_score: float
  vector_score: float
  final_score: float
  rerank_score: float | None

Citation:
  doc_id: str
  chunk_id: str
  source: str
  title: str
  snippet: str
  score: float
  metadata: dict[str, Any]
```

metadata 建议保留：

```text
source
page
section
filename
created_at
tags
```

边界：

- 数据模型不负责文件解析；
- 数据模型不负责切分；
- 数据模型不负责检索；
- 数据模型只做必要字段校验。

### 第 2 步：文档解析 Parser

文件：

```text
my_agent/rag/parser.py
my_agent/rag/markdown_parser.py
my_agent/rag/parser_registry.py
tests/test_rag_parser.py
```

定义：

```text
RawDocument
DocumentParser
MarkdownDocumentParser
DocumentParserRegistry
```

`RawDocument` 字段：

```text
source: str
filename: str
content: str | bytes
metadata: dict[str, Any]
```

`DocumentParser` 抽象接口：

```text
supported_extensions: tuple[str, ...]
parse(raw_document: RawDocument) -> list[Document]
```

为什么 `parse()` 返回 `list[Document]`：

- Markdown 第一版通常是一个文件解析成一个 Document；
- PDF 后续可能按页、章节或目录解析成多个 Document；
- 返回 list 可以避免以后扩展 PDF、Word 时修改接口。

Markdown 解析规则：

- 支持 `.md` 和 `.markdown`；
- 从第一个一级标题 `# title` 提取 `Document.title`；
- 没有一级标题时，使用 `RawDocument.filename` 作为 title；
- 第一版不做复杂 Markdown AST 解析，只保留可检索文本；
- `Document.source` 来自 `RawDocument.source`；
- `Document.metadata` 合并原始 metadata，并补充：
  - `source`
  - `filename`
  - `extension`
  - `parser`
  - `title`
  - `headings`

ParserRegistry 行为：

```text
register(parser)
get_parser(filename)
parse(raw_document)
```

扩展 PDF 时只需要新增：

```text
my_agent/rag/pdf_parser.py
```

并实现同一个接口：

```text
PdfDocumentParser(DocumentParser)
  supported_extensions = (".pdf",)
  parse(raw_document) -> list[Document]
```

主链路保持不变：

```text
RawDocument
  -> DocumentParserRegistry
  -> DocumentParser
  -> list[Document]
  -> TextChunker
```

测试要求：

- MarkdownParser 能解析 `.md` 内容为 Document；
- 能从一级标题提取 title；
- 没有一级标题时使用 filename 作为 title；
- metadata 会保留 source、filename、extension、parser、headings；
- ParserRegistry 能按 `.md` 和 `.markdown` 找到 MarkdownParser；
- 不支持的扩展名会抛出明确异常。

边界：

- Parser 只负责把不同文件格式转成标准 `Document`；
- Parser 不负责 Chunk 切分；
- Parser 不负责 Embedding；
- Parser 不调用 ToolExecutor。

### 第 3 步：Chunk 切分

文件：

```text
my_agent/rag/chunker.py
tests/test_rag_chunker.py
```

实现：

```text
TextChunker
  chunk_size: int
  overlap: int
  split(document: Document) -> list[Chunk]
  split_many(documents: list[Document]) -> list[Chunk]
```

规则：

- 第一版按字符长度切分；
- 支持 overlap；
- `chunk_id` 可以使用 `{doc_id}:{index}`；
- `Chunk.metadata` 继承 `Document.metadata`；
- `Chunk.metadata` 补充 `source`、`title`、`chunk_index`。

边界：

- 不做文件读取；
- 不做 Markdown / PDF / Word 解析；
- 不做 Embedding。

### 第 4 步：确定性 Embedding 与内存索引

文件：

```text
my_agent/rag/embedding.py
my_agent/rag/index.py
tests/test_rag_index.py
```

实现：

```text
SimpleEmbeddingModel
  tokenize(text: str) -> list[str]
  embed(text: str) -> dict[str, float]
  cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float

InMemoryChunkIndex
  add_chunks(chunks: list[Chunk]) -> None
  keyword_search(query: str, top_k: int) -> list[RetrievedChunk]
  vector_search(query: str, top_k: int) -> list[RetrievedChunk]
```

Embedding 规则：

- 不能使用随机向量；
- 第一版使用确定性词袋；
- 英文按单词分词；
- 中文可按单字或 2-gram；
- 统一转小写；
- 用词频构造稀疏向量；
- 使用 cosine similarity。

边界：

- 不依赖真实模型；
- 不引入外部向量数据库；
- 保留后续替换 Embedding 和 Index 的接口边界。

### 第 5 步：Hybrid Retriever、Rerank 与 Citation

文件：

```text
my_agent/rag/retriever.py
my_agent/rag/reranker.py
my_agent/rag/citation.py
tests/test_rag_retriever.py
```

实现：

```text
HybridRetriever
  retrieve(query: str, top_k: int) -> list[RetrievedChunk]

SimpleReranker
  rerank(query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]

CitationBuilder
  build(retrieved_chunks: list[RetrievedChunk]) -> list[Citation]
```

混合分数：

```text
final_score = keyword_weight * keyword_score + vector_weight * vector_score
```

默认权重：

```text
keyword_weight = 0.4
vector_weight = 0.6
```

边界：

- Retriever 负责召回和融合；
- Reranker 只负责重排；
- CitationBuilder 只负责引用数据转换；
- 不在这些模块中调用 ToolExecutor。

### 第 6 步：RetrievalTool

文件：

```text
my_agent/rag/retrieval_tool.py
tests/test_retrieval_tool.py
```

实现标准 Tool：

```text
RetrievalTool(Tool)
  definition.name = "retrieval.search"
  run(arguments) -> dict
```

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

返回结构：

```python
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

接入方式：

```text
RetrievalTool
  -> ToolRegistry.register()
  -> ToolExecutor.execute(ToolCallRequest(name="retrieval.search", ...))
  -> ToolCallResult
```

### 第 7 步：RAG Trace 与 Retrieval Test

文件：

```text
my_agent/rag/trace.py
my_agent/rag/eval.py
tests/test_rag_eval.py
```

定义：

```text
RagTrace
RetrievalTestCase
RetrievalEvalResult
RetrievalEvaluator
```

Trace 记录：

```text
query
retrieved_chunks
keyword_score
vector_score
final_score
rerank_score
citations
duration_ms
```

Retrieval Test 输入：

```text
query
expected_doc_ids
expected_chunk_keywords
top_k
```

Retrieval Test 输出：

```text
hit
matched_doc_ids
missing_doc_ids
top_chunks
trace
```

排查问题时的解释路径：

```text
1. keyword_score 全低：关键词召回失败或 query 表达不匹配；
2. vector_score 全低：Embedding 表达能力不足或 chunk 切分不合适；
3. final_score 排序异常：融合权重不合适；
4. rerank_score 排序异常：Rerank 策略需要调整；
5. citations 缺失：引用构造或 metadata 传递有问题；
6. 所有召回都不相关：知识库本身可能没有答案。
```

## 5. 最终演示目标

最终应能写出如下调用链：

```python
raw_document = RawDocument(
    source="local://agentic-rag.md",
    filename="agentic-rag.md",
    content="# Agentic RAG 介绍\n\nAgentic RAG 会把检索能力封装为工具，由 Agent 按需调用。",
    metadata={"tags": ["rag", "agent"]},
)

parser_registry = DocumentParserRegistry()
parser_registry.register(MarkdownDocumentParser())
documents = parser_registry.parse(raw_document)

chunks = TextChunker(chunk_size=100, overlap=20).split_many(documents)
index = InMemoryChunkIndex(SimpleEmbeddingModel())
index.add_chunks(chunks)

retriever = HybridRetriever(index=index)
tool = RetrievalTool(retriever=retriever)

registry = ToolRegistry()
registry.register(tool)

result = ToolExecutor(registry).execute(
    ToolCallRequest(
        name="retrieval.search",
        arguments={"query": "Agentic RAG 如何调用检索？", "top_k": 3},
    )
)
```

预期结果：

```text
result.success = True
result.data["chunks"] 包含相关 chunk
result.data["citations"] 包含 source、chunk_id、snippet、score
```

## 6. 面试讲法

可以这样描述：

> 我参考 RAGFlow 的分层设计，把 RAG 拆成文档解析、数据模型、Chunk 切分、确定性 Embedding、内存索引、关键词与向量混合召回、Rerank、引用溯源和 Retrieval Test。解析层先支持 Markdown，但通过 DocumentParser 抽象和 ParserRegistry 保留了扩展 PDF、Word、HTML 的入口。Retrieval 最终被封装成标准 Tool，Agent 只通过 ToolExecutor 调用 `retrieval.search`，不依赖具体文件格式、向量库或 Embedding 实现。这样后续替换真实解析器、Embedding、向量数据库、Rerank 服务时，只需要替换对应适配层，不影响 Agent 主流程。

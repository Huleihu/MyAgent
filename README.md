# MyAgent

MyAgent 是一个用于演示确定性 Agent 工作流、RAG 检索与运行时可观测性的实验项目。项目提供 Python Runtime 与 FastAPI 服务，并配套一个 Next.js 开发者控制台，用于查看多轮对话、Citation、Node Trace、Tool Trace 和 Retrieval Trace。

## 核心能力

- 确定性 Agent Runtime、工具调用与会话隔离。
- 内存索引 RAG：文档入库与查询链路职责分离。
- 多阶段在线检索 Trace：`retrieve → rerank → citation`。
- FastAPI 会话 API：创建会话并发送多轮消息。
- Next.js 可观测性控制台：展示聊天回答、引用和当前或历史回合的调试信息。
- 前端 BFF 代理：浏览器仅请求相对路径 `/api/...`，Python 服务地址仅保留在服务端环境变量中。

## 项目结构

```text
my_agent/
  rag/            # 文档入库、检索、重排、引用、Trace 与评估
  runtime/        # Agent Runtime 与会话回合执行
  state/          # Session、Runtime Node Trace、Tool Trace 等状态模型
  web/            # FastAPI API、内存会话存储与确定性 Demo Runtime
frontend/
  app/            # Next.js App Router 页面与 BFF Route Handler
  components/     # 聊天、引用、会话与 Trace 面板
  lib/            # API Client、类型与格式化工具
  stores/         # 浏览器本地会话目录与回合状态
  tests/          # Vitest 与 React Testing Library 测试
tests/            # Python unittest 测试
docs/             # 设计、交接与开发文档
```

## 快速开始

### 环境要求

- Python Conda 环境：`myagent-py311`
- Node.js 与 npm

### 启动 Python 后端

在项目根目录执行：

```powershell
conda run -n myagent-py311 uvicorn my_agent.web.app:app --reload --port 8000
```

健康检查地址：<http://127.0.0.1:8000/health>

### 一键启动与停止本地开发服务

在项目根目录执行以下命令即可启动 Python 后端与 Next.js 前端。脚本只清除其自身和子进程的代理变量，不会修改系统代理或 `.env`：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1
```

也可以直接双击项目根目录的 `start-dev.cmd`。脚本会优先使用 `MYAGENT_PYTHON` 指定的解释器，再尝试查找名为 `myagent-py311` 的 Conda 环境。

默认会打开 <http://localhost:3000>。如不希望打开浏览器，附加 `-NoBrowser`；如当前终端未激活项目 Python 环境，可通过 `-PythonExecutable` 指定解释器路径。停止两个开发服务：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-dev.ps1
```

也可以直接双击项目根目录的 `stop-dev.cmd` 停止服务。

### 启动前端控制台

另开一个终端：

```powershell
cd frontend
Copy-Item .env.example .env.local
npm.cmd install
npm.cmd run dev
```

打开 <http://localhost:3000>。

`frontend/.env.local` 的默认配置如下：

```env
AGENT_API_BASE_URL=http://127.0.0.1:8000
```

该变量只由 Next.js 服务端 BFF 使用，不会暴露给浏览器。前端通过 `/api/sessions` 和 `/api/sessions/{sessionId}/messages` 请求，再由 BFF 转发到 Python API。

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 服务健康检查 |
| `POST` | `/sessions` | 创建内存会话，返回 `session_id` |
| `POST` | `/sessions/{session_id}/messages` | 发送用户消息并返回当前回合结果与 Trace |

发送消息示例：

```json
{
  "user_input": "介绍项目中的 RAG 检索流程"
}
```

消息响应包含以下主要字段：

- `session_id`：当前会话标识。
- `output_text`：Agent 最终回答。
- `citations`：仅属于当前回合的引用。
- `node_traces`：Runtime Node Trace。
- `tool_traces`：工具执行 Trace；检索工具的 `result.retrieval_trace` 包含内部检索阶段信息。

## RAG 与 Retrieval Trace

文档入库与查询保持分离：

```text
入库：Document → Parser → Chunker → Embedding → Index
查询：Query → Retriever → Reranker → Citation
```

一次成功的 `retrieval.search` 会记录在线查询的三个阶段：

```text
用户 Query
  → HybridRetriever（retrieve）
  → SimpleReranker（rerank）
  → CitationBuilder（citation）
  → RetrievalTool 返回结果与 retrieval_trace
```

`RetrievalTrace` 记录 query、`top_k`、各阶段 Chunk 摘要与数量、阶段耗时和总耗时。Chunk 摘要只保存稳定的 `chunk_id`、`doc_id`、排名和分数；不会保存正文、snippet、完整 metadata 或 embedding。

前端右侧面板从当前选中的 `ChatTurn` 读取 Citation、Node Trace 和 Tool Trace，并在任意 Tool Trace 的 `result.retrieval_trace` 中查找 Retrieval Trace。因此，历史回合与不同 session 的调试数据不会混用。

## 测试与构建

### Python

```powershell
conda run -n myagent-py311 python -m unittest discover -s tests -v
```

### 前端

```powershell
cd frontend
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run test
npm.cmd run build
```

## 当前限制

- 当前 RAG 使用确定性的内存索引，未接入真实 LLM、数据库或外部向量库。
- Retrieval Trace MVP 覆盖成功与无命中查询；阶段异常通过外层 Tool Trace 的错误信息定位。
- 前端会话目录与聊天回合仅保存在浏览器本地，不提供服务端持久化或用户认证。
- `retrieval_trace` 当前会随检索工具结果进入 Agent observation。接入真实 LLM 前，建议将业务结果与遥测数据进一步分离。

## 更多文档

- [项目交接与设计说明](docs/project-handoff.md)
- [前端说明](frontend/README.md)
# DeepSeek Provider MVP

默认不设置 `MYAGENT_LLM_PROVIDER` 时，Web Demo 继续使用离线、确定性的 `DemoRagPlanner`，不会访问模型服务。

如需启用 DeepSeek，可先复制模板：`Copy-Item .env.example .env`。随后将其中变量设置到后端进程环境中，并填写本地 `DEEPSEEK_API_KEY`；不要将 `.env` 或真实密钥提交到 Git。默认模型为 `deepseek-v4-flash`，地址为 `https://api.deepseek.com`。

```powershell
$env:MYAGENT_LLM_PROVIDER="deepseek"
$env:DEEPSEEK_API_KEY="在本机设置的密钥"
$env:MYAGENT_LLM_MODEL="deepseek-v4-flash"
& 'D:\software\Anaconda\envs\myagent-py311\python.exe' -m uvicorn my_agent.web.app:app --reload
```

当前 MVP 固定关闭 Thinking，并且每轮只支持一个工具调用。自动化测试注入 Fake SDK，不会调用 DeepSeek 或产生费用。可选真实冒烟测试仅应在本地设置密钥后，手动启动后端并发送一次聊天请求。

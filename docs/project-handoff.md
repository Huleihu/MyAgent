# 项目交接文档

## 1. 项目目标

本项目用于实现一个简化版 Agent Runtime 与 Agentic RAG 能力，帮助面试时说明以下经历：

```text
1. 基于 JSON DSL 的轻量级 Agent Runtime；
2. Agentic RAG 链路，Retrieval 作为 Agent 可调用 Tool；
3. ReAct / Plan-and-Execute 风格 Agent Loop 与标准 Tool Calling；
4. State、Memory、Checkpoint、Trace 与 Agent Eval 数据基础。
```

当前阶段已经完成第一块基础能力：**Tool Calling 框架 MVP**。

## 2. 当前已完成内容

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

## 3. 当前调用链

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

最小使用示例：

```python
from my_agent.tools.executor import ToolExecutor
from my_agent.tools.function_tool import FunctionTool
from my_agent.tools.registry import ToolRegistry
from my_agent.tools.schema import ToolCallRequest

tool = FunctionTool(
    name="calculator.add",
    description="计算两个数字之和",
    parameters={
        "type": "object",
        "properties": {
            "a": {"type": "number"},
            "b": {"type": "number"},
        },
        "required": ["a", "b"],
    },
    func=lambda arguments: {"result": arguments["a"] + arguments["b"]},
    tags=("math",),
)

registry = ToolRegistry()
registry.register(tool)

result = ToolExecutor(registry).execute(
    ToolCallRequest(
        name="calculator.add",
        arguments={"a": 1, "b": 2},
        call_id="call-001",
    )
)
```

## 4. 当前提交历史

```text
d8f2aef 新增工具调用数据模型与异常
081ce9e 新增工具抽象接口与开发环境配置
b2a4fa0 新增工具注册表
7dfcf0a 新增函数工具包装器
5005229 新增工具执行器
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
Ran 23 tests in 0.001s
OK
```

说明：

- Codex 当前默认 `python` 曾显示为 Python 3.7.4；
- 用户已经在本地激活 `myagent-py311` 并确认 requirements 已安装；
- 后续建议用户在 `myagent-py311` 环境中运行测试。

## 6. 下一阶段计划

下一阶段实现 Agentic RAG Tool。

推荐按以下提交粒度推进：

```text
1. 新增 RAG 数据模型
2. 新增文本 Chunk 切分器
3. 新增确定性 Embedding 与内存索引
4. 新增混合召回、重排和引用构造
5. 新增 RetrievalTool
6. 新增 RAG Trace 与 Retrieval Test
```

对应设计文档：

```text
docs/agentic-rag-tool-design.md
```

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
- `retrieval.search` 的 `top_k` 使用 integer，不使用 number；
- SimpleEmbeddingModel 不允许使用随机向量；
- Retrieval Test 必须能解释召回失败原因。

## 8. 面试主线

Tool 框架可这样讲：

> 我先实现了一套标准 Tool Calling 框架，把工具定义、注册、调用请求、执行结果和异常包装统一起来。Agent 不直接依赖具体工具，只依赖 ToolExecutor 和 Tool 接口。Retrieval、MCP、SQL、HTTP API 都可以作为 Tool 注册进来。

Agentic RAG 可这样讲：

> RAG 链路参考 RAGFlow 的分层思路，但做了轻量化实现。底层拆成 Document、Chunker、Embedding、Index、Retriever、Reranker、Citation 和 Eval。Retrieval 被封装成 `retrieval.search` Tool，因此 Agent 主流程不需要关心知识库内部怎么检索，后续替换向量库或模型也不会影响 Agent Runtime。

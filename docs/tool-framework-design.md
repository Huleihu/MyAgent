# Tool Calling 框架开发文档

## 1. 目标

本阶段实现一个轻量级 Tool Calling 框架，为后续 Agentic RAG、ReAct Agent Loop、JSON DSL Runtime 和 Trace 追踪提供统一工具调用基础。

第一版只关注工具调用协议层，不接真实大模型、不接真实 MCP、不实现复杂权限系统。

核心目标：

- 支持工具注册、查找和工具定义导出；
- 支持 OpenAI function calling 兼容的工具参数 schema；
- 支持标准化工具调用请求和执行结果；
- 支持结构化错误返回，方便 Trace、Eval 和前端展示；
- 支持最小参数校验、异常捕获和耗时记录；
- 支持普通 Python 函数包装为 Tool，便于测试和演示。

## 2. 设计原则

- Agent 不直接依赖具体工具实现，只依赖统一 Tool 接口；
- ToolRegistry 只负责注册和查找，不负责执行；
- ToolExecutor 是工具执行边界，负责校验、调用、异常包装和耗时记录；
- 具体工具内部逻辑不得泄漏到 Agent Loop 或 DSL Runtime；
- 第一版只做必要能力，不引入完整 JSON Schema 校验器，不提前设计复杂权限和异步调度。

## 3. 模块划分

计划新增目录：

```text
my_agent/
  core/
    __init__.py
    errors.py
    interfaces.py

  tools/
    __init__.py
    schema.py
    registry.py
    executor.py
    function_tool.py

tests/
  test_tool_framework.py
```

### 3.1 core/interfaces.py

职责：

- 定义核心协议，不放具体实现；
- 为工具、后续 LLM、Embedding、Memory 等能力提供扩展边界。

第一版只定义 `Tool` 协议：

```python
class Tool(Protocol):
    @property
    def definition(self) -> ToolDefinition:
        ...

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        ...
```

后续扩展：

- `RetrievalTool` 实现 `Tool`；
- `MCPToolAdapter` 实现 `Tool`；
- `SQLTool`、`HTTPTool`、`FunctionTool` 都实现 `Tool`。

### 3.2 core/errors.py

职责：

- 定义 Tool 框架内部使用的统一异常；
- ToolExecutor 捕获这些异常后转换为结构化错误。

第一版异常：

```text
ToolError               工具异常基类
ToolNotFoundError       工具不存在
ToolAlreadyExistsError  工具重复注册
ToolValidationError     工具参数或定义校验失败
ToolExecutionError      工具执行失败
```

### 3.3 tools/schema.py

职责：

- 定义工具调用相关数据模型；
- 作为 Agent Loop、DSL Runtime、Trace 模块之间的公共数据契约。

核心模型：

```text
ToolDefinition
ToolCallRequest
ToolCallResult
```

`ToolDefinition` 字段：

```text
name: str
description: str
parameters: dict[str, Any]
tags: tuple[str, ...]
```

约束：

- `name` 必须非空；
- `description` 必须非空；
- `parameters` 必须是 JSON Schema object schema；
- `tags` 用于后续按场景筛选工具。

`parameters` 第一版强制至少满足：

```json
{
  "type": "object",
  "properties": {
    "a": {"type": "number"},
    "b": {"type": "number"}
  },
  "required": ["a", "b"]
}
```

最小校验规则：

- `parameters["type"]` 必须等于 `"object"`；
- `parameters["properties"]` 必须存在且为 `dict`；
- `parameters["required"]` 如果存在，必须是 `list[str]`；
- `required` 中的字段必须出现在 `properties` 中。

`ToolCallRequest` 字段：

```text
name: str
arguments: dict[str, Any]
call_id: str | None
```

约束：

- `name` 必须非空；
- `arguments` 必须是 dict；
- `call_id` 用于后续 Trace 和多工具调用关联。

`ToolCallResult` 字段：

```text
name: str
success: bool
data: dict[str, Any] | None
error: dict[str, str] | None
duration_ms: float
call_id: str | None
```

注意：`error` 不使用字符串，第一版就使用结构化对象。

错误结构：

```json
{
  "type": "ToolValidationError",
  "message": "Missing required arguments: a, b"
}
```

约束：

- `success=True` 时，`data` 必须是 dict，`error` 必须为 `None`；
- `success=False` 时，`error` 必须包含 `type` 和 `message`；
- `duration_ms` 由 ToolExecutor 统一写入。

### 3.4 tools/registry.py

职责：

- 管理运行时可用工具；
- 提供工具注册、查找和定义导出；
- 不执行工具。

核心接口：

```text
register(tool)
get(name)
list_definitions(tags=None)
```

行为：

- 注册同名工具时抛出 `ToolAlreadyExistsError`；
- 查找不存在工具时抛出 `ToolNotFoundError`；
- `list_definitions()` 返回所有工具定义；
- `list_definitions(tags=("rag",))` 返回包含对应 tag 的工具定义。

### 3.5 tools/executor.py

职责：

- 作为工具执行边界；
- 统一完成工具查找、参数校验、执行、异常包装和耗时记录。

执行流程：

```text
1. 接收 ToolCallRequest；
2. 根据 request.name 从 ToolRegistry 查找工具；
3. 校验 request.arguments 是否满足 ToolDefinition.parameters 的 required；
4. 记录开始时间；
5. 调用 tool.run(arguments)；
6. 校验工具返回值必须是 dict；
7. 成功时返回 ToolCallResult(success=True, data=...)；
8. 失败时返回 ToolCallResult(success=False, error={type, message})；
9. 无论成功失败都写入 duration_ms。
```

第一版只做轻量参数校验：

- `arguments` 必须是 dict；
- `required` 字段必须存在；
- 不校验 number/string/object 等完整 JSON Schema 类型。

这样避免过度设计，同时保留后续替换为完整 JSON Schema 校验器的扩展点。

### 3.6 tools/function_tool.py

职责：

- 把普通 Python 函数包装成 Tool；
- 用于单元测试、示例和简单工具扩展。

使用方式：

```python
tool = FunctionTool(
    name="calculator.add",
    description="计算两个数字之和",
    parameters={
        "type": "object",
        "properties": {
            "a": {"type": "number"},
            "b": {"type": "number"}
        },
        "required": ["a", "b"]
    },
    func=lambda arguments: {"result": arguments["a"] + arguments["b"]},
    tags=("math",)
)
```

## 4. 调用链路

标准链路：

```text
具体工具 FunctionTool / RetrievalTool / MCPToolAdapter
        |
        v
ToolRegistry.register(tool)
        |
        v
Agent Loop 或 DSL Runtime 构造 ToolCallRequest
        |
        v
ToolExecutor.execute(request)
        |
        v
ToolCallResult
```

模型侧链路：

```text
ToolRegistry.list_definitions()
        |
        v
转换为 LLM 可识别的 function/tool schema
        |
        v
模型选择工具并生成参数
        |
        v
Runtime 执行 ToolCallRequest
```

关键边界：

- 模型只看到 `ToolDefinition`；
- 模型只负责选择工具和生成参数；
- Runtime 负责真实执行、校验、异常处理和 Trace。

## 5. 与 RAGFlow 设计的对应关系

RAGFlow 中工具大致由以下部分协作：

- `ToolParamBase.get_meta()`：生成 function/tool schema；
- `ToolBase.invoke()` / `invoke_async()`：执行具体工具；
- `LLMToolPluginCallSession`：接收模型 tool call 并分发执行；
- Agent 组件：收集普通工具和 MCP 工具，然后绑定到模型。

本项目简化映射：

```text
ToolDefinition       -> RAGFlow 的 get_meta()
Tool.run()           -> RAGFlow 的 invoke()
ToolRegistry         -> RAGFlow 的 tools_map
ToolExecutor         -> RAGFlow 的 LLMToolPluginCallSession
FunctionTool         -> 本项目用于测试和演示的轻量工具包装
```

差异：

- RAGFlow 的 Tool 深度嵌入 Agent Canvas；
- 本项目第一版让 Tool 框架独立存在；
- 后续 JSON DSL Runtime 再通过 ToolExecutor 调用工具。

## 6. 测试计划

第一版测试集中在 `tests/test_tool_framework.py`：

1. 注册工具后可以通过 registry 获取工具定义；
2. 重复注册同名工具会抛出 `ToolAlreadyExistsError`；
3. 查找不存在工具会抛出 `ToolNotFoundError`；
4. `parameters` 不是 object schema 时会抛出 `ToolValidationError`；
5. `required` 字段不存在于 `properties` 时会抛出 `ToolValidationError`；
6. 正常工具调用返回 `success=True` 和 `data`；
7. 缺少 required 参数返回 `success=False`，并返回结构化 `ToolValidationError`；
8. 工具内部抛异常时返回 `success=False`，并返回结构化 `ToolExecutionError`；
9. 工具返回非 dict 时返回 `success=False`；
10. `ToolCallResult.duration_ms` 会被写入，且大于等于 0。

## 7. 后续扩展点

### 7.1 Agentic RAG Tool

新增：

```text
my_agent/rag/retrieval/retrieval_tool.py
```

实现：

```text
definition.name = "retrieval.search"
definition.parameters = object schema
run(arguments) -> {"chunks": [...], "citations": [...]}
```

### 7.2 ReAct Agent Loop

Agent Loop 不直接调用具体工具，只构造：

```text
ToolCallRequest(name=..., arguments=...)
```

然后交给：

```text
ToolExecutor.execute(request)
```

### 7.3 JSON DSL Runtime

Tool 节点只需要从节点配置中读取：

```text
tool_name
input_mapping
output_mapping
```

然后调用 ToolExecutor。

### 7.4 MCP 扩展

新增：

```text
tools/mcp_adapter.py
```

让 MCP 工具适配为同一个 `Tool` 协议。

## 8. 暂不实现内容

第一版明确不实现：

- 真实 LLM 调用；
- 真实 MCP 网络连接；
- 完整 JSON Schema 校验；
- 工具权限系统；
- 异步并发执行；
- Human-in-the-loop 审批；
- 持久化 Trace。

这些能力会在 Tool 框架稳定后按模块逐步接入。

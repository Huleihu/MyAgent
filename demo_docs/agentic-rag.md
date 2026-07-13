# Agentic RAG

Agentic RAG 把知识检索封装为 `retrieval.search` 标准工具。Agent Loop 可以先发起工具调用，
再根据工具返回的文档片段和 Citation 形成最终回答。检索结果包含 Chunk、相关性分数和来源信息，
因此回答能够追溯到演示知识库中的具体文档。

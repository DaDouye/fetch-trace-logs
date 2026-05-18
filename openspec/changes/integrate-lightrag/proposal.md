## Why

当前 JIRA 问题分析主要依赖预定义规则匹配和 Claude AI 的能力，但缺乏对历史问题、代码库上下文和 trace 模式的系统性检索增强。引入 LightRAG 可以通过向量检索提供相关的历史案例、代码位置和 trace 模式，作为 AI 分析的上下文补充，提升问题定位的准确性。

## What Changes

- **新增 LightRAG 索引模块** (`api/analyzer/lightrag_indexer.py`)
  - 支持对 JIRA 问题、Trace 数据和代码库进行增量索引
  - 使用 minimaxi embedding API 进行向量嵌入
  - 本地文件系统存储 (`./lightrag_data`)
  - 服务重启时可重建索引

- **增强 AI 分析流程**
  - 在 AI 分析前先通过 LightRAG 检索相关上下文
  - 将检索结果注入 Claude prompt，提升分析质量

- **索引数据结构**
  - JIRA 问题索引：summary、description、customfield_19900、keywords
  - Trace 索引：SQL 语句、API paths、错误模式
  - 代码库索引：Java 文件（Controller、Service、DAO 等）

## Capabilities

### New Capabilities

- `lightrag-indexer`: 增量索引 JIRA 问题、Trace 日志和代码库
- `rag-enhanced-ai-analysis`: 基于 LightRAG 上下文增强的 AI 问题分析

## Impact

- **新增依赖**: `lightrag` (PyPI 包)
- **存储**: `./lightrag_data` 目录存放向量索引
- **Embedding**: minimaxi embedding API
- **影响模块**: `api/analyzer/jira_analyzer.py` (AI 分析增强)
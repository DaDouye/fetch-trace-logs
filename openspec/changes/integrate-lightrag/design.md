## Context

当前 JIRA 分析系统包含三个主要组件：

1. **规则引擎** (`rule_engine.py`) - 预定义模式匹配技术错误
2. **代码搜索** (`code_search.py`) - 基于关键词搜索代码文件
3. **Claude AI 分析** (`ai_analyzer.py`) - 使用 minimaxi proxy 调用 Claude 进行问题分析

现有 AI 分析的局限：
- AI 仅基于当前 JIRA 内容和代码搜索结果进行分析
- 缺乏对历史相似问题的检索能力
- 无法利用 trace 日志中的模式匹配经验
- 代码搜索仅基于精确关键词匹配，无法语义检索

**约束条件：**
- 使用 minimaxi API 作为 embedding 服务
- 索引数据存储在本地文件系统 `./lightrag_data`
- 服务重启时可重建索引（索引非持久化要求）
- minimaxi API 需要通过 proxy 访问，SSL 证书验证需跳过

## Goals / Non-Goals

**Goals:**
- 引入 LightRAG 向量检索增强 AI 分析上下文
- 支持 JIRA 问题、Trace 数据、代码库的增量索引
- 通过语义检索找到相关的历史问题和代码模式
- 提升 AI 问题定位的准确性

**Non-Goals:**
- 图关系建模（暂时不需要）
- 索引持久化到数据库
- 替换现有的 Claude AI 分析
- 完整的知识图谱构建

## Decisions

### Decision 1: LightRAG Library Selection

**选择:** `lightrag` (PyPI 简化版)

**原因:**
- 用户明确表示不需要图关系
- 简化版更轻量、配置少
- 适合快速集成

**替代方案考虑:**
- `lightrag-hku`: 功能更全但复杂，对当前需求过度设计
- 自建向量检索: 工作量大，不必要

### Decision 2: Embedding API

**选择:** minimaxi embedding API

**原因:**
- 复用现有的 minimaxi Claude API 代理
- 统一认证方式（API Key 已配置在 .env）
- 与 Claude 模型在同一平台，延迟更低

**调用方式:**
- 需要找到 minimaxi embedding 的实际 endpoint
- 目前已知 Claude endpoint: `https://api.minimaxi.com/anthropic/v1/messages`
- embedding endpoint 可能类似: `https://api.minimaxi.com/embedding/v1` 或类似

### Decision 3: Storage Location

**选择:** `./lightrag_data` 本地文件系统

**原因:**
- 用户明确选择
- 实现简单，无需额外服务
- 服务重启可重建

**权衡:**
- 每次重启需重建索引（可接受）
- 多实例部署无法共享索引（当前为单机服务，无问题）

### Decision 4: Indexing Strategy

**选择:** 实时增量索引

**原因:**
- JIRA 分析完成即索引，不遗漏
- Trace 数据获取后即索引
- 代码搜索结果自动索引

**触发时机:**
- `use_ai=true` 分析完成后，索引当前 JIRA 内容
- Trace fetch 成功后，索引 trace 数据
- 代码搜索完成后，索引相关代码文件

## Risks / Trade-offs

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| minimaxi embedding API 不支持或格式不同 | 无法进行 embedding | 预留 OpenAI/HuggingFace 作为 fallback |
| 索引数据过大 | 占用过多磁盘空间 | 定期清理或限制索引总量 |
| 服务重启重建索引慢 | 首次分析延迟高 | 提供手动预热接口 |
| embedding 延迟高 | 整体分析变慢 | 异步索引，不阻塞主流程 |

## Open Questions

1. **minimaxi embedding API**
   - 实际的 API endpoint 是什么？
   - 请求/响应格式是什么？
   - 需要验证

2. **lightrag 库细节**
   - 具体 API 用法需查看文档
   - 与 minimaxi embedding 的兼容性需测试

3. **索引容量管理**
   - 是否需要限制单个索引类型的最大文档数？
   - 清理策略是什么？

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    LightRAG Integration Architecture                     │
└─────────────────────────────────────────────────────────────────────────┘

  DATA FLOW:
  ═════════

  ┌─────────────┐     ┌─────────────────┐     ┌─────────────────────────┐
  │ JIRA Issue  │────▶│  LightRAG       │────▶│  Vector Store           │
  │   Content   │     │  Indexer        │     │  (./lightrag_data)      │
  └─────────────┘     └─────────────────┘     └─────────────────────────┘
                              ▲
                              │
  ┌─────────────┐     ┌───────┴─────────┐
  │ Trace Data  │────▶│  Extract API    │
  │             │     │  paths, SQL     │
  └─────────────┘     └─────────────────┘

  QUERY FLOW:
  ══════════

  ┌─────────────┐     ┌─────────────────┐     ┌─────────────────────────┐
  │ User Query  │────▶│  LightRAG       │────▶│  Retrieve top-k         │
  │ (JIRA URL)  │     │  Query          │     │  Similar docs           │
  └─────────────┘     └─────────────────┘     └───────────┬─────────────┘
                                                          │
                                                          ▼
                                                ┌─────────────────────────┐
                                                │  Enhanced Claude        │
                                                │  Prompt + RAG Context   │
                                                └─────────────────────────┘

  FILES:
  ═════
  api/analyzer/lightrag_indexer.py   - LightRAG 索引和检索核心
  api/analyzer/rag_enhanced_ai.py    - RAG 增强的 AI 分析器
  .env                               - 新增 MINIMAXI_EMBEDDING_API_URL
  ./lightrag_data/                   - 向量索引存储目录
```
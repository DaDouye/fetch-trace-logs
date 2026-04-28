## Context

当前系统架构：
```
Frontend (Vue 3) → API Server (FastAPI) → JavaCallChainAnalyzer
         │                    │
    AnalyzerForm        POST /api/analyze
    (Repo + API必填)    (repo_key + api_path)
```

目标架构：
```
Frontend (Vue 3) → API Server (FastAPI) → 多分析器
         │                    │
    JiraAnalysisForm    POST /api/analyze-jira
    (JIRA URL 必填)     (jira_url + 可选 repo_key/api_path/trace_id)
```

## Goals / Non-Goals

**Goals:**
- JIRA URL 作为唯一必填项
- 支持 4 种分析组合（见输入/输出矩阵）
- 保留原有调用链分析作为辅助能力
- 规则匹配 + 可选 AI 增强的问题原因分析

**Non-Goals:**
- 不修改现有 `POST /api/analyze` 接口（保持向后兼容）
- 不做 JIRA 写操作（只读取）
- AI 增强作为可选模块，不强制依赖

## Decisions

### 1. 后端新增接口 vs 复用现有接口

| 方案 | 优点 | 缺点 |
|------|------|------|
| A. 新增 `POST /api/analyze-jira` | 职责单一，复杂度低 | 接口数量增加 |
| B. 扩展现有 `/api/analyze` | 无需新接口 | 逻辑混杂，参数校验复杂 |

**选择方案 A**：新增独立接口，原有调用链分析保持不变。

### 2. JIRA 内容获取

复用 `scripts/fetch_jira_souche.py` 中的逻辑，或抽取为独立模块：

```python
# api/jira_client.py
class JiraClient:
    def __init__(self, base_url: str, username: str, password: str)
    def get_issue(self, issue_key: str) -> dict  # 返回问题详情
    def get_comments(self, issue_key: str) -> list
    def get_attachments(self, issue_key: str) -> list
```

### 3. 输入/输出矩阵（后端）

| jira_url | repo_key | api_path | trace_id | 结果 |
|----------|----------|----------|----------|------|
| ✅ | - | - | - | 只返回 JIRA 内容 |
| ✅ | ✅ | - | - | JIRA + 扫描代码库 + 原因分析 |
| ✅ | ✅ | ✅ | - | JIRA + 调用链 + 代码上下文 + 原因分析 |
| ✅ | ✅ | - | ✅ | JIRA + 扫描代码库 + 链路数据 + 原因分析 |
| ✅ | ✅ | ✅ | ✅ | 全部功能 |
| ✅ | - | ✅ | - | 返回错误：需要提供 Repo |
| ✅ | - | - | ✅ | JIRA + 链路数据 + 原因分析 |

### 4. 问题原因分析策略

```
JIRA 内容提取
     │
     ├── 关键词提取（接口名、类名、错误码）
     │         │
     │         ▼
     │   代码搜索（基于 Repo）
     │         │
     │         ▼
     │   链路数据（如果有 Trace ID）
     │         │
     └─────────┼─────────┐
               │         │
               ▼         ▼
        规则引擎      AI 增强（可选）
        匹配         大模型分析
               │         │
               └────┬────┘
                    ▼
               原因分析结果
```

规则匹配模式（YAML 配置）：
```yaml
rules:
  - pattern: "NullPointerException"
    category: "空指针"
    keywords: ["null", "NPE", "空对象"]
    suggestion: "检查对象是否为空"

  - pattern: "SQLException"
    category: "数据库异常"
    keywords: ["sql", "数据库", "连接"]
    suggestion: "检查数据库连接和 SQL 语句"
```

### 5. 代码搜索策略

当无 API Path 但有 Repo 时：
1. 从 JIRA 摘要/描述中提取关键词
2. 在代码库中搜索匹配的 Java 文件
3. 返回匹配的文件列表及上下文

```python
def search_codebase(repo_path: str, keywords: list) -> list:
    """搜索代码库返回匹配结果"""
    results = []
    for keyword in keywords:
        for java_file in Path(repo_path).rglob("*.java"):
            if keyword in java_file.read_text():
                results.append({
                    "file": str(java_file),
                    "keyword": keyword,
                    "matches": [...]  # 匹配的行
                })
    return results
```

### 6. 前端组件变更

```
frontend/src/
├── components/
│   ├── AnalyzerForm.vue      # 重构：JiraAnalysisForm
│   ├── JiraAnalysisView.vue   # 新增：JIRA 分析结果视图
│   ├── TreeView.vue           # 保留（辅助展示）
│   ├── AsciiView.vue          # 保留（辅助展示）
│   └── GraphView.vue          # 保留（辅助展示）
├── stores/
│   └── analyzer.js            # 重构：支持新接口
└── api/
    └── index.js               # 新增 analyzeJira API
```

### 7. API 设计

**POST /api/analyze-jira**

Request:
```json
{
  "jira_url": "https://jira.souche-inc.com/browse/PROJ-123",
  "repo_key": "super_mario",      // optional
  "api_path": "/v1/customer/save", // optional
  "trace_id": "xxx",              // optional
  "trace_date": "2026-04-27",    // optional
  "cookies": "JSESSIONID=xxx",   // optional
  "use_ai": false                // optional, default false
}
```

Response:
```json
{
  "jira": {
    "key": "PROJ-123",
    "summary": "用户无法保存订单",
    "description": "...",
    "comments": [...],
    "status": "Open"
  },
  "code_context": {
    "files": [...],
    "call_chain": {...}  // 如果提供了 api_path
  },
  "trace_data": {...},   // 如果提供了 trace_id
  "analysis": {
    "possible_causes": [
      {"category": "空指针", "evidence": "...", "suggestion": "..."}
    ],
    "ai_enhanced": false
  }
}
```

## Risks / Trade-offs

- [Risk] JIRA 关键词提取可能不准确
  → Mitigation：提供多种提取策略（正则、NLP 简化版），支持配置
- [Risk] 代码库搜索在大仓库中可能慢
  → Mitigation：限制搜索范围（只看 web/src/main/java），超时控制
- [Trade-off] AI 增强可选 vs 规则匹配准确性
  → 选择：先用规则匹配，AI 作为可选增强，用户自行决定是否开启

## Open Questions

1. JIRA 认证方式？当前是用户名+密码，是否支持 Token？
2. AI 增强具体调用哪个 LLM 接口？
3. 是否需要缓存 JIRA 内容（避免重复请求）？

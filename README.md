
# Fetch Trace Logs & RAG Analysis System

## 项目概述

这是一个综合性的 Java 接口调用链分析系统，包含以下核心功能：

1. **API 调用链分析**：基于 Git 仓库代码分析 Java 接口的调用链
2. **链路追踪集成**：从 Souche 链路追踪系统获取运行时数据
3. **可视化展示**：提供树形视图、ASCII 视图和图形视图多种展示方式
4. **RAG 知识库**（可选）：基于 Git 仓库和日志文件的 RAG 知识库分析

## 功能特点

### JIRA 问题分析
- 输入 JIRA URL 自动获取问题详情
- 基于规则匹配的问题原因分析
- 可选 AI 增强分析
- 代码库搜索定位相关代码
- 调用链分析集成（当提供 API Path 时）
- 链路追踪数据集成（当提供 Trace ID 时）

### API 调用链分析
- 输入 API 路径（如 `/v1/customerAction/saveOrUpdateCustomer`）
- 自动扫描 Git 仓库代码，追踪调用链
- 支持 Controller → Service → DAO 等多层调用分析
- 可选集成 Souche 链路追踪系统获取运行时数据

### RAG 知识库分析
- 分析 Git 仓库中的代码
- 结合日志文件进行问题分析
- 自动定位代码中的问题
- 提供 AI 驱动的修复方案
- 与链路追踪数据集成进行深度分析

### 可视化展示
- **树形视图 (TreeView)**：层级展示调用链结构
- **ASCII 视图 (AsciiView)**：纯文本展示，适合快速预览
- **图形视图 (GraphView)**：基于 Vue Flow 的交互式图形展示

## 安装

### 后端依赖
```bash
pip install -r requirements.txt
```

对于 RAG 功能还需要安装：
```bash
pip install langchain langchain-community faiss-cpu sentence-transformers gitpython
```

### 前端依赖
```bash
cd frontend
npm install
```

## 使用方法

### 启动 API 服务
```bash
python api_server.py
```
服务将在 http://localhost:8080 启动，提供以下接口：
- `GET /` - 服务信息
- `GET /api/repos` - 获取可用仓库列表
- `POST /api/analyze` - 分析 API 调用链
- `POST /api/analyze-jira` - 分析 JIRA 问题
- `GET /api/health` - 健康检查

### 启动前端开发服务器
```bash
cd frontend
npm run dev
```
前端将在 http://localhost:5173 启动（默认 Vite 端口）

### RAG 分析
```bash
# 基础 RAG 分析
python rag_log_analyzer.py --repo-path /path/to/repo --log-file /path/to/logfile.log

# 集成 trace 数据分析
python integrate_trace_rag.py --trace-id TRACE_ID --date DATE --repo-path /path/to/repo
```

### JIRA 问题获取
```bash
# 设置环境变量
export JIRA_BASE_URL='https://jira.souche-inc.com/'
export JIRA_USERNAME='your_username'
export JIRA_PASSWORD='your_password_or_api_token'

# 运行脚本
python scripts/fetch_jira_souche.py ISSUE_KEY
```

### 运行 RAG 示例
```bash
python demo_rag.py
```

## API 接口文档

### 分析 API 调用链

**POST /api/analyze**

请求体：
```json
{
  "api_path": "/v1/customerAction/saveOrUpdateCustomer",
  "repo_key": "super_mario",
  "trace_id": "1774764304798_AKFw",
  "date": "2026-04-23",
  "cookies": "JSESSIONID=xxx"
}
```

参数说明：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| api_path | string | 是 | API 路径，如 `/v1/customerAction/saveOrUpdateCustomer` |
| repo_key | string | 是 | 仓库标识，对应 config 中的仓库配置 |
| trace_id | string | 否 | Trace ID，用于获取链路追踪数据 |
| date | string | 否 | 日期，格式 `YYYY-MM-DD` |
| cookies | string | 否 | Trace API 认证 cookies |

### 分析 JIRA 问题

**POST /api/analyze-jira**

请求体：
```json
{
  "jira_url": "https://jira.souche-inc.com/browse/PROJ-123",
  "repo_key": "super_mario",
  "api_path": "/v1/customer/save",
  "trace_id": "1774764304798_AKFw",
  "trace_date": "2026-04-23",
  "cookies": "JSESSIONID=xxx",
  "use_ai": false
}
```

参数说明：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| jira_url | string | 是 | JIRA URL 地址 |
| repo_key | string | 否 | 仓库标识（提供 api_path 时必填） |
| api_path | string | 否 | API 路径（提供时进行调用链分析） |
| trace_id | string | 否 | Trace ID（获取链路追踪数据） |
| trace_date | string | 否 | Trace 日期 |
| cookies | string | 否 | Trace API 认证 cookies |
| use_ai | bool | 否 | 是否使用 AI 增强分析 |

返回示例：
```json
{
  "jira_url": "https://jira.souche-inc.com/browse/PROJ-123",
  "issue_key": "PROJ-123",
  "jira": {
    "key": "PROJ-123",
    "summary": "用户无法保存订单",
    "description": "...",
    "status": "Open",
    "comments": [...]
  },
  "code_context": {
    "files": [...],
    "call_chain": {...
    
    }
  },
  "analysis": {
    "possible_causes": [
      {"category": "空指针", "suggestion": "检查对象是否为空"}
    ],
    "ai_enhanced": false
  }
}
```

### 获取仓库列表

**GET /api/repos**

返回示例：
```json
{
  "repos": [
    {"key": "super_mario", "url": "git@github.com:xxx/super_mario.git", "name": "super_mario"}
  ]
}
```

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (Vue 3)                      │
│   ┌──────────────────┐         ┌──────────────────────────┐│
│   │   JIRA 分析视图   │         │     调用链分析视图        ││
│   │ JiraAnalysisView │         │ TreeView/Ascii/GraphView ││
│   └──────────────────┘         └──────────────────────────┘│
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP API
┌────────────────────────────▼────────────────────────────────┐
│                    API Server (FastAPI)                      │
│   ┌─────────────────┐  ┌─────────────────────────────────┐  │
│   │  JiraAnalyzer   │  │    JavaCallChainAnalyzer       │  │
│   │  (JIRA 分析)     │  │    (调用链分析)                 │  │
│   └─────────────────┘  └─────────────────────────────────┘  │
│   ┌─────────────────┐  ┌─────────────────────────────────┐  │
│   │  RuleEngine     │  │    CodeSearch                   │  │
│   │  (规则匹配)      │  │    (代码搜索)                   │  │
│   └─────────────────┘  └─────────────────────────────────┘  │
└────────────────────────────┬────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────┐
│                      Code Repos (Git)                        │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│   │ super_mario  │  │   gateway    │  │   ...       │     │
│   └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

### 核心组件

1. **Frontend (Vue 3)**：基于 Naive UI 的前端界面
   - **JiraAnalysisForm** - JIRA 分析表单（JIRA URL 必填）
   - **JiraAnalysisView** - JIRA 分析结果展示
   - **AnalyzerForm** - 调用链分析表单（保留原有功能）
   - Pinia 状态管理
   - Vue Flow 图形库实现调用链可视化

2. **API Server (FastAPI)**：REST API 服务
   - `/api/analyze` - 调用链分析入口
   - `/api/analyze-jira` - JIRA 问题分析入口
   - `/api/repos` - 仓库列表查询

3. **Analyzer Modules**：
   - **JiraAnalyzer** - JIRA 问题分析编排
   - **RuleEngine** - 规则匹配原因分析
   - **CodeSearch** - 代码库关键词搜索
   - **JavaCallChainAnalyzer** - 调用链分析

## 配置

请参考 `config.py` 文件以调整系统参数，如嵌入模型、数据库路径等。

## 使用场景

1. **链路追踪分析**：深入分析分布式系统调用链
2. **错误诊断**：快速定位日志中的错误源头
3. **性能分析**：分析慢查询和性能瓶颈
4. **代码审查**：辅助识别潜在问题
5. **故障排查**：自动化问题定位和解决建议
6. **JIRA 问题管理**：获取和管理 JIRA 问题详情

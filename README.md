# Fetch Trace Logs & RAG Analysis System

这是一个综合性的系统，包含多个功能模块：

1. 从 Souche 链路追踪系统获取并分析链路日志
2. 基于 Git 仓库和日志文件的 RAG（检索增强生成）知识库系统
3. 从 JIRA 获取问题详情

## 功能特点

### 链路日志获取
- 从 Souche 链路追踪系统获取分布式链路数据
- 提取 SQL 查询及其执行详情
- 生成结构化的 JSON 输出文件

### RAG 知识库分析
- 分析 Git 仓库中的代码
- 结合日志文件进行问题分析
- 自动定位代码中的问题
- 提供 AI 驱动的修复方案
- 与链路追踪数据集成进行深度分析

### JIRA 问题获取
- 从 JIRA 系统获取问题详情
- 显示问题的标准字段及自定义字段
- 显示附件信息

## 安装

```bash
pip install -r requirements.txt
```

对于 RAG 功能还需要安装：
```bash
pip install langchain langchain-community faiss-cpu sentence-transformers gitpython
```

## 使用方法

### 获取链路日志
```bash
python scripts/fetch_trace_souche.py --trace-id 1774764304798_AKFw --date 2026-03-29
```

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

## 系统架构

1. **数据获取层**：从 Souche 和 JIRA 系统获取数据
2. **代码库分析层**：扫描 Git 仓库中的代码文件
3. **向量化层**：使用 Sentence Transformers 创建嵌入
4. **检索层**：FAISS 向量数据库进行相似性搜索
5. **生成层**：基于 LLM 的问题分析和修复建议

## 配置

请参考 `config.py` 文件以调整系统参数，如嵌入模型、数据库路径等。

## 使用场景

1. **链路追踪分析**：深入分析分布式系统调用链
2. **错误诊断**：快速定位日志中的错误源头
3. **性能分析**：分析慢查询和性能瓶颈
4. **代码审查**：辅助识别潜在问题
5. **故障排查**：自动化问题定位和解决建议
6. **JIRA 问题管理**：获取和管理 JIRA 问题详情
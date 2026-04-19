# GitHub/Git 项目代码 + 日志文件 RAG 知识库系统

这是一个基于 LangChain、FAISS 和 Sentence Transformers 的 RAG (Retrieval Augmented Generation) 系统，能够：

1. 分析 Git 仓库中的代码
2. 结合日志文件进行问题分析
3. 自动定位代码中的问题
4. 提供 AI 驱动的修复方案

## 功能特点

- **代码库分析**：扫描 Git 仓库中的所有代码文件
- **日志分析**：解析日志文件，识别错误和异常
- **智能检索**：使用向量相似度匹配相关代码段
- **问题定位**：AI 自动定位可能导致问题的代码位置
- **修复建议**：提供针对性的修复方案
- **Trace 集成**：与现有的 trace 日志获取工具集成

## 安装依赖

确保已安装所需依赖：

```bash
pip install -r requirements.txt
```

额外需要的包：
- langchain
- langchain-community
- faiss-cpu
- sentence-transformers
- gitpython

## 使用方法

### 方法一：分析现有日志文件

```bash
python rag_log_analyzer.py --repo-path /path/to/your/git/repo --log-file /path/to/your/logfile.log
```

### 方法二：集成 trace 数据分析

```bash
# 获取新的 trace 数据并分析
python integrate_trace_rag.py --trace-id YOUR_TRACE_ID --date 2023-01-01 --repo-path /path/to/your/repo --cookies "your_cookies_here"

# 分析已有的 trace 文件
python integrate_trace_rag.py --trace-file /path/to/trace_file.json --repo-path /path/to/your/repo
```

### 方法三：直接使用 RAG 类

```python
from rag_log_analyzer import GitLogRAG

# 创建 RAG 实例
rag_system = GitLogRAG(repo_path="/path/to/repo", log_file_path="/path/to/logfile.log")

# 处理仓库和日志
rag_system.process_repo_and_logs()

# 分析特定问题
problem_description = "应用程序在处理大量数据时出现内存溢出错误"
result = rag_system.analyze_log_issue(problem_description)

print(result["answer"])
```

## 系统架构

1. **数据加载层**：
   - Git 代码库加载器
   - 日志文件解析器

2. **向量化层**：
   - 使用 Sentence Transformers 创建嵌入
   - FAISS 向量数据库存储

3. **检索层**：
   - 相似性搜索算法
   - 上下文检索机制

4. **生成层**：
   - 基于 LLM 的问题分析
   - 代码定位和修复建议

## 配置选项

查看 `config.py` 文件以调整各种参数：

- 嵌入模型选择
- 向量数据库路径
- 文本块大小和重叠
- 检索数量等

## 集成现有功能

该系统与现有的 trace 日志获取功能完美集成：

- 可以分析从 Souche 系统获取的 trace 数据
- 自动提取 SQL 查询并分析性能问题
- 结合代码库上下文提供优化建议

## 使用场景

1. **错误诊断**：快速定位日志中的错误源头
2. **性能分析**：分析慢查询和性能瓶颈
3. **代码审查**：辅助识别潜在问题
4. **故障排查**：自动化问题定位和解决建议
## Why

当前系统是"API调用链分析工具"，输入Repo + API Path 输出调用链。但实际使用场景中，用户通常先遇到JIRA问题，需要的是"这个问题是什么原因"。现有工具需要用户手动从JIRA复制API路径等信息再分析，流程割裂。

## What Changes

- **输入模式改变**：JIRA URL 必填，Repo / API Path / Trace ID 改为非必填
- **新增 JIRA 内容获取**：根据 JIRA URL 获取问题描述、评论、附件等信息
- **新增问题原因分析**：基于规则匹配 + 可选 AI 增强，分析问题可能原因
- **代码搜索范围调整**：
  - 有 Repo + API Path → 分析调用链 + 代码上下文
  - 有 Repo 无 API Path → 扫描整个代码库匹配 JIRA 关键词
  - 有 Trace ID → 获取链路数据辅助分析
  - 无 Repo 有 API Path → 不执行分析，提示需要提供 Repo
- **前端视图改变**：JIRA 问题分析视图替代原有调用链视图（TreeView/AsciiView/GraphView 保留为辅助）

## Capabilities

### New Capabilities

- `jira-problem-analysis`: JIRA 问题分析核心能力
  - 输入：JIRA URL (必填)，Repo/API Path/Trace ID (可选)
  - 输出：JIRA 内容 + 问题原因分析 + 相关代码上下文
- `jira-content-fetch`: 从 JIRA 系统获取问题详情
- `problem-cause-analysis`: 问题原因分析（规则匹配 + 可选 AI）
- `codebase-search`: 基于关键词的代码库搜索

## Impact

- 前端：`AnalyzerForm.vue` 重构，移除必填校验，添加 JIRA URL 输入
- 前端：新增 `JiraAnalysisView.vue` 展示 JIRA 内容和分析结果
- 后端：新增 `POST /api/analyze-jira` 接口
- 后端：`JavaCallChainAnalyzer` 保留但支持无 API Path 模式（扫描全库）
- 新增依赖：`jira` Python 库（用于 JIRA API 调用）

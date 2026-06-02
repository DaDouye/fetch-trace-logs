## Why

构建一个一次性 ETL 脚本，将 2025 年全年线上 Jira ONLINEBUG 项目数据同步至 PostgreSQL 数据库，作为 AI 分析线上问题的数据源参考。

## What Changes

- 新增 `scripts/fetch_onlinebugs_2025.py`：一次性拉取 2025 年 ONLINEBUG 所有缺陷数据
- 新增数据库表 `jira_online_issue_2025`：存储 issue 明细及评论
- 复用现有的 `JiraClient` 认证体系，通过 `.config` 文件加载环境变量

## Capabilities

### New Capabilities

- `jira-onlinebug-2025-etl`：一次性 ETL，将 2025 年 ONLINEBUG 项目数据（含 customfield_19900 和评论）同步至 `jira_online_issue_2025` 表

## Impact

- 新建 `scripts/fetch_onlinebugs_2025.py`
- 新建目标表 `super_mario.jira_online_issue_2025`
- 依赖现有 `api/jira_client.py` 的 `JiraClient` 类和认证加载逻辑
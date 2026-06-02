## ADDED Requirements

### Requirement: Jira ONLINEBUG 2025 数据拉取
系统 SHALL 提供一次性 ETL 脚本 `scripts/fetch_onlinebugs_2025.py`，将 2025 年全年 ONLINEBUG 项目中 issuetype=缺陷 的所有 issue 同步至 PostgreSQL 表 `jira_online_issue_2025`。

#### Scenario: 脚本成功执行
- **WHEN** 执行 `python scripts/fetch_onlinebugs_2025.py`
- **THEN** 系统通过 JQL `project = ONLINEBUG AND issuetype = 缺陷 AND created >= 2025-01-01 AND created <= 2025-12-31` 分页拉取所有匹配 issue
- **AND** 每条 issue 的基本信息、customfield_19900、评论列表被写入 `jira_online_issue_2025` 表
- **AND** 脚本退出码为 0 并打印拉取总数

#### Scenario: 网络超时重试
- **WHEN** Jira API 请求返回超时或 5xx 错误
- **THEN** 系统重试最多 3 次，每次间隔 1 秒
- **AND** 重试失败后打印错误并退出

#### Scenario: customfield_19900 为空
- **WHEN** 某 issue 的 customfield_19900 字段不存在或为空
- **THEN** 该字段在数据库中存储为 NULL

#### Scenario: 评论为空
- **WHEN** 某 issue 无评论
- **THEN** comments 字段存储为空 JSON 数组 `[]`

### Requirement: 目标表结构
`jira_online_issue_2025` 表 SHALL 包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(32) PK | Issue key，如 ONLINEBUG-15935 |
| project | VARCHAR(32) | 项目名，固定为 ONLINEBUG |
| issue_num | INTEGER | Issue 编号，从 id 拆分 |
| summary | TEXT | 概要 |
| status | VARCHAR(32) | 状态 |
| assignee | VARCHAR(128) | 经办人 displayName |
| reporter | VARCHAR(128) | 报告人 displayName |
| created_date | TIMESTAMP | 创建时间 |
| online_desc | TEXT | customfield_19900 |
| comments | TEXT | JSON 数组格式评论列表 |
| fetched_at | TIMESTAMP | 拉取时间戳，默认 NOW() |

#### Scenario: 数据重复执行
- **WHEN** 脚本执行两次（表已存在数据）
- **THEN** 使用 `INSERT ... ON CONFLICT (id) DO UPDATE` 语义，相同 id 覆盖更新

### Requirement: 环境变量加载
系统 SHALL 从 `scripts/../.config` 文件加载 Jira 认证环境变量（JIRA_USERNAME, JIRA_PASSWORD, JIRA_BASE_URL）。

#### Scenario: 缺少认证信息
- **WHEN** 环境变量 JIRA_USERNAME 或 JIRA_PASSWORD 未设置
- **THEN** 脚本打印错误信息并以退出码 1 终止
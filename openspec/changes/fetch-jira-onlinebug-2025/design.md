## Context

2025 年全年的线上 Jira ONLINEBUG 数据需要导入 PostgreSQL，供 AI 分析使用。数据源为 `https://jira.souche-inc.com`，目标库为 `test.database3500.scsite.net:3500`，database `super_mario`，目标表 `jira_online_issue_2025`。一次性 ETL，拉完即结束。

现有代码库已有 `scripts/fetch_jira_souche.py`（JQL 分页搜索）和 `api/jira_client.py`（JiraClient，支持 `get_issue` 和 `get_comments`），可复用。

## Goals / Non-Goals

**Goals:**
- 一次性拉取 2025 年 ONLINEBUG 所有 issuetype=缺陷 的 issue
- 每条 issue 存储：基本信息 + customfield_19900 + 评论列表
- 数据落入 `super_mario.jira_online_issue_2025`

**Non-Goals:**
- 不是增量同步，不考虑增量更新逻辑
- 不做数据清洗或转换，只做原样存储
- 不涉及 Jira 写入或修改

## Decisions

**1. 脚本结构：复用 JiraClient，分离 DB 写入**

不在 `JiraClient` 里塞数据库写入逻辑，而是：
```
scripts/fetch_onlinebugs_2025.py
  ├─ 加载 .config 环境变量
  ├─ 创建 JiraClient
  ├─ JQL 分页拉取 issues（每条只拉基本信息，含 customfield_19900）
  └─ 对每个 issue 调用 get_comments，拼装后插入 PG
```

**Why**: 保持脚本自包含，后续删除或改写不影响 `jira_client.py`。

**2. 数据库连接：psycopg2 直接写入**

使用 `psycopg2` 直连 PostgreSQL，每次插入后 `conn.commit()`。

**Why**: 数据量仅 1507 条，一次性写入，连接池或 ORM 过度设计。

**3. 表结构**

```sql
CREATE TABLE IF NOT EXISTS jira_online_issue_2025 (
    id            VARCHAR(32)   PRIMARY KEY,  -- ONLINEBUG-XXXXX
    project       VARCHAR(32),
    issue_num     INTEGER,
    summary       TEXT,
    status        VARCHAR(32),
    assignee      VARCHAR(128),
    reporter      VARCHAR(128),
    created_date  TIMESTAMP,
    online_desc   TEXT,
    comments      TEXT,
    fetched_at    TIMESTAMP DEFAULT NOW()
);
```

**4. Comments 存储：JSON 数组**

多条评论存为一个 JSON 字段 `comments`，格式 `[{"author":"...","body":"...","created":"..."}, ...]`，方便 AI 上下文注入。

**5. JQL 查询**

```
project = ONLINEBUG AND issuetype = 缺陷 AND created >= 2025-01-01 AND created <= 2025-12-31
```

按 50 条/页分页，API 总调用约 30 次。

## Risks / Trade-offs

- [Risk] Jira API 限流 → **Mitigation**: 加 `time.sleep(0.5)` 间隔，控制速率
- [Risk] `customfield_19900` 为空或不存在 → **Mitigation**: 字段不存在时存 NULL
- [Risk] 评论数为 0 → **Mitigation**: 存空数组 `[]`，不跳过
- [Risk] 使用 Sequel Pro 确认连接的是 MySQL 而非 PostgreSQL → **Mitigation**: 脚本改用 pymysql，ON DUPLICATE KEY UPDATE 语法

## Open Questions

- 无重大遗留问题
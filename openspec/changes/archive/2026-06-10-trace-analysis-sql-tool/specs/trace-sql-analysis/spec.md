## ADDED Requirements

### Requirement: Trace SQL Analysis Page
系统 SHALL 提供独立的链路 SQL 分析页面，用户输入 trace_id 和 cookies，获取链路中所有 SQL 的整理结果。

#### Scenario: Successful SQL extraction
- **WHEN** 用户在 `/trace-analysis` 页面输入有效的 trace_id 和 cookies 并点击"分析"
- **THEN** 系统调用 `/api/analyze-trace` 接口，返回链路 SQL 列表，前端展示整理后的 SQL 卡片

#### Scenario: No SQL in trace
- **WHEN** 用户输入的 trace_id 有效但链路中无 SQL 操作
- **THEN** 前端展示空状态 "未检测到 SQL 操作"

#### Scenario: Invalid trace or expired cookie
- **WHEN** 用户输入无效的 trace_id 或过期的 cookies
- **THEN** 前端展示错误提示 "链路获取失败，请检查 trace_id 和 cookies"

### Requirement: SQL List Display
每条 SQL SHALL 以卡片形式展示，包含数据库信息、耗时、原始 SQL 和整理后 SQL。

#### Scenario: Display SQL card
- **WHEN** API 返回 SQL 列表
- **THEN** 每个 SQL 项展示: 数据库 host/db_name、耗时(is_batch/duration_ms)、原始 SQL、整理后 SQL

#### Scenario: Copy formatted SQL
- **WHEN** 用户点击 SQL 卡片的复制按钮
- **THEN** 整理后的 SQL 被复制到剪贴板

### Requirement: Analyze-trace API
`POST /api/analyze-trace` 接口 SHALL 接受 trace_id 和 cookies，返回链路 SQL 列表及格式化结果。

#### Scenario: Valid request
- **WHEN** POST `/api/analyze-trace` with `{ trace_id: string, cookies: string }`
- **THEN** 返回 `{ sql_list: [{ db_host, db_name, db_port, sql, params, formatted_sql, duration_ms, is_batch, result_size }, ...] }`

#### Scenario: Missing parameters
- **WHEN** POST `/api/analyze-trace` without trace_id or cookies
- **THEN** 返回 422 Unprocessable Entity，错误信息指出缺失参数

#### Scenario: Unauthorized
- **WHEN** POST `/api/analyze-trace` with invalid/expired cookies
- **THEN** 返回 401 Unauthorized
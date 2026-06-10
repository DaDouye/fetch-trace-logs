## Why

用户在排查数据库问题时，需要从链路追踪数据中提取 SQL 语句并整理成可读的格式化形式。当前系统没有提供专门的链路 SQL 提取接口，需要一个独立页面支持输入 trace_id 和 cookie，直接获取并整理链路中涉及的所有 SQL。

## What Changes

### Backend
- **新增接口**: `POST /api/analyze-trace`
  - 输入: `{ trace_id: string, cookies: string }`
  - 输出: `{ sql_list: [{ db_host, db_name, db_port, sql, params, formatted_sql, duration_ms, is_batch, result_size }, ...] }`
  - 复用现有 trace 采集逻辑（与 `/api/analyze` 相同的 trace 数据来源）

### Frontend
- **引入 Vue Router**，实现路由管理
- **新增页面路由**: `/trace-analysis`
- **新增页面组件**: `TraceAnalysis.vue` — 输入 trace_id 和 cookies，展示整理后的 SQL 列表
- **新增 Store**: `traceStore.js` — 管理链路分析状态
- **修改 `App.vue`**: 改为 `<router-view>` 容器

## Capabilities

### New Capabilities
- `trace-sql-analysis`: 提供链路 SQL 提取和格式化能力，用户输入 trace_id 和 cookies，获取链路中所有 SQL 的整理结果

### Modified Capabilities
- (无)

## Impact

- **后端**: 新增 `/api/analyze-trace` 端点，复用现有 trace 采集逻辑
- **前端**: 引入 vue-router，新增一个页面路由
- **API 变更**: 新增 `/api/analyze-trace` 接口
## 1. Backend API

- [x] 1.1 新增 `POST /api/analyze-trace` 接口
- [x] 1.2 实现 trace 数据获取逻辑（复用现有采集逻辑）
- [x] 1.3 实现 SQL 参数解析和格式化
- [x] 1.4 返回格式: `{ sql_list: [{ db_host, db_name, db_port, sql, params, formatted_sql, duration_ms, is_batch, result_size }, ...] }`
- [x] 1.5 添加参数校验和错误处理

## 2. Frontend Router Setup

- [x] 2.1 安装 vue-router 依赖
- [x] 2.2 创建 `router/index.js`，配置 `/trace-analysis` 路由
- [x] 2.3 修改 `App.vue`，改为 `<router-view>` 容器
- [x] 2.4 添加默认路由重定向到 `/trace-analysis`

## 3. Frontend Store

- [x] 3.1 创建 `stores/traceStore.js` (Pinia)
- [x] 3.2 实现 `analyzeTrace(trace_id, cookies)` action
- [x] 3.3 管理 `sqlList`、`loading`、`error` 状态

## 4. Frontend Page Component

- [x] 4.1 创建 `pages/TraceAnalysisPage.vue` 页面组件
- [x] 4.2 实现输入区: Trace ID + Cookies + 分析按钮
- [x] 4.3 实现输出区: SQL 列表卡片展示
- [x] 4.4 每条 SQL 卡片显示: db_host/db_name、耗时、原始 SQL、整理后 SQL
- [x] 4.5 添加加载状态和错误提示
- [x] 4.6 添加空状态展示（无 SQL 时）
- [x] 4.7 添加复制按钮（一键复制整理后 SQL）

## 5. Integration & Styling

- [x] 5.1 页面样式与现有 JIRA 分析页面保持一致
- [x] 5.2 集成到 Naive UI 组件体系
- [x] 5.3 测试路由切换

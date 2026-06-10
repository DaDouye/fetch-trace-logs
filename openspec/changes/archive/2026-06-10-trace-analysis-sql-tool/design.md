## Context

当前系统 `fetch-trace-logs` 提供 JIRA 问题分析和调用链分析能力，但缺少专门的链路 SQL 提取功能。用户需要输入 trace_id 和 cookies，直接获取链路中涉及的所有 SQL 并整理成可读格式。

**现有系统状态:**
- 前端: Vue 3 + Pinia + Naive UI，单页面架构，无路由
- 后端: FastAPI，提供 `/api/analyze` (调用链分析) 和 `/api/analyze-jira` (JIRA 分析)
- Trace 采集: 现有 `/api/analyze` 已能获取链路数据，其中包含 SQL 信息

**约束:**
- 后端 trace 采集逻辑不变，新增 API 端点封装
- 前端需引入 Vue Router 实现路由管理

## Goals / Non-Goals

**Goals:**
- 新增 `/api/analyze-trace` 接口，输入 trace_id + cookies，输出链路 SQL 列表及格式化结果
- 新增 `/trace-analysis` 前端页面，提供独立的链路 SQL 整理工具
- 复用现有 trace 采集逻辑，不引入新的 trace 数据源

**Non-Goals:**
- 不修改现有的 `/api/analyze` 和 `/api/analyze-jira` 接口
- 不做 SQL 执行或危险操作，只做提取和格式化
- 不引入新的数据库连接能力

## Decisions

### 1. 后端新增 `/api/analyze-trace` 接口

**决定**: 新增独立接口 `/api/analyze-trace`，专门返回链路 SQL 数据

**原因**:
- 职责单一，接口语义清晰
- 区别于通用的调用链分析接口
- 后续可独立扩展（如增加 SQL 统计、慢查询分析等）

**替代方案**:
- 复用 `/api/analyze` 并通过参数控制返回格式 → 拒绝，污染现有接口

### 2. SQL 格式化在前端还是后端做

**决定**: 后端返回 `formatted_sql`，前端直接展示

**原因**:
- 后端已有链路数据，更容易做参数替换
- 前端只需展示，降低前端复杂度
- 后续如需调整格式，只需改后端

### 3. 前端路由方案

**决定**: 引入 Vue Router，实现 `/trace-analysis` 路由

**原因**:
- 用户明确需要 `/trace-analysis` 路径
- 后续可扩展更多页面
- 与现有 JIRA 分析页面解耦

**替代方案**:
- Tab 切换 → 拒绝，不符合用户对路径的预期

## Risks / Trade-offs

| 风险 | 描述 | 缓解 |
|------|------|------|
| trace 数据无 SQL | 某些链路可能不包含 SQL 操作 | 返回空列表，前端展示"未检测到 SQL" |
| SQL 参数解析失败 | sqlParams 格式不规则导致解析失败 | 后端做解析，前端优雅降级展示原始 SQL |
| Cookie 过期 | 链路服务认证失败 | 后端返回 401，前端提示重新输入 |

## Open Questions

1. **SQL 列表为空时的展示策略**: 是显示空状态，还是显示原始 trace 数据摘要？
2. **是否需要支持复制 SQL**: 用户可能需要一键复制整理后的 SQL

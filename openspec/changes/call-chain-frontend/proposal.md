## Why

当前项目已有 `api_server.py` 提供 Java 调用链静态分析能力，但只能通过 curl 或 Postman 调用，缺乏用户友好的界面。前端团队和测试人员需要直观地输入 API 路径并查看调用链，无法独立使用现有后端服务。

## What Changes

- **新增 Vue 3 前端项目**（Vite + Naive UI），提供可视化分析界面
- 仓库选择器：下拉选择已配置的 Git 仓库（调用 `GET /api/repos`）
- API 路径输入框：支持手动输入或拼接 API 路径
- Trace 参数输入：Trace ID、Date、Cookies（均为可选）
- 分析结果展示（Tab 切换）：
  - **ASCII 视图**：直接渲染后端返回的 `ascii_graph` 字段
  - **树状图视图**：可折叠节点，点击节点显示 tooltip（file path + line number）
  - **图形视图**：vue-flow 轻量有向图，水平布局，节点颜色按层级区分，点击节点显示 tooltip

## Capabilities

### New Capabilities

- `call-chain-ui`: 前端分析界面，支持 API 输入、仓库选择、Trace 参数、三种调用链展示模式
- `call-chain-graph-view`: 轻量图形视图组件，基于 vue-flow

### Modified Capabilities

- 无

## Impact

- 新增 `frontend/` 目录（Vite + Vue 3 + Naive UI 项目）
- 后端接口不变（`/api/analyze` 和 `/api/repos` 保持兼容）
- 需要处理跨域问题（前端 dev server:5173 → 后端:8080）
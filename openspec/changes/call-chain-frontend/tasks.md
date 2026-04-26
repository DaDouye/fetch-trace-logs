## 1. 项目初始化

- [x] 1.1 创建 `frontend/` 目录，使用 Vite 初始化 Vue 3 项目
- [x] 1.2 安装依赖：naive-ui, @vue-flow/core, axios, pinia
- [x] 1.3 配置 `vite.config.js` 代理（`/api` → `http://localhost:8080`）
- [x] 1.4 验证项目启动（`npm run dev`）并访问页面

## 2. API 层封装

- [x] 2.1 创建 `src/api/index.js`，封装 axios 实例和后端接口调用
- [x] 2.2 实现 `fetchRepos()` → `GET /api/repos`
- [x] 2.3 实现 `analyzeApi(params)` → `POST /api/analyze`

## 3. Pinia Store

- [x] 3.1 创建 `src/stores/analyzer.js`，管理分析状态（repos 列表、当前结果、loading 状态）
- [x] 3.2 实现 `loadRepos()` action
- [x] 3.3 实现 `analyze(params)` action

## 4. AnalyzerForm 组件

- [x] 4.1 创建 `src/components/AnalyzerForm.vue`
- [x] 4.2 实现仓库下拉选择器（n-select，选项从 store 加载）
- [x] 4.3 实现 API 路径输入框（n-input）
- [x] 4.4 实现 Trace ID、Date、Cookies 可选输入字段
- [x] 4.5 实现"分析"按钮，触发 store.analyze()
- [x] 4.6 添加表单校验（仓库和 API 路径必填）
- [x] 4.7 加载状态和错误提示处理

## 5. AsciiView 组件

- [x] 5.1 创建 `src/components/AsciiView.vue`
- [x] 5.2 使用 `<pre>` 标签渲染 `ascii_graph`
- [x] 5.3 添加空状态处理（无数据时显示提示）

## 6. TreeView 组件

- [x] 6.1 创建 `src/components/TreeView.vue`
- [x] 6.2 实现 `buildTree()` 函数，将扁平 call_chain 转为树结构
- [x] 6.3 使用 n-tree 或自实现渲染可折叠树节点
- [x] 6.4 点击节点显示 tooltip（file_path + line_number）

## 7. GraphView 组件

- [x] 7.1 创建 `src/components/GraphView.vue`
- [x] 7.2 实现 `buildGraphData()` 函数，将 call_chain 转为 vue-flow 节点/边
- [x] 7.3 集成 @vue-flow/core，渲染水平布局有向图
- [x] 7.4 实现节点颜色按层级区分（Controller蓝/Service绿/Internal灰/DAO橙/SQL红）
- [x] 7.5 点击节点显示 tooltip（file_path + line_number）

## 8. App.vue 主组件

- [x] 8.1 创建 `src/App.vue`
- [x] 8.2 整合 AnalyzerForm + 三个视图组件
- [x] 8.3 实现 Tab 切换（n-tabs：ASCII / 树状图 / 图形视图）
- [x] 8.4 Tab 切换保持已有结果不丢失

## 9. 样式与优化

- [x] 9.1 添加全局样式（`src/styles/main.css`）
- [x] 9.2 调整图形视图节点样式（圆角、字体、颜色）
- [x] 9.3 验证响应式布局（表格宽度自适应）
- [x] 9.4 添加 Loading 状态（n-spin 或 skeleton）
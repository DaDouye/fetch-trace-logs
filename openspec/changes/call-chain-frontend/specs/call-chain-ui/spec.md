## ADDED Requirements

### Requirement: 仓库选择器
前端 SHALL 提供下拉选择器，加载时调用 `GET /api/repos` 获取仓库列表并展示。

#### Scenario: 页面加载仓库列表
- **WHEN** 用户打开分析页面
- **THEN** 系统自动调用 `GET /api/repos` 并将返回的仓库填充到下拉选择器

#### Scenario: 用户选择仓库
- **WHEN** 用户从下拉列表选择一个仓库
- **THEN** 系统 SHALL 保存所选仓库 key，用于后续分析请求

---

### Requirement: API 路径输入
前端 SHALL 提供文本输入框，供用户输入 API 路径（如 `/v1/customer/saveOrUpdate`）。

#### Scenario: 用户输入 API 路径
- **WHEN** 用户在输入框中输入 API 路径
- **THEN** 系统 SHALL 记录该路径，去除尾部斜杠（如 `/v1/customer/saveOrUpdate/` → `/v1/customer/saveOrUpdate`）

---

### Requirement: Trace 参数输入
前端 SHALL 提供可选输入字段：Trace ID、Date、Cookies。

#### Scenario: 用户输入 Trace 参数
- **WHEN** 用户在可选字段中输入 Trace ID、Date 或 Cookies
- **THEN** 系统 SHALL 在调用 `/api/analyze` 时将这些值作为请求体字段传递

#### Scenario: 用户不输入 Trace 参数
- **WHEN** 用户不填写任何 Trace 参数
- **THEN** 系统 SHALL 调用 `/api/analyze` 时不传递这些字段（后端已定义均为 Optional）

---

### Requirement: 分析请求提交
前端 SHALL 在用户填写必填字段（仓库 + API 路径）后，点击"分析"按钮时调用 `POST /api/analyze`。

#### Scenario: 提交分析请求
- **WHEN** 用户点击"分析"按钮且必填字段已填写
- **THEN** 系统 SHALL 发送 POST 请求到 `/api/analyze`，并在请求过程中显示加载状态

#### Scenario: 必填字段为空
- **WHEN** 用户点击"分析"按钮但未填写仓库或 API 路径
- **THEN** 系统 SHALL 显示友好错误提示，不发送请求

#### Scenario: 请求失败
- **WHEN** 后端返回非 2xx 状态码
- **THEN** 系统 SHALL 在界面显示后端返回的错误信息

---

### Requirement: ASCII 视图展示
前端 SHALL 在"ASCII"标签页中直接渲染后端返回的 `ascii_graph` 字段（预格式化文本）。

#### Scenario: 查看 ASCII 视图
- **WHEN** 用户切换到"ASCII"标签页
- **THEN** 系统 SHALL 使用 `<pre>` 标签渲染 `ascii_graph` 内容

---

### Requirement: 树状图视图展示
前端 SHALL 在"树状图"标签页中将 `call_chain` 数组渲染为可折叠树形结构。

#### Scenario: 渲染树状图
- **WHEN** 用户切换到"树状图"标签页
- **THEN** 系统 SHALL 将 `call_chain` 扁平数组重建为树结构，并渲染为可折叠节点

#### Scenario: 点击树节点显示详情
- **WHEN** 用户点击树节点
- **THEN** 系统 SHALL 显示 tooltip，内容包含 `class_name`、`method_name`、`file_path`、`line_number`

---

### Requirement: 图形视图展示
前端 SHALL 在"图形视图"标签页中使用 vue-flow 渲染轻量有向图。

#### Scenario: 渲染图形视图
- **WHEN** 用户切换到"图形视图"标签页
- **THEN** 系统 SHALL 将 `call_chain` 转换为 vue-flow 节点和边，水平布局，节点颜色按层级区分

#### Scenario: 节点颜色按层级区分
- **WHEN** 系统渲染图形视图
- **THEN** Controller 层节点显示蓝色，Service 层显示绿色，Internal 层显示灰色，DAO 层显示橙色，SQL 层显示红色

#### Scenario: 点击图形节点显示详情
- **WHEN** 用户点击图形视图中的节点
- **THEN** 系统 SHALL 显示 tooltip，内容包含 `class_name`、`method_name`、`file_path`、`line_number`

---

### Requirement: Tab 切换状态保持
前端 SHALL 在用户切换展示标签页时保持分析结果不丢失。

#### Scenario: Tab 切换不丢失数据
- **WHEN** 用户先查看 ASCII 视图，再切换到树状图视图
- **THEN** 系统 SHALL 保留已加载的分析结果，无需重新请求
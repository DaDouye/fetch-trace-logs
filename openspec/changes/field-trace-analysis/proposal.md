## Why

现有的 `/api/analyze` 只能从 API 路径出发展示整个接口的调用链（Controller → Service → Mapper → SQL），但无法回答"响应里的某个字段值究竟是怎么来的"这种精细问题。当排查线上数据异常时，需要快速定位某个字段的数据来源、赋值逻辑和转换链路。

## What Changes

- 新增 `POST /api/analysis` 后端接口，支持根据项目名、接口路径（或方法名）、响应字段路径进行字段级溯源
- 新建 `FieldTracer` 类实现字段溯源核心逻辑：JSON路径解析 → DTO字段定位 → 赋值点搜索 → 数据来源追踪 → DB字段/SQL提取
- 新增前端页面 `/analysis`，提供表单输入和溯源结果的可视化展示
- 支持 `Result<T>` 包装类的自动解包（`data.xxx` → `Result.data` → 泛型 DTO）
- 支持 6 种字段赋值模式的识别：setter、builder、构造函数、BeanUtils.copyProperties、MapStruct 映射、直接字段赋值
- 对于 BeanUtils/MapStruct 场景，对比源和目标类的同名字段做推测性匹配

## Capabilities

### New Capabilities

- `field-trace-analysis`: 字段级溯源分析能力，从 JSON 响应字段路径反向追踪到数据库表字段和 SQL 语句

### Modified Capabilities

<!-- 不修改现有 spec，这是一个全新的独立功能 -->

## Impact

- **后端**: `api_server.py` 新增端点；新建 `api/analyzer/field_tracer.py`；可复用 `api/analyze.py` 中的 Controller 定位、Service 查找、Mapper/SQL 提取等方法
- **前端**: `router/index.js` 新增路由；新建 `FieldAnalysisPage.vue`、`FieldAnalysisForm.vue`、`FieldTraceView.vue`；`api/index.js` 新增接口调用
- **无破坏性变更**：现有 `/api/analyze` 端点不受影响
## Context

项目已有 FastAPI 后端（`api_server.py`）提供 Java 调用链静态分析，通过 `POST /api/analyze` 返回调用链数据。需要在不修改后端的前提下，构建 Vue 3 前端页面。

```
当前：
curl -X POST http://localhost:8080/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"api_path": "/v1/customer/save", "repo_key": "super_mario"}'

目标：浏览器访问 Vue 前端 → 输入 → 查看调用链
```

## Goals / Non-Goals

**Goals:**
- 提供可视化界面，输入 API 路径即可分析调用链
- 支持三种展示模式：ASCII 文本、树状图、图形视图
- 节点点击显示 file_path + line_number tooltip
- 支持 Trace 相关参数输入
- 仓库下拉选择

**Non-Goals:**
- 不修改后端接口或数据模型
- 图形视图仅做轻量展示（不实现缩放、拖拽、导出等高级功能）
- 不做权限认证

## Decisions

### 1. 技术栈

| 模块 | 选型 | 原因 |
|------|------|------|
| 构建工具 | Vite | Vue 3 官方推荐，快速 HMR |
| UI 框架 | Naive UI | Vue 3 原生、轻量、主题定制灵活 |
| 图形库 | @vue-flow/core + @vue-flow/background + @vue-flow/minimap | Vue 3 专用流程图库，比 D3 轻 |
| HTTP 客户端 | axios | 拦截器方便，统一错误处理 |
| 状态管理 | Pinia | 工程化标配 |

**替代方案考虑：**
- Element Plus：组件丰富但体积大，此项目仅需要一个表单+标签页，不划算
- D3.js：灵活但学习成本高，vue-flow 足以满足轻量图形需求

### 2. 项目结构

```
frontend/
├── src/
│   ├── main.js
│   ├── App.vue
│   ├── api/
│   │   └── index.js          # axios 实例，调用后端接口
│   ├── components/
│   │   ├── AnalyzerForm.vue  # 表单组件（仓库选择+API路径+Trace参数）
│   │   ├── AsciiView.vue    # ASCII 文本视图
│   │   ├── TreeView.vue     # 树状图视图
│   │   └── GraphView.vue    # vue-flow 图形视图
│   ├── stores/
│   │   └── analyzer.js      # Pinia store
│   └── styles/
│       └── main.css
├── index.html
├── vite.config.js
└── package.json
```

### 3. 跨域处理

前端 dev server (localhost:5173) 调用后端 API (localhost:8080)，Vite 配置代理：

```js
// vite.config.js
export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true
      }
    }
  }
})
```

生产环境：后端同域部署，或 Nginx 反向代理。

### 4. 调用链数据模型

后端 `POST /api/analyze` 返回结构：

```json
{
  "api_path": "/v1/customer/save",
  "method": "POST",
  "controller": "CustomerAction",
  "controller_method": "save",
  "call_chain": [
    {
      "layer": "Controller",
      "class_name": "CustomerAction",
      "method_name": "save",
      "file_path": "web/src/main/java/com/jiaxuan/supermario/json/...java",
      "line_number": 42,
      "sql": null,
      "annotation": "@Rest(\"save\")",
      "is_entry": true
    }
  ],
  "ascii_graph": "..."
}
```

前端将其转换为树结构和 vue-flow 节点/边数据。

### 5. 树状图数据结构转换

```js
function buildTree(callChain) {
  const map = new Map()
  const roots = []

  callChain.forEach(node => {
    map.set(`${node.layer}-${node.class_name}-${node.method_name}`, {
      ...node,
      children: []
    })
  })

  callChain.forEach(node => {
    const current = map.get(`${node.layer}-${node.class_name}-${node.method_name}`)
    if (node.is_entry) {
      roots.push(current)
    }
  })

  return roots
}
```

### 6. 图形视图节点颜色

| Layer | 颜色 |
|-------|------|
| Controller | #3b82f6 (蓝) |
| Service | #22c55e (绿) |
| Internal | #9ca3af (灰) |
| DAO | #f97316 (橙) |
| SQL | #ef4444 (红) |

## Risks / Trade-offs

- [Risk] 后端返回的 `call_chain` 是扁平数组，前端需自行重建树结构
  → Mitigation：实现 `buildTree()` 转换函数，基于 `is_entry` 和父子关系构建
- [Risk] 图形视图水平布局可能产生长链，适合 5-7 层，超过后需要滚动
  → Mitigation：先做 MVP，后续考虑横向虚拟化

## Open Questions

- 图形节点唯一标识：当前使用 `layer-class_name-method_name` 组合，是否足够唯一？（如有重载方法可能冲突）→ 暂不处理，后续按需加 line_number
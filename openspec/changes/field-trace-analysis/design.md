## Context

当前系统已有 `/api/analyze` 接口，能从 Controller 向下正向追踪调用链到 SQL。但缺少**字段级反向溯源**能力——给定 JSON 响应中的某个字段路径，追溯其值的来源和转换链路。

约束：
- 项目使用 `Result<T>.success(vo)` 作为统一响应包装，JSON 中的 `data` 字段对应 `Result.data`
- 代码库包含 BeanUtils.copyProperties、MapStruct 等映射工具
- 需同时支持本地仓库和远程 Git 仓库

## Goals / Non-Goals

**Goals:**
- 根据接口路径或 Java 方法名定位 Controller/入口方法
- 解析 Controller 方法的返回类型，解开 `Result<T>` 泛型包装
- 将 JSON 路径映射到 DTO 类的具体字段
- 在 Service 层搜索该字段的所有赋值点
- 从赋值点追踪数据来源（Entity 字段、计算表达式、其他 DTO）
- 最终追踪到 Mapper → MyBatis XML → SQL → DB 表字段
- 对 BeanUtils.copyProperties 场景做同名推测匹配

**Non-Goals:**
- 不追踪跨服务调用（RPC/HTTP 远程调用链）
- 不解析 JPQL/HQL（仅处理 MyBatis XML）
- 不处理动态 SQL 的完整运行时参数
- 不支持多级 MapStruct 嵌套映射（仅追踪一层映射）

## Decisions

### 1. 架构：新建独立 `FieldTracer` 类，复用现有基础设施

```
┌─────────────────────────────────────────────────────────────────┐
│                     FieldTracer (新)                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  analyze(project, api_path?, method_name?, field_path)         │
│       │                                                         │
│       ├── Step 1: _locate_entry(api_path or method_name)       │
│       │    复用 JavaCallChainAnalyzer._find_controller_method   │
│       │                                                         │
│       ├── Step 2: _parse_return_type(controller_file)           │
│       │    提取返回类型 → 解开 Result<T> → 获取 DTO 类名       │
│       │                                                         │
│       ├── Step 3: _resolve_json_path(field_path)                │
│       │    解析 "data.userId" → 跳过 data → 定位到 DTO 字段    │
│       │    解析 "data.list[0].name" → 处理数组下标              │
│       │                                                         │
│       ├── Step 4: _find_field_assignments(dto_class, field)    │
│       │    在 Service 层搜索 6 种赋值模式                       │
│       │                                                         │
│       └── Step 5: _trace_to_source(assignment)                  │
│            追踪赋值右值 → Entity → Mapper → SQL → DB 字段      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

选择 `FieldTracer` 继承/组合 `JavaCallChainAnalyzer`，而非修改现有类。理由：
- 现有 `JavaCallChainAnalyzer` 已有 900+ 行，职责单一（正向调用链）
- 字段溯源是正交能力，独立更易维护和测试
- 复用：文件读取、Controller 查找、Service 实现查找、Mapper/SQL 提取

### 2. JSON 路径解析策略

```
输入路径: "data.list[0].name"

解析:
  ["data", "list[0]", "name"]         # 分割路径段

  "data" → Result.data 字段           # 硬编码: 跳过包装类字段
  "list[0]" → DTO 的 list 字段, 下标0  # 识别数组标记
  "name" → 目标字段                    # 最终追踪目标
```

`Result<T>` 包装类解包策略：
- 硬编码 `data` 为 `Result.data` 的 JSON 序列化字段名
- 从 Controller 方法签名中解析 `Result<CustomerVO>` 获取 `CustomerVO`
- 解析 `CustomerVO.java` 找到实际字段

### 3. 6 种赋值模式识别

| 优先级 | 模式 | 正则/策略 | 置信度 |
|--------|------|-----------|--------|
| 1 | Setter | `vo\.setXxx\((.+)\)` | 高 |
| 2 | Builder | `.xxx\((.+)\).*\.build\(\)` | 高 |
| 3 | 构造函数 | `new XxxVO\((.+)\)` 定位参数位置 | 中 |
| 4 | copyProperties | `BeanUtils\.copyProperties\((\w+),\s*vo\)` → 对比同名推断 | 低(推测) |
| 5 | MapStruct | `xxxMapper\.toXxxVO\((\w+)\)` → 对比推断 | 低(推测) |
| 6 | 直接赋值 | `vo\.xxx\s*=\s*(.+)` | 高 |

搜索范围：以 Controller 调用的 Service 方法为起点，向下递归搜索所有 Service 实现。

### 4. 推测性匹配策略（BeanUtils/MapStruct）

当识​​别到 copyProperties 或 MapStruct 模式时：
1. 解析源对象类型（如 `CustomerEntity`）
2. 找到源类的字段定义
3. 与目标 VO/DTO 做字段名和类型匹配
4. 输出标注 `[推测] 基于同名字段匹配` + 展示匹配依据

### 5. 前端组件架构

```
FieldAnalysisPage.vue
├── FieldAnalysisForm.vue        # 项目选择 + 接口/方法 + 字段路径 输入
└── FieldTraceView.vue           # 溯源结果可视化
    ├── 面包屑式链路展示          # JSON → DTO → Service → Entity → DB
    ├── 代码片段高亮              # 每个节点的文件位置和代码
    └── 推测标注                  # 对推测部分用虚线/问号标识
```

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| 构造函数参数位置推断不准确（重载、过多参数） | 仅处理参数 ≤5 的构造，超过标记为"无法确定" |
| 同名推测匹配可能错误（Entity 和 VO 同名字段但来源不同） | 标注 `[推测]`，展示匹配依据让用户判断 |
| MyBatis 注解 SQL（`@Select`）而非 XML | 额外搜索 Mapper 接口的注解 SQL |
| 局部变量追踪链断裂（`String x = entity.getId(); vo.setId(x)`） | 在方法体内做一轮局部变量解析，但不跨方法追踪变量 |
| 远程仓库模式下的性能（需多次读取文件） | 利用现有 `_read_file` 缓存机制 |

## Open Questions

- 无
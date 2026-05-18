## Context

**当前状态：**
```
┌─────────────┐   regex提取   ┌─────────────┐   直接搜索   ┌─────────────┐
│ Jira描述    │ ───────────▶ │   关键词     │ ──────────▶ │   代码      │
│ (描述随意)   │              │ (不精准)    │             │   搜索      │
└─────────────┘              └─────────────┘             └─────────────┘
```

**问题：**
- JIRA描述格式随意，关键词分隔质量差
- 关键词和代码路径没有标准化映射
- 匹配结果不准确，召回率低

**Swagger数据源验证：**
- 地址: `https://super-mario.stable.dasouche.net/api-docs?group=souche`
- 认证: 无需认证
- 返回: 38个API分组，Swagger 1.2格式
- 示例API: `/v1/customerAction/saveOrUpdateCustomer.json` (POST) - "crm改版保存或更新客户信息"

## Goals / Non-Goals

**Goals:**
- 建立标准化的接口-关键词映射表
- Swagger API自动同步接口列表
- 手动打标保证标签质量
- JIRA关键词模糊匹配接口标签，提升定位准确性
- 复用现有调用链分析和AI分析能力

**Non-Goals:**
- 不做打标管理页面（直接数据库操作）
- 不修改现有调用链分析和AI分析逻辑
- 不做自动打标（AI生成标签）

## Decisions

### 1. 新数据库表设计

```sql
CREATE TABLE api_tag_mapping (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    api_path        VARCHAR(255) NOT NULL COMMENT '接口路径',
    http_method     VARCHAR(10) DEFAULT 'POST' COMMENT 'HTTP方法',
    api_summary     VARCHAR(500) COMMENT '接口中文描述',
    tag             VARCHAR(200) NOT NULL COMMENT '标签关键词',
    tag_type        VARCHAR(20) DEFAULT 'manual' COMMENT 'manual/auto',
    project         VARCHAR(100) DEFAULT 'super-mario' COMMENT '项目标识',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    created_by      VARCHAR(100),
    UNIQUE KEY uk_api_tag (api_path, tag)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE swagger_api_sync_log (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    sync_time       DATETIME DEFAULT CURRENT_TIMESTAMP,
    api_count       INT COMMENT '同步接口数量',
    status          VARCHAR(20) COMMENT 'success/failed',
    error_msg       TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 2. Swagger同步模块

```python
# api/swagger_client.py
class SwaggerClient:
    SWAGGER_URL = "https://super-mario.stable.dasouche.net/api-docs"
    GROUP_PARAM = "group=souche"

    def fetch_api_groups(self) -> List[Dict]:
        """获取所有API分组"""

    def fetch_api_details(self, group_path: str) -> List[Dict]:
        """获取分组下所有API详情"""

    def sync_to_database(self):
        """同步到api_tag_mapping表，仅同步api_path和api_summary"""
```

**同步策略：**
- 首次同步：全量插入 api_path 和 api_summary
- 定时同步（可选）：增量更新，仅新增接口
- 不自动打标：tag字段初始为空

### 3. 模糊匹配策略

```python
def match_jira_keywords_to_apis(jira_keywords: List[str], db_session) -> List[str]:
    """
    JIRA关键词模糊匹配接口标签
    匹配规则：
    - 关键词包含在接口标签中 → 匹配
    - 标签包含在关键词中 → 匹配
    - 分词匹配：关键词"客户管理" 匹配 标签"客户|管理"
    """
    matched_apis = []
    for keyword in jira_keywords:
        # 查询tag包含keyword或keyword包含tag的接口
        apis = session.query(ApiTagMapping).filter(
            or_(
                ApiTagMapping.tag.contains(keyword),
                keyword.contains(ApiTagMapping.tag)
            )
        ).all()
        matched_apis.extend([api.api_path for api in apis])
    return list(set(matched_apis))
```

### 4. JIRA分析流程改造

```
┌──────────────────────────────────────────────────────────────────────┐
│                        新流程                                         │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│   ┌─────────────┐    分隔关键词   ┌─────────────┐   模糊匹配        │
│   │ JIRA描述    │ ──────────────▶ │ JIRA关键词   │ ────────────────▶│
│   └─────────────┘                └─────────────┘                   │
│                                   │                                   │
│                                   ▼                                   │
│                            ┌─────────────┐                           │
│                            │ 接口标签     │                           │
│                            │ 模糊匹配    │                           │
│                            └──────┬──────┘                           │
│                                   │                                   │
│                                   ▼                                   │
│                            ┌─────────────┐   调用链分析              │
│                            │ 匹配接口    │ ───────────────────────▶ │
│                            │ api_path   │                           │
│                            └─────────────┘                           │
│                                                               │       │
│                                                               ▼       │
│                                                    ┌─────────────┐    │
│                                                    │ AI分析      │    │
│                                                    └─────────────┘    │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

### 5. 关键词提取改造

**现有逻辑 (`jira_client.py`):**
```python
def extract_keywords(issue_data):
    # 从JIRA描述用正则分隔出关键词
    api_paths = re.findall(r'/v\d+/...', text)
    class_names = re.findall(r'\b[A-Z]\w+Service\b', text)
    ...
```

**新逻辑：**
```python
def extract_keywords(issue_data) -> Dict[str, List[str]]:
    # 保持原有分隔逻辑作为兜底
    jira_keywords = self._extract_from_jira_description(issue_data)

    # 新增：从数据库查询匹配的接口
    matched_apis = self._match_apis_from_db(jira_keywords)

    return {
        'jira_keywords': jira_keywords,      # 原有：从JIRA分隔
        'matched_apis': matched_apis,         # 新增：从标签匹配
        'api_paths': matched_apis,            # 传给调用链分析
        ...
    }
```

## Risks / Trade-offs

- [Risk] 模糊匹配可能匹配到多个接口
  → Mitigation：返回所有匹配接口，由调用链分析筛选最相关的

- [Risk] 手动打标工作量大
  → Mitigation：先对高频接口打标，初期只覆盖核心业务接口

- [Risk] Swagger API网络不通
  → Mitigation：同步失败时使用本地缓存数据

- [Trade-off] 关键词来源：JIRA分隔 vs 接口标签
  → 选择：JIRA分隔作为兜底，接口标签作为主数据源

## Open Questions

1. 手动打标的标签格式？如 "客户|创建|保存" 还是 "客户管理,创建,保存"？
2. 是否需要区分不同项目的Swagger？当前只有 `super-mario`
3. 同步频率？首次手动触发还是定时任务？

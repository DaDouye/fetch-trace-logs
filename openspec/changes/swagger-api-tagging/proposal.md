## Why

当前JIRA问题分析依赖从JIRA描述中用正则分隔关键词来匹配代码，这种方式关键词来源分散、质量参差不齐，导致匹配不准确。通过从Swagger API获取标准化接口列表，配合手动打标，可以建立高质量的接口-关键词映射，提升问题定位的准确性。

## What Changes

1. **新增Swagger API接口同步模块**
   - 定时或手动从 `https://super-mario.stable.dasouche.net/api-docs?group=souche` 获取接口列表
   - 解析 Swagger 1.2 格式，提取 path、method、summary 等信息
   - 存储到数据库 `api_tag_mapping` 表

2. **新增接口打标管理**
   - 手动为每个接口打标签关键词（直接在数据库insert/update，暂不做页面）
   - 支持一个接口多个标签
   - 标签类型区分手动/自动打标

3. **改造JIRA关键词匹配逻辑**
   - 现有逻辑：从JIRA描述分隔关键词 → 直接搜索代码
   - 新逻辑：JIRA关键词 → 模糊匹配接口标签 → 获取接口 → 调用链分析

4. **匹配到的接口进行调用链分析和AI问题分析**
   - 复用现有 `JavaCallChainAnalyzer` 进行代码调用链分析
   - 复用现有 `AIAnalyzer` 进行问题原因分析

## Capabilities

### New Capabilities
- `swagger-api-sync`: 从Swagger API同步接口列表到本地数据库
- `api-tag-mapping`: 管理和查询接口-标签映射关系
- `jira-keyword-matching`: 基于接口标签的JIRA关键词匹配

### Modified Capabilities
- `jira-problem-analyzer`: 改造关键词来源，从Swagger接口标签匹配，而非直接从JIRA描述分隔

## Impact

- **新数据库表**: `api_tag_mapping` - 存储接口和标签的映射关系
- **新Python模块**: `api/swagger_client.py` - Swagger API同步
- **改造模块**: `api/jira_client.py` - 关键词提取逻辑改造
- **改造模块**: `api/analyzer/jira_analyzer.py` - 匹配逻辑改造
- **无前端变更**: 手动打标直接操作数据库
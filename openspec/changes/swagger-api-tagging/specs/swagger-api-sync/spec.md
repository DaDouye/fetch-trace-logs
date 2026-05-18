## ADDED Requirements

### Requirement: Swagger API同步
系统 SHALL 支持从Swagger API获取接口列表并存储到数据库。

#### Scenario: 获取API分组列表
- **WHEN** 调用同步功能
- **THEN** 系统 SHALL 从 `https://super-mario.stable.dasouche.net/api-docs?group=souche` 获取API分组列表
- **AND** 系统 SHALL 解析返回的38个分组路径

#### Scenario: 获取分组下API详情
- **WHEN** 获取到分组路径如 `/souche/ai-controller`
- **THEN** 系统 SHALL 从 `https://super-mario.stable.dasouche.net/api-docs/souche/ai-controller` 获取该分组下所有API
- **AND** 系统 SHALL 提取每个API的 path、method、summary 字段

#### Scenario: 存储到数据库
- **WHEN** 解析完所有API详情
- **THEN** 系统 SHALL 将 api_path、http_method、api_summary 存储到 api_tag_mapping 表
- **AND** 系统 SHALL 使用 INSERT ... ON DUPLICATE KEY UPDATE 避免重复插入
- **AND** 系统 SHALL 记录同步日志到 swagger_api_sync_log 表

#### Scenario: 同步完成统计
- **WHEN** 同步完成
- **THEN** 系统 SHALL 记录同步的API数量
- **AND** 系统 SHALL 记录同步状态（success/failed）和错误信息（如有）

### Requirement: 同步触发方式
系统 SHALL 支持手动触发和定时同步两种方式。

#### Scenario: 手动触发同步
- **WHEN** 用户调用同步接口或脚本
- **THEN** 系统 SHALL 立即执行同步任务
- **AND** 返回同步结果摘要

#### Scenario: 定时同步（可选）
- **WHEN** 配置了定时同步
- **THEN** 系统 SHALL 每天凌晨2点自动执行同步
- **AND** 使用现有定时任务框架

### Requirement: 网络异常处理
系统 SHALL 处理Swagger API网络不可达的情况。

#### Scenario: Swagger API访问失败
- **WHEN** Swagger API返回非200状态码或超时
- **THEN** 系统 SHALL 记录错误日志
- **AND** 系统 SHALL 返回同步失败状态
- **AND** 系统 SHALL 使用本地缓存数据（如有）继续服务
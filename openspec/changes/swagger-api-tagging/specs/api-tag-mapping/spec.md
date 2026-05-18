## ADDED Requirements

### Requirement: 接口标签存储
系统 SHALL 支持为每个接口存储多个标签。

#### Scenario: 存储接口标签
- **WHEN** 手动插入接口标签数据
- **THEN** 系统 SHALL 在 api_tag_mapping 表中存储 api_path 和 tag
- **AND** tag字段 SHALL 支持存储多个关键词，用 | 分隔（如 "客户|创建|保存"）

#### Scenario: 标签类型标识
- **WHEN** 存储标签时
- **THEN** 系统 SHALL 记录 tag_type 为 'manual'（手动打标）
- **AND** tag_type SHALL 支持 'auto'（自动打标，预留）

#### Scenario: 唯一性约束
- **WHEN** 插入重复的 api_path + tag 组合
- **THEN** 系统 SHALL 使用 ON DUPLICATE KEY UPDATE 更新现有记录
- **AND** 不会创建重复记录

### Requirement: 标签查询
系统 SHALL 支持按接口路径和标签查询。

#### Scenario: 按接口路径查询
- **WHEN** 查询某个接口的所有标签
- **THEN** 系统 SHALL 返回该接口的所有标签记录

#### Scenario: 按标签查询接口
- **WHEN** 查询某个标签关联的所有接口
- **THEN** 系统 SHALL 返回所有 tag 字段包含该关键词的接口

#### Scenario: 模糊匹配标签
- **WHEN** JIRA关键词需要匹配接口标签
- **THEN** 系统 SHALL 支持 LIKE 模糊匹配
- **AND** 匹配规则：关键词包含在标签中 OR 标签包含在关键词中

### Requirement: 标签数据管理
系统 SHALL 支持通过数据库直接管理标签数据。

#### Scenario: 新增标签
- **WHEN** 需要为某个接口新增标签
- **THEN** 运维 SHALL 直接在数据库执行 INSERT
- **AND** SQL格式: `INSERT INTO api_tag_mapping (api_path, tag, created_by) VALUES ('/v1/xxx.json', '标签', 'username')`

#### Scenario: 更新标签
- **WHEN** 需要更新某个接口的标签
- **THEN** 运维 SHALL 直接在数据库执行 UPDATE
- **AND** SQL格式: `UPDATE api_tag_mapping SET tag='新标签' WHERE api_path='/v1/xxx.json'`

#### Scenario: 批量导入标签
- **WHEN** 需要批量导入标签
- **THEN** 运维 SHALL 使用 CSV + LOAD DATA 或批量 INSERT
- **AND** 系统 SHALL 支持幂等操作（重复导入不重复创建）
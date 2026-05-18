## ADDED Requirements

### Requirement: JIRA关键词提取
系统 SHALL 继续从JIRA描述中提取关键词作为兜底数据源。

#### Scenario: 从JIRA描述提取关键词
- **WHEN** 分析JIRA问题时
- **THEN** 系统 SHALL 从 summary、description 等字段提取关键词
- **AND** 提取规则 SHALL 包括：API路径、类名、错误模式、业务术语

#### Scenario: 关键词分隔
- **WHEN** 提取到JIRA关键词
- **THEN** 系统 SHALL 对长文本进行分词处理
- **AND** 分词 SHALL 使用简单的中文分词或正则分隔

### Requirement: 关键词模糊匹配接口
系统 SHALL 使用JIRA关键词匹配接口标签，返回匹配的接口列表。

#### Scenario: 模糊匹配接口标签
- **WHEN** 有JIRA关键词列表
- **THEN** 系统 SHALL 查询 api_tag_mapping 表
- **AND** 匹配条件 SHALL 为：tag LIKE '%keyword%' OR keyword LIKE CONCAT('%', tag, '%')

#### Scenario: 返回多个匹配接口
- **WHEN** 多个接口的标签匹配到同一关键词
- **THEN** 系统 SHALL 返回所有匹配的 api_path
- **AND** 系统 SHALL 去重返回结果

#### Scenario: 关键词与标签双向匹配
- **WHEN** JIRA关键词为 "客户管理"
- **AND** 接口标签为 "客户"
- **THEN** 系统 SHALL 匹配成功（因为关键词包含标签）
- **WHEN** JIRA关键词为 "客户"
- **AND** 接口标签为 "客户管理"
- **THEN** 系统 SHALL 匹配成功（因为标签包含关键词）

### Requirement: 匹配结果传递给调用链分析
系统 SHALL 将匹配到的接口路径传递给JavaCallChainAnalyzer进行调用链分析。

#### Scenario: 有匹配接口时
- **WHEN** JIRA关键词匹配到至少一个接口
- **THEN** 系统 SHALL 获取 matched_apis 列表
- **AND** 系统 SHALL 将 matched_apis 赋值给 api_paths 字段
- **AND** 系统 SHALL 调用现有的调用链分析逻辑

#### Scenario: 无匹配接口时
- **WHEN** JIRA关键词未匹配到任何接口
- **THEN** 系统 SHALL 记录日志 "未匹配到接口，使用JIRA关键词直接搜索代码"
- **AND** 系统 SHALL fallback 到原有的关键词搜索逻辑

### Requirement: 匹配结果置信度
系统 SHALL 为匹配结果提供置信度参考。

#### Scenario: 计算匹配置信度
- **WHEN** 返回匹配接口时
- **THEN** 系统 SHALL 标记 matched_apis 的来源
- **AND** 如果多个关键词匹配到同一接口，置信度 SHALL 提高
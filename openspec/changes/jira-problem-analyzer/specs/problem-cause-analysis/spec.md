# problem-cause-analysis

## ADDED Requirements

### Requirement: Rule-Based Cause Analysis
The system SHALL analyze JIRA content using rule matching to identify possible problem causes.

#### Scenario: NullPointerException Detection
- **WHEN** JIRA content contains "NullPointerException" or "NPE"
- **THEN** system SHALL return cause category "空指针"
- **AND** suggestion SHALL include "检查对象是否为空"

#### Scenario: SQLException Detection
- **WHEN** JIRA content contains "SQLException" or database-related errors
- **THEN** system SHALL return cause category "数据库异常"
- **AND** suggestion SHALL include "检查数据库连接和 SQL 语句"

#### Scenario: Timeout Detection
- **WHEN** JIRA content contains "timeout" or "超时"
- **THEN** system SHALL return cause category "超时问题"
- **AND** suggestion SHALL include "检查接口响应时间和超时配置"

### Requirement: AI-Enhanced Analysis (Optional)
The system SHALL support AI-enhanced analysis when use_ai parameter is true.

#### Scenario: AI Analysis Enabled
- **WHEN** user sets `use_ai: true` and all required parameters are provided
- **THEN** system SHALL send combined context to LLM for analysis
- **AND** response SHALL include AI-generated suggestions

#### Scenario: AI Analysis Disabled
- **WHEN** user sets `use_ai: false` or does not provide it
- **THEN** system SHALL use only rule-based analysis
- **AND** response SHALL indicate `ai_enhanced: false`

### Requirement: Cause Categorization
The system SHALL categorize identified causes into standard categories.

#### Scenario: Cause Categories
- **WHEN** causes are identified
- **THEN** each cause SHALL have a category field
- **AND** category SHALL be one of: 空指针, 数据库异常, 超时问题, 业务逻辑错误, 配置错误, 未知
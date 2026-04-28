# jira-content-fetch

## ADDED Requirements

### Requirement: JIRA Issue Retrieval
The system SHALL fetch JIRA issue details including summary, description, status, and basic fields.

#### Scenario: Valid JIRA URL
- **WHEN** user provides a valid JIRA URL (e.g., `https://jira.souche-inc.com/browse/PROJ-123`)
- **THEN** system SHALL extract issue key from URL
- **AND** system SHALL return issue summary, description, status, and reporter

### Requirement: JIRA Comments Retrieval
The system SHALL fetch all comments associated with the JIRA issue.

#### Scenario: Issue with Comments
- **WHEN** JIRA issue has comments
- **THEN** system SHALL return list of comments with author and timestamp

#### Scenario: Issue without Comments
- **WHEN** JIRA issue has no comments
- **THEN** system SHALL return empty comments array

### Requirement: Keyword Extraction from JIRA
The system SHALL extract keywords from JIRA content to aid in code search.

#### Scenario: Extract API Paths
- **WHEN** JIRA description contains API paths (e.g., `/v1/customer/save`)
- **THEN** system SHALL extract these as keywords for code search

#### Scenario: Extract Class Names
- **WHEN** JIRA description contains Java class names (e.g., `CustomerService`)
- **THEN** system SHALL extract these as keywords for code search

#### Scenario: Extract Error Messages
- **WHEN** JIRA description contains error messages or stack traces
- **THEN** system SHALL extract error patterns as keywords
# jira-problem-analysis

## ADDED Requirements

### Requirement: JIRA URL as Primary Input
The system SHALL accept a JIRA URL as the only required input. All other parameters (repo, API path, trace ID) are optional.

#### Scenario: JIRA URL Only
- **WHEN** user provides only a valid JIRA URL
- **THEN** system fetches and displays the JIRA issue content
- **AND** analysis is limited to JIRA content only

#### Scenario: JIRA URL with Repo
- **WHEN** user provides JIRA URL and repo_key
- **THEN** system fetches JIRA content
- **AND** system searches codebase for relevant code based on JIRA keywords
- **AND** system performs cause analysis

#### Scenario: JIRA URL with Repo and API Path
- **WHEN** user provides JIRA URL, repo_key, and api_path
- **THEN** system fetches JIRA content
- **AND** system performs call chain analysis
- **AND** system combines results for comprehensive analysis

#### Scenario: JIRA URL with Repo and Trace ID
- **WHEN** user provides JIRA URL, repo_key, and trace_id
- **THEN** system fetches JIRA content
- **AND** system fetches trace data
- **AND** system searches codebase for relevant code
- **AND** system performs cause analysis

#### Scenario: JIRA URL with API Path but No Repo
- **WHEN** user provides JIRA URL and api_path but no repo_key
- **THEN** system returns an error message: "Repo is required when API path is provided"
- **AND** no analysis is performed

### Requirement: Analysis Result Output
The system SHALL return a unified response containing JIRA content, code context (if applicable), trace data (if applicable), and analysis results.

#### Scenario: Complete Analysis Result
- **WHEN** all optional parameters are provided
- **THEN** response SHALL contain jira, code_context, trace_data, and analysis sections

#### Scenario: Minimal Analysis Result
- **WHEN** only JIRA URL is provided
- **THEN** response SHALL contain only the jira section
# codebase-search

## ADDED Requirements

### Requirement: Full Codebase Search
The system SHALL search the entire codebase when repo is provided but API path is not.

#### Scenario: Search with Keywords
- **WHEN** repo_key is provided without api_path
- **THEN** system SHALL extract keywords from JIRA content
- **AND** system SHALL search Java files matching those keywords
- **AND** system SHALL return matching files with line numbers

#### Scenario: Search Scope Limitation
- **WHEN** searching codebase
- **THEN** search SHALL be limited to `web/src/main/java/**/*.java` files
- **AND** XML mapper files SHALL be excluded unless explicitly needed

### Requirement: Call Chain Search
The system SHALL perform call chain analysis when both repo and API path are provided.

#### Scenario: Full Call Chain Analysis
- **WHEN** repo_key and api_path are both provided
- **THEN** system SHALL perform call chain analysis as before
- **AND** results SHALL be included in code_context.call_chain

### Requirement: Search Result Format
The system SHALL return search results in a structured format.

#### Scenario: Search Results Structure
- **WHEN** code search returns results
- **THEN** each result SHALL contain file_path, matched_line, and line_number
- **AND** results SHALL be grouped by file
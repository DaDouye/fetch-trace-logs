# RAG-Enhanced AI Analysis

## ADDED Requirements

### Requirement: RAG-Enhanced AI Analysis
When AI analysis is enabled (`use_ai=true`), the system SHALL first query LightRAG for relevant context before calling Claude. Retrieved context SHALL be injected into the prompt.

### Requirement: Context Retrieval
The system SHALL retrieve up to 5 most relevant documents from LightRAG based on the current JIRA issue content. Retrieved documents SHALL include:
- Similar historical JIRA issues
- Related code files
- Relevant trace patterns

### Requirement: Enhanced Claude Prompt
The system SHALL construct an enhanced prompt containing:
- Original JIRA content (summary, description, customfield_19900)
- LightRAG retrieved context (similar issues, related code, trace patterns)
- Code search results
- Call chain analysis results

### Requirement: Graceful Degradation
If LightRAG retrieval fails or returns no results, the system SHALL proceed with standard AI analysis without RAG context. Error SHALL be logged but not propagated.
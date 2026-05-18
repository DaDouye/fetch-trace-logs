# LightRAG Indexer

## ADDED Requirements

### Requirement: Incremental JIRA Issue Indexing
The system SHALL automatically index JIRA issues when they are analyzed. Each issue's summary, description, customfield_19900, and extracted keywords SHALL be stored in the LightRAG vector store.

### Requirement: Trace Data Indexing
The system SHALL index Trace data including SQL statements, API paths (type=http-server), and error patterns. Indexing happens when trace data is successfully fetched.

### Requirement: Codebase Indexing
The system SHALL index Java source files (Controller, Service, DAO, etc.) for semantic search. Indexing is performed when code search results are generated.

### Requirement: Minimaxi Embedding Integration
The system SHALL use the minimaxi embedding API for vectorizing text. The embedding model SHALL be configured via environment variable or .env file.

### Requirement: Local Filesystem Storage
The system SHALL store LightRAG index data in `./lightrag_data` directory. Index data SHALL be rebuildable on service restart.

### Requirement: LightRAG Index Management
The system SHALL provide methods to:
- Initialize the vector store on startup
- Add documents to the index incrementally
- Query the index for similar documents
- Clear and rebuild the index on demand

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
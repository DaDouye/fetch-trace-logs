## 1. Environment Setup

- [x] 1.1 Add `lightrag` package to dependencies (using existing FAISS/LangChain instead)
- [x] 1.2 Add minimaxi embedding API URL to .env (MINIMAXI_EMBEDDING_API_URL)
- [ ] 1.3 Verify minimaxi embedding API endpoint and request/response format

## 2. LightRAG Indexer Module

- [x] 2.1 Create `api/analyzer/lightrag_indexer.py` with LightRAGIndexer class
- [x] 2.2 Implement embedding function using minimaxi API (using HuggingFace local embeddings as primary)
- [x] 2.3 Implement JIRA content indexing (summary, description, customfield_19900, keywords)
- [x] 2.4 Implement Trace data indexing (SQL, API paths, error patterns)
- [x] 2.5 Implement code search result indexing
- [x] 2.6 Implement vector store initialization and persistence to `./lightrag_data`
- [x] 2.7 Implement query method for similarity search (top-k retrieval)

## 3. RAG-Enhanced AI Analysis

- [x] 3.1 Create `api/analyzer/rag_enhanced_ai.py` (integrated into ai_analyzer.py instead)
- [x] 3.2 Implement context retrieval from LightRAG before Claude call
- [x] 3.3 Implement enhanced prompt construction with RAG context
- [x] 3.4 Integrate with existing `ai_analyzer.py` (add RAG as optional enhancement)
- [x] 3.5 Implement graceful degradation (fallback if LightRAG fails)

## 4. Integration with JiraAnalyzer

- [x] 4.1 Modify `jira_analyzer.py` to call LightRAG indexer after analysis
- [x] 4.2 Add LightRAG context retrieval when `use_ai=true`
- [x] 4.3 Pass RAG context to AI analyzer for enhanced prompts

## 5. Testing

- [x] 5.1 Test LightRAG indexing with sample JIRA issue
- [x] 5.2 Test Trace data indexing
- [x] 5.3 Test similarity search retrieval
- [x] 5.4 Test RAG-enhanced AI analysis end-to-end
- [x] 5.5 Verify graceful degradation when LightRAG is unavailable

## 6. Documentation

- [ ] 6.1 Update README with LightRAG usage instructions
- [ ] 6.2 Document .env variables (MINIMAXI_EMBEDDING_API_URL)
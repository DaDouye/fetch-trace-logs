## 1. Backend - JIRA Client Module

- [x] 1.1 Create `api/jira_client.py` with `JiraClient` class
- [x] 1.2 Implement `get_issue()` to fetch JIRA issue details
- [x] 1.3 Implement `get_comments()` to fetch issue comments
- [x] 1.4 Implement `extract_keywords()` to extract API paths, class names, error patterns from JIRA content
- [x] 1.5 Add JIRA authentication support (username/password or token)

## 2. Backend - Analysis Engine

- [x] 2.1 Create `api/analyzer/jira_analyzer.py` for unified analysis orchestration
- [x] 2.2 Create `api/analyzer/rule_engine.py` for rule-based cause analysis
- [x] 2.3 Define rule patterns for common error categories (NullPointer, SQLException, Timeout, etc.)
- [x] 2.4 Create `api/analyzer/code_search.py` for codebase keyword search
- [x] 2.5 Implement `search_codebase()` function with scope limitation to `web/src/main/java/**/*.java`
- [x] 2.6 Add optional AI enhancement support (call LLM when use_ai=true) - Reserved for future

## 3. Backend - New API Endpoint

- [x] 3.1 Add `POST /api/analyze-jira` endpoint to `api_server.py`
- [x] 3.2 Implement input validation (jira_url required, repo required if api_path provided)
- [x] 3.3 Implement input/output matrix logic per design spec
- [x] 3.4 Return unified response with jira, code_context, trace_data, analysis sections
- [x] 3.5 Add error handling for JIRA connection failures

## 4. Backend - Integration

- [x] 4.1 Integrate `JavaCallChainAnalyzer` for call chain analysis when api_path provided
- [x] 4.2 Integrate trace data fetching when trace_id provided
- [x] 4.3 Ensure existing `POST /api/analyze` remains unchanged (backward compatible)

## 5. Frontend - API Layer

- [x] 5.1 Update `frontend/src/api/index.js` - add `analyzeJira(params)` function
- [x] 5.2 Map new API response to frontend data structure

## 6. Frontend - Store

- [x] 6.1 Refactor `frontend/src/stores/analyzer.js`
- [x] 6.2 Add `jiraUrl` state and validation
- [x] 6.3 Add `analyzeJira(params)` action
- [x] 6.4 Support new response structure (jira, code_context, analysis)

## 7. Frontend - Form Component

- [x] 7.1 Create `JiraAnalysisForm.vue` with JIRA URL as required field
- [x] 7.2 Change JIRA URL input to required field with validation
- [x] 7.3 Change Repo dropdown to optional
- [x] 7.4 Change API Path input to optional
- [x] 7.5 Update optional fields (Trace ID, Date, Cookies)
- [x] 7.6 Add "Use AI Enhancement" checkbox

## 8. Frontend - Analysis View Component

- [x] 8.1 Create `frontend/src/components/JiraAnalysisView.vue`
- [x] 8.2 Display JIRA issue content (summary, description, status, comments)
- [x] 8.3 Display possible causes and suggestions
- [x] 8.4 Display code search results (file list with matched lines)
- [x] 8.5 Display call chain (reusing TreeView/AsciiView/GraphView)
- [x] 8.6 Display trace data summary if available

## 9. Frontend - App Integration

- [x] 9.1 Update `frontend/src/App.vue` to use new JiraAnalysisForm
- [x] 9.2 Update tab/view structure to show JiraAnalysisView
- [x] 9.3 Maintain backward compatibility with existing call chain views (preserved as separate tab)

## 10. Testing & Documentation

- [x] 10.1 Update README.md with new JIRA analysis usage instructions
- [ ] 10.2 Test full flow with sample JIRA issue
- [ ] 10.3 Verify all input combinations work per matrix

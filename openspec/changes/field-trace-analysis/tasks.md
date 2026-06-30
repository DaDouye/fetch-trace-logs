## 1. Backend - FieldTracer core

- [x] 1.1 Create `api/analyzer/field_tracer.py` with `FieldTracer` class skeleton, inheriting from or composing `JavaCallChainAnalyzer` to reuse file reading, repo management, Service/Mapper lookup methods
- [x] 1.2 Implement `locate_entry()` - locate Controller method by api_path or method_name, reuse existing `_find_controller_method` logic, add method_name-based search
- [x] 1.3 Implement `parse_return_type()` - extract return type from Controller method signature, unwrap `Result<T>` generic to get DTO class name, resolve DTO file path
- [x] 1.4 Implement `resolve_json_path()` - parse JSON field path (dot-separated with array index support), map each segment through wrapper classes and DTO fields, handle `@JsonProperty` annotations
- [x] 1.5 Implement `find_field_assignments()` - search Service layer for 6 assignment patterns (setter, builder, constructor, copyProperties, MapStruct, direct assignment) for the target DTO field
- [x] 1.6 Implement `trace_to_source()` - trace assignment right-hand side to Entity field, resolve Mapper method, extract SQL from MyBatis XML or `@Select` annotation, map to DB table/column
- [x] 1.7 Implement speculative matching for BeanUtils/MapStruct scenarios - compare source and target class fields by name/type, mark results as speculative

## 2. Backend - API endpoint

- [x] 2.1 Add `FieldAnalysisRequest` Pydantic model and `POST /api/analysis` endpoint in `api_server.py` with input validation (project_name required, api_path or method_name required)
- [x] 2.2 Wire up the endpoint to `FieldTracer`, handle errors (400/404/500) with appropriate messages
- [ ] 2.3 Test the endpoint manually with sample requests

## 3. Frontend - API layer and router

- [x] 3.1 Add `analyzeField()` API function in `frontend/src/api/index.js`
- [x] 3.2 Add `/analysis` route in `frontend/src/router/index.js`

## 4. Frontend - Components

- [x] 4.1 Create `frontend/src/pages/FieldAnalysisPage.vue` with page layout (title, form area, result area)
- [x] 4.2 Create `frontend/src/components/FieldAnalysisForm.vue` with project dropdown (from GET /api/repos), api_path input, method_name input, field_path input, and submit button with validation
- [x] 4.3 Create `frontend/src/components/FieldTraceView.vue` with breadcrumb/timeline visualization showing trace chain from JSON path to SQL, code snippet display, speculative match indicators

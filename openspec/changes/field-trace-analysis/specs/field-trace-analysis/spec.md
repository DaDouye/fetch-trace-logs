## ADDED Requirements

### Requirement: Field trace analysis input validation
The system SHALL accept a POST request to `/api/analysis` with a JSON body containing `project_name` (required), `api_path` (optional), `method_name` (optional), and `field_path` (optional). At least one of `api_path` or `method_name` MUST be provided.

#### Scenario: Valid input with api_path
- **WHEN** user submits `{"project_name": "superMario", "api_path": "/v1/customer/getById", "field_path": "data.userId"}`
- **THEN** system accepts the request and starts field trace analysis

#### Scenario: Valid input with method_name
- **WHEN** user submits `{"project_name": "superMario", "method_name": "getCustomerById", "field_path": "data.userId"}`
- **THEN** system accepts the request and starts field trace analysis

#### Scenario: Missing both api_path and method_name
- **WHEN** user submits `{"project_name": "superMario", "field_path": "data.userId"}` without api_path or method_name
- **THEN** system returns 400 error with message indicating at least one of api_path or method_name is required

#### Scenario: Missing project_name
- **WHEN** user submits `{"api_path": "/v1/customer/getById"}` without project_name
- **THEN** system returns 400 error with message indicating project_name is required

### Requirement: Controller method location
The system SHALL locate the Controller class and method based on the provided `api_path` or `method_name` by searching Java source files in the project repository.

#### Scenario: Found by api_path
- **WHEN** a valid api_path is provided and matches a Spring MVC mapping annotation
- **THEN** system returns the controller class name, method name, file path, and line number

#### Scenario: Found by method_name
- **WHEN** a valid method_name is provided and matches a public method in a Controller class
- **THEN** system returns the controller class name, method name, file path, and line number

#### Scenario: Not found
- **WHEN** the api_path or method_name cannot be matched to any Controller method
- **THEN** system returns 404 error with message indicating the controller method was not found

### Requirement: Return type parsing and Result wrapper unwrapping
The system SHALL parse the return type of the located Controller method and unwrap the `Result<T>` generic wrapper to identify the actual DTO/VO class.

#### Scenario: Result wrapper with DTO
- **WHEN** Controller method returns `Result<CustomerVO>` and field_path starts with "data."
- **THEN** system skips the "data" path segment (mapped to Result.data) and resolves CustomerVO as the DTO class

#### Scenario: Non-Result return type
- **WHEN** Controller method returns a non-Result type (e.g., plain String or ResponseEntity)
- **THEN** system directly uses the return type as the DTO class without unwrapping

### Requirement: JSON path to DTO field mapping
The system SHALL map a JSON field path to the corresponding DTO class field, handling Jackson annotations and naming conventions.

#### Scenario: Simple dot path
- **WHEN** field_path is "data.userId" and CustomerVO has a field `private String userId`
- **THEN** system identifies CustomerVO.userId as the target field

#### Scenario: Array index path
- **WHEN** field_path is "data.list[0].name" and CustomerVO has a `List<ItemVO> list` field, and ItemVO has a `name` field
- **THEN** system resolves through the List type to ItemVO, then identifies ItemVO.name as the target field

#### Scenario: JsonProperty annotation
- **WHEN** DTO field has `@JsonProperty("user_name")` and field_path references "user_name"
- **THEN** system correctly maps the JSON name to the Java field

### Requirement: Field assignment tracking in Service layer
The system SHALL search Service implementation methods for assignments to the target DTO field using 6 identification patterns: setter, builder, constructor, BeanUtils.copyProperties, MapStruct mapping, and direct field assignment.

#### Scenario: Setter pattern detected
- **WHEN** Service code contains `vo.setUserId(entity.getId())`
- **THEN** system identifies this as the assignment point and parses the parameter `entity.getId()`

#### Scenario: Builder pattern detected
- **WHEN** Service code contains `.userId(entity.getId()).build()`
- **THEN** system identifies the builder chain assignment for the userId field

#### Scenario: BeanUtils copyProperties detected
- **WHEN** Service code contains `BeanUtils.copyProperties(entity, vo)` and both have a field named "userId"
- **THEN** system identifies this as a copyProperties assignment and marks it as `[推测]` with matching field details

#### Scenario: No assignment found in immediate Service
- **WHEN** target field is not assigned in the directly called Service method
- **THEN** system recursively searches called sub-services and internal methods

### Requirement: Data source tracing to Entity and database
The system SHALL trace the assignment's right-hand side to identify the data source, continuing through Entity classes to database table columns and SQL statements.

#### Scenario: Trace through Entity getter
- **WHEN** assignment is `vo.setUserId(entity.getId())` and CustomerEntity has `private Long id` with `@TableField("id")`
- **THEN** system identifies CustomerEntity.id as the data source, mapped to DB column `id`

#### Scenario: Trace to MyBatis XML SQL
- **WHEN** data source is CustomerEntity.id and CustomerMapper has a selectById method
- **THEN** system extracts the corresponding SQL from CustomerMapper.xml: `SELECT id, ... FROM t_customer WHERE id = #{id}`

#### Scenario: Trace to MyBatis annotation SQL
- **WHEN** data source is an Entity field and the Mapper method uses `@Select` annotation instead of XML
- **THEN** system extracts the SQL from the annotation

#### Scenario: Computed/transformed value
- **WHEN** assignment is `vo.setFullName(entity.getFirstName() + " " + entity.getLastName())`
- **THEN** system identifies it as a computed value from multiple source fields and lists all contributing fields

### Requirement: Field trace result presentation
The system SHALL return a structured result containing the complete trace chain from JSON path to database source.

#### Scenario: Complete trace chain
- **WHEN** field trace analysis completes successfully
- **THEN** result includes a trace chain with entries for: JSON path segment, wrapper class (if applicable), DTO field definition, assignment point(s), data source Entity field, DB column mapping, and SQL statement

#### Scenario: Partial trace (incomplete chain)
- **WHEN** some steps in the trace chain cannot be resolved (e.g., Service assignment not found)
- **THEN** result includes all successfully traced steps and indicates where the trace stopped with reason

### Requirement: Frontend field analysis page
The system SHALL provide a frontend page at `/analysis` with a form for input parameters and a visualization of the trace result.

#### Scenario: Form submission
- **WHEN** user fills in project name, api_path or method_name, and field path, then submits
- **THEN** the trace result is displayed showing the complete field lineage

#### Scenario: Project list loading
- **WHEN** the page loads
- **THEN** available project repositories are loaded from GET /api/repos and displayed in a dropdown selector

#### Scenario: Breadcrumb trace visualization
- **WHEN** trace result is displayed
- **THEN** the lineage is shown as a breadcrumb/timeline from JSON path down to SQL, with each node showing file location and code snippet

#### Scenario: Speculative match indication
- **WHEN** a step is based on speculative matching (BeanUtils/MapStruct)
- **THEN** the visualization clearly marks it with a visual indicator (dashed border or question mark icon) and shows the matching evidence
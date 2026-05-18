## 1. 数据库准备

- [x] 1.1 创建 api_tag_mapping 表 (在 api/swagger_client.py 中通过 _init_database 初始化)
- [x] 1.2 创建 swagger_api_sync_log 表 (在 api/swagger_client.py 中通过 _init_database 初始化)

## 2. Swagger同步模块

- [x] 2.1 新建 api/swagger_client.py - SwaggerClient类
- [x] 2.2 实现 fetch_api_groups() - 获取所有API分组
- [x] 2.3 实现 fetch_api_details() - 获取分组下API详情
- [x] 2.4 实现 sync_to_database() - 同步到api_tag_mapping表
- [x] 2.5 添加网络异常处理和日志记录
- [x] 2.6 首次同步测试 - 从Swagger获取所有接口 (342 APIs synced)

## 3. 手动打标

- [x] 3.1 编写打标SQL示例文档 (内嵌在swagger_client.py的main函数中)
- [x] 3.2 手动对高频接口打标（预约、客户、公海、意向相关）(35 APIs tagged)

## 4. JIRA关键词匹配改造

- [x] 4.1 在 api/jira_client.py 添加 match_apis_from_db() 方法
- [x] 4.2 修改 extract_keywords() 返回 matched_apis
- [x] 4.3 在 api/analyzer/jira_analyzer.py 使用 matched_apis 替换原有搜索逻辑

## 5. 端到端测试

- [x] 5.1 同步一批API接口到数据库
- [x] 5.2 手动打标几个接口
- [x] 5.3 用一个JIRA问题测试 - 验证关键词能匹配到接口 (匹配成功)
- [ ] 5.4 验证调用链分析和AI分析正常工作

## 6. 文档和部署

- [ ] 6.1 编写打标操作手册（SQL示例）
- [ ] 6.2 更新 README 或相关文档

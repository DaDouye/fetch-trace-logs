## 1. 准备阶段

- [x] 1.1 确认目标表已存在（MySQL 连接权限验证）
- [x] 1.2 确认 .config 中 JIRA_USERNAME / JIRA_PASSWORD / JIRA_BASE_URL 已配置

## 2. 脚本实现

- [x] 2.1 创建 `scripts/fetch_onlinebugs_2025.py`，包含：
  - 加载 .config 环境变量
  - 使用 JiraClient 拉取 JQL 分页结果
  - 对每条 issue 单独调用 get_comments 并拼装 JSON
  - 使用 pymysql 写入 MySQL（INSERT ... ON DUPLICATE KEY UPDATE）
- [x] 2.2 实现重试逻辑（API 超时/5xx，最多 3 次，间隔 1 秒）
- [x] 2.3 处理 customfield_19900 为 NULL 的情况
- [x] 2.4 处理评论为空存 `[]` 的情况

## 3. 测试验证

- [x] 3.1 在测试库执行脚本，验证数据行数 ≈ 1507
- [x] 3.2 抽样检查 `online_desc` 和 `comments` 字段内容完整
- [x] 3.3 确认 comments JSON 格式可解析
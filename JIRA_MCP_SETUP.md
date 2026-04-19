# Jira MCP (Model Context Protocol) 配置

此配置允许 Claude Code 与您的 Jira 服务器集成，通过 Model Context Protocol 提供以下功能：

- 查询和创建 Jira 问题
- 获取项目信息
- 用户信息访问

## 配置步骤

1. 将环境变量添加到您的 shell 配置中：
   ```bash
   export JIRA_USERNAME="yexiaojiao"
   export JIRA_PASSWORD="123456"
   ```

2. 确保您可以访问 Jira 服务器：https://jira.souche-inc.com/

## 使用方法

一旦配置完成，Claude 将能够：
- 根据上下文自动查找相关的 Jira 问题
- 创建新的问题或更新现有问题
- 提供项目和用户信息

## 安全注意事项

- 请确保您的凭据安全，不要将包含敏感信息的文件提交到版本控制
- 使用专用的 API 令牌而不是主密码（如果 Jira 支持）

## 故障排除

如果遇到连接问题，请检查：
- 网络连接到 Jira 服务器
- 认证凭据是否正确
- 您是否有权限访问请求的数据
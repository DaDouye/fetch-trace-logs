# 设置Jira认证信息

要运行Jira获取脚本，您需要设置以下环境变量：

```bash
export JIRA_USERNAME="yexiaojiao"
export JIRA_PASSWORD="123456"
```

然后您可以运行脚本来获取问题信息：

```bash
./scripts/fetch_jira_issue.sh ONLINEBUG-15935
```

或者直接运行Python脚本：

```bash
python3 ./scripts/fetch_jira_souche.py ONLINEBUG-15935
```

## 获取API令牌（如果使用API令牌认证）

如果您的Jira实例要求使用API令牌而不是密码：

1. 登录到您的Jira实例
2. 前往账户设置
3. 找到"安全"或"API令牌"部分
4. 生成新的API令牌
5. 在环境变量中使用API令牌代替密码

## 故障排除

如果出现401错误（认证失败）：
- 检查用户名和密码是否正确
- 确认您的账户具有访问指定问题的权限
- 如果使用API令牌，请确保使用正确的格式

如果出现404错误（未找到）：
- 确认问题键（如ONLINEBUG-15935）拼写正确
- 确认问题存在于指定的Jira实例中
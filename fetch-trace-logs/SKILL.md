---
name: fetch-trace-logs
description: 从 Souche 链路追踪系统获取并分析链路日志。从分布式链路中提取 SQL 查询及其执行详情，用于调试和分析。
---

# 获取链路日志 (Fetch Trace Logs)

从 Souche 链路追踪系统获取并分析链路日志。从分布式链路中提取 SQL 查询及其执行详情，用于调试和分析。

## 快速开始

获取链路日志需要：
1. Souche 链路追踪系统的访问权限和有效的 cookies
2. 链路 ID (Trace ID)
3. 日期 (YYYY-MM-DD 格式)

## 基本用法

### 根据链路 ID 获取

```bash
python ~/.qoder/skills/fetch-trace-logs/scripts/fetch_trace_souche.py \
  --trace-id 1774764304798_AKFw \
  --date 2026-03-29
```

### 使用自定义 Cookies

```bash
python ~/.qoder/skills/fetch-trace-logs/scripts/fetch_trace_souche.py \
  --trace-id 1774764304798_AKFw \
  --date 2026-03-29 \
  --cookies "_user_iid=xxx; JSESSIONID=xxx"
```

### 获取 Souche 主机信息

```bash
python ~/.qoder/skills/fetch-trace-logs/scripts/fetch_trace_souche.py --souche-host
```

## 输出

脚本输出一个包含 SQL 详情的 JSON 文件：
- **文件名格式**: `trace_{trace_id}_{yyyyMMddHHmmss}_sql_details.json`
- **保存位置**: 桌面 (默认) 或通过 `--output-dir` 指定

### 输出结构

```json
{
  "summary": {
    "trace_id": "1774764304798_AKFw",
    "date": "2026-03-29",
    "sql_count": 59,
    "detail_count": 59,
    "generated_at": "2026-03-29T14:30:45.123456"
  },
  "sql_details": [
    {
      "rid": "1774764304798_AKFw-1.3.1.1",
      "detail": {
        "sql": "SELECT id, name FROM users WHERE id = '12345'"
      }
    }
  ]
}
```

## 配置

### 默认参数 (在脚本中)

编辑脚本中的以下值来设置默认值：

```python
DEFAULT_ENDPOINT = "https://trace.souche-inc.com"
DEFAULT_TRACE_ID = "your_trace_id"
DEFAULT_DATE = "2026-03-29"

# Cookie 参数
DEFAULT_USER_IID = "your_user_id"
DEFAULT_TRACKNICK = "your_nickname"
DEFAULT_SECURITY_TOKEN = "your_token"
DEFAULT_ACW_TC = "your_acw_tc"
DEFAULT_JSESSIONID = "your_session_id"
```

## 常见工作流程

### 从链路中提取 SQL 查询

1. 从应用日志或监控中获取链路 ID
2. 使用链路 ID 和日期运行脚本
3. 查看生成的 `*_sql_details.json` 文件
4. 分析 SQL 查询的性能问题

### 调试 SQL 性能

```bash
# 从链路中提取所有 SQL
python scripts/fetch_trace_souche.py \
  --trace-id 1774764304798_AKFw \
  --date 2026-03-29

# 输出将保存到桌面：
# trace_1774764304798_AKFw_20260329143045_sql_details.json
```

## 命令行选项

| 选项 | 说明 | 默认值 |
|----------|-------------|---------|
| `--endpoint` | Souche 链路追踪 API 端点 | https://trace.souche-inc.com |
| `--trace-id` | 要获取的链路 ID | (来自 DEFAULT_TRACE_ID) |
| `--date` | 链路日期 (YYYY-MM-DD) | (来自 DEFAULT_DATE) |
| `--cookies` | 用于认证的 Cookies | (从默认值自动生成) |
| `--insecure` | 禁用 SSL 验证 | False |
| `--output-dir` | 输出目录 | ~/Desktop |
| `--no-extract-sql` | 禁用 SQL 提取 | False |
| `--souche-host` | 获取主机信息 | - |

## 认证

脚本需要 Souche 链路追踪系统的有效 cookies。你可以通过以下方式设置：

1. **在脚本中设置默认值**: 编辑 `DEFAULT_*` 变量
2. **通过命令行传递**: 使用 `--cookies` 参数
3. **浏览器开发者工具**: 登录链路追踪系统后从浏览器复制 cookies

## 其他资源

- API 详情参见 [reference.md](reference.md)
- 使用示例参见 [examples.md](examples.md)

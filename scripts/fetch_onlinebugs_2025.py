#!/usr/bin/env python3
"""
Jira ONLINEBUG 2026 上半年数据 ETL
一次性拉取 2026-01-01 至 2026-06-30 的 ONLINEBUG 项目缺陷数据，
落库至 MySQL jira_online_issue_2026_up 表。
"""
import os
import sys
import json
import time
import random
from datetime import datetime
from pathlib import Path

import requests
import pymysql
from requests.auth import HTTPBasicAuth

# 加载 .config 环境变量（与 fetch_jira_souche.py 保持一致）
env_path = Path(__file__).parent.parent / '.config'
if env_path.exists():
    try:
        import dotenv
        dotenv.load_dotenv(dotenv_path=env_path)
    except ImportError:
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip().strip('"\'')


JIRA_BASE_URL = os.getenv('JIRA_BASE_URL', 'https://jira.souche-inc.com/')
JIRA_USERNAME = os.getenv('JIRA_USERNAME')
JIRA_PASSWORD = os.getenv('JIRA_PASSWORD')

MYSQL_HOST = os.getenv('MYSQL_HOST', 'test.database3500.scsite.net')
MYSQL_PORT = int(os.getenv('MYSQL_PORT', '3500'))
MYSQL_USER = os.getenv('MYSQL_USER', 'souche_rw')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD', 'Ewm3prj6WRcwbv4x')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE', 'super_mario')

TARGET_TABLE = "jira_online_issue_2026_up"
DATE_RANGE_LABEL = "2026 上半年"
JQL = "project = ONLINEBUG AND issuetype = 缺陷 AND created >= 2026-01-01 AND created <= 2026-06-30"
MAX_RESULTS_PER_PAGE = 50
MAX_RETRIES = 3
RETRY_DELAY = 1


def build_mysql_connection():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )


def ensure_table_exists(conn):
    """建表语句（IF NOT EXISTS）"""
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS {TARGET_TABLE} (
        id            VARCHAR(32)   PRIMARY KEY,
        project       VARCHAR(32),
        issue_num     INTEGER,
        summary       TEXT,
        status        VARCHAR(32),
        assignee      VARCHAR(128),
        reporter      VARCHAR(128),
        created_date  DATETIME,
        online_desc   TEXT,
        comments      TEXT,
        fetched_at    DATETIME DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """
    with conn.cursor() as cur:
        cur.execute(create_sql)
    conn.commit()


def parse_issue_key(key):
    """从 ONLINEBUG-XXXXX 拆分 project 和 issue_num"""
    parts = key.split('-', 1)
    project = parts[0] if len(parts) > 0 else key
    try:
        issue_num = int(parts[1]) if len(parts) > 1 else None
    except ValueError:
        issue_num = None
    return project, issue_num


def jira_request(method, url, **kwargs):
    """带重试的 Jira API 请求"""
    auth = HTTPBasicAuth(str(JIRA_USERNAME), str(JIRA_PASSWORD))
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    kwargs.setdefault('timeout', 60)

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.request(method, url, headers=headers, auth=auth, **kwargs)
            if response.status_code < 500:
                return response
        except requests.exceptions.RequestException as e:
            if attempt == MAX_RETRIES - 1:
                raise
            time.sleep(RETRY_DELAY * (attempt + 1))
            continue

        if attempt < MAX_RETRIES - 1:
            time.sleep(RETRY_DELAY * (attempt + 1))

    return response


def get_issue_with_fields(issue_key, fields=None):
    """获取单个 issue 详情"""
    field_str = fields or "*all"
    url = f"{JIRA_BASE_URL}/rest/api/2/issue/{issue_key}?fields={field_str}"
    response = jira_request('GET', url)
    if response.status_code == 200:
        return response.json()
    elif response.status_code == 404:
        return None
    else:
        raise Exception(f"Failed to fetch issue {issue_key}: {response.status_code} {response.text}")


def get_comments(issue_key):
    """获取 issue 的所有评论"""
    url = f"{JIRA_BASE_URL}/rest/api/2/issue/{issue_key}/comment"
    response = jira_request('GET', url)
    if response.status_code == 200:
        data = response.json()
        return data.get('comments', [])
    else:
        raise Exception(f"Failed to fetch comments for {issue_key}: {response.status_code} {response.text}")


def search_issues(jql, start_at=0, max_results=50, fields=None):
    """JQL 搜索（单页）"""
    from urllib.parse import quote
    encoded_jql = quote(jql, safe='')
    url = f"{JIRA_BASE_URL}/rest/api/2/search?jql={encoded_jql}&startAt={start_at}&maxResults={max_results}"
    if fields:
        url += "&fields=" + ",".join(fields)

    response = jira_request('GET', url)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"JQL search failed: {response.status_code} {response.text}")


def paginated_search(jql, max_results_per_page=50):
    """分页搜索 generator"""
    start_at = 0
    while True:
        results = search_issues(jql, start_at=start_at, max_results=max_results_per_page)
        issues = results.get('issues', [])
        if not issues:
            break
        for issue in issues:
            yield issue
        if len(issues) < max_results_per_page:
            break
        start_at += len(issues)


def extract_fields(issue_data):
    """从 Jira API 返回提取需要存储的字段"""
    fields = issue_data.get('fields', {})
    key = issue_data.get('key', '')

    project, issue_num = parse_issue_key(key)

    # 处理 assignee/reporter（可能是 None）
    assignee_name = ''
    if fields.get('assignee'):
        assignee_name = fields['assignee'].get('displayName', '') or fields['assignee'].get('name', '')

    reporter_name = ''
    if fields.get('reporter'):
        reporter_name = fields['reporter'].get('displayName', '') or fields['reporter'].get('name', '')

    # created_date 处理
    created_raw = fields.get('created', '')
    try:
        # 转换 Jira ISO 格式为 MySQL DATETIME 格式
        created_date = created_raw.replace('Z', '+00:00')
        if created_date:
            created_date = created_date[:19]  # 2026-01-01T00:00:00+00:00 -> 2026-01-01T00:00:00
    except (ValueError, TypeError):
        created_date = None

    # online_desc = customfield_19900
    online_desc = fields.get('customfield_19900') or ''

    # status 处理
    status_val = fields.get('status')
    if isinstance(status_val, dict):
        status = status_val.get('name', '') or ''
    else:
        status = status_val or ''

    return {
        'id': key,
        'project': project,
        'issue_num': issue_num,
        'summary': fields.get('summary', '') or '',
        'status': status,
        'assignee': assignee_name,
        'reporter': reporter_name,
        'created_date': created_date,
        'online_desc': online_desc,
    }


def insert_issue(conn, issue_data, comments_list):
    """插入或更新单条 issue（含评论）"""
    comments_json = json.dumps(comments_list, ensure_ascii=False)

    sql = f"""
    INSERT INTO {TARGET_TABLE}
        (id, project, issue_num, summary, status, assignee, reporter, created_date, online_desc, comments, fetched_at)
    VALUES
        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
    ON DUPLICATE KEY UPDATE
        project       = VALUES(project),
        issue_num     = VALUES(issue_num),
        summary       = VALUES(summary),
        status        = VALUES(status),
        assignee      = VALUES(assignee),
        reporter      = VALUES(reporter),
        created_date  = VALUES(created_date),
        online_desc   = VALUES(online_desc),
        comments      = VALUES(comments),
        fetched_at    = VALUES(fetched_at);
    """

    with conn.cursor() as cur:
        cur.execute(sql, (
            issue_data['id'],
            issue_data['project'],
            issue_data['issue_num'],
            issue_data['summary'],
            issue_data['status'],
            issue_data['assignee'],
            issue_data['reporter'],
            issue_data['created_date'],
            issue_data['online_desc'],
            comments_json,
        ))
    conn.commit()


def main():
    if not JIRA_USERNAME or not JIRA_PASSWORD:
        print("Error: JIRA_USERNAME and JIRA_PASSWORD must be set in .config or environment variables.")
        sys.exit(1)

    print(f"[{datetime.now().isoformat()}] 开始拉取 Jira ONLINEBUG {DATE_RANGE_LABEL} 数据")
    print(f"JQL: {JQL}")

    # 1. 建表
    conn = build_mysql_connection()
    try:
        ensure_table_exists(conn)
        print(f"目标表 {TARGET_TABLE} 就绪")
    finally:
        conn.close()

    # 2. 分页拉取 issues
    fetched_count = 0
    error_count = 0

    print("开始分页拉取 issues...")
    for issue in paginated_search(JQL, max_results_per_page=MAX_RESULTS_PER_PAGE):
        key = issue.get('key', '')
        if not key:
            continue

        try:
            # 额外请求：获取完整 fields（含 customfield_19900）和评论
            full_issue = get_issue_with_fields(key)
            if not full_issue:
                print(f"  [WARN] Issue {key} not found, skip")
                continue

            comments = get_comments(key)
            comments_formatted = [
                {
                    'author': c.get('author', {}).get('displayName', '') or '',
                    'body': c.get('body', '') or '',
                    'created': c.get('created', '') or ''
                }
                for c in comments
            ]

            issue_data = extract_fields(full_issue)

            conn = build_mysql_connection()
            try:
                insert_issue(conn, issue_data, comments_formatted)
                fetched_count += 1
                if fetched_count % 50 == 0:
                    print(f"  已处理 {fetched_count} 条...")
            finally:
                conn.close()

        except Exception as e:
            error_count += 1
            print(f"  [ERROR] 处理 {key} 时出错: {e}")
            continue

        # 限流
        time.sleep(0.5 + random.uniform(0, 0.2))

    print(f"\n[{datetime.now().isoformat()}] 完成")
    print(f"成功: {fetched_count}, 失败: {error_count}")
    print(f"目标表 {TARGET_TABLE} 数据已就绪")


if __name__ == "__main__":
    main()

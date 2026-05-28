#!/usr/bin/env python3
"""
Fetch logs from Optimus log platform (log-eye.souche-inc.com).
"""

import argparse
import json
import os
import sys
import ssl
import re
from datetime import datetime
from typing import Optional, List, Dict, Any
from urllib.parse import quote

import urllib.request
import urllib.error


class LogFetcher:
    """A class to fetch logs from Optimus log platform."""

    def __init__(self, cookies: Optional[str] = None, verify_ssl: bool = True):
        """Initialize the LogFetcher.

        Args:
            cookies: Optional cookies string for authentication
            verify_ssl: Whether to verify SSL certificates
        """
        self.endpoint = "https://log-eye.souche-inc.com"
        self.cookies = cookies or os.getenv("LOG_COOKIES") or os.getenv("TRACE_COOKIES") or os.getenv("SOUCHE_TRACE_COOKIES")
        self.verify_ssl = verify_ssl
        self.last_error = None

    def fetch_logs(
        self,
        app_code: str,
        env: str,
        level: str = "ERROR",
        content: str = "",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        page_num: int = 0,
        page_size: int = 50,
        namespace: str = "souche",
        node_name: str = "",
        clazz: str = "",
        thread: str = "",
        sort: str = "desc"
    ) -> Dict[str, Any]:
        """Fetch logs from Optimus platform.

        Args:
            app_code: Application code (e.g., "super-mario")
            env: Environment (e.g., "prod", "test")
            level: Log level filter (e.g., "ERROR", "INFO,WARN,ERROR")
            content: Log content keyword search
            start_time: Start timestamp in milliseconds
            end_time: End timestamp in milliseconds
            page_num: Page number (0-indexed)
            page_size: Number of logs per page
            namespace: Namespace (default "souche")
            node_name: Specific node/container name
            clazz: Class name filter
            thread: Thread name filter
            sort: Sort order ("desc" or "asc")

        Returns:
            Log response as dictionary
        """
        url = f"{self.endpoint}/query/logs"

        # Build request body
        request_body = {
            "namespace": namespace,
            "appCode": app_code,
            "env": env,
            "level": level,
            "thread": thread,
            "content": content,
            "sort": sort,
            "pageNum": page_num,
            "pageSize": page_size,
            "nodeName": node_name,
            "clazz": clazz
        }

        # Add time range if provided
        if start_time:
            request_body["startTime"] = start_time
        if end_time:
            request_body["endTime"] = end_time

        return self._make_request(url, request_body)

    def fetch_error_logs(
        self,
        app_code: str,
        env: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        content: str = "",
        page_size: int = 50,
        namespace: str = "souche"
    ) -> Dict[str, Any]:
        """Fetch error logs (ERROR level only).

        Args:
            app_code: Application code
            env: Environment
            start_time: Start timestamp in milliseconds
            end_time: End timestamp in milliseconds
            content: Additional content filter
            page_size: Number of logs per page
            namespace: Namespace

        Returns:
            Log response as dictionary
        """
        return self.fetch_logs(
            app_code=app_code,
            env=env,
            level="ERROR",
            content=content,
            start_time=start_time,
            end_time=end_time,
            page_size=page_size,
            namespace=namespace,
            sort="desc"
        )

    def _make_request(self, url: str, request_body: Dict[str, Any]) -> Dict[str, Any]:
        """Make HTTP POST request and return JSON response.

        Args:
            url: The URL to request
            request_body: Request body as dictionary

        Returns:
            The JSON response as a dictionary
        """
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": "https://logplatform.souche-inc.com",
            "Referer": "https://logplatform.souche-inc.com/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "priority": "u=1, i"
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(request_body).encode('utf-8'),
            headers=headers,
            method='POST'
        )

        self.last_error = None

        if self.cookies:
            req.add_header("Cookie", self.cookies)

        try:
            if self.verify_ssl:
                with urllib.request.urlopen(req, timeout=60) as response:
                    content = response.read().decode('utf-8')
            else:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, timeout=60, context=ctx) as response:
                    content = response.read().decode('utf-8')

            if not content or content.strip() == '':
                self.last_error = {
                    "type": "empty_response",
                    "message": "日志平台返回空内容"
                }
                return {"success": False, "error": "Empty response from log platform"}

            result = json.loads(content)

            # Check for API-level errors
            if isinstance(result, dict):
                code = result.get("code") or result.get("status")
                message = result.get("message") or result.get("msg") or result.get("error")
                if code not in (None, 0, "0", 200, "200", True) and message:
                    self.last_error = {
                        "type": "platform_error",
                        "message": str(message),
                        "code": code
                    }
                    return {"success": False, "error": str(message)}

            return result

        except urllib.error.HTTPError as e:
            self.last_error = {
                "type": "http_error",
                "message": f"日志平台返回 HTTP {e.code}: {e.reason}",
                "code": e.code
            }
            return {"success": False, "error": f"HTTP Error {e.code}: {e.reason}"}

        except urllib.error.URLError as e:
            self.last_error = {
                "type": "network_error",
                "message": f"无法访问日志平台: {e.reason}"
            }
            return {"success": False, "error": f"URL Error: {e.reason}"}

        except json.JSONDecodeError as e:
            self.last_error = {
                "type": "invalid_response",
                "message": "日志平台返回内容不是有效数据"
            }
            return {"success": False, "error": f"JSON Decode Error: {str(e)}"}

    @staticmethod
    def parse_log_entries(response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse log entries from API response.

        Args:
            response: API response dictionary

        Returns:
            List of parsed log entries
        """
        entries = []

        if not response or response.get("success") is False:
            return entries

        # The response structure may vary - common patterns:
        # - {"data": {"list": [...]}}
        # - {"result": [...]}
        # - {"logs": [...]}
        data = response.get("data", response)

        log_list = None
        if isinstance(data, dict):
            log_list = (
                data.get("list")
                or data.get("logs")
                or data.get("result")
                or data.get("data")
            )
        elif isinstance(data, list):
            log_list = data

        if not log_list:
            return entries

        for item in log_list:
            if not isinstance(item, dict):
                continue

            entry = {
                "timestamp": item.get("timestamp") or item.get("time") or item.get("@timestamp"),
                "level": item.get("level") or item.get("severity") or "UNKNOWN",
                "content": item.get("content") or item.get("message") or item.get("msg") or "",
                "app_code": item.get("appCode") or item.get("app_code") or "",
                "env": item.get("env") or "",
                "node_name": item.get("nodeName") or item.get("node_name") or "",
                "thread": item.get("thread") or "",
                "class_name": item.get("clazz") or item.get("class") or item.get("className") or "",
                "trace_id": item.get("traceId") or item.get("trace_id") or "",
                "span_id": item.get("spanId") or item.get("span_id") or "",
            }
            entries.append(entry)

        return entries

    @staticmethod
    def format_log_entry(entry: Dict[str, Any]) -> str:
        """Format a single log entry as readable string.

        Args:
            entry: Log entry dictionary

        Returns:
            Formatted log string
        """
        timestamp = entry.get("timestamp", "")
        level = entry.get("level", "UNKNOWN")
        content = entry.get("content", "")

        parts = []
        if timestamp:
            parts.append(f"[{timestamp}]")
        parts.append(f"[{level}]")
        if entry.get("thread"):
            parts.append(f"[{entry.get('thread')}]")
        if entry.get("class_name"):
            parts.append(f"[{entry.get('class_name')}]")
        parts.append(content)

        return " ".join(parts)


# ========== DEFAULT PARAMETERS ==========

DEFAULT_APP_CODE = "super-mario"
DEFAULT_ENV = "prod"
DEFAULT_NAMESPACE = "souche"
DEFAULT_LEVEL = "ERROR"
DEFAULT_PAGE_SIZE = 50
DEFAULT_VERIFY_SSL = False

# Default cookies (from environment or use provided)
DEFAULT_COOKIES = os.getenv("LOG_COOKIES", "")


# ========== MAIN ==========

def main():
    parser = argparse.ArgumentParser(description="Fetch logs from Optimus log platform")
    parser.add_argument("--app-code", default=DEFAULT_APP_CODE, help="Application code")
    parser.add_argument("--env", default=DEFAULT_ENV, choices=["prod", "test", "pre"],
                        help="Environment")
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE, help="Namespace")
    parser.add_argument("--level", default=DEFAULT_LEVEL, help="Log level (e.g., ERROR, INFO,WARN,ERROR)")
    parser.add_argument("--content", default="", help="Log content keyword")
    parser.add_argument("--start-time", type=int, help="Start timestamp in milliseconds")
    parser.add_argument("--end-time", type=int, help="End timestamp in milliseconds")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE, help="Page size")
    parser.add_argument("--cookies", default=DEFAULT_COOKIES, help="Authentication cookies")
    parser.add_argument("--insecure", action="store_true", default=not DEFAULT_VERIFY_SSL,
                        help="Disable SSL verification")
    parser.add_argument("--output", help="Output file (default: stdout)")

    args = parser.parse_args()

    if not args.cookies:
        print("Warning: No cookies provided, request may fail", file=sys.stderr)

    fetcher = LogFetcher(cookies=args.cookies, verify_ssl=not args.insecure)

    result = fetcher.fetch_logs(
        app_code=args.app_code,
        env=args.env,
        level=args.level,
        content=args.content,
        start_time=args.start_time,
        end_time=args.end_time,
        page_size=args.page_size,
        namespace=args.namespace
    )

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"Output written to {args.output}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

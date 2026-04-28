#!/usr/bin/env python3
"""
JIRA Client for fetching issue details and extracting keywords
"""

import os
import re
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse
import requests
from requests.auth import HTTPBasicAuth


class JiraClient:
    """JIRA API Client"""

    def __init__(self, base_url: str = None, username: str = None, password: str = None):
        """
        Initialize JIRA client

        :param base_url: JIRA base URL (e.g., https://jira.souche-inc.com)
        :param username: Username for authentication
        :param password: Password or API token
        """
        self.base_url = (base_url or os.getenv('JIRA_BASE_URL', 'https://jira.souche-inc.com/')).rstrip('/')
        self.username = username or os.getenv('JIRA_USERNAME')
        self.password = password or os.getenv('JIRA_PASSWORD') or os.getenv('JIRA_API_TOKEN')

    def _ensure_credentials(self):
        """Ensure credentials are available, raise error if not"""
        if not self.username or not self.password:
            raise ValueError("JIRA username and password/token are required. Please set JIRA_USERNAME and JIRA_PASSWORD environment variables.")

    def _get_auth(self):
        return HTTPBasicAuth(str(self.username), str(self.password))

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make HTTP request to JIRA API"""
        self._ensure_credentials()
        headers = kwargs.pop('headers', {})
        headers.setdefault("Accept", "application/json")
        headers.setdefault("Content-Type", "application/json")

        # 设置超时时间 60 秒
        kwargs.setdefault('timeout', 60)

        response = requests.request(
            method,
            url,
            headers=headers,
            auth=self._get_auth(),
            **kwargs
        )

        if response.status_code == 401:
            raise Exception("JIRA authentication failed. Please check credentials.")
        elif response.status_code == 404:
            raise Exception(f"JIRA resource not found: {url}")
        elif response.status_code >= 400:
            raise Exception(f"JIRA API error: {response.status_code} - {response.text}")

        return response

    def get_issue(self, issue_key: str, fields: str = "*all") -> Dict[str, Any]:
        """
        Fetch details of a JIRA issue

        :param issue_key: Issue key (e.g., 'PROJ-123')
        :param fields: Fields to include (default "*all" to get all fields including custom fields)
        :return: Issue details as dictionary
        """
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}?fields={fields}"
        response = self._request('GET', url)
        return response.json()

    def get_comments(self, issue_key: str) -> List[Dict[str, Any]]:
        """
        Fetch all comments for a JIRA issue

        :param issue_key: Issue key
        :return: List of comments
        """
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}/comment"
        response = self._request('GET', url)
        data = response.json()
        return data.get('comments', [])

    def get_attachments(self, issue_key: str) -> List[Dict[str, Any]]:
        """
        Fetch attachment metadata for a JIRA issue

        :param issue_key: Issue key
        :return: List of attachments
        """
        issue = self.get_issue(issue_key)
        fields = issue.get('fields', {})
        return fields.get('attachment', [])

    def extract_issue_key(self, jira_url: str) -> Optional[str]:
        """
        Extract issue key from JIRA URL

        :param jira_url: Full JIRA URL (e.g., https://jira.souche-inc.com/browse/PROJ-123)
        :return: Issue key (e.g., 'PROJ-123') or None if not found
        """
        # Match patterns like PROJ-123 or ONLINEBUG-15935
        match = re.search(r'/browse/([A-Z]+-\d+)', jira_url)
        if match:
            return match.group(1)

        # Try to find any PROJECT-123 pattern
        match = re.search(r'([A-Z]+-\d+)', jira_url)
        if match:
            return match.group(1)

        return None

    def extract_keywords(self, issue_data: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Extract keywords from JIRA issue for code search

        :param issue_data: Issue data from get_issue()
        :return: Dict with keys 'api_paths', 'class_names', 'error_patterns'
        """
        keywords = {
            'api_paths': [],
            'class_names': [],
            'error_patterns': [],
            'business_terms': []
        }

        # Combine all text fields for analysis
        fields = issue_data.get('fields', {})
        text_content = self._get_text_content(fields)

        # Extract API paths (e.g., /v1/customer/save)
        api_path_pattern = r'/[a-zA-Z0-9_/-]+\.[a-zA-Z]+|/v\d+/[a-zA-Z0-9_/-]+'
        keywords['api_paths'] = list(set(re.findall(api_path_pattern, text_content)))

        # Extract potential class names (PascalCase)
        class_pattern = r'\b[A-Z][a-zA-Z0-9]*(?:Service|Controller|DAO|Action|Manager|Mapper|Impl|Model|Entity)\b'
        keywords['class_names'] = list(set(re.findall(class_pattern, text_content)))

        # Extract error patterns
        error_patterns = [
            r'NullPointerException', r'NPE', r'NullPointer',
            r'SQLException', r'SQLError',
            r'TimeoutException', r' timeout ',
            r'OutOfMemoryError', r'OOM',
            r'IndexOutOfBoundsException',
            r'ConcurrentModificationException',
            r'IllegalArgumentException',
            r'IllegalStateException',
            r'Connection refused',
            r'SocketTimeoutException'
        ]
        for pattern in error_patterns:
            if re.search(pattern, text_content, re.IGNORECASE):
                keywords['error_patterns'].append(pattern.replace(r'\b', ''))

        # Extract business-related terms (订单、取消、销售、客户、公海等)
        business_terms = [
            r'订单', r'取消', r'销售', r'客户', r'归属',
            r'公海', r'战败', r'变更', r'状态', r'审批',
            r'Order', r'Cancel', r'Sales', r'Customer', r'CustomerOwned',
            r'OrderCancel', r'OrderService', r'SalesService', r'CustomerService'
        ]
        for term in business_terms:
            if re.search(term, text_content, re.IGNORECASE):
                keywords['business_terms'].append(term)

        return keywords

    def _get_text_content(self, fields: Dict[str, Any]) -> str:
        """Extract all text content from issue fields"""
        parts = []

        # Basic fields
        for field in ['summary', 'description']:
            value = fields.get(field)
            if value:
                parts.append(str(value))

        # Custom fields that might contain useful text
        for key, value in fields.items():
            if value and isinstance(value, str) and len(value) < 10000:
                parts.append(value)

        return ' '.join(parts)

    def get_issue_summary(self, issue_key: str) -> Dict[str, Any]:
        """
        Get a summary of JIRA issue with key information

        :param issue_key: Issue key
        :return: Summary dict with essential fields
        """
        issue = self.get_issue(issue_key)
        fields = issue.get('fields', {})

        return {
            'key': issue.get('key'),
            'summary': fields.get('summary', ''),
            'description': fields.get('description', ''),
            'status': fields.get('status', {}).get('name', ''),
            'priority': fields.get('priority', {}).get('name', ''),
            'reporter': fields.get('reporter', {}).get('displayName', '') if fields.get('reporter') else '',
            'assignee': fields.get('assignee', {}).get('displayName', '') if fields.get('assignee') else '',
            'created': fields.get('created', ''),
            'updated': fields.get('updated', ''),
            'issue_type': fields.get('issuetype', {}).get('name', ''),
            'project': fields.get('project', {}).get('name', ''),
            'labels': fields.get('labels', []),
            'customfield_19900': fields.get('customfield_19900', ''),
            'attachment': fields.get('attachment', [])
        }


def main():
    """Test JIRA client"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python jira_client.py <JIRA_URL>")
        sys.exit(1)

    jira_url = sys.argv[1]
    client = JiraClient()

    issue_key = client.extract_issue_key(jira_url)
    if not issue_key:
        print(f"Could not extract issue key from URL: {jira_url}")
        sys.exit(1)

    print(f"Fetching issue: {issue_key}")

    # Get issue summary
    summary = client.get_issue_summary(issue_key)
    print(f"\nSummary: {summary['summary']}")
    print(f"Status: {summary['status']}")
    print(f"Priority: {summary['priority']}")

    # Get comments
    comments = client.get_comments(issue_key)
    print(f"\nComments: {len(comments)}")

    # Extract keywords
    issue = client.get_issue(issue_key)
    keywords = client.extract_keywords(issue)
    print(f"\nKeywords extracted:")
    print(f"  API paths: {keywords['api_paths']}")
    print(f"  Class names: {keywords['class_names']}")
    print(f"  Error patterns: {keywords['error_patterns']}")


if __name__ == "__main__":
    main()
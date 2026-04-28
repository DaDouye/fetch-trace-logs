#!/usr/bin/env python3
"""
Jira Issue Fetcher
This script fetches details of a specific Jira issue or a list of issues using JQL query with pagination.
"""
import os
import sys
import requests
from requests.auth import HTTPBasicAuth
import json
from urllib.parse import urlparse, quote
from pathlib import Path

# Load environment variables from .config file if it exists
env_path = Path(__file__).parent.parent / '.config'
if env_path.exists():
    try:
        import dotenv
        dotenv.load_dotenv(dotenv_path=env_path)
    except ImportError:
        # If python-dotenv is not installed, manually read the .config file
        import io
        with open(env_path, 'r') as f:
          for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip().strip('"\'')


class JiraClient:
    def __init__(self, base_url, username=None, password=None, api_token=None):
        """
        Initialize the Jira client
        :param base_url: Base URL of the Jira instance (e.g., https://jira.souche-inc.com)
        :param username: Username for authentication
        :param password: Password or API token for authentication
        :param api_token: API token (alternative to password)
        """
        self.base_url = base_url.rstrip('/')
        self.username = username or os.getenv('JIRA_USERNAME')
        self.password = password or os.getenv('JIRA_PASSWORD') or api_token or os.getenv('JIRA_API_TOKEN')

        if not self.username or not self.password:
            raise ValueError("Username and password/API token are required")

    def get_issue(self, issue_key):
        """
        Fetch details of a specific Jira issue
        :param issue_key: The issue key (e.g., ONLINEBUG-15935)
        :return: Issue details as dictionary
        """
        url = f"{self.base_url}/rest/api/2/issue/{issue_key}"

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        auth = HTTPBasicAuth(str(self.username), str(self.password))

        response = requests.get(url, headers=headers, auth=auth)

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            raise Exception("Authentication failed. Please check your credentials.")
        elif response.status_code == 404:
            raise Exception(f"Issue {issue_key} not found.")
        else:
            raise Exception(f"Failed to fetch issue {issue_key}. Status code: {response.status_code}, Response: {response.text}")

    def search_issues(self, jql, start_at=0, max_results=50, fields=None):
        """
        Search for issues using JQL with pagination support
        :param jql: JQL query string
        :param start_at: Start position for pagination (default 0)
        :param max_results: Maximum number of results per page (default 50, max 100)
        :param fields: List of fields to include in the response (optional)
        :return: Search results as dictionary
        """
        encoded_jql = quote(jql, safe='')
        url = f"{self.base_url}/rest/api/2/search?jql={encoded_jql}&startAt={start_at}&maxResults={max_results}"

        if fields:
            url += "&fields=" + ",".join(fields)

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        auth = HTTPBasicAuth(str(self.username), str(self.password))

        response = requests.get(url, headers=headers, auth=auth)

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            raise Exception("Authentication failed. Please check your credentials.")
        else:
            raise Exception(f"Failed to search issues. JQL: {jql}, Status code: {response.status_code}, Response: {response.text}")

    def paginated_search_issues(self, jql, max_results_per_page=50, max_total_results=None, fields=None):
        """
        Search for issues using JQL with automatic pagination
        :param jql: JQL query string
        :param max_results_per_page: Maximum results per page (default 50)
        :param max_total_results: Maximum total results to fetch (None for all)
        :param fields: List of fields to include in the response (optional)
        :return: Generator that yields individual issues
        """
        start_at = 0
        total_fetched = 0

        while True:
            # Determine how many results to fetch in this iteration
            current_max_results = max_results_per_page
            if max_total_results is not None:
                remaining = max_total_results - total_fetched
                current_max_results = min(current_max_results, remaining)

            if current_max_results <= 0:
                break

            results = self.search_issues(jql, start_at=start_at, max_results=current_max_results, fields=fields)
            issues = results.get('issues', [])

            if not issues:
                break  # No more issues to fetch

            for issue in issues:
                yield issue
                total_fetched += 1
                if max_total_results is not None and total_fetched >= max_total_results:
                    return

            # Check if there are more results
            if len(issues) < current_max_results:
                # We received fewer issues than requested, so no more pages
                break

            start_at += len(issues)

    def print_issue_summary(self, issue_data):
        """
        Print a summary of the issue
        :param issue_data: Issue data returned by get_issue()
        """
        fields = issue_data.get('fields', {})

        print("=" * 60)
        print(f"JIRA ISSUE: {issue_data.get('key', 'N/A')}")
        print("=" * 60)

        print(f"Summary: {fields.get('summary', 'N/A')}")
        print(f"Status: {fields.get('status', {}).get('name', 'N/A')}")
        print(f"Priority: {fields.get('priority', {}).get('name', 'N/A')}")
        print(f"Reporter: {fields.get('reporter', {}).get('displayName', 'N/A') if fields.get('reporter') else 'N/A'}")
        print(f"Assignee: {fields.get('assignee', {}).get('displayName', 'Unassigned') if fields.get('assignee') else 'Unassigned'}")
        print(f"Created: {fields.get('created', 'N/A')}")
        print(f"Updated: {fields.get('updated', 'N/A')}")

        description = fields.get('description')
        if description:
            print(f"\nDescription:\n{description[:500]}{'...' if len(description) > 500 else ''}")

        print("\nAdditional fields:")
        print(f"- Issue Type: {fields.get('issuetype', {}).get('name', 'N/A')}")
        print(f"- Project: {fields.get('project', {}).get('name', 'N/A')} ({fields.get('project', {}).get('key', 'N/A')})")

        if 'labels' in fields and fields['labels']:
            print(f"- Labels: {', '.join(fields['labels'])}")

        # Display custom field 19900 if it exists
        custom_field_value = fields.get('customfield_19900')
        if custom_field_value:
            print(f"- Custom Field 19900: {custom_field_value}")

        # Display attachments if they exist
        attachments = fields.get('attachment', [])
        if attachments:
            print(f"- Attachments: {len(attachments)} file(s)")
            for i, attachment in enumerate(attachments[:5], 1):  # Show max 5 attachments
                print(f"  {i}. {attachment.get('filename', 'Unknown')} "
                      f"(Size: {attachment.get('size', 'Unknown')}, "
                      f"Author: {attachment.get('author', {}).get('displayName', 'Unknown')})")
            if len(attachments) > 5:
                print(f"  ... and {len(attachments) - 5} more")
        else:
            print("- Attachments: None")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  For single issue: python fetch_jira_souche.py <ISSUE_KEY>")
        print("  For JQL search: python fetch_jira_souche.py --search \"<JQL_QUERY>\" [--start-at START_AT] [--max-results MAX_RESULTS]")
        print("")
        print("Example:")
        print("  python fetch_jira_souche.py ONLINEBUG-15935")
        print("  python fetch_jira_souche.py --search \"project = ONLINEBUG AND issuetype = 缺陷 AND created >= 2025-01-01 AND created <= 2025-12-31\"")
        sys.exit(1)

    # Get credentials from environment or use default values
    jira_url = os.getenv('JIRA_BASE_URL', 'https://jira.souche-inc.com/')
    username = os.getenv('JIRA_USERNAME')
    password = os.getenv('JIRA_PASSWORD')

    if not username or not password:
        print("Error: Please set JIRA_USERNAME and JIRA_PASSWORD environment variables.")
        print("Example:")
        print("  export JIRA_USERNAME='your_username'")
        print("  export JIRA_PASSWORD='your_password_or_api_token'")
        sys.exit(1)

    try:
        client = JiraClient(jira_url, username, password)

        if sys.argv[1] == '--search':
            # Handle JQL search
            jql_query = sys.argv[2] if len(sys.argv) > 2 else ""

            # Parse additional options
            start_at = 0
            max_results = None
            i = 3
            while i < len(sys.argv):
                if sys.argv[i] == '--start-at' and i + 1 < len(sys.argv):
                    start_at = int(sys.argv[i + 1])
                    i += 2
                elif sys.argv[i] == '--max-results' and i + 1 < len(sys.argv):
                    max_results = int(sys.argv[i + 1])
                    i += 2
                else:
                    i += 1

            print(f"Searching for issues with JQL: {jql_query}")
            print(f"Start at: {start_at}, Max results: {max_results or 'unlimited'}")

            # Specify fields to retrieve including custom field and attachments
            fields = ['summary', 'status', 'priority', 'reporter', 'assignee', 'created', 'updated',
                     'description', 'issuetype', 'project', 'labels', 'customfield_19900', 'attachment']

            # Use pagination to retrieve all matching issues
            count = 0
            for issue in client.paginated_search_issues(jql_query, max_results_per_page=50, max_total_results=max_results, fields=fields):
                client.print_issue_summary(issue)
                count += 1
                print(f"\n--- {count} issue(s) processed ---\n")

                # Stop if we reached the max_results
                if max_results and count >= max_results:
                    break

            print(f"Total issues retrieved: {count}")
        else:
            # Handle single issue retrieval
            issue_key = sys.argv[1]
            issue_data = client.get_issue(issue_key)
            client.print_issue_summary(issue_data)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

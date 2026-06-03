#!/usr/bin/env python3
"""
JIRA Problem Analyzer - Unified analysis orchestration
"""

import os
import re
import glob
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from api.jira_client import JiraClient
from api.analyzer.rule_engine import RuleEngine
from api.analyzer.code_search import CodeSearch
from api.analyzer.claude_code_service import ClaudeCodeAnalysisService
from api.analyzer.repository_context import LocalCodeDirContext, build_code_dir_metadata, resolve_local_code_dir
from api.analyzer.lightrag_indexer import LightRAGIndexer


class JiraAnalyzer:
    """
    Unified JIRA problem analyzer
    Orchestrates JIRA fetching, code search, and cause analysis
    """

    def __init__(
        self,
        repo_key: str = None,
        repo_path: str = None,
        repo_url: str = None,
        repo_urls: List[Dict[str, str]] = None
    ):
        """
        Initialize analyzer

        :param repo_key: Repository key from config
        :param repo_path: Direct local code directory
        :param repo_url: Compatible field; URL maps to ./repos/<repo_name>, local path is used directly
        :param repo_urls: List of local code directories or compatible repo inputs
        """
        self.repo_key = repo_key
        self.repo_url = repo_url
        self.ref = None
        self.repo_urls = repo_urls
        self.local_code_context: Optional[LocalCodeDirContext] = None

        if repo_urls and not (repo_path or repo_url or repo_key):
            self.repo_path = None
        else:
            self.local_code_context = resolve_local_code_dir(
                repo_path=repo_path,
                repo_key=repo_key,
                repo_url=repo_url,
                use_default=not (repo_path or repo_url or repo_key)
            )
            self.repo_path = self.local_code_context.local_path

        self.multi_repo_paths = []
        if self.repo_urls:
            for repo_info in self.repo_urls:
                context = self._resolve_repo_info_context(repo_info)
                self.multi_repo_paths.append(self._local_context_to_repo_info(context))
            print(f"[JiraAnalyzer] Initialized with {len(self.multi_repo_paths)} code directories")

        self.jira_client = JiraClient()
        self.rule_engine = RuleEngine()
        self.code_search = CodeSearch(self.repo_path) if self.repo_path else None
        self._claude_services: Dict[str, ClaudeCodeAnalysisService] = {}
        self._rag_indexer = None

    def _get_claude_service(self, repo_path: Optional[str] = None) -> ClaudeCodeAnalysisService:
        target_path = repo_path or self.repo_path
        if not target_path:
            raise ValueError("缺少本地仓库路径，无法执行 Claude Code CLI 代码分析")
        if target_path not in self._claude_services:
            self._claude_services[target_path] = ClaudeCodeAnalysisService(target_path)
        return self._claude_services[target_path]

    @property
    def rag_indexer(self) -> LightRAGIndexer:
        if self._rag_indexer is None:
            self._rag_indexer = LightRAGIndexer()
        return self._rag_indexer

    def _repo_url_from_key(self, repo_key: str = None) -> Optional[str]:
        if not repo_key:
            return None
        from config_manager import get_git_repo_url
        return get_git_repo_url(repo_key)

    def _is_repo_url(self, value: str) -> bool:
        if not value:
            return False
        value = value.strip()
        return (
            value.startswith("http://")
            or value.startswith("https://")
            or value.startswith("git@")
            or value.startswith("ssh://")
        )

    def _resolve_repo_info_context(self, repo_info) -> LocalCodeDirContext:
        if isinstance(repo_info, str):
            return resolve_local_code_dir(repo_url=repo_info)
        repo_path = repo_info.get('repo_path') if isinstance(repo_info, dict) else getattr(repo_info, 'repo_path', None)
        repo_url = repo_info.get('repo_url') if isinstance(repo_info, dict) else getattr(repo_info, 'repo_url', None)
        if not repo_path and repo_url and not self._is_repo_url(repo_url):
            repo_path = repo_url
            repo_url = None
        return resolve_local_code_dir(repo_path=repo_path, repo_url=repo_url)

    @staticmethod
    def _local_context_to_repo_info(context: LocalCodeDirContext) -> Dict[str, Any]:
        metadata = build_code_dir_metadata(context)
        return {
            'repo_url': context.requested_value,
            'repo_path': context.local_path,
            'local_path': context.local_path,
            **metadata
        }

    def _ensure_repo_context_from_services(self, services: List[str]) -> None:
        """Infer repository context from service names when the request omitted repo fields."""
        if self.repo_path or self.repo_url or self.multi_repo_paths:
            return
        if not services:
            return

        from config_manager import get_all_git_repos

        repos = get_all_git_repos()
        matched = []
        normalized_services = {self._normalize_repo_key(service) for service in services if service}
        for key, url in repos.items():
            repo_name = url.split('/')[-1].replace('.git', '')
            candidates = {
                self._normalize_repo_key(key),
                self._normalize_repo_key(repo_name)
            }
            if normalized_services & candidates:
                matched.append({'key': key, 'url': url, 'repo_name': repo_name})

        if not matched:
            print(f"[JiraAnalyzer] No repository matched services: {services}")
            return

        if len(matched) == 1:
            repo = matched[0]
            self.repo_key = repo['key']
            self.repo_url = repo['url']
            context = resolve_local_code_dir(repo_url=repo['url'])
            self.local_code_context = context
            self.repo_path = context.local_path
            self.code_search = CodeSearch(self.repo_path) if self.repo_path else None
            print(f"[JiraAnalyzer] Auto-selected repo {repo['key']} for services: {services}")
            return

        self.multi_repo_paths = []
        for repo in matched:
            context = resolve_local_code_dir(repo_url=repo['url'])
            self.multi_repo_paths.append(self._local_context_to_repo_info(context))
        print(f"[JiraAnalyzer] Auto-selected {len(self.multi_repo_paths)} repos for services: {services}")

    @staticmethod
    def _normalize_repo_key(value: str) -> str:
        return re.sub(r'[^a-z0-9]+', '_', (value or '').lower()).strip('_')

    def _search_code(
        self,
        api_paths: Optional[List[str]] = None,
        class_names: Optional[List[str]] = None,
        error_patterns: Optional[List[str]] = None,
        business_terms: Optional[List[str]] = None,
        source: str = 'unknown'
    ) -> List[Dict[str, Any]]:
        """Search configured repository context and tag results with evidence source."""
        if self.multi_repo_paths:
            all_search_results = []
            for repo_info in self.multi_repo_paths:
                local_path = repo_info.get('local_path')
                repo_url = repo_info.get('repo_url')
                print(f"[CodeContext] Searching repo: {repo_url}, path: {local_path}, source: {source}")
                code_search = CodeSearch(local_path) if local_path else None
                if not code_search:
                    continue
                search_results = code_search.search(
                    api_paths=api_paths or [],
                    class_names=class_names or [],
                    error_patterns=error_patterns or [],
                    business_terms=business_terms or []
                )
                for result in search_results:
                    result['repo_url'] = repo_url
                    result['source'] = source
                all_search_results.extend(search_results)
                print(f"[CodeContext] Search results from {repo_url}: {len(search_results)} files")
            return all_search_results

        if not self.code_search:
            return []

        search_results = self.code_search.search(
            api_paths=api_paths or [],
            class_names=class_names or [],
            error_patterns=error_patterns or [],
            business_terms=business_terms or []
        )
        for result in search_results:
            result['source'] = source
        return search_results

    @staticmethod
    def _merge_file_results(existing: List[Dict[str, Any]], incoming: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged = list(existing or [])
        seen = {
            (item.get('repo_url'), item.get('file_path'), item.get('keyword'))
            for item in merged
        }
        for item in incoming or []:
            key = (item.get('repo_url'), item.get('file_path'), item.get('keyword'))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    def analyze(
        self,
        jira_url: str,
        api_paths: Optional[List[str]] = None,
        trace_id: Optional[str] = None,
        trace_date: Optional[str] = None,
        cookies: Optional[str] = None,
        use_ai: bool = False,
        environment: Optional[str] = None,
        time_window: Optional[Dict[str, Any]] = None,
        problem_type: Optional[str] = None,
        services: Optional[List[str]] = None,
        extra_clues: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze JIRA issue and provide problem cause analysis

        :param jira_url: Full JIRA URL
        :param api_paths: Optional list of API paths for call chain analysis
        :param trace_id: Optional trace ID for runtime data
        :param trace_date: Optional date for trace data
        :param cookies: Optional cookies for trace API auth
        :param use_ai: Whether to use AI enhancement (reserved for future)
        :param environment: Target environment (e.g., "production", "staging")
        :param time_window: Time window for data filtering, e.g. {"start": "2024-05-01T00:00:00Z", "end": "2024-05-01T23:59:59Z"}
        :param problem_type: Type of problem (e.g., "error", "performance", "business")
        :param services: List of services to focus on
        :param extra_clues: Additional clues from user input
        :return: Analysis result dict
        """
        # Store user input parameters for later use in analysis
        self.user_context = {
            'environment': environment,
            'time_window': time_window,
            'problem_type': problem_type,
            'services': services or [],
            'extra_clues': extra_clues
        }
        self._ensure_repo_context_from_services(self.user_context['services'])
        # Extract issue key from URL
        issue_key = self.jira_client.extract_issue_key(jira_url)
        if not issue_key:
            raise ValueError(f"Could not extract issue key from URL: {jira_url}")

        result = {
            'jira_url': jira_url,
            'issue_key': issue_key,
            'jira': None,
            'code_context': {},
            'trace_data': None,
            'analysis': {
                'possible_causes': [],
                'ai_enhanced': False
            }
        }

        # 1. Fetch JIRA content
        result['jira'] = self._fetch_jira_content(issue_key)
        trace_resolution = self._resolve_trace_id(trace_id, result['jira'])
        result['trace_id'] = trace_resolution['trace_id']
        result['trace_id_source'] = trace_resolution['source']
        result['trace_id_candidates'] = trace_resolution['candidates']
        result['trace_id_note'] = trace_resolution['note']

        # 2. Build code context
        result['code_context'] = self._build_code_context(
            issue_key, api_paths, trace_resolution['trace_id'], trace_date, cookies
        )

        # 3. Perform cause analysis
        result['analysis'] = self._analyze_causes(result, use_ai=use_ai)

        return result

    def _fetch_jira_content(self, issue_key: str) -> Dict[str, Any]:
        """Fetch JIRA issue content and comments"""
        # Get issue summary
        summary = self.jira_client.get_issue_summary(issue_key)

        # Get attachments
        attachments = self.jira_client.get_attachments(issue_key)
        attachment_list = [
            {
                'filename': a.get('filename', ''),
                'size': a.get('size', 0),
                'author': a.get('author', {}).get('displayName', 'Unknown')
            }
            for a in attachments
        ]

        comments = self.jira_client.get_comments(issue_key)
        comment_list = [
            {
                'author': c.get('author', {}).get('displayName', 'Unknown'),
                'body': c.get('body', ''),
                'created': c.get('created', '')
            }
            for c in comments
        ]

        # Extract keywords for code search
        issue_full = self.jira_client.get_issue(issue_key)
        keywords = self.jira_client.extract_keywords(issue_full)

        return {
            'key': summary['key'],
            'summary': summary['summary'],
            'description': summary['description'],
            'status': summary['status'],
            'priority': summary['priority'],
            'reporter': summary['reporter'],
            'assignee': summary['assignee'],
            'created': summary['created'],
            'updated': summary['updated'],
            'issue_type': summary['issue_type'],
            'project': summary['project'],
            'labels': summary['labels'],
            'customfield_19900': summary.get('customfield_19900', ''),
            'attachment': summary.get('attachment', []),
            'attachments': attachment_list,
            'comments': comment_list,
            'keywords': keywords
        }

    def _resolve_trace_id(self, request_trace_id: Optional[str], jira: Dict[str, Any]) -> Dict[str, Any]:
        manual_trace_id = (request_trace_id or '').strip()
        candidates = self._extract_trace_id_candidates_from_jira(jira)
        if manual_trace_id:
            return {
                'trace_id': manual_trace_id,
                'source': 'manual',
                'candidates': candidates,
                'note': '使用用户手动填写的 Trace ID'
            }
        if candidates:
            note = '从 Jira 文本自动识别到 Trace ID'
            if len(candidates) > 1:
                note = f'从 Jira 文本识别到 {len(candidates)} 个 Trace ID，默认使用第一个'
            return {
                'trace_id': candidates[0],
                'source': 'jira',
                'candidates': candidates,
                'note': note
            }
        return {
            'trace_id': None,
            'source': 'none',
            'candidates': [],
            'note': '未从 Jira 文本识别到 Trace ID'
        }

    def _extract_trace_id_candidates_from_jira(self, jira: Dict[str, Any]) -> List[str]:
        text_parts = [
            str(jira.get('summary') or ''),
            str(jira.get('description') or ''),
            str(jira.get('customfield_19900') or '')
        ]
        for comment in jira.get('comments') or []:
            text_parts.append(str(comment.get('body') or ''))
        text = '\n'.join(text_parts)

        tagged_pattern = re.compile(
            r'(?:trace\s*[-_ ]?id|traceid|链路\s*id|链路ID)\s*[:：=]\s*([0-9]{13}_[A-Za-z0-9]+)',
            re.IGNORECASE
        )
        matches = tagged_pattern.findall(text)

        candidates = []
        seen = set()
        for trace_id in matches:
            if trace_id in seen:
                continue
            seen.add(trace_id)
            candidates.append(trace_id)
        return candidates

    def _build_code_context(
        self,
        issue_key: str,
        api_paths: Optional[List[str]],
        trace_id: Optional[str],
        trace_date: Optional[str],
        cookies: Optional[str]
    ) -> Dict[str, Any]:
        """Build code context from various sources"""
        context = {
            'files': [],
            'call_chains': [],
            'search_keywords': [],
            'logs': []
        }

        # Get user context for filtering
        user_context = getattr(self, 'user_context', {})
        services = user_context.get('services', [])
        environment = user_context.get('environment', 'prod')
        time_window = user_context.get('time_window')
        problem_type = user_context.get('problem_type', 'error')
        extra_clues = user_context.get('extra_clues', '')

        print(f"[CodeContext] repo_path: {self.repo_path}")
        print(f"[CodeContext] repo_key: {self.repo_key}")
        print(f"[CodeContext] api_paths: {api_paths}")
        print(f"[CodeContext] multi_repo_paths: {len(self.multi_repo_paths) if self.multi_repo_paths else 0} repos")

        has_repo_context = bool(self.repo_path or self.repo_url or self.multi_repo_paths)
        if not has_repo_context:
            print("[CodeContext] No repository context, code search will be skipped")

        # Get keywords from JIRA for search
        issue_full = self.jira_client.get_issue(issue_key)
        keywords = self.jira_client.extract_keywords(issue_full)
        context['search_keywords'] = keywords
        print(f"[CodeContext] Keywords: {keywords}")

        search_api_paths = keywords.get('api_paths', []) or []

        # Fetch trace data if trace ID provided
        trace_api_paths = []
        if trace_id:
            trace_data = self._fetch_trace_data(trace_id, trace_date, cookies)
            context['trace_data'] = trace_data
            print(f"[CodeContext] Trace data: {trace_data}")

            # Extract API paths from trace data if no api_paths provided
            if trace_data and not trace_data.get('error'):
                try:
                    trace_api_paths = self._normalize_api_paths(trace_data.get('api_paths', []))
                    print(f"[CodeContext] Extracted {len(trace_api_paths)} API paths from trace: {trace_api_paths}")
                except Exception as e:
                    print(f"[CodeContext] Failed to extract API paths from trace: {e}")

        # Fetch log data based on user context and JIRA keywords
        log_data = self._fetch_log_data(
            services=services,
            environment=environment,
            time_window=time_window,
            problem_type=problem_type,
            extra_clues=extra_clues,
            keywords=keywords,
            cookies=cookies
        )
        if log_data:
            context['logs'] = log_data
            print(f"[CodeContext] Log data: fetched {len(log_data.get('entries', []))} entries")

        code_context_paths = self._normalize_api_paths(api_paths or search_api_paths or trace_api_paths)
        print(f"[CodeContext] Claude Code CLI paths: {code_context_paths}")
        if has_repo_context:
            cli_context = self._build_code_context_with_claude(
                jira=self.jira_client.get_issue(issue_key),
                api_paths=code_context_paths,
                trace_data=context.get('trace_data'),
                logs=log_data,
                keywords=keywords,
                user_context=user_context
            )
            context['files'] = cli_context.get('files', [])
            context['call_chains'] = cli_context.get('call_chains', [])
            context['claude_code'] = {
                'summary': cli_context.get('summary', ''),
                'warnings': cli_context.get('warnings', []),
                'metadata': cli_context.get('metadata', {})
            }
            print(f"[CodeContext] Claude Code CLI files={len(context['files'])}, call_chains={len(context['call_chains'])}")
        else:
            print("[CodeContext] No repository context, Claude Code CLI code analysis will be skipped")

        return context

    def _build_code_context_with_claude(
        self,
        jira: Dict[str, Any],
        api_paths: List[str],
        trace_data: Optional[Dict[str, Any]],
        logs: Optional[Dict[str, Any]],
        keywords: Dict[str, Any],
        user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        if self.multi_repo_paths:
            files = []
            call_chains = []
            summaries = []
            warnings = []
            metadata = {'analysis_engine': 'claude_code_cli', 'repos': []}
            for repo_info in self.multi_repo_paths:
                local_path = repo_info.get('local_path')
                service = self._get_claude_service(local_path)
                result = service.build_jira_code_context(
                    jira=jira,
                    api_paths=api_paths,
                    trace_context=trace_data,
                    logs=logs,
                    search_keywords=keywords,
                    user_context=user_context,
                    ref=None
                )
                repo_url = repo_info.get('repo_url')
                for item in result.get('files', []):
                    item.setdefault('repo_url', repo_url)
                    files.append(item)
                for item in result.get('call_chains', []):
                    item.setdefault('repo_url', repo_url)
                    call_chains.append(item)
                if result.get('summary'):
                    summaries.append(result['summary'])
                warnings.extend(result.get('warnings', []))
                metadata['repos'].append({
                    'repo_path': repo_info.get('local_path'),
                    'source': repo_info.get('source'),
                    'requested_value': repo_info.get('requested_value'),
                    'is_git_repo': repo_info.get('is_git_repo'),
                    'head_commit': repo_info.get('head_commit'),
                    'metadata': result.get('metadata', {})
                })
            return {
                'files': files,
                'call_chains': call_chains,
                'summary': '\n'.join(summaries),
                'warnings': warnings,
                'metadata': metadata
            }

        service = self._get_claude_service()
        return service.build_jira_code_context(
            jira=jira,
            api_paths=api_paths,
            trace_context=trace_data,
            logs=logs,
            search_keywords=keywords,
            user_context=user_context,
            ref=self.ref
        )

    def _analyze_call_chain(self, api_path: str) -> Optional[Dict[str, Any]]:
        """Perform call chain analysis using Claude Code CLI."""
        if self.multi_repo_paths:
            repo_info = self.multi_repo_paths[0]
            return self._get_claude_service(repo_info.get('local_path')).analyze_call_chain(
                api_path=api_path,
                ref=None
            )
        return self._get_claude_service().analyze_call_chain(api_path=api_path, ref=self.ref)

    @staticmethod
    def _normalize_api_paths(api_paths: Optional[List[str]]) -> List[str]:
        if not api_paths:
            return []
        try:
            from scripts.fetch_trace_souche import TraceFetcher
            normalized = [
                TraceFetcher.normalize_api_path(path)
                for path in api_paths
            ]
        except Exception:
            normalized = api_paths
        return [path for path in dict.fromkeys(normalized) if path]

    def _fetch_trace_data(self, trace_id: str, date: str, cookies: str) -> Optional[Dict[str, Any]]:
        """Fetch trace data from Souche tracing system"""
        try:
            from scripts.fetch_trace_souche import TraceFetcher
            effective_date = date or self._infer_trace_date(trace_id)
            if not effective_date:
                failure_reason = "未提供 Trace 日期，且无法从 Trace ID 推断日期。请填写 Trace 日期（YYYY-MM-DD）。"
                return {
                    'trace_id': trace_id,
                    'date': effective_date,
                    'requested_date': date,
                    'success': False,
                    'error': failure_reason,
                    'failure_reason': failure_reason
                }
            verify_ssl = os.getenv("TRACE_VERIFY_SSL", "false").lower() == "true"
            fetcher = TraceFetcher(
                endpoint=self._resolve_trace_endpoint(),
                cookies=cookies,
                verify_ssl=verify_ssl
            )
            trace_data = fetcher.fetch_trace(trace_id, effective_date)
            if trace_data:
                return self._summarize_trace(trace_id, effective_date, trace_data, fetcher, requested_date=date)
            failure_reason = self._build_trace_failure_reason(trace_id, effective_date, fetcher, requested_date=date)
            return {
                'trace_id': trace_id,
                'date': effective_date,
                'requested_date': date,
                'success': False,
                'error': failure_reason,
                'failure_reason': failure_reason
            }
        except Exception as e:
            return {
                'trace_id': trace_id,
                'date': date,
                'success': False,
                'error': str(e),
                'failure_reason': str(e)
            }

    def _build_trace_failure_reason(
        self,
        trace_id: str,
        date: str,
        fetcher,
        requested_date: Optional[str] = None
    ) -> str:
        inferred_time = self._infer_trace_time(trace_id)
        date_hint = f"Trace ID 时间约为 {inferred_time}。" if inferred_time else ""
        date_mismatch_hint = ""
        inferred_date = self._infer_trace_date(trace_id)
        if requested_date and inferred_date and requested_date != inferred_date:
            date_mismatch_hint = f"你选择的 Trace 日期是 {requested_date}，但 Trace ID 推断日期是 {inferred_date}。"
        last_error = getattr(fetcher, 'last_error', None)

        if last_error:
            message = last_error.get('message') or '链路平台未返回有效数据'
            if last_error.get('type') in {'http_error', 'network_error', 'invalid_response'}:
                return f"{message} {date_hint}{date_mismatch_hint}".strip()
            if last_error.get('type') == 'empty_response':
                return f"链路平台返回空数据。{date_hint}{date_mismatch_hint}请确认登录凭证是否有效、是否有该 Trace 的访问权限。"
            return f"{message} {date_hint}{date_mismatch_hint}".strip()

        return f"未获取到 Trace 数据。{date_hint}{date_mismatch_hint}请确认 Trace ID、日期、登录凭证和访问权限。"

    def _infer_trace_time(self, trace_id: str) -> Optional[str]:
        match = re.match(r'(\d{13})', trace_id or '')
        if not match:
            return None
        try:
            from datetime import datetime, timezone, timedelta
            ts = int(match.group(1)) / 1000
            return datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return None

    def _infer_trace_date(self, trace_id: str) -> Optional[str]:
        inferred_time = self._infer_trace_time(trace_id)
        if not inferred_time:
            return None
        return inferred_time[:10]

    def _resolve_trace_endpoint(self) -> str:
        configured_endpoint = os.getenv("TRACE_ENDPOINT")
        if configured_endpoint:
            return configured_endpoint.rstrip("/")

        environment = (getattr(self, 'user_context', {}) or {}).get('environment') or ''
        if environment in {'测试环境', '测试', 'test', 'testing'}:
            return "http://test-trace.dasouche-inc.net"
        return "https://trace.souche-inc.com"

    def _summarize_trace(
        self,
        trace_id: str,
        date: str,
        trace_data: Dict[str, Any],
        fetcher,
        requested_date: Optional[str] = None
    ) -> Dict[str, Any]:
        from scripts.fetch_trace_souche import TraceFetcher

        spans = self._extract_trace_spans(trace_data)
        if not spans:
            failure_reason = self._build_trace_failure_reason(trace_id, date, fetcher, requested_date=requested_date)
            return {
                'trace_id': trace_id,
                'date': date,
                'requested_date': requested_date,
                'success': False,
                'error': failure_reason,
                'failure_reason': failure_reason,
                'raw_status': {
                    'has_response': True,
                    'response_keys': list(trace_data.keys()) if isinstance(trace_data, dict) else []
                }
            }

        sql_entries = TraceFetcher.extract_sql_data(trace_data)
        api_paths = TraceFetcher.extract_api_paths(trace_data)
        services = sorted({
            span.get('service_name')
            for span in spans
            if span.get('service_name') and span.get('service_name') != 'Unknown'
        })
        error_spans = [span for span in spans if span.get('has_error')]
        slowest_span = max(spans, key=lambda span: span.get('duration_ms') or 0, default=None)
        readable_sql = self._build_readable_sql(sql_entries, fetcher)

        return {
            'trace_id': trace_id,
            'date': date,
            'requested_date': requested_date,
            'success': True,
            'span_count': len(spans),
            'services': services,
            'slowest_node': slowest_span,
            'has_error': bool(error_spans),
            'error_nodes': error_spans[:5],
            'has_sql': bool(sql_entries),
            'sql_count': len(sql_entries),
            'sql': readable_sql,
            'api_paths': api_paths,
            'evidence_summary': self._build_trace_evidence_summary(
                spans, services, slowest_span, error_spans, readable_sql
            )
        }

    def _extract_trace_search_keywords(self, trace_summary: Dict[str, Any]) -> Dict[str, List[str]]:
        error_patterns = []
        business_terms = []

        for node in trace_summary.get('error_nodes') or []:
            for value in (
                node.get('operation_name'),
                node.get('service_name'),
                node.get('error_text')
            ):
                self._append_search_terms(value, error_patterns, business_terms)

        slowest_node = trace_summary.get('slowest_node') or {}
        self._append_search_terms(slowest_node.get('operation_name'), error_patterns, business_terms)

        for sql_item in trace_summary.get('sql') or []:
            sql = sql_item.get('sql') or ''
            tables = re.findall(
                r'\b(?:FROM|JOIN|UPDATE|INTO)\s+([A-Za-z0-9_.$`]+)',
                sql,
                flags=re.IGNORECASE
            )
            for table in tables[:5]:
                business_terms.append(table.strip('`'))

        return {
            'error_patterns': list(dict.fromkeys(error_patterns))[:10],
            'business_terms': list(dict.fromkeys(business_terms))[:10]
        }

    @staticmethod
    def _append_search_terms(value: Optional[str], error_patterns: List[str], business_terms: List[str]) -> None:
        if not value:
            return

        text = str(value)
        api_paths = re.findall(r'/[A-Za-z0-9_./{}-]+', text)
        business_terms.extend(api_paths)

        class_like_terms = re.findall(r'\b[A-Z][A-Za-z0-9_]*(?:Exception|Error|Controller|Service|Action|Dao|Mapper)\b', text)
        error_patterns.extend(class_like_terms)

        method_like_terms = re.findall(r'\b[a-z][A-Za-z0-9_]{3,}\b', text)
        ignored = {
            'true', 'false', 'null', 'error', 'exception', 'failed', 'failure',
            'http', 'server', 'client', 'unknown'
        }
        for term in method_like_terms:
            if term.lower() not in ignored:
                business_terms.append(term)

    def _fetch_log_data(
        self,
        services: List[str],
        environment: str,
        time_window: Optional[Dict[str, Any]],
        problem_type: str,
        extra_clues: str,
        keywords: Dict[str, Any],
        cookies: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Fetch log data from Optimus log platform.

        Args:
            services: List of services to fetch logs from
            environment: Target environment (e.g., "prod", "test", "生产环境")
            time_window: Time window for filtering, e.g. {"start": "2024-05-01T00:00:00Z", "end": "2024-05-01T23:59:59Z"}
            problem_type: Type of problem (e.g., "error", "performance", "其他")
            extra_clues: Additional clues from user
            keywords: Keywords extracted from JIRA
            cookies: Authentication cookies

        Returns:
            Log data summary or None if fetch fails
        """
        # If no services provided and no error patterns, skip log fetching
        if not services and not keywords.get('error_patterns') and not extra_clues:
            print("[LogFetcher] No services or error patterns provided, skipping log fetch")
            return None

        try:
            from scripts.fetch_log_optimus import LogFetcher

            # Map environment name to log API format
            env_mapping = {
                'prod': 'prod',
                'production': 'prod',
                '生产环境': 'prod',
                '生产': 'prod',
                'test': 'test',
                'testing': 'test',
                '测试环境': 'test',
                '测试': 'test',
                'pre': 'pre',
                'pre环境': 'pre'
            }
            log_env = env_mapping.get(environment, environment if environment else 'prod')
            print(f"[LogFetcher] Using env: {log_env} (input: {environment})")

            # Determine log level based on problem type
            # Always fetch ERROR logs for troubleshooting unless explicitly performance issue
            if problem_type in ('performance', 'slow', '性能', '慢'):
                level = "WARN,ERROR"
            else:
                # For error, other, or unspecified - prioritize ERROR logs
                level = "ERROR"

            # Build content filter from error patterns and extra clues
            content_filters = []
            if keywords.get('error_patterns'):
                content_filters.extend(keywords['error_patterns'][:3])
            if extra_clues:
                # Use first 100 chars of extra clues as filter
                content_filters.append(extra_clues[:100])

            content = ",".join(content_filters) if content_filters else ""

            # Calculate time window
            start_time_ms = None
            end_time_ms = None
            if time_window:
                import time
                from datetime import datetime
                if time_window.get('start'):
                    try:
                        start_str = time_window['start']
                        # Handle Chinese date format "2026/5/20 00:00:00"
                        # Also handle ISO format "2024-05-01T00:00:00Z"
                        start_str = start_str.replace('/', '-')
                        if 'T' not in start_str and 'Z' not in start_str:
                            # Chinese format without timezone
                            start_dt = datetime.strptime(start_str, '%Y-%m-%d %H:%M:%S')
                            # Assume China timezone (UTC+8)
                            from datetime import timezone, timedelta
                            start_dt = start_dt.replace(tzinfo=timezone(timedelta(hours=8)))
                        else:
                            start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                        start_time_ms = int(start_dt.timestamp() * 1000)
                    except Exception as e:
                        print(f"[LogFetcher] Failed to parse start time: {time_window['start']}, error: {e}")
                        pass
                if time_window.get('end'):
                    try:
                        end_str = time_window['end']
                        end_str = end_str.replace('/', '-')
                        if 'T' not in end_str and 'Z' not in end_str:
                            end_dt = datetime.strptime(end_str, '%Y-%m-%d %H:%M:%S')
                            from datetime import timezone, timedelta
                            end_dt = end_dt.replace(tzinfo=timezone(timedelta(hours=8)))
                        else:
                            end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
                        end_time_ms = int(end_dt.timestamp() * 1000)
                    except Exception as e:
                        print(f"[LogFetcher] Failed to parse end time: {time_window['end']}, error: {e}")
                        pass

            # If no explicit time window, default to last 1 hour
            if not start_time_ms:
                import time
                start_time_ms = int(time.time() * 1000) - 3600 * 1000
            if not end_time_ms:
                import time
                end_time_ms = int(time.time() * 1000)

            # If no explicit time window, default to last 1 hour
            if not start_time_ms:
                import time
                start_time_ms = int(time.time() * 1000) - 3600 * 1000
            if not end_time_ms:
                import time
                end_time_ms = int(time.time() * 1000)

            logs_result = []
            log_summary = {
                'service_count': 0,
                'total_entries': 0,
                'error_count': 0,
                'services': []
            }

            # Fetch logs for each service
            for service in services[:5]:  # Limit to 5 services
                print(f"[LogFetcher] Fetching logs for service: {service}, env: {environment}")

                fetcher = LogFetcher(cookies=cookies, verify_ssl=False)
                result = fetcher.fetch_logs(
                    app_code=service,
                    env=environment,
                    level=level,
                    content=content,
                    start_time=start_time_ms,
                    end_time=end_time_ms,
                    page_size=50,
                    namespace="souche"
                )

                if result and result.get("success") is not False:
                    entries = LogFetcher.parse_log_entries(result)
                    if entries:
                        logs_result.extend(entries)
                        log_summary['service_count'] += 1
                        log_summary['total_entries'] += len(entries)
                        log_summary['services'].append(service)

                        # Count errors
                        error_entries = [e for e in entries if 'ERROR' in str(e.get('level', ''))]
                        log_summary['error_count'] += len(error_entries)

            if not logs_result:
                print("[LogFetcher] No logs found")
                return None

            # Build evidence summary
            evidence_parts = []
            evidence_parts.append(f"成功从日志平台获取 {log_summary['total_entries']} 条日志。")
            if log_summary['services']:
                evidence_parts.append(f"涉及服务：{', '.join(log_summary['services'][:5])}。")
            if log_summary['error_count'] > 0:
                evidence_parts.append(f"其中包含 {log_summary['error_count']} 条 ERROR 日志。")

            # Extract error patterns from logs
            error_messages = []
            for entry in logs_result[:20]:
                if 'ERROR' in str(entry.get('level', '')):
                    content = entry.get('content', '')
                    if content:
                        # Extract first line of error
                        error_line = content.split('\n')[0][:200]
                        error_messages.append(error_line)

            return {
                'success': True,
                'service_count': log_summary['service_count'],
                'total_entries': log_summary['total_entries'],
                'error_count': log_summary['error_count'],
                'services': log_summary['services'][:5],
                'entries': logs_result[:100],  # Limit to 100 entries
                'error_messages': error_messages[:10],
                'evidence_summary': ''.join(evidence_parts),
                'time_window': {
                    'start': start_time_ms,
                    'end': end_time_ms
                }
            }

        except ImportError as e:
            print(f"[LogFetcher] LogFetcher module not available: {e}")
            return None
        except Exception as e:
            print(f"[LogFetcher] Error fetching logs: {e}")
            import traceback
            print(f"[LogFetcher] Traceback: {traceback.format_exc()}")
            return None

    def _extract_trace_spans(self, trace_data: Any) -> List[Dict[str, Any]]:
        spans = []

        def as_ms(value):
            try:
                number = float(value or 0)
            except (TypeError, ValueError):
                return 0
            return round(number, 2)

        def has_error(node):
            error_fields = [
                node.get('errtag'),
                node.get('error'),
                node.get('exception'),
                node.get('status'),
                node.get('result')
            ]
            text = ' '.join(str(item) for item in error_fields if item)
            return bool(text and re.search(r'error|exception|fail|失败|异常|true', text, re.IGNORECASE))

        def error_text(node):
            error_fields = [
                node.get('errtag'),
                node.get('error'),
                node.get('exception'),
                node.get('status'),
                node.get('result'),
                node.get('msg'),
                node.get('message'),
                node.get('path'),
                node.get('operationName'),
                node.get('name')
            ]
            return ' '.join(str(item) for item in error_fields if item)[:300]

        def visit(node):
            if isinstance(node, dict):
                node_type = node.get('type')
                service_name = node.get('app') or node.get('serviceName') or node.get('service') or 'Unknown'
                operation_name = node.get('path') or node.get('operationName') or node.get('name') or node_type or 'Unknown'
                duration = node.get('cost') if node.get('cost') is not None else node.get('duration')

                if node_type or node.get('rid') or node.get('spanId') or node.get('operationName'):
                    spans.append({
                        'id': node.get('rid') or node.get('spanId') or node.get('id'),
                        'service_name': service_name,
                        'operation_name': operation_name,
                        'type': node_type or 'unknown',
                        'duration_ms': as_ms(duration),
                        'time': node.get('time') or node.get('timestamp') or '',
                        'has_error': has_error(node),
                        'error_text': error_text(node)
                    })

                for value in node.values():
                    if isinstance(value, (dict, list)):
                        visit(value)
            elif isinstance(node, list):
                for item in node:
                    visit(item)

        visit(trace_data)
        return spans

    def _build_readable_sql(self, sql_entries: List[Dict[str, Any]], fetcher) -> List[Dict[str, Any]]:
        readable = []
        seen = set()

        for entry in sql_entries[:10]:
            rid = entry.get('rid') or entry.get('id')
            sql_text = None
            if rid:
                try:
                    detail = fetcher.fetch_sql_detail(rid)
                    sql_text = self._prettify_sql(fetcher.format_complete_sql(detail))
                except Exception:
                    sql_text = None

            if not sql_text:
                sql_text = self._prettify_sql(
                    entry.get('sql') or entry.get('path') or entry.get('sqlText') or entry.get('statement')
                )

            if not sql_text or sql_text in seen:
                continue

            seen.add(sql_text)
            readable.append({
                'rid': rid,
                'service_name': entry.get('app') or entry.get('serviceName') or 'Unknown',
                'duration_ms': entry.get('cost') or entry.get('duration') or 0,
                'sql': sql_text
            })

        return readable

    def _prettify_sql(self, sql: Optional[str]) -> Optional[str]:
        if not sql:
            return None

        text = ' '.join(str(sql).split())
        keywords = [
            'SELECT', 'FROM', 'WHERE', 'LEFT JOIN', 'RIGHT JOIN', 'INNER JOIN',
            'JOIN', 'ORDER BY', 'GROUP BY', 'HAVING', 'LIMIT', 'INSERT INTO',
            'UPDATE', 'DELETE FROM', 'SET', 'VALUES'
        ]

        for keyword in sorted(keywords, key=len, reverse=True):
            text = re.sub(rf'\b{keyword}\b', f'\n{keyword}', text, flags=re.IGNORECASE)

        return text.strip()

    def _build_trace_evidence_summary(
        self,
        spans: List[Dict[str, Any]],
        services: List[str],
        slowest_span: Optional[Dict[str, Any]],
        error_spans: List[Dict[str, Any]],
        readable_sql: List[Dict[str, Any]]
    ) -> str:
        parts = []
        parts.append(f"成功获取 Trace，共 {len(spans)} 个节点。")
        if services:
            parts.append(f"涉及服务：{', '.join(services[:8])}。")
        if slowest_span:
            parts.append(
                f"最慢节点为 {slowest_span.get('service_name')}.{slowest_span.get('operation_name')}，"
                f"耗时 {slowest_span.get('duration_ms')}ms。"
            )
        if error_spans:
            first_error = error_spans[0]
            parts.append(
                f"发现异常节点：{first_error.get('service_name')}.{first_error.get('operation_name')}。"
            )
        else:
            parts.append("未从链路节点中识别到明确异常标记。")
        if readable_sql:
            parts.append(f"链路中包含 SQL，共整理 {len(readable_sql)} 条可读 SQL。")
        else:
            parts.append("链路中未发现 SQL。")
        return ''.join(parts)

    def _analyze_causes(self, result: Dict[str, Any], use_ai: bool = False) -> Dict[str, Any]:
        """Analyze JIRA content to identify possible problem causes"""
        causes = []

        jira = result.get('jira', {})
        code_context = result.get('code_context', {})
        trace_data = result.get('code_context', {}).get('trace_data')

        # Combine all text for analysis
        text_to_analyze = self._combine_text_for_analysis(jira, code_context)

        # Rule-based analysis (always run)
        rule_causes = self.rule_engine.analyze(text_to_analyze)
        causes.extend(rule_causes)

        # Add code context evidence if available
        if code_context.get('files'):
            causes = self._enrich_with_code_evidence(causes, code_context['files'])

        code_trace_causes = self._build_code_trace_causes(jira, code_context, trace_data)
        if code_trace_causes:
            causes = code_trace_causes + causes

        # Claude Code CLI-enhanced analysis
        ai_enhanced = False
        rag_context = None
        if use_ai:
            if os.getenv("RAG_CONTEXT_ENABLED", "false").lower() == "true":
                rag_context = self.rag_indexer.get_context_for_analysis(jira, code_context)
                print(f"[_analyze_causes] RAG context retrieved: {len(rag_context) if rag_context else 0} chars")

            cli_result = self._analyze_causes_with_claude(
                jira=jira,
                code_context=code_context,
                trace_data=trace_data,
                rule_causes=causes,
                rag_context=rag_context
            )
            cli_causes = cli_result.get('possible_causes', [])
            if cli_causes:
                causes.extend(cli_causes)
            if cli_result.get('summary'):
                causes.append({
                    'id': 'claude_code_summary',
                    'category': 'Claude Code 综合结论',
                    'analysis': cli_result['summary'],
                    'suggestion': '优先按照 Claude Code CLI 关联到的代码位置、Trace 节点和日志证据排查。',
                    'confidence': 0.8,
                    'metadata': cli_result.get('metadata', {})
                })
            ai_enhanced = True

        if os.getenv("RAG_AUTO_INDEX", "false").lower() == "true":
            try:
                self.rag_indexer.index_jira_issue(jira.get('key', ''), jira)
                if code_context.get('files'):
                    self.rag_indexer.index_code_files(code_context['files'])
                trace_data_for_index = code_context.get('trace_data')
                if trace_data_for_index and not trace_data_for_index.get('error'):
                    self.rag_indexer.index_trace_data(
                        trace_data_for_index.get('trace_id', ''),
                        trace_data_for_index
                    )
            except Exception as e:
                print(f"[_analyze_causes] RAG indexing error: {e}")

        return {
            'possible_causes': causes,
            'ai_enhanced': ai_enhanced
        }

    def _analyze_causes_with_claude(
        self,
        jira: Dict[str, Any],
        code_context: Dict[str, Any],
        trace_data: Optional[Dict[str, Any]],
        rule_causes: List[Dict[str, Any]],
        rag_context: Optional[str]
    ) -> Dict[str, Any]:
        user_context = getattr(self, 'user_context', {})
        if self.multi_repo_paths:
            possible_causes = []
            summaries = []
            metadata = {'analysis_engine': 'claude_code_cli', 'repos': []}
            for repo_info in self.multi_repo_paths:
                result = self._get_claude_service(repo_info.get('local_path')).analyze_jira_causes(
                    jira=jira,
                    code_context=code_context,
                    trace_context=trace_data,
                    rule_causes=rule_causes,
                    user_context=user_context,
                    rag_context=rag_context,
                    ref=None
                )
                repo_url = repo_info.get('repo_url')
                for cause in result.get('possible_causes', []):
                    cause.setdefault('repo_url', repo_url)
                    possible_causes.append(cause)
                if result.get('summary'):
                    summaries.append(result['summary'])
                metadata['repos'].append({
                    'repo_path': repo_info.get('local_path'),
                    'source': repo_info.get('source'),
                    'requested_value': repo_info.get('requested_value'),
                    'is_git_repo': repo_info.get('is_git_repo'),
                    'head_commit': repo_info.get('head_commit'),
                    'metadata': result.get('metadata', {})
                })
            return {
                'possible_causes': possible_causes,
                'summary': '\n'.join(summaries),
                'metadata': metadata
            }

        return self._get_claude_service().analyze_jira_causes(
            jira=jira,
            code_context=code_context,
            trace_context=trace_data,
            rule_causes=rule_causes,
            user_context=user_context,
            rag_context=rag_context,
            ref=self.ref
        )

    def _combine_text_for_analysis(self, jira: Dict, code_context: Dict) -> str:
        """Combine all text sources for analysis"""
        parts = []

        # JIRA content
        if jira.get('summary'):
            parts.append(jira['summary'])
        if jira.get('description'):
            parts.append(jira['description'])

        # Comments
        for comment in jira.get('comments', []):
            if comment.get('body'):
                parts.append(comment['body'])

        # Keywords
        keywords = jira.get('keywords', {})
        for key, values in keywords.items():
            if values:
                parts.extend(values)

        trace_data = code_context.get('trace_data')
        if trace_data and not trace_data.get('error'):
            for node in trace_data.get('error_nodes') or []:
                parts.append(str(node.get('operation_name') or ''))
                parts.append(str(node.get('error_text') or ''))
            if trace_data.get('evidence_summary'):
                parts.append(trace_data['evidence_summary'])

        log_data = code_context.get('logs')
        if log_data and log_data.get('error_messages'):
            parts.extend(log_data.get('error_messages') or [])

        return ' '.join(parts)

    def _enrich_with_code_evidence(self, causes: List[Dict], search_results: List[Dict]) -> List[Dict]:
        """Add code evidence to causes"""
        for cause in causes:
            # Find matching files for this cause
            matching_files = []
            for pattern in cause.get('keywords', []):
                for result in search_results:
                    file_path = result.get('file_path', '').lower()
                    match_text = ' '.join(
                        match.get('content', '')
                        for match in result.get('matches', [])
                    ).lower()
                    if pattern.lower() in file_path or pattern.lower() in match_text:
                        matching_files.append(result)

            if matching_files:
                cause['evidence_files'] = matching_files[:3]  # Limit to 3 files

        return causes

    def _build_code_trace_causes(
        self,
        jira: Dict[str, Any],
        code_context: Dict[str, Any],
        trace_data: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        if not trace_data or trace_data.get('error'):
            return []

        error_nodes = trace_data.get('error_nodes') or []
        call_chains = code_context.get('call_chains') or []
        files = code_context.get('files') or []
        logs = code_context.get('logs') or {}
        if not error_nodes and not logs.get('error_messages'):
            return []
        if not call_chains and not files:
            return []

        primary_error = error_nodes[0] if error_nodes else {}
        api_path = self._pick_primary_api_path(trace_data, call_chains)
        chain = self._pick_call_chain_for_api(api_path, call_chains)
        controller = chain.get('controller') or ''
        controller_method = chain.get('controller_method') or ''
        controller_text = (
            f"{controller}.{controller_method}()"
            if controller and controller_method
            else api_path or primary_error.get('operation_name') or 'Trace 异常节点'
        )

        evidence_files = self._select_code_evidence_files(files, api_path, controller, controller_method)
        related_code = self._format_related_code(evidence_files, chain)
        trace_error_text = primary_error.get('error_text') or primary_error.get('operation_name') or ''
        log_error_text = ''
        if logs.get('error_messages'):
            log_error_text = logs['error_messages'][0]

        analysis_parts = [
            f"Trace 在 {primary_error.get('service_name', 'Unknown')} 的 {primary_error.get('operation_name', api_path or '未知节点')} 标记为异常。"
        ]
        if controller_text:
            analysis_parts.append(f"该链路已映射到代码入口 {controller_text}，问题应优先沿这个入口的调用链排查。")
        if trace_error_text:
            analysis_parts.append(f"Trace 异常信息：{trace_error_text[:180]}。")
        if log_error_text:
            analysis_parts.append(f"日志错误片段：{log_error_text[:180]}。")
        if evidence_files:
            top = evidence_files[0]
            analysis_parts.append(
                f"代码搜索命中 {top.get('file_path')}，关键词为 {top.get('keyword')}，说明异常线索和代码路径存在交集。"
            )

        suggestion_parts = [
            f"从 {controller_text} 开始检查入参、空值判断、业务规则分支和下游服务返回。" if controller_text else "从 Trace 异常节点对应的接口入口开始检查。",
            "结合 Trace 中的异常节点和慢节点，逐层核对调用链中的 Service/DAO 方法。",
            "如果命中 SQL 表名，继续检查查询条件、分页参数、数据权限和空结果处理。"
        ]

        cause = {
            'id': 'trace_code_path',
            'category': '代码路径异常',
            'analysis': ''.join(analysis_parts),
            'suggestion': '\n'.join(f"{index + 1}. {item}" for index, item in enumerate(suggestion_parts)),
            'confidence': 0.86 if evidence_files else 0.78,
            'related_code': related_code,
            'evidence_files': evidence_files[:5],
            'trace_error_node': primary_error,
            'api_path': api_path
        }

        return [cause]

    @staticmethod
    def _pick_primary_api_path(trace_data: Dict[str, Any], call_chains: List[Dict[str, Any]]) -> str:
        for chain in call_chains:
            if chain.get('api_path'):
                return chain['api_path']
        paths = trace_data.get('api_paths') or []
        return paths[0] if paths else ''

    @staticmethod
    def _pick_call_chain_for_api(api_path: str, call_chains: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not call_chains:
            return {}
        for item in call_chains:
            if api_path and item.get('api_path') == api_path:
                return item.get('call_chain') or {}
        return call_chains[0].get('call_chain') or {}

    @staticmethod
    def _select_code_evidence_files(
        files: List[Dict[str, Any]],
        api_path: str,
        controller: str,
        controller_method: str
    ) -> List[Dict[str, Any]]:
        if not files:
            return []

        priority_terms = [
            term.lower()
            for term in [api_path, controller, controller_method]
            if term
        ]

        def score(item):
            text = ' '.join([
                str(item.get('file_path') or ''),
                str(item.get('keyword') or ''),
                ' '.join(match.get('content', '') for match in item.get('matches', []))
            ]).lower()
            value = 0
            for term in priority_terms:
                if term and term in text:
                    value += 10
            if item.get('source') == 'trace':
                value += 3
            return value

        return sorted(files, key=score, reverse=True)

    @staticmethod
    def _format_related_code(evidence_files: List[Dict[str, Any]], chain: Dict[str, Any]) -> str:
        if evidence_files:
            first = evidence_files[0]
            line = ''
            matches = first.get('matches') or []
            if matches and matches[0].get('line_number'):
                line = f":{matches[0]['line_number']}"
            return f"{first.get('file_path')}{line}"

        controller_file = chain.get('controller_file')
        controller_line = chain.get('controller_line')
        if controller_file:
            return f"{controller_file}:{controller_line}" if controller_line else controller_file
        return ''


def main():
    """Test JIRA analyzer"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python jira_analyzer.py <JIRA_URL> [repo_key]")
        sys.exit(1)

    jira_url = sys.argv[1]
    repo_key = sys.argv[2] if len(sys.argv) > 2 else None

    analyzer = JiraAnalyzer(repo_key=repo_key)
    result = analyzer.analyze(jira_url)

    import json
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

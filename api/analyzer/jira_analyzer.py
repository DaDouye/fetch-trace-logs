#!/usr/bin/env python3
"""
JIRA Problem Analyzer - Unified analysis orchestration
"""

import os
import json
import hashlib
import re
import glob
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from api.jira_client import JiraClient
# from api.analyzer.comment_insights import CommentInsightExtractor, HistoricalIssueIndex
from api.analyzer.rule_engine import RuleEngine
from api.analyzer.code_search import CodeSearch
from api.analyzer.ai_analyzer import AIAnalyzer
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
        repo_urls: List[Dict[str, str]] = None,
        ref: str = "master"
    ):
        """
        Initialize analyzer

        :param repo_key: Repository key from config
        :param repo_path: Direct repository path (alternative to repo_key)
        :param repo_url: Remote Git URL (alternative to repo_key)
        :param repo_urls: List of Git URLs (alternative to repo_key, supports multiple repos)
        :param ref: Git branch/commit (used with repo_url)
        """
        self.repo_key = repo_key
        self.repo_url = repo_url
        self.ref = ref
        self.repo_urls = repo_urls  # List of {repo_url, ref} dicts

        if repo_path:
            self.repo_path = repo_path
        elif repo_url:
            self.repo_path = self._clone_or_get_local_repo(repo_url, ref) if self._is_repo_url(repo_url) else None
        elif repo_key:
            self.repo_path = self._resolve_repo_path(repo_key)
        else:
            self.repo_path = None

        # If repo_urls is provided (multiple repos), clone all to local
        self.multi_repo_paths = []
        if self.repo_urls:
            for repo_info in self.repo_urls:
                # Support both dict and Pydantic model
                r_url = repo_info.get('repo_url') if isinstance(repo_info, dict) else repo_info.repo_url
                r_ref = repo_info.get('ref', 'master') if isinstance(repo_info, dict) else getattr(repo_info, 'ref', 'master')
                if not self._is_repo_url(r_url):
                    print(f"[JiraAnalyzer] Skipping non-repository input: {r_url}")
                    continue
                local_path = self._clone_or_get_local_repo(r_url, r_ref)
                if local_path:
                    self.multi_repo_paths.append({
                        'repo_url': r_url,
                        'ref': r_ref,
                        'local_path': local_path
                    })
            print(f"[JiraAnalyzer] Initialized with {len(self.multi_repo_paths)} repos")

        self.jira_client = JiraClient()
        self.rule_engine = RuleEngine()
        # self.comment_insight_extractor = CommentInsightExtractor()
        # self.historical_issue_index = HistoricalIssueIndex()
        self.code_search = CodeSearch(self.repo_path) if self.repo_path else None
        # For multi-repo mode, we don't use single code_search but search each repo separately
        self._ai_analyzer = None
        self._rag_indexer = None

    @property
    def ai_analyzer(self) -> AIAnalyzer:
        if self._ai_analyzer is None:
            self._ai_analyzer = AIAnalyzer()
        return self._ai_analyzer

    @property
    def rag_indexer(self) -> LightRAGIndexer:
        if self._rag_indexer is None:
            self._rag_indexer = LightRAGIndexer()
        return self._rag_indexer

    def _resolve_repo_path(self, repo_key: str = None) -> Optional[str]:
        """Resolve repository path from key or return None"""
        if not repo_key:
            return None

        from config_manager import get_git_repo_url
        repo_url = get_git_repo_url(repo_key)
        if not repo_url:
            return None

        repo_name = repo_url.split('/')[-1].replace('.git', '')
        direct_path = os.path.join('./repos', repo_name)
        if os.path.exists(direct_path):
            return direct_path

        existing_clones = sorted(glob.glob(os.path.join('./repos', f"{repo_name}-*")))
        for clone_path in existing_clones:
            if os.path.isdir(clone_path):
                return clone_path

        return direct_path

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

    def _clone_or_get_local_repo(self, repo_url: str, ref: str = "master") -> str:
        """
        Clone remote repository or get existing local repository path

        :param repo_url: Remote repository URL
        :return: Local repository path
        """
        import git
        repo_name = repo_url.split('/')[-1].replace('.git', '')
        safe_ref = re.sub(r'[^A-Za-z0-9_.-]+', '_', ref or 'master')
        repo_hash = hashlib.sha1(repo_url.encode('utf-8')).hexdigest()[:8]
        local_path = os.path.join('./repos', f"{repo_name}-{safe_ref}-{repo_hash}")

        # Check if local repo exists
        if os.path.exists(local_path):
            print(f"[JiraAnalyzer] Repo already exists: {local_path}, pulling...")
            try:
                existing_repo = git.Repo(local_path)
                existing_repo.remotes.origin.fetch(ref)
                self._checkout_ref(existing_repo, ref)
            except Exception as e:
                print(f"[JiraAnalyzer] Pull failed: {e}, will use existing")
        else:
            print(f"[JiraAnalyzer] Cloning repo: {repo_url} ({ref})")
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            try:
                repo = git.Repo.clone_from(repo_url, local_path)
                self._checkout_ref(repo, ref)
            except Exception as e:
                print(f"[JiraAnalyzer] Clone failed: {e}")
                return None

        return local_path

    def _checkout_ref(self, repo, ref: str):
        if not ref:
            return
        try:
            repo.git.checkout(ref)
        except Exception:
            repo.git.checkout("FETCH_HEAD")

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
            self.repo_path = self._resolve_repo_path(repo['key'])
            self.code_search = CodeSearch(self.repo_path) if self.repo_path else None
            print(f"[JiraAnalyzer] Auto-selected repo {repo['key']} for services: {services}")
            return

        self.multi_repo_paths = []
        for repo in matched:
            local_path = self._resolve_repo_path(repo['key'])
            self.multi_repo_paths.append({
                'repo_url': repo['url'],
                'ref': 'master',
                'local_path': local_path
            })
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
        explicit_code_context = bool(
            api_paths
            or self.repo_key
            or self.repo_url
            or self.repo_urls
            or self.user_context['services']
        )
        if explicit_code_context:
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
        # comment_insights = self.comment_insight_extractor.extract(result['jira'])
        # result['jira']['comment_insights'] = comment_insights
        # result['historical_cases'] = self.historical_issue_index.search(
        #     result['jira'],
        #     comment_insights,
        #     limit=5
        # )
        # result['jira']['historical_cases'] = result['historical_cases']
        trace_resolution = self._resolve_trace_id(trace_id, result['jira'])
        result['trace_id'] = trace_resolution['trace_id']
        result['trace_id_source'] = trace_resolution['source']
        result['trace_id_candidates'] = trace_resolution['candidates']
        result['trace_id_note'] = trace_resolution['note']

        # 2. Build code context
        result['code_context'] = self._build_code_context(
            issue_key,
            api_paths,
            trace_resolution['trace_id'],
            trace_date,
            cookies,
            enable_code_context=explicit_code_context
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
        cookies: Optional[str],
        enable_code_context: bool = False
    ) -> Dict[str, Any]:
        """Build code context from various sources"""
        context = {
            'files': [],
            'call_chains': [],
            'business_evidence': [],
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
        print(f"[CodeContext] enable_code_context: {enable_code_context}")

        has_repo_context = bool(self.repo_path or self.repo_url or self.multi_repo_paths)
        if not enable_code_context:
            print("[CodeContext] Skipping code search and call chain because code analysis was not requested")
        elif not has_repo_context:
            print("[CodeContext] No repository context, code search will be skipped")

        # Get keywords from JIRA for search
        issue_full = self.jira_client.get_issue(issue_key)
        keywords = self.jira_client.extract_keywords(issue_full)
        context['search_keywords'] = keywords
        print(f"[CodeContext] Keywords: {keywords}")

        # 使用 JIRA 中的 api_paths 进行代码搜索
        search_api_paths = keywords.get('api_paths', [])
        if not search_api_paths:
            search_api_paths = []
        searched_keywords = {
            'api_paths': set(search_api_paths),
            'class_names': set(keywords.get('class_names', [])),
            'error_patterns': set(keywords.get('error_patterns', [])),
            'business_terms': set(keywords.get('business_terms', []))
        }

        if enable_code_context and has_repo_context:
            context['files'] = self._search_code(
                api_paths=search_api_paths,
                class_names=keywords.get('class_names', []),
                error_patterns=keywords.get('error_patterns', []),
                business_terms=keywords.get('business_terms', []),
                source='jira'
            )
            print(f"[CodeContext] Search results: {len(context['files'])} files")
        elif enable_code_context:
            print("[CodeContext] Skipping code search because no repository was provided")

        # Fetch trace data if trace ID provided
        trace_api_paths = []
        if trace_id:
            trace_data = self._fetch_trace_data(trace_id, trace_date, cookies)
            context['trace_data'] = trace_data
            print(f"[CodeContext] Trace summary: {self._format_trace_log_summary(trace_data)}")

            # Extract API paths from trace data if no api_paths provided
            if trace_data and not trace_data.get('error'):
                try:
                    trace_api_paths = self._normalize_api_paths(trace_data.get('api_paths', []))
                    print(f"[CodeContext] Extracted {len(trace_api_paths)} API paths from trace: {trace_api_paths}")
                    trace_keywords = self._extract_trace_search_keywords(trace_data)
                    if enable_code_context and has_repo_context and (
                        set(trace_api_paths) - searched_keywords['api_paths']
                        or set(trace_keywords['error_patterns']) - searched_keywords['error_patterns']
                        or set(trace_keywords['business_terms']) - searched_keywords['business_terms']
                    ):
                        trace_search_results = self._search_code(
                            api_paths=trace_api_paths,
                            error_patterns=trace_keywords['error_patterns'],
                            business_terms=trace_keywords['business_terms'],
                            source='trace'
                        )
                        context['files'] = self._merge_file_results(context['files'], trace_search_results)
                        searched_keywords['api_paths'].update(trace_api_paths)
                        searched_keywords['error_patterns'].update(trace_keywords['error_patterns'])
                        searched_keywords['business_terms'].update(trace_keywords['business_terms'])
                        print(f"[CodeContext] Search results after trace evidence: {len(context['files'])} files")
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

        # Perform call chain analysis for all paths at once
        # 优先使用用户提供的api_paths，其次是trace提取的
        call_chain_paths = self._normalize_api_paths(api_paths if api_paths else trace_api_paths)
        print(f"[CodeContext] Call chain paths: {call_chain_paths}")
        if enable_code_context and call_chain_paths:
            call_chain_result = self._analyze_call_chain(call_chain_paths)
            if call_chain_result:
                context['call_chains'].append({
                    'api_path': call_chain_paths,  # all paths
                    'call_chain': call_chain_result
                })
            print(f"[CodeContext] Call chains: {len(context['call_chains'])}")

        if enable_code_context:
            context['business_evidence'] = self._extract_business_evidence(context)
            print(f"[CodeContext] Business evidence: {len(context['business_evidence'])}")

        return context

    @staticmethod
    def _format_trace_log_summary(trace_data: Optional[Dict[str, Any]]) -> str:
        if not trace_data:
            return "none"
        if trace_data.get('error'):
            return f"error={trace_data.get('error')}"
        return (
            f"success={trace_data.get('success')}, "
            f"spans={trace_data.get('span_count', 0)}, "
            f"sql={trace_data.get('sql_count', 0)}, "
            f"api_paths={len(trace_data.get('api_paths') or [])}"
        )

    def _analyze_call_chain(self, api_paths: List[str]) -> Optional[Dict[str, Any]]:
        """Perform call chain analysis using existing analyzer.

        Accepts a list of API paths and analyzes them together for efficiency.
        """
        if not self.repo_path and not self.repo_key and not self.repo_url and not self.multi_repo_paths:
            print(f"[CallChain] No repo configured, skipping call chain analysis")
            return None

        if not api_paths:
            return None

        try:
            from api.analyze import JavaCallChainAnalyzer
            print(f"[CallChain] Analyzing call chains for {len(api_paths)} paths: {api_paths}")

            # Multi-repo mode: analyze first repo (call chain analysis is typically repo-specific)
            if self.multi_repo_paths:
                repo_info = self.multi_repo_paths[0]
                if repo_info.get('local_path') and os.path.exists(repo_info.get('local_path')):
                    analyzer = JavaCallChainAnalyzer(repo_path=repo_info.get('local_path'))
                else:
                    analyzer = JavaCallChainAnalyzer(repo_url=repo_info.get('repo_url'), ref=repo_info.get('ref', 'master'))
            elif self.repo_url:
                analyzer = JavaCallChainAnalyzer(repo_url=self.repo_url, ref=self.ref)
            elif self.repo_path and os.path.exists(self.repo_path):
                analyzer = JavaCallChainAnalyzer(repo_path=self.repo_path)
            else:
                analyzer = JavaCallChainAnalyzer(repo_key=self.repo_key)
            result = analyzer.analyze(api_paths)  # Pass list directly
            print(f"[CallChain] Result: {result.get('error', 'success')}")
            return result
        except Exception as e:
            print(f"[CallChain] Error: {e}")
            import traceback
            print(f"[CallChain] Traceback: {traceback.format_exc()}")
            return {'error': str(e)}

    @staticmethod
    def _normalize_api_paths(api_paths: Optional[List[str]]) -> List[str]:
        if not api_paths:
            return []
        # Flatten in case of nested lists (e.g., [['a','b']])
        flat = []
        for p in api_paths:
            if isinstance(p, list):
                flat.extend(p)
            elif isinstance(p, str) and p:
                # Handle JSON-serialized lists like "['/a','/b']"
                try:
                    # Try to parse as JSON array
                    if p.startswith('[') and p.endswith(']'):
                        parsed = json.loads(p)
                        if isinstance(parsed, list):
                            flat.extend(str(x) for x in parsed)
                            continue
                except Exception:
                    pass
                flat.append(p)
        try:
            from scripts.fetch_trace_souche import TraceFetcher
            normalized = []
            for path in flat:
                result = TraceFetcher.normalize_api_path(path)
                if isinstance(result, list):
                    normalized.extend(result)
                elif result:
                    normalized.append(result)
        except Exception:
            normalized = flat
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

    def _extract_business_evidence(self, code_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        evidence = []
        method_snippets = self._collect_call_chain_method_snippets(code_context.get('call_chains') or [])
        for snippet in method_snippets:
            hints = self._extract_business_hints_from_snippet(snippet)
            if hints:
                evidence.append({
                    'type': 'code_method',
                    'file_path': snippet.get('file_path'),
                    'line_number': snippet.get('line_number'),
                    'class_name': snippet.get('class_name'),
                    'method_name': snippet.get('method_name'),
                    'hints': hints
                })

        trace_data = code_context.get('trace_data') or {}
        for item in self._extract_zero_result_sql(trace_data.get('sql') or []):
            evidence.append({
                'type': 'trace_sql_zero_result',
                'sql': item.get('sql'),
                'rid': item.get('rid'),
                'service_name': item.get('service_name'),
                'signal': item.get('zero_signal')
            })

        logs = code_context.get('logs') or {}
        for message in logs.get('error_messages') or []:
            if self._has_zero_signal(message):
                evidence.append({
                    'type': 'log_zero_result',
                    'message': message[:240],
                    'signal': 'zero_result'
                })

        return evidence[:12]

    def _collect_call_chain_method_snippets(self, call_chains: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        snippets = []
        seen = set()

        for item in call_chains:
            chain = item.get('call_chain') or {}
            for node in self._flatten_call_chain_nodes(chain):
                file_path = node.get('file_path')
                method_name = node.get('method_name')
                if not file_path or file_path == 'Not found' or not method_name:
                    continue
                key = (file_path, method_name)
                if key in seen:
                    continue
                seen.add(key)
                method_body = self._read_method_body(file_path, method_name, node.get('line_number') or 1)
                if not method_body:
                    continue
                snippets.append({
                    'file_path': file_path,
                    'line_number': node.get('line_number') or 1,
                    'class_name': node.get('class_name') or '',
                    'method_name': method_name,
                    'body': method_body
                })

        return snippets

    def _flatten_call_chain_nodes(self, chain: Dict[str, Any]) -> List[Dict[str, Any]]:
        nodes = []

        def visit(value):
            if isinstance(value, list):
                for item in value:
                    visit(item)
                return
            if not isinstance(value, dict):
                return
            if value.get('class_name') or value.get('method_name'):
                nodes.append(value)
            for child in value.get('children') or []:
                visit(child)
            for child in value.get('call_chain') or []:
                visit(child)

        visit(chain.get('call_chain') if isinstance(chain, dict) and chain.get('call_chain') else chain)
        return nodes

    def _read_method_body(self, file_path: str, method_name: str, line_number: int) -> str:
        if not file_path:
            return ''

        if not os.path.exists(file_path):
            candidate = os.path.join(os.getcwd(), file_path)
            if os.path.exists(candidate):
                file_path = candidate
            else:
                return ''

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
        except Exception:
            return ''

        start = max(0, line_number - 1)
        signature_pattern = re.compile(rf'\b{re.escape(method_name)}\s*\(')
        for idx in range(start, min(len(lines), start + 30)):
            if signature_pattern.search(lines[idx]):
                start = idx
                break

        body_lines = []
        brace_count = 0
        started = False
        for idx in range(start, min(len(lines), start + 220)):
            line = lines[idx]
            if not started and '{' not in line:
                body_lines.append(line)
                continue
            started = True
            body_lines.append(line)
            brace_count += line.count('{') - line.count('}')
            if brace_count == 0 and idx > start:
                break

        return ''.join(body_lines)

    def _extract_business_hints_from_snippet(self, snippet: Dict[str, Any]) -> List[Dict[str, Any]]:
        body = snippet.get('body') or ''
        if not body:
            return []

        hints = []
        business_terms = ('在途', '卖车', '意向', '评估师', '分配', '数量', '为空', '不存在', '放弃', '不匹配')
        evidence_markers = ('//', 'log.', 'return', 'throw', 'if ', 'if(', 'count', 'Count')
        for index, line in enumerate(body.splitlines(), 1):
            text = line.strip()
            if not text:
                continue
            if not any(term in text for term in business_terms):
                continue
            if not any(marker in text for marker in evidence_markers):
                continue
            hints.append({
                'line_offset': index,
                'content': text[:260]
            })
            if len(hints) >= 8:
                break

        return hints

    @staticmethod
    def _extract_zero_result_sql(sql_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = []
        for item in sql_items:
            text = ' '.join(str(item.get(key) or '') for key in ('sql', 'result', 'rows', 'row_count', 'count'))
            zero_signal = JiraAnalyzer._detect_zero_signal(text)
            if not zero_signal:
                continue
            enriched = dict(item)
            enriched['zero_signal'] = zero_signal
            result.append(enriched)
        return result

    @staticmethod
    def _has_zero_signal(text: Any) -> bool:
        return bool(JiraAnalyzer._detect_zero_signal(str(text or '')))

    @staticmethod
    def _detect_zero_signal(text: str) -> str:
        if not text:
            return ''
        patterns = [
            (r'\bcount\s*[:=]\s*0\b', 'count=0'),
            (r'\brows?\s*[:=]\s*0\b', 'rows=0'),
            (r'\brow_count\s*[:=]\s*0\b', 'row_count=0'),
            (r'\bnums?\s*[:=]\s*0\b', 'nums=0'),
            (r'\btotal\s*[:=]\s*0\b', 'total=0'),
            (r'\bresult\s*[:=]\s*0\b', 'result=0'),
            (r'\bselect\s+count\s*\([^)]*\).*?\b0\b', 'select_count_zero'),
        ]
        for pattern, signal in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return signal
        return ''

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
            'http', 'server', 'client', 'unknown', 'com', 'souche', 'danube',
            'java', 'javax', 'starter', 'business', 'model', 'domain'
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
            detail = None
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
                'sql': sql_text,
                'result': self._extract_sql_result_signal(entry, detail)
            })

        return readable

    @staticmethod
    def _extract_sql_result_signal(entry: Dict[str, Any], detail: Optional[Dict[str, Any]]) -> str:
        candidates = []

        def collect(value):
            if value is None:
                return
            if isinstance(value, dict):
                for key, child in value.items():
                    lowered = str(key).lower()
                    if lowered in {'result', 'rows', 'rowcount', 'row_count', 'count', 'total', 'nums', 'affectedrows'}:
                        candidates.append(f"{key}={child}")
                    collect(child)
                return
            if isinstance(value, list):
                if not value:
                    candidates.append("rows=0")
                for child in value[:5]:
                    collect(child)
                return

        collect(entry)
        collect(detail)
        return '; '.join(dict.fromkeys(str(item) for item in candidates if item))[:300]

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
        # comment_insights = jira.get('comment_insights') or {}
        # historical_cases = result.get('historical_cases') or []

        # Combine all text for analysis
        text_to_analyze = self._combine_text_for_analysis(jira, code_context)

        # Rule-based analysis (always run)
        rule_causes = self.rule_engine.analyze(text_to_analyze)
        causes.extend(rule_causes)

        # comment_cause = self._build_comment_insight_cause(comment_insights, historical_cases)
        # if comment_cause:
        #     causes.insert(0, comment_cause)

        # Add code context evidence if available
        if code_context.get('files'):
            causes = self._enrich_with_code_evidence(causes, code_context['files'])

        code_trace_causes = self._build_code_trace_causes(jira, code_context, trace_data)
        if code_trace_causes:
            causes = code_trace_causes + causes
        else:
            code_context_causes = self._build_code_context_causes(jira, code_context)
            if code_context_causes:
                causes = code_context_causes + causes

        # AI-enhanced analysis
        ai_enhanced = False
        rag_context = None
        if use_ai:
            try:
                if os.getenv("RAG_CONTEXT_ENABLED", "false").lower() == "true":
                    rag_context = self.rag_indexer.get_context_for_analysis(jira, code_context)
                    print(f"[_analyze_causes] RAG context retrieved: {len(rag_context) if rag_context else 0} chars")

                ai_result = self.ai_analyzer.analyze(jira, code_context, trace_data, rag_context)
                ai_causes = ai_result.get('possible_causes', [])

                if ai_causes:
                    causes.extend(ai_causes)
                    ai_enhanced = True
                else:
                    # AI didn't return useful results, add a default analysis
                    causes.append({
                        'id': 'ai_analysis',
                        'category': '问题分析',
                        'analysis': f'根据JIRA问题「{jira.get("summary", "")}」的分析，'
                                    f'问题可能涉及业务流程、状态管理或数据一致性问题。'
                                    f'建议检查相关接口的入参、权限以及数据库状态。',
                        'suggestion': '1. 检查接口调用参数是否完整\n2. 验证用户权限和状态\n3. 查看相关数据库记录\n4. 确认业务流程是否正确执行',
                        'confidence': 0.7
                    })
                    ai_enhanced = True
            except Exception as e:
                # AI调用失败时添加默认分析
                causes.append({
                    'id': 'ai_analysis_error',
                    'category': '问题分析',
                    'analysis': f'系统分析完成，根据问题描述「{jira.get("summary", "")}」，'
                                f'该问题可能涉及以下方面：\n'
                                f'1. 业务流程执行异常\n'
                                f'2. 数据状态不一致\n'
                                f'3. 接口调用失败或超时\n'
                                f'4. 权限或认证问题\n\n'
                                f'AI分析服务暂时不可用，请人工排查。',
                    'suggestion': '1. 检查相关接口的日志\n2. 验证数据状态\n3. 确认业务流程是否正常',
                    'confidence': 0.5
                })

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
            # 'comment_insights': comment_insights,
            # 'historical_cases': historical_cases
        }

    def _build_comment_insight_cause(
        self,
        comment_insights: Dict[str, Any],
        historical_cases: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Promote tester comments and historical issue conclusions into a first-class cause."""
        if not comment_insights.get('has_comments') and not historical_cases:
            return None

        category = comment_insights.get('root_cause_category') or '测试备注结论'
        resolution = comment_insights.get('resolution_action') or '未明确'
        final_comment = comment_insights.get('final_comment') or '当前 Jira 暂无测试备注结论'
        real_bug = comment_insights.get('is_real_bug')
        bug_text = '是' if real_bug is True else '否' if real_bug is False else '未明确'
        similar_text = ''
        if historical_cases:
            top = historical_cases[0]
            similar_text = (
                f" 相似历史问题 {top.get('issue_key')}「{top.get('summary')}」"
                f" 的结论为：{top.get('root_cause_category')} / {top.get('resolution_action')}。"
            )

        return {
            'id': 'comment_insight',
            'category': category,
            'analysis': (
                f"测试备注识别到的处理结论：{resolution}；是否真实缺陷：{bug_text}。"
                f"末条备注：{final_comment[:240]}。{similar_text}"
            ),
            'suggestion': '优先核对测试备注中的最终结论、数据订正或第三方/权限说明，再决定是否继续做代码排查。',
            'confidence': 0.88 if comment_insights.get('has_comments') else 0.62,
            'comment_insights': comment_insights,
            'historical_cases': historical_cases[:3]
        }

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
        business_inference = self._infer_business_precondition(code_context)
        trace_error_text = primary_error.get('error_text') or primary_error.get('operation_name') or ''
        log_error_text = ''
        if logs.get('error_messages'):
            log_error_text = logs['error_messages'][0]

        analysis_parts = []
        if business_inference:
            analysis_parts.append(business_inference['analysis'])
        else:
            analysis_parts.append(
                f"Trace 在 {primary_error.get('service_name', 'Unknown')} 的 {primary_error.get('operation_name', api_path or '未知节点')} 标记为异常。"
            )
        if controller_text:
            analysis_parts.append(f"该链路已映射到代码入口 {controller_text}，问题应优先沿这个入口的调用链排查。")
        if trace_error_text:
            analysis_parts.append(f"Trace 异常信息：{trace_error_text[:180]}。")
        if log_error_text:
            analysis_parts.append(f"日志错误片段：{log_error_text[:180]}。")
        if evidence_files:
            top = evidence_files[0]
            if top.get('match_quality') == 'weak':
                analysis_parts.append(
                    f"代码搜索基于关键词 {top.get('keyword')} 命中 {top.get('file_path')}，但该命中质量较弱，仅作为辅助线索。"
                )
            else:
                analysis_parts.append(
                    f"代码搜索命中 {top.get('file_path')}，关键词为 {top.get('keyword')}，可作为异常线索与代码路径的交叉证据。"
                )

        if business_inference:
            suggestion_parts = business_inference['suggestions']
        else:
            suggestion_parts = [
                f"从 {controller_text} 开始检查入参、空值判断、业务规则分支和下游服务返回。" if controller_text else "从 Trace 异常节点对应的接口入口开始检查。",
                "结合 Trace 中的异常节点和慢节点，逐层核对调用链中的 Service/DAO 方法。",
                "如果命中 SQL 表名，继续检查查询条件、分页参数、数据权限和空结果处理。"
            ]

        cause = {
            'id': 'trace_code_path',
            'category': business_inference.get('category', '代码路径异常') if business_inference else '代码路径异常',
            'analysis': ''.join(analysis_parts),
            'suggestion': '\n'.join(f"{index + 1}. {item}" for index, item in enumerate(suggestion_parts)),
            'confidence': business_inference.get('confidence', 0.86 if evidence_files else 0.78) if business_inference else (0.86 if evidence_files else 0.78),
            'related_code': related_code,
            'evidence_files': evidence_files[:5],
            'business_evidence': code_context.get('business_evidence') or [],
            'trace_error_node': primary_error,
            'api_path': api_path
        }

        return [cause]

    def _build_code_context_causes(
        self,
        jira: Dict[str, Any],
        code_context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        call_chains = code_context.get('call_chains') or []
        files = code_context.get('files') or []
        if not call_chains and not files:
            return []

        chain = call_chains[0].get('call_chain') if call_chains else {}
        chain = chain or {}
        api_path = self._stringify_api_path(
            call_chains[0].get('api_path') if call_chains else ''
        )
        controller = chain.get('controller') or ''
        controller_method = chain.get('controller_method') or ''
        controller_text = (
            f"{controller}.{controller_method}()"
            if controller and controller_method
            else api_path or '相关代码入口'
        )
        evidence_files = self._select_code_evidence_files(files, api_path, controller, controller_method)
        related_code = self._format_related_code(evidence_files, chain)
        business_inference = self._infer_business_precondition(code_context)

        analysis_parts = []
        if business_inference:
            analysis_parts.append(business_inference['analysis'])
        elif api_path or controller or controller_method:
            analysis_parts.append(f"已根据服务/接口线索映射到代码入口 {controller_text}。")
        if files:
            top = evidence_files[0] if evidence_files else files[0]
            if top.get('match_quality') == 'weak':
                analysis_parts.append(
                    f"代码搜索命中 {len(files)} 个文件，首要命中为 {top.get('file_path')}，但关键词 {top.get('keyword')} 的命中质量较弱。"
                )
            else:
                analysis_parts.append(
                    f"代码搜索命中 {len(files)} 个相关文件，首要命中为 {top.get('file_path')}，关键词为 {top.get('keyword')}。"
                )
        if not analysis_parts:
            analysis_parts.append(f"已获取 JIRA「{jira.get('summary', '')}」对应的代码上下文。")

        suggestion_parts = business_inference['suggestions'] if business_inference else [
            f"优先检查 {controller_text} 的入参校验、权限判断、业务状态分支和下游调用返回。",
            "查看命中文件中的关键词上下文，确认是否与 JIRA 描述的问题现象一致。",
            "如果问题与数据异常相关，继续沿 Service/DAO 调用检查查询条件、数据权限和状态更新。"
        ]

        return [{
            'id': 'code_context_path',
            'category': business_inference.get('category', '代码证据分析') if business_inference else '代码证据分析',
            'analysis': ''.join(analysis_parts),
            'suggestion': '\n'.join(f"{index + 1}. {item}" for index, item in enumerate(suggestion_parts)),
            'confidence': business_inference.get('confidence', 0.74 if evidence_files else 0.62) if business_inference else (0.74 if evidence_files else 0.62),
            'related_code': related_code,
            'evidence_files': evidence_files[:5],
            'business_evidence': code_context.get('business_evidence') or [],
            'api_path': api_path
        }]

    def _infer_business_precondition(self, code_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        evidence = code_context.get('business_evidence') or []
        if not evidence:
            return None

        evidence_text = ' '.join(
            json.dumps(item, ensure_ascii=False)
            for item in evidence
        )
        has_sell_car_intention = all(term in evidence_text for term in ('卖车', '在途')) and '意向' in evidence_text
        has_zero_result = any(
            item.get('type') in {'trace_sql_zero_result', 'log_zero_result'}
            for item in evidence
        ) or self._has_zero_signal(evidence_text)
        has_assessor_distribution = '评估师' in evidence_text and '分配' in evidence_text
        has_explicit_missing_intention = '不存在在途的卖车意向' in evidence_text

        if has_sell_car_intention and (has_zero_result or has_explicit_missing_intention):
            action = '分配评估师' if has_assessor_distribution else '当前操作'
            runtime_text = (
                "Trace/日志证据中相关查询返回 0，说明当前客户没有命中在途卖车意向数据，"
                if has_zero_result
                else "代码中存在“不存在在途的卖车意向，无法分配评估师”的明确失败分支，"
            )
            return {
                'category': '业务前置条件未满足',
                'analysis': (
                    f"代码证据显示{action}依赖客户存在在途卖车意向；"
                    f"{runtime_text}"
                    "因此更可能是业务前置条件不满足，而不是单纯的入参、权限或下游调用异常。"
                ),
                'suggestions': [
                    "核对该客户是否存在 is_sell_car=是 且 operation/access phase 处于在途集合的卖车意向。",
                    "用 Trace 中的 SQL 参数复查意向表，确认 customerId、评估师、阶段条件是否导致查询结果为 0。",
                    "如果业务上允许分配，先补齐或修复该客户的在途卖车意向；如果不允许，前端/产品应在操作入口提示不可分配原因。"
                ],
                'confidence': 0.9 if has_zero_result else 0.84
            }

        return None

    @staticmethod
    def _pick_primary_api_path(trace_data: Dict[str, Any], call_chains: List[Dict[str, Any]]) -> str:
        for chain in call_chains:
            if chain.get('api_path'):
                return JiraAnalyzer._stringify_api_path(chain['api_path'])
        paths = trace_data.get('api_paths') or []
        # Flatten in case api_paths contains nested lists
        flat_paths = []
        for p in paths:
            if isinstance(p, list):
                flat_paths.extend(p)
            elif isinstance(p, str):
                flat_paths.append(p)
        return flat_paths[0] if flat_paths else ''

    @staticmethod
    def _stringify_api_path(api_path: Any) -> str:
        if isinstance(api_path, list):
            return api_path[0] if api_path else ''
        return api_path or ''

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
            value = item.get('evidence_score') or 0
            for term in priority_terms:
                if term and term in text:
                    value += 10
            if item.get('source') == 'trace':
                value += 3
            if item.get('match_quality') == 'weak':
                value -= 4
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

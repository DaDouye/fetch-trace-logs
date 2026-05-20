#!/usr/bin/env python3
"""
JIRA Problem Analyzer - Unified analysis orchestration
"""

import os
import hashlib
import re
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from api.jira_client import JiraClient
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
        return os.path.join('./repos', repo_name)

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

    def analyze(
        self,
        jira_url: str,
        api_paths: Optional[List[str]] = None,
        trace_id: Optional[str] = None,
        trace_date: Optional[str] = None,
        cookies: Optional[str] = None,
        use_ai: bool = False
    ) -> Dict[str, Any]:
        """
        Analyze JIRA issue and provide problem cause analysis

        :param jira_url: Full JIRA URL
        :param api_paths: Optional list of API paths for call chain analysis
        :param trace_id: Optional trace ID for runtime data
        :param trace_date: Optional date for trace data
        :param cookies: Optional cookies for trace API auth
        :param use_ai: Whether to use AI enhancement (reserved for future)
        :return: Analysis result dict
        """
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

        # 2. Build code context
        result['code_context'] = self._build_code_context(
            issue_key, api_paths, trace_id, trace_date, cookies
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
            'keywords': keywords
        }

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
            'search_keywords': []
        }

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

        # 使用 JIRA 中的 api_paths 进行代码搜索
        search_api_paths = keywords.get('api_paths', [])
        if not search_api_paths:
            search_api_paths = []

        # Multi-repo mode: search each repo and merge results
        if self.multi_repo_paths:
            all_search_results = []
            for repo_info in self.multi_repo_paths:
                local_path = repo_info.get('local_path')
                repo_url = repo_info.get('repo_url')
                print(f"[CodeContext] Searching repo: {repo_url}, path: {local_path}")
                code_search = CodeSearch(local_path) if local_path else None
                if code_search:
                    search_results = code_search.search(
                        api_paths=search_api_paths,
                        class_names=keywords.get('class_names', []),
                        error_patterns=keywords.get('error_patterns', []),
                        business_terms=keywords.get('business_terms', [])
                    )
                    # Add repo_url to each result for tracking source
                    for result in search_results:
                        result['repo_url'] = repo_url
                    all_search_results.extend(search_results)
                    print(f"[CodeContext] Search results from {repo_url}: {len(search_results)} files")
            context['files'] = all_search_results
            print(f"[CodeContext] Total search results from all repos: {len(all_search_results)} files")
        elif self.code_search:
            search_results = self.code_search.search(
                api_paths=search_api_paths,
                class_names=keywords.get('class_names', []),
                error_patterns=keywords.get('error_patterns', []),
                business_terms=keywords.get('business_terms', [])
            )
            context['files'] = search_results
            print(f"[CodeContext] Search results: {len(search_results)} files")
        else:
            print("[CodeContext] Skipping code search because no repository was provided")

        # Fetch trace data if trace ID provided
        trace_api_paths = []
        if trace_id:
            trace_data = self._fetch_trace_data(trace_id, trace_date, cookies)
            context['trace_data'] = trace_data
            print(f"[CodeContext] Trace data: {trace_data}")

            # Extract API paths from trace data if no api_paths provided
            if not api_paths and trace_data and not trace_data.get('error'):
                try:
                    trace_api_paths = trace_data.get('api_paths', [])
                    print(f"[CodeContext] Extracted {len(trace_api_paths)} API paths from trace: {trace_api_paths}")

                    # Use trace API paths for code search if no other API paths
                    if not search_api_paths and trace_api_paths:
                        if self.multi_repo_paths:
                            # Multi-repo: search each repo
                            all_search_results = []
                            for repo_info in self.multi_repo_paths:
                                local_path = repo_info.get('local_path')
                                repo_url = repo_info.get('repo_url')
                                code_search = CodeSearch(local_path) if local_path else None
                                if code_search:
                                    search_results = code_search.search(
                                        api_paths=trace_api_paths,
                                        class_names=keywords.get('class_names', []),
                                        error_patterns=keywords.get('error_patterns', []),
                                        business_terms=keywords.get('business_terms', [])
                                    )
                                    for result in search_results:
                                        result['repo_url'] = repo_url
                                    all_search_results.extend(search_results)
                            context['files'] = all_search_results
                        elif self.code_search:
                            search_results = self.code_search.search(
                                api_paths=trace_api_paths,
                                class_names=keywords.get('class_names', []),
                                error_patterns=keywords.get('error_patterns', []),
                                business_terms=keywords.get('business_terms', [])
                            )
                            context['files'] = search_results
                        print(f"[CodeContext] Search results from trace API paths: {len(context['files'])} files")
                except Exception as e:
                    print(f"[CodeContext] Failed to extract API paths from trace: {e}")

        # Perform call chain analysis for each API path
        # 优先使用用户提供的api_paths，其次是trace提取的
        call_chain_paths = api_paths if api_paths else trace_api_paths
        print(f"[CodeContext] Call chain paths: {call_chain_paths}")
        if call_chain_paths:
            for api_path in call_chain_paths:
                call_chain_result = self._analyze_call_chain(api_path)
                if call_chain_result:
                    context['call_chains'].append({
                        'api_path': api_path,
                        'call_chain': call_chain_result
                    })
            print(f"[CodeContext] Call chains: {len(context['call_chains'])}")

        return context

    def _analyze_call_chain(self, api_path: str) -> Optional[Dict[str, Any]]:
        """Perform call chain analysis using existing analyzer"""
        if not self.repo_key and not self.repo_url and not self.multi_repo_paths:
            print(f"[CallChain] No repo_key or repo_url or repo_urls, skipping call chain analysis for {api_path}")
            return None

        try:
            from api.analyze import JavaCallChainAnalyzer
            print(f"[CallChain] Analyzing call chain for: {api_path}")

            # Multi-repo mode: analyze first repo (call chain analysis is typically repo-specific)
            if self.multi_repo_paths:
                repo_info = self.multi_repo_paths[0]
                analyzer = JavaCallChainAnalyzer(repo_url=repo_info.get('repo_url'), ref=repo_info.get('ref', 'master'))
            elif self.repo_url:
                analyzer = JavaCallChainAnalyzer(repo_url=self.repo_url, ref=self.ref)
            else:
                analyzer = JavaCallChainAnalyzer(repo_key=self.repo_key)
            result = analyzer.analyze(api_path)
            print(f"[CallChain] Result: {result.get('error', 'success')}")
            return result
        except Exception as e:
            print(f"[CallChain] Error: {e}")
            import traceback
            print(f"[CallChain] Traceback: {traceback.format_exc()}")
            return {'error': str(e)}

    def _fetch_trace_data(self, trace_id: str, date: str, cookies: str) -> Optional[Dict[str, Any]]:
        """Fetch trace data from Souche tracing system"""
        try:
            from scripts.fetch_trace_souche import TraceFetcher
            verify_ssl = os.getenv("TRACE_VERIFY_SSL", "false").lower() == "true"
            fetcher = TraceFetcher(cookies=cookies, verify_ssl=verify_ssl)
            trace_data = fetcher.fetch_trace(trace_id, date)
            if trace_data:
                return self._summarize_trace(trace_id, date, trace_data, fetcher)
            failure_reason = self._build_trace_failure_reason(trace_id, date, fetcher)
            return {
                'trace_id': trace_id,
                'date': date,
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

    def _build_trace_failure_reason(self, trace_id: str, date: str, fetcher) -> str:
        inferred_time = self._infer_trace_time(trace_id)
        date_hint = f"Trace ID 时间约为 {inferred_time}。" if inferred_time else ""
        last_error = getattr(fetcher, 'last_error', None)

        if last_error:
            message = last_error.get('message') or '链路平台未返回有效数据'
            if last_error.get('type') in {'http_error', 'network_error', 'invalid_response'}:
                return f"{message} {date_hint}".strip()
            if last_error.get('type') == 'empty_response':
                return f"链路平台返回空数据。{date_hint}请确认登录凭证是否有效、是否有该 Trace 的访问权限。"
            return f"{message} {date_hint}".strip()

        return f"未获取到 Trace 数据。{date_hint}请确认 Trace ID、日期、登录凭证和访问权限。"

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

    def _summarize_trace(self, trace_id: str, date: str, trace_data: Dict[str, Any], fetcher) -> Dict[str, Any]:
        from scripts.fetch_trace_souche import TraceFetcher

        spans = self._extract_trace_spans(trace_data)
        if not spans:
            failure_reason = self._build_trace_failure_reason(trace_id, date, fetcher)
            return {
                'trace_id': trace_id,
                'date': date,
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
                        'has_error': has_error(node)
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

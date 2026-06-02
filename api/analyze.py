#!/usr/bin/env python3
"""
Java 代码调用链静态分析器
用于分析 Spring Boot 项目中的接口调用链路
支持本地仓库和远程 Git 两种模式
"""

import os
import re
import glob
import json
import hashlib
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple, Union
from pathlib import Path

from api.git_fetcher import get_git_fetcher, GitFetcher
from api.analyzer.claude_code_service import ClaudeCodeAnalysisService


@dataclass
class CallChainNode:
    """调用链节点"""
    layer: str
    class_name: str
    method_name: str
    file_path: str
    line_number: int
    sql: Optional[str] = None
    children: List['CallChainNode'] = field(default_factory=list)
    annotation: Optional[str] = None
    is_entry: bool = False


class JavaCallChainAnalyzer:
    """Java 调用链分析器"""

    # 常见非业务方法黑名单
    EXCLUDED_METHODS = {
        'toString', 'hashCode', 'equals', 'getClass', 'logger',
        'wait', 'notify', 'notifyAll', 'length', 'isEmpty', 'getMessage',
        'log', 'info', 'error', 'warn', 'debug', 'remove', 'clear',
        'set', 'get', 'put', 'contains', 'entrySet', 'keySet', 'values',
        'list', 'map', 'set', 'is', 'has', 'new', 'if', 'for', 'while'
    }

    def __init__(
        self,
        repo_path: str = None,
        repo_key: str = None,
        repo_url: str = None,
        ref: str = "master"
    ):
        """
        初始化分析器

        :param repo_path: 本地仓库路径（优先使用）
        :param repo_key: 仓库键名（从 config 获取 URL）
        :param repo_url: 远程仓库 URL（直接指定，使用 GitFetcher）
        :param ref: Git 分支/ commit（配合 repo_url 使用）
        """
        self._git_fetcher: Optional[GitFetcher] = None
        self._use_remote = False
        self.repo_url = repo_url
        self.ref = ref

        if repo_path:
            self.repo_path = repo_path
            self._use_remote = False
        elif repo_key:
            from config_manager import get_git_repo_url
            url = get_git_repo_url(repo_key)
            if not url:
                raise ValueError(f"在配置中找不到键名为 '{repo_key}' 的Git仓库地址")
            self.repo_url = url
            local_repo_path = self._resolve_local_repo_path(url)
            if not local_repo_path:
                local_repo_path = self._clone_or_get_local_repo(url, ref)
            self.repo_path = local_repo_path
            self._use_remote = False
        elif repo_url:
            self.repo_path = self._clone_or_get_local_repo(repo_url, ref)
            self._use_remote = False
        else:
            raise ValueError("必须提供 repo_path、repo_key 或 repo_url 参数")

        self.web_src_path = os.path.join(self.repo_path, 'web/src/main/java')
        self.config_path = os.path.join(self.repo_path, 'web/config')
        self.claude_service = ClaudeCodeAnalysisService(self.repo_path)

        self._controller_cache: Dict[str, Tuple[str, str, int]] = {}
        self._service_impl_cache: Dict[str, str] = {}
        self._mapper_sql_cache: Dict[str, Dict[str, str]] = {}

    @staticmethod
    def _resolve_local_repo_path(repo_url: str) -> Optional[str]:
        repo_name = repo_url.split('/')[-1].replace('.git', '')
        direct_path = os.path.join('./repos', repo_name)
        if os.path.isdir(direct_path):
            return direct_path

        existing_clones = sorted(glob.glob(os.path.join('./repos', f"{repo_name}-*")))
        for clone_path in existing_clones:
            if os.path.isdir(clone_path):
                return clone_path
        return None

    @staticmethod
    def _clone_or_get_local_repo(repo_url: str, ref: str = "master") -> str:
        import git
        repo_name = repo_url.split('/')[-1].replace('.git', '')
        safe_ref = re.sub(r'[^A-Za-z0-9_.-]+', '_', ref or 'master')
        repo_hash = hashlib.sha1(repo_url.encode('utf-8')).hexdigest()[:8]
        local_path = os.path.join('./repos', f"{repo_name}-{safe_ref}-{repo_hash}")

        if os.path.exists(local_path):
            repo = git.Repo(local_path)
            try:
                repo.remotes.origin.fetch(ref)
                JavaCallChainAnalyzer._checkout_ref(repo, ref)
            except Exception:
                pass
            return local_path

        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        repo = git.Repo.clone_from(repo_url, local_path)
        JavaCallChainAnalyzer._checkout_ref(repo, ref)
        return local_path

    @staticmethod
    def _checkout_ref(repo, ref: str) -> None:
        if not ref:
            return
        try:
            repo.git.checkout(ref)
        except Exception:
            repo.git.checkout("FETCH_HEAD")

    def analyze(self, api_path: str, trace_id: str = None, date: str = None, cookies: str = None) -> Dict[str, Any]:
        api_path = self._normalize_api_path(api_path)
        if api_path.endswith('.json'):
            api_path = api_path[:-5]
        if api_path.endswith('/'):
            api_path = api_path[:-1]

        trace_data = None
        if trace_id:
            trace_data = self._fetch_trace_data(trace_id, date, cookies)

        result = self.claude_service.analyze_call_chain(
            api_path=api_path,
            trace_context=trace_data,
            ref=self.ref
        )
        result['api_path'] = api_path
        if trace_data:
            result['trace_data'] = trace_data
        return result

    @staticmethod
    def _normalize_api_path(api_path: str) -> str:
        try:
            from scripts.fetch_trace_souche import TraceFetcher
            return TraceFetcher.normalize_api_path(api_path) or (api_path or '').strip()
        except Exception:
            return (api_path or '').strip()

    def _read_file(self, file_path: str) -> Optional[str]:
        """读取文件内容，兼容本地和远程模式"""
        if self._use_remote:
            # 远程模式：使用 GitFetcher
            return self._git_fetcher.get_file(file_path)
        else:
            # 本地模式：直接读取
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            except Exception:
                return None

    def _file_exists(self, file_path: str) -> bool:
        """检查文件是否存在"""
        if self._use_remote:
            return self._git_fetcher.file_exists(file_path)
        else:
            return os.path.exists(file_path)

    def _find_controller_method(self, api_path: str) -> Optional[Tuple[str, str, str, int]]:
        search_path = api_path.strip('/')
        if search_path.endswith('.json'):
            search_path = search_path[:-5]

        if api_path in self._controller_cache:
            return self._controller_cache[api_path]

        if self._use_remote:
            return self._find_controller_method_remote(api_path)
        else:
            return self._find_controller_method_local(api_path)

    def _find_controller_method_local(self, api_path: str) -> Optional[Tuple[str, str, str, int]]:
        """本地模式：查找 Controller 方法"""
        json_dir = os.path.join(self.web_src_path, 'com/jiaxuan/supermario/json')
        if not os.path.exists(json_dir):
            return None

        REST_ANNOTATION_PATTERN = re.compile(r'@Rest\s*\(\s*value\s*=\s*["\']([^"\']+)["\'].*?\)', re.DOTALL)

        for root, dirs, files in os.walk(json_dir):
            for file in files:
                if not file.endswith('.java'):
                    continue

                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                result = self._extract_controller_from_content(content, file_path, api_path)
                if result:
                    self._controller_cache[api_path] = result
                    return result

        return None

    def _find_controller_method_remote(self, api_path: str) -> Optional[Tuple[str, str, str, int]]:
        """远程模式：查找 Controller 方法"""
        json_dir = 'web/src/main/java/com/jiaxuan/supermario/json'
        files = self._git_fetcher.list_files(json_dir)
        if not files:
            return None

        REST_ANNOTATION_PATTERN = re.compile(r'@Rest\s*\(\s*value\s*=\s*["\']([^"\']+)["\'].*?\)', re.DOTALL)

        for file_rel_path in files:
            if not file_rel_path.endswith('.java'):
                continue

            content = self._read_file(file_rel_path)
            if not content:
                continue

            result = self._extract_controller_from_content(content, file_rel_path, api_path)
            if result:
                self._controller_cache[api_path] = result
                return result

        return None

    def _extract_controller_from_content(
        self,
        content: str,
        file_path: str,
        api_path: str
    ) -> Optional[Tuple[str, str, str, int]]:
        """从文件内容中提取 Controller 信息"""
        class_match = re.search(r'public\s+class\s+(\w+)', content)
        if not class_match:
            return None
        class_name = class_match.group(1)

        pkg_match = re.search(r'package\s+([\w\.]+)\s*;', content)
        package_prefix = ''
        if pkg_match:
            pkg = pkg_match.group(1)
            for part in pkg.split('.'):
                if part in ['v1', 'v2', 'v3', 'crm', 'ai', 'admin']:
                    package_prefix = part
                    break

        api_match = re.search(r'@Api\s*\(\s*value\s*=\s*["\']([^"\']+)["\']', content)
        api_value = api_match.group(1) if api_match else class_name

        REST_ANNOTATION_PATTERN = re.compile(r'@Rest\s*\(\s*value\s*=\s*["\']([^"\']+)["\'].*?\)', re.DOTALL)

        for match in REST_ANNOTATION_PATTERN.finditer(content):
            rest_path = match.group(1).strip('/')

            possible_paths = [
                f"/{package_prefix}/{api_value}/{rest_path}" if package_prefix else f"/{api_value}/{rest_path}",
                f"/{rest_path}",
            ]

            for full_path in possible_paths:
                if self._match_api_path(full_path, api_path):
                    method_name = self._find_method_for_annotation(content, match.start())
                    line_number = content[:match.start()].count('\n') + 1

                    return (class_name, method_name, file_path, line_number)

        return None

    def _match_api_path(self, found_path: str, target_path: str) -> bool:
        found = found_path.strip('/')
        target = target_path.strip('/')

        if found.endswith('.json'):
            found = found[:-5]
        if target.endswith('.json'):
            target = target[:-5]

        if found == target:
            return True
        if target.startswith(found + '/') or found.startswith(target + '/'):
            return True
        return False

    def _find_method_for_annotation(self, content: str, annotation_pos: int) -> str:
        search_start = annotation_pos
        search_end = min(annotation_pos + 500, len(content))
        snippet = content[search_start:search_end]
        method_match = re.search(
            r'public\s+(?:<[^>]+>\s*)?[\w<>\[\],\s.?]+\s+(\w+)\s*\(',
            snippet
        )
        return method_match.group(1) if method_match else "unknown"

    def _build_call_chain(self, class_name: str, method_name: str, file_path: str, line_number: int) -> CallChainNode:
        content = self._read_file(file_path)
        if not content:
            # 创建空节点
            return CallChainNode(
                layer='Controller',
                class_name=class_name,
                method_name=method_name,
                file_path=file_path,
                line_number=line_number,
                annotation=f'@Rest("{method_name}")',
                is_entry=True
            )

        root = CallChainNode(
            layer='Controller',
            class_name=class_name,
            method_name=method_name,
            file_path=file_path,
            line_number=line_number,
            annotation=f'@Rest("{method_name}")',
            is_entry=True
        )

        # 查找外部服务调用
        method_calls = list(self._extract_method_calls(content, method_name, line_number))
        for call in method_calls:
            child_node = self._trace_call(call['class'], call['method'], call['line'])
            if child_node:
                root.children.append(child_node)

        # 查找 this. 形式的内部方法调用
        internal_calls = list(self._extract_this_method_calls(content, method_name, line_number))
        for internal in internal_calls:
            child_node = self._trace_this_call(file_path, internal['method'], internal['line'])
            if child_node:
                root.children.append(child_node)

        return root

    def _extract_method_calls(self, content: str, method_name: str, start_line: int) -> List[Dict]:
        """从方法体中提取外部服务调用 (xxxService.method())"""
        lines = content.split('\n')

        method_start = -1
        brace_count = 0
        in_method = False

        for i in range(start_line - 1, len(lines)):
            line = lines[i]
            if method_start == -1 and '{' in line:
                method_start = i
                in_method = True

            if in_method:
                brace_count += line.count('{') - line.count('}')
                if brace_count == 0 and method_start != i:
                    break

                # 匹配 xxxService.method() 或 xxxMapper.method() 或 xxxDAO.method()
                service_call_match = re.search(
                    r'(\w+Service|\w+DAO|\w+Mapper|\w+Manager)\.(\w+)\s*\(',
                    line
                )
                if service_call_match:
                    line_no = i + 1
                    service_field = service_call_match.group(1)
                    service_method = service_call_match.group(2)

                    if service_method not in self.EXCLUDED_METHODS:
                        yield {'class': service_field, 'method': service_method, 'line': line_no}

    def _extract_this_method_calls(self, content: str, method_name: str, start_line: int) -> List[Dict]:
        """从方法体中提取 this.method() 形式的内部方法调用"""
        lines = content.split('\n')

        method_start = -1
        brace_count = 0
        in_method = False

        for i in range(start_line - 1, len(lines)):
            line = lines[i]
            if method_start == -1 and '{' in line:
                method_start = i
                in_method = True

            if in_method:
                brace_count += line.count('{') - line.count('}')
                if brace_count == 0 and method_start != i:
                    break

                # 只匹配 this.method() 形式的调用
                internal_match = re.search(r'this\.(\w+)\s*\(', line)
                if internal_match:
                    method_called = internal_match.group(1)
                    line_no = i + 1

                    if method_called not in self.EXCLUDED_METHODS and method_called != method_name:
                        yield {'class': 'internal', 'method': method_called, 'line': line_no}

    def _trace_call(self, service_field: str, method_name: str, line_number: int) -> Optional[CallChainNode]:
        """追踪外部服务调用"""
        impl_path = self._find_service_impl(service_field)
        if not impl_path:
            return CallChainNode(layer='Service', class_name=service_field, method_name=method_name,
                               file_path='Not found', line_number=line_number)

        impl_content = self._read_file(impl_path)
        if not impl_content:
            return CallChainNode(layer='Service', class_name=service_field, method_name=method_name,
                               file_path=impl_path, line_number=line_number)

        impl_method = self._find_implementation_method(impl_content, method_name)
        if not impl_method:
            return CallChainNode(layer='Service', class_name=service_field, method_name=method_name,
                               file_path=impl_path, line_number=line_number)

        service_class_name = os.path.basename(impl_path).replace('.java', '')
        service_node = CallChainNode(layer='Service', class_name=service_class_name, method_name=method_name,
                                   file_path=impl_path, line_number=impl_method['line'])

        # 提取 DAO/Mapper 调用
        for call in self._extract_method_calls(impl_content, impl_method['name'], impl_method['line']):
            if any(x in call['class'] for x in ['DAO', 'Mapper', 'Manager']):
                dao_node = self._trace_dao_call(call['class'], call['method'], call['line'])
                if dao_node:
                    service_node.children.append(dao_node)

        # 提取 this. 形式的内部方法调用
        internal_calls = list(self._extract_this_method_calls(impl_content, impl_method['name'], impl_method['line']))
        for internal in internal_calls:
            child_node = self._trace_this_call(impl_path, internal['method'], internal['line'])
            if child_node:
                service_node.children.append(child_node)

        return service_node

    def _trace_this_call(self, class_path: str, method_name: str, line_number: int) -> Optional[CallChainNode]:
        """追踪 this.method() 调用"""
        content = self._read_file(class_path)
        if not content:
            return CallChainNode(layer='Internal', class_name=os.path.basename(class_path).replace('.java', ''),
                               method_name=method_name, file_path=class_path, line_number=line_number)

        method_info = self._find_method_in_content(content, method_name)
        if not method_info:
            return CallChainNode(layer='Internal', class_name=os.path.basename(class_path).replace('.java', ''),
                               method_name=method_name, file_path=class_path, line_number=line_number)

        class_name = os.path.basename(class_path).replace('.java', '')
        internal_node = CallChainNode(layer='Internal', class_name=class_name, method_name=method_name,
                                    file_path=class_path, line_number=method_info['line'])

        # 继续追踪该方法内的所有外部服务调用 (DAO/Mapper 和 Service)
        for call in self._extract_method_calls(content, method_info['name'], method_info['line']):
            if any(x in call['class'] for x in ['DAO', 'Mapper', 'Manager']):
                dao_node = self._trace_dao_call(call['class'], call['method'], call['line'])
                if dao_node:
                    internal_node.children.append(dao_node)
            elif 'Service' in call['class']:
                service_node = self._trace_call(call['class'], call['method'], call['line'])
                if service_node:
                    internal_node.children.append(service_node)

        # 继续追踪该方法内的 this. 调用
        internal_calls = list(self._extract_this_method_calls(content, method_info['name'], method_info['line']))
        for internal in internal_calls:
            child_node = self._trace_this_call(class_path, internal['method'], internal['line'])
            if child_node:
                internal_node.children.append(child_node)

        return internal_node

    def _find_method_in_content(self, content: str, method_name: str) -> Optional[Dict]:
        """在文件内容中查找私有方法定义"""
        pattern = re.compile(rf'private\s+(?:\w+(?:<[^>]+>)?\s+)+{re.escape(method_name)}\s*\(', re.DOTALL)
        match = pattern.search(content)
        if match:
            return {'name': method_name, 'line': content[:match.start()].count('\n') + 1}

        # 也尝试 public 方法
        pattern = re.compile(rf'public\s+(?:\w+(?:<[^>]+>)?\s+)+{re.escape(method_name)}\s*\(', re.DOTALL)
        match = pattern.search(content)
        if match:
            return {'name': method_name, 'line': content[:match.start()].count('\n') + 1}

        return None

    def _find_service_impl(self, service_interface: str) -> Optional[str]:
        """查找 Service 实现类路径"""
        if service_interface in self._service_impl_cache:
            return self._service_impl_cache[service_interface]

        base_name = service_interface
        for suffix in ['Service', 'DAO', 'Mapper', 'Manager', 'Repository']:
            if base_name.endswith(suffix):
                base_name = base_name[:-len(suffix)]
                break

        # 处理 i 前缀约定: iCustomerService -> CustomerServiceImpl
        if base_name.startswith('I') and len(base_name) > 1:
            base_name = base_name[0].lower() + base_name[1:]
        elif base_name.startswith('i'):
            base_name = base_name[1:]
        impl_name = base_name + 'ServiceImpl.java'

        if self._use_remote:
            # 远程模式：搜索文件
            impl_path = self._search_remote_file('web/src/main/java/com/jiaxuan/supermario/service/impl', impl_name)
            if impl_path:
                self._service_impl_cache[service_interface] = impl_path
                return impl_path
        else:
            # 本地模式
            impl_dir = os.path.join(self.web_src_path, 'com/jiaxuan/supermario/service/impl')
            if os.path.exists(impl_dir):
                for root, dirs, files in os.walk(impl_dir):
                    for file in files:
                        if file.lower() == impl_name.lower():
                            impl_path = os.path.join(root, file)
                            self._service_impl_cache[service_interface] = impl_path
                            return impl_path

        return None

    def _search_remote_file(self, directory: str, filename: str) -> Optional[str]:
        """在远程仓库目录中搜索文件"""
        files = self._git_fetcher.list_files(directory)
        for file_path in files:
            if file_path.endswith(filename):
                return file_path
            # 也检查带路径的
            if filename in file_path:
                return file_path
        return None

    def _trace_dao_call(self, dao_class: str, method_name: str, line_number: int) -> Optional[CallChainNode]:
        """追踪 DAO/Mapper 调用"""
        mapper_name = dao_class
        for suffix in ['DAO', 'Mapper', 'Manager']:
            if mapper_name.endswith(suffix):
                mapper_name = mapper_name[:-len(suffix)]
                break
        mapper_name += 'Mapper'

        mapper_path = self._find_mapper_file(mapper_name)
        if not mapper_path:
            return CallChainNode(layer='DAO', class_name=dao_class, method_name=method_name,
                               file_path='Not found', line_number=line_number)

        sql = self._get_sql_from_mapper(mapper_name, method_name)

        dao_node = CallChainNode(layer='DAO', class_name=dao_class, method_name=method_name,
                                file_path=mapper_path, line_number=line_number)

        if sql:
            sql_node = CallChainNode(layer='SQL', class_name=mapper_name, method_name=method_name,
                                    file_path=mapper_path, line_number=line_number, sql=sql)
            dao_node.children.append(sql_node)

        return dao_node

    def _find_mapper_file(self, mapper_name: str) -> Optional[str]:
        """查找 Mapper 接口文件"""
        mapper_file = mapper_name + '.java'

        if self._use_remote:
            return self._search_remote_file('web/src/main/java/com/jiaxuan/supermario/dao/mapper', mapper_file)
        else:
            mapper_dir = os.path.join(self.web_src_path, 'com/jiaxuan/supermario/dao/mapper')
            if os.path.exists(mapper_dir):
                for root, dirs, files in os.walk(mapper_dir):
                    if mapper_file in files:
                        return os.path.join(root, mapper_file)
        return None

    def _get_sql_from_mapper(self, mapper_name: str, method_name: str) -> Optional[str]:
        """从 MyBatis XML 获取 SQL"""
        cache_key = mapper_name
        if cache_key in self._mapper_sql_cache:
            return self._mapper_sql_cache[cache_key].get(method_name)

        if self._use_remote:
            # 远程模式：需要从 config 目录获取 XML
            sqlmap_dir = 'web/config'
            xml_files = self._git_fetcher.list_files(sqlmap_dir)
            class_name = mapper_name
            for suffix in ['Mapper', 'DAO', 'Manager']:
                if class_name.endswith(suffix):
                    class_name = class_name[:-len(suffix)]
                    break
            class_name = class_name + 'Mapper'

            for xml_path in xml_files:
                if not xml_path.endswith('.xml'):
                    continue

                xml_content = self._read_file(xml_path)
                if not xml_content:
                    continue

                ns_match = re.search(r'namespace\s*=\s*["\']([^"\']+)["\']', xml_content)
                if not ns_match:
                    continue

                full_mapper_name = ns_match.group(1)
                mn_lower = mapper_name.lower()
                cn_lower = class_name.lower()
                fn_lower = full_mapper_name.lower()

                if not (fn_lower.endswith('.' + mn_lower) or fn_lower.endswith('/' + mn_lower) or
                        fn_lower.endswith('.' + cn_lower) or fn_lower.endswith('/' + cn_lower)):
                    continue

                sql_cache = self._mapper_sql_cache.setdefault(cache_key, {})

                for sql_match in re.finditer(
                    r'<(?P<type>select|insert|update|delete)\s+id\s*=\s*["\'](\w+)["\'][^>]*>(?P<sql>.*?)</(?P=type)>',
                    xml_content, re.DOTALL | re.IGNORECASE
                ):
                    sql_id = sql_match.group(2)
                    sql_text = sql_match.group('sql').strip()
                    sql_text = re.sub(r'\s+', ' ', sql_text)
                    sql_cache[sql_id] = sql_text

                return sql_cache.get(method_name)
        else:
            # 本地模式
            sqlmap_dir = self.config_path
            if not os.path.exists(sqlmap_dir):
                return None

            class_name = mapper_name
            for suffix in ['Mapper', 'DAO', 'Manager']:
                if class_name.endswith(suffix):
                    class_name = class_name[:-len(suffix)]
                    break
            class_name = class_name + 'Mapper'

            xml_files = list(Path(sqlmap_dir).glob('**/*Mapper.xml'))

            for xml_file in xml_files:
                with open(xml_file, 'r', encoding='utf-8', errors='ignore') as f:
                    xml_content = f.read()

                ns_match = re.search(r'namespace\s*=\s*["\']([^"\']+)["\']', xml_content)
                if not ns_match:
                    continue

                full_mapper_name = ns_match.group(1)
                mn_lower = mapper_name.lower()
                cn_lower = class_name.lower()
                fn_lower = full_mapper_name.lower()
                if not (fn_lower.endswith('.' + mn_lower) or fn_lower.endswith('/' + mn_lower) or
                        fn_lower.endswith('.' + cn_lower) or fn_lower.endswith('/' + cn_lower)):
                    continue

                sql_cache = self._mapper_sql_cache.setdefault(cache_key, {})

                for sql_match in re.finditer(
                    r'<(?P<type>select|insert|update|delete)\s+id\s*=\s*["\'](\w+)["\'][^>]*>(?P<sql>.*?)</(?P=type)>',
                    xml_content, re.DOTALL | re.IGNORECASE
                ):
                    sql_id = sql_match.group(2)
                    sql_text = sql_match.group('sql').strip()
                    sql_text = re.sub(r'\s+', ' ', sql_text)
                    sql_cache[sql_id] = sql_text

                return sql_cache.get(method_name)

        return None

    def _find_implementation_method(self, content: str, method_name: str) -> Optional[Dict]:
        """在实现类中查找方法"""
        pattern = re.compile(rf'public\s+(?:static\s+)?(?:\w+(?:<[^>]+>)?\s+)+{re.escape(method_name)}\s*\(', re.DOTALL)
        match = pattern.search(content)
        if match:
            return {'name': method_name, 'line': content[:match.start()].count('\n') + 1}
        return None

    def analyze_from_trace(self, trace_id: str, date: str = None, cookies: str = None) -> Dict[str, Any]:
        trace_data = self._fetch_raw_trace_data(trace_id, date, cookies)
        warnings = []
        result = {
            'api_path': None,
            'source': 'trace',
            'trace_data': trace_data,
            'detected_api_paths': [],
            'call_chains': [],
            'warnings': warnings
        }

        if not trace_data:
            warnings.append('未获取到 Trace 数据，无法自动识别入口 API')
            return result

        if trace_data.get('error'):
            warnings.append(trace_data['error'])
            return result

        api_paths = self._extract_api_paths_from_trace(trace_data)
        result['detected_api_paths'] = api_paths
        if not api_paths:
            warnings.append('已获取 Trace，但未能识别入口 API')
            return result

        for api_path in api_paths:
            result['call_chains'].append({
                'api_path': api_path,
                'call_chain': self.analyze(api_path)
            })

        return result

    @staticmethod
    def _extract_api_paths_from_trace(trace_data: Dict[str, Any]) -> List[str]:
        try:
            from scripts.fetch_trace_souche import TraceFetcher
            raw_paths = TraceFetcher.extract_api_paths(trace_data)
        except Exception:
            raw_paths = trace_data.get('api_paths', []) if isinstance(trace_data, dict) else []

        api_paths = []
        seen = set()
        for path in raw_paths or []:
            normalized = JavaCallChainAnalyzer._normalize_api_path(path)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            api_paths.append(normalized)
        return api_paths

    def _fetch_raw_trace_data(self, trace_id: str, date: str = None, cookies: str = None) -> Optional[Dict]:
        try:
            from scripts.fetch_trace_souche import TraceFetcher
            effective_date = date or self._infer_trace_date(trace_id)
            if not effective_date:
                return {'error': '未提供 Trace 日期，且无法从 Trace ID 推断日期。请填写 Trace 日期（YYYY-MM-DD）。'}
            verify_ssl = os.getenv("TRACE_VERIFY_SSL", "false").lower() == "true"
            fetcher = TraceFetcher(cookies=cookies, verify_ssl=verify_ssl)
            return fetcher.fetch_trace(trace_id, effective_date)
        except Exception as e:
            return {'error': str(e)}

    @staticmethod
    def _infer_trace_date(trace_id: str) -> Optional[str]:
        match = re.match(r'^(\d{13})_', trace_id or '')
        if not match:
            return None
        try:
            ts = int(match.group(1)) / 1000
            return datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
        except Exception:
            return None

    def _fetch_trace_data(self, trace_id: str, date: str, cookies: str = None) -> Optional[Dict]:
        """获取运行时 Trace 数据"""
        try:
            from scripts.fetch_trace_souche import TraceFetcher
            verify_ssl = os.getenv("TRACE_VERIFY_SSL", "false").lower() == "true"
            fetcher = TraceFetcher(cookies=cookies, verify_ssl=verify_ssl)
            trace_data = fetcher.fetch_trace(trace_id, date)
            if trace_data:
                sql_entries = TraceFetcher.extract_sql_data(trace_data)
                return {'trace_id': trace_id, 'span_count': len(sql_entries) if sql_entries else 0,
                        'has_sql': len(sql_entries) > 0 if sql_entries else False}
        except Exception as e:
            return {'error': str(e)}
        return None

    def _format_ascii(self, node: CallChainNode, api_path: str, prefix: str = '', is_last: bool = True) -> str:
        """生成 ASCII 调用链图"""
        lines = []

        if node.is_entry:
            lines.append(f"{api_path}")
            lines.append("│")
        else:
            connector = '└── ' if is_last else '├── '
            lines.append(f"{prefix}{connector}[{node.layer}] {node.class_name}.{node.method_name}()")

        if node.sql:
            sql_preview = node.sql[:100] + '...' if len(node.sql) > 100 else node.sql
            lines.append(f"{prefix}    └── SQL: {sql_preview}")

        child_prefix = prefix + ('    ' if is_last else '│   ')
        for i, child in enumerate(node.children):
            is_last_child = (i == len(node.children) - 1)
            lines.append(self._format_ascii(child, '', child_prefix, is_last_child))

        return '\n'.join(lines)

    def _serialize_call_chain(self, node: CallChainNode) -> List[Dict]:
        """序列化调用链为 JSON 友好格式（保留树结构）"""
        result = {
            'layer': node.layer, 'class_name': node.class_name, 'method_name': node.method_name,
            'file_path': node.file_path, 'line_number': node.line_number, 'sql': node.sql,
            'annotation': node.annotation, 'is_entry': node.is_entry,
            'children': [self._serialize_call_chain(child) for child in node.children]
        }
        return [result]


def main():
    import sys
    if len(sys.argv) < 3:
        print("Usage: python analyze.py <api_path> <repo_key> [repo_url]")
        print("  repo_url is optional, will use repo_key or local repo instead")
        sys.exit(1)

    api_path = sys.argv[1]
    repo_key = sys.argv[2] if len(sys.argv) > 2 else None
    repo_url = sys.argv[3] if len(sys.argv) > 3 else None

    if repo_url:
        analyzer = JavaCallChainAnalyzer(repo_url=repo_url)
    elif repo_key:
        analyzer = JavaCallChainAnalyzer(repo_key=repo_key)
    else:
        print("Error: must provide repo_key or repo_url")
        sys.exit(1)

    result = analyzer.analyze(api_path)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

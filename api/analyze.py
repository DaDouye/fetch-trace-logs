#!/usr/bin/env python3
"""
Java 代码调用链静态分析器
用于分析 Spring Boot 项目中的接口调用链路
"""

import os
import re
import json
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path


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

    def __init__(self, repo_path: str = None, repo_key: str = None):
        if repo_key:
            from config_manager import get_git_repo_url
            repo_url = get_git_repo_url(repo_key)
            if not repo_url:
                raise ValueError(f"在配置中找不到键名为 '{repo_key}' 的Git仓库地址")
            repo_name = repo_url.split('/')[-1].replace('.git', '')
            self.repo_path = os.path.join('./repos', repo_name)
        elif repo_path:
            self.repo_path = repo_path
        else:
            raise ValueError("必须提供 repo_path 或 repo_key 参数")

        self.web_src_path = os.path.join(self.repo_path, 'web/src/main/java')
        self.config_path = os.path.join(self.repo_path, 'web/config')

        self._controller_cache: Dict[str, Tuple[str, str, int]] = {}
        self._service_impl_cache: Dict[str, str] = {}
        self._mapper_sql_cache: Dict[str, Dict[str, str]] = {}

    def analyze(self, api_path: str, trace_id: str = None, date: str = None, cookies: str = None) -> Dict[str, Any]:
        api_path = api_path.strip()
        if api_path.endswith('.json'):
            api_path = api_path[:-5]
        if api_path.endswith('/'):
            api_path = api_path[:-1]

        controller_info = self._find_controller_method(api_path)
        if not controller_info:
            return {'error': f'找不到 API: {api_path}', 'api_path': api_path}

        controller_class, controller_method, controller_file, controller_line = controller_info
        call_chain = self._build_call_chain(controller_class, controller_method, controller_file, controller_line)

        trace_data = None
        if trace_id:
            trace_data = self._fetch_trace_data(trace_id, date, cookies)

        ascii_graph = self._format_ascii(call_chain, api_path)

        result = {
            'api_path': api_path,
            'method': 'POST',
            'controller': controller_class,
            'controller_method': controller_method,
            'call_chain': self._serialize_call_chain(call_chain),
            'ascii_graph': ascii_graph
        }

        if trace_data:
            result['trace_data'] = trace_data

        return result

    def _find_controller_method(self, api_path: str) -> Optional[Tuple[str, str, str, int]]:
        search_path = api_path.strip('/')
        if search_path.endswith('.json'):
            search_path = search_path[:-5]

        if api_path in self._controller_cache:
            return self._controller_cache[api_path]

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

                class_match = re.search(r'public\s+class\s+(\w+)', content)
                if not class_match:
                    continue
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

                            result = (class_name, method_name, file_path, line_number)
                            self._controller_cache[api_path] = result
                            return result

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
        method_match = re.search(r'public\s+\w+(?:<[^>]+>)?\s+(\w+)\s*\(', snippet)
        return method_match.group(1) if method_match else "unknown"

    def _build_call_chain(self, class_name: str, method_name: str, file_path: str, line_number: int) -> CallChainNode:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

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

        with open(impl_path, 'r', encoding='utf-8', errors='ignore') as f:
            impl_content = f.read()

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
        with open(class_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

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
                # 追踪到其他 Service
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

        impl_dir = os.path.join(self.web_src_path, 'com/jiaxuan/supermario/service/impl')
        if os.path.exists(impl_dir):
            for root, dirs, files in os.walk(impl_dir):
                for file in files:
                    if file.lower() == impl_name.lower():
                        impl_path = os.path.join(root, file)
                        self._service_impl_cache[service_interface] = impl_path
                        return impl_path

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

    def _fetch_trace_data(self, trace_id: str, date: str, cookies: str = None) -> Optional[Dict]:
        """获取运行时 Trace 数据"""
        try:
            from scripts.fetch_trace_souche import TraceFetcher
            fetcher = TraceFetcher(cookies=cookies, verify_ssl=False)
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
        print("Usage: python analyze.py <api_path> <repo_key>")
        sys.exit(1)

    api_path = sys.argv[1]
    repo_key = sys.argv[2]

    analyzer = JavaCallChainAnalyzer(repo_key=repo_key)
    result = analyzer.analyze(api_path)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()



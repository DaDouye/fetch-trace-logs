#!/usr/bin/env python3
"""
字段级溯源分析器
从 JSON 响应字段路径反向追踪到数据库表字段和 SQL 语句
"""

import os
import re
from typing import Optional, List, Dict, Any, Tuple

from api.analyze import JavaCallChainAnalyzer


class FieldTracer:
    """字段级溯源分析器，组合 JavaCallChainAnalyzer 复用基础设施"""

    # 6 种赋值模式的正则
    SETTER_PATTERN = re.compile(r'(\w+)\.set(\w+)\s*\((.+?)\)\s*;', re.DOTALL)
    BUILDER_PATTERN = re.compile(r'\.(\w+)\s*\(([^)]*)\)', re.DOTALL)
    DIRECT_ASSIGN_PATTERN = re.compile(r'(\w+)\.(\w+)\s*=\s*([^;]+);')
    COPY_PROPERTIES_PATTERN = re.compile(
        r'BeanUtils\.copyProperties\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)',
        re.DOTALL
    )
    MAPSTRUCT_PATTERN = re.compile(
        r'(\w+)\.to(\w+)\s*\((\w+)\)',
        re.DOTALL
    )

    # JSON 注解
    JSON_PROPERTY_PATTERN = re.compile(r'@JsonProperty\s*\(\s*["\']([^"\']+)["\']')
    JSON_FIELD_PATTERN = re.compile(r'@JSONField\s*\(\s*name\s*=\s*["\']([^"\']+)["\']')

    def __init__(
        self,
        repo_key: str = None,
        repo_url: str = None,
        ref: str = "master"
    ):
        # 尝试多种方式初始化 analyzer：
        # 1. repo_key 在 config 中 → 正常初始化
        # 2. repo_key 不在 config 中 → 尝试作为本地路径 ./repos/<repo_key>
        try:
            self._analyzer = JavaCallChainAnalyzer(
                repo_key=repo_key,
                repo_url=repo_url,
                ref=ref
            )
        except ValueError:
            # config 中找不到，尝试直接作为本地仓库路径
            local_path = os.path.join('./repos', repo_key) if repo_key else None
            if local_path and os.path.isdir(local_path):
                self._analyzer = JavaCallChainAnalyzer(repo_path=local_path)
            else:
                raise ValueError(
                    f"在配置中找不到键名为 '{repo_key}' 的Git仓库地址，"
                    f"且本地路径 './repos/{repo_key}' 也不存在"
                )
        self._field_cache: Dict[str, Dict[str, Any]] = {}
        self._class_path_cache: Dict[str, str] = {}

    # ── public API ──────────────────────────────────────────────

    def trace(
        self,
        api_path: str = None,
        method_name: str = None,
        field_path: str = None
    ) -> Dict[str, Any]:
        """主入口：执行字段级溯源分析"""
        errors = []

        # 解析查询参数
        query_params = {}
        clean_api_path = api_path
        if api_path and '?' in api_path:
            clean_api_path, qs = api_path.split('?', 1)
            query_params = self._parse_query_params(qs)

        # Step 1: 定位入口方法
        entry = self._locate_entry(clean_api_path, method_name)
        if entry.get('error'):
            return entry

        controller_file = entry['file_path']
        controller_method = entry['method_name']
        controller_class = entry['class_name']

        # Step 2: 解析返回类型 → DTO
        return_type_info = self._parse_return_type(controller_file, controller_method)
        if return_type_info.get('error'):
            return return_type_info

        wrapper_class = return_type_info.get('wrapper_class')
        dto_class_name = return_type_info['dto_class_name']
        dto_file = return_type_info.get('dto_file')

        # Step 3: 解析 JSON 路径 → DTO 字段
        path_result = self._resolve_json_path(
            field_path, wrapper_class, dto_class_name, dto_file
        )
        if path_result.get('error'):
            path_result['_partial'] = True
            path_result['controller'] = {
                'class_name': controller_class,
                'method_name': controller_method,
                'file_path': controller_file,
                'line_number': entry.get('line_number', 0)
            }
            path_result['return_type_info'] = return_type_info
            return path_result

        target_field = path_result['target_field']
        path_segments = path_result['path_segments']

        # Step 4: 搜索赋值点（传入查询参数用于分支裁剪）
        assignments, search_debug = self._find_field_assignments(
            dto_class_name, target_field,
            controller_class, controller_method,
            query_params
        )

        # Step 5: 追踪数据来源
        trace_results = []
        for assign in (assignments or []):
            source = self._trace_to_source(assign)
            if source:
                trace_results.append(source)

        return {
            'field_path': field_path,
            'api_path': api_path,
            'query_params': query_params,
            'path_segments': path_segments,
            'wrapper_class': wrapper_class,
            'dto_class': dto_class_name,
            'dto_file': dto_file,
            'target_field': target_field,
            'target_field_line': path_result.get('target_field_line'),
            'target_field_type': path_result.get('target_field_type'),
            'target_field_annotations': path_result.get('target_field_annotations'),
            'controller': {
                'class_name': controller_class,
                'method_name': controller_method,
                'file_path': controller_file,
                'line_number': entry.get('line_number', 0)
            },
            'assignments': assignments or [],
            'trace_chain': trace_results,
            'search_debug': search_debug,
            'errors': errors
        }

    # ── Step 1: 定位入口方法 ────────────────────────────────────

    def _locate_entry(
        self, api_path: str = None, method_name: str = None
    ) -> Dict[str, Any]:
        """根据 api_path 或 method_name 定位 Controller 方法"""
        if api_path:
            # 剥离查询参数和 .json 后缀
            clean_path = api_path.split('?')[0].rstrip('/')
            controller_info = self._analyzer._find_controller_method(clean_path)
            if controller_info:
                class_name, method, file_path, line = controller_info
                return {
                    'class_name': class_name,
                    'method_name': method,
                    'file_path': file_path,
                    'line_number': line
                }
            return {'error': f'找不到 API: {api_path}'}

        if method_name:
            return self._find_method_in_controllers(method_name)

        return {'error': 'api_path 或 method_name 至少需要一个'}

    def _find_method_in_controllers(self, method_name: str) -> Dict[str, Any]:
        """按方法名在所有 Controller 类中搜索"""
        search_roots = []
        if not self._analyzer._use_remote and self._analyzer.repo_path:
            web_src = os.path.join(self._analyzer.repo_path, 'web/src/main/java')
            if os.path.exists(web_src):
                search_roots.append(web_src)
        else:
            search_roots.append('web/src/main/java')

        for search_root in search_roots:
            if self._analyzer._use_remote:
                all_files = self._analyzer._git_fetcher.list_files(search_root)
                for file_path in all_files:
                    if not file_path.endswith('.java'):
                        continue
                    content = self._read_file(file_path)
                    if not content:
                        continue
                    result = self._check_controller_method(content, file_path, method_name)
                    if result:
                        return result
            else:
                for root, dirs, files in os.walk(search_root):
                    for file in files:
                        if not file.endswith('.java'):
                            continue
                        file_path = os.path.join(root, file)
                        content = self._read_file(file_path)
                        if not content:
                            continue
                        result = self._check_controller_method(content, file_path, method_name)
                        if result:
                            return result

        return {'error': f'找不到方法: {method_name}'}

    def _check_controller_method(
        self, content: str, file_path: str, method_name: str
    ) -> Optional[Dict[str, Any]]:
        """检查文件是否是 Controller 并包含目标方法"""
        # 判断是否是 Controller (有 @Rest, @Controller, @RestController)
        if not re.search(r'@(?:Rest\b|RestControl|Control)', content):
            return None

        # 搜索目标方法
        pattern = re.compile(
            rf'public\s+(?:<[^>]+>\s*)?[\w<>\[\],\s.?]+\s+{re.escape(method_name)}\s*\(',
            re.DOTALL
        )
        match = pattern.search(content)
        if not match:
            return None

        class_match = re.search(r'public\s+class\s+(\w+)', content)
        if not class_match:
            return None

        return {
            'class_name': class_match.group(1),
            'method_name': method_name,
            'file_path': file_path,
            'line_number': content[:match.start()].count('\n') + 1
        }

    # ── Step 2: 解析返回类型 ────────────────────────────────────

    def _parse_return_type(
        self, file_path: str, method_name: str
    ) -> Dict[str, Any]:
        """解析 Controller 方法的返回类型，解开 Result<T> 包装"""
        content = self._read_file(file_path)
        if not content:
            return {'error': f'无法读取文件: {file_path}'}

        # 查找方法签名
        pattern = re.compile(
            rf'public\s+(?:<[^>]+>\s*)?([\w<>\[\],\s.?]+)\s+{re.escape(method_name)}\s*\(',
            re.DOTALL
        )
        match = pattern.search(content)
        if not match:
            return {'error': f'在 {file_path} 中找不到方法: {method_name}'}

        return_type = match.group(1).strip()

        # 检查是否是 Result<T> 包装类
        result_match = re.match(r'(?:List\s*<\s*)?Result\s*<\s*(\w+)\s*>\s*$', return_type)
        wrapper_class = None
        dto_class_name = None

        if result_match:
            wrapper_class = 'Result'
            dto_class_name = result_match.group(1)
        else:
            # 非 Result 包装，直接使用返回类型
            clean = return_type.replace('List<', '').replace('>', '').strip()
            dto_class_name = clean

        # 找到 DTO 文件
        dto_file = self._resolve_class_file(dto_class_name)

        return {
            'return_type': return_type,
            'wrapper_class': wrapper_class,
            'dto_class_name': dto_class_name,
            'dto_file': dto_file,
            'method_line': content[:match.start()].count('\n') + 1
        }

    # ── Step 3: JSON 路径 → DTO 字段 ────────────────────────────

    def _resolve_json_path(
        self,
        field_path: str,
        wrapper_class: str,
        dto_class_name: str,
        dto_file: str = None
    ) -> Dict[str, Any]:
        """解析 JSON 路径，映射到 DTO 的 Java 字段"""
        if not field_path:
            return {'error': 'field_path 不能为空'}

        segments = self._parse_path_segments(field_path)
        if not segments:
            return {'error': f'无法解析字段路径: {field_path}'}

        path_segments_detail = []

        # 如果第一个字段是 wrapper 的 JSON 字段名，跳过
        start_idx = 0
        if wrapper_class and segments:
            first_seg = segments[0]
            if isinstance(first_seg, tuple):
                seg_name = first_seg[0]
            else:
                seg_name = first_seg
            # data 是 Result 类的字段
            path_segments_detail.append({
                'segment': seg_name,
                'class': wrapper_class,
                'field': 'data' if seg_name == 'data' else seg_name,
                'role': 'wrapper',
                'note': f'{wrapper_class}.data 包装类字段，跳过'
            })
            start_idx = 1

        # 从 DTO 类开始逐段解析
        current_class = dto_class_name
        current_file = dto_file or self._resolve_class_file(current_class)

        for i in range(start_idx, len(segments)):
            seg = segments[i]
            if isinstance(seg, tuple):
                seg_name, array_idx = seg
            else:
                seg_name = seg
                array_idx = None

            if not current_file:
                path_segments_detail.append({
                    'segment': seg_name,
                    'class': current_class,
                    'error': f'找不到类文件: {current_class}'
                })
                continue

            # 在 current_class 中查找该字段
            field_info = self._find_field_in_class(current_class, current_file, seg_name)
            if not field_info:
                path_segments_detail.append({
                    'segment': seg_name,
                    'class': current_class,
                    'error': f'在 {current_class} 中找不到字段映射: {seg_name}'
                })
                continue

            field_info['class'] = current_class
            field_info['segment'] = seg_name
            if array_idx is not None:
                field_info['array_index'] = array_idx

            path_segments_detail.append(field_info)

            # 如果该字段是 List 或引用类型，继续解析下一层
            field_type = field_info.get('field_type', '')
            list_match = re.match(r'List\s*<\s*(\w+)\s*>', field_type)
            if list_match:
                current_class = list_match.group(1)
                current_file = self._resolve_class_file(current_class)
            elif field_type and field_type[0].isupper():
                # 自定义类型引用
                current_class = field_type
                current_file = self._resolve_class_file(current_class)
            else:
                # 基本类型，这是最终的目标字段
                break

        # 最后一段是目标字段
        last_detail = path_segments_detail[-1] if path_segments_detail else None
        target_field = last_detail.get('field', '') if last_detail else ''

        return {
            'path_segments': path_segments_detail,
            'target_field': target_field,
            'target_field_line': last_detail.get('line_number') if last_detail else None,
            'target_field_type': last_detail.get('field_type') if last_detail else None,
            'target_field_annotations': last_detail.get('annotations') if last_detail else None
        }

    def _parse_path_segments(self, field_path: str) -> List:
        """解析 'data.list[0].name' → ['data', ('list', 0), 'name']"""
        parts = field_path.split('.')
        segments = []
        for part in parts:
            array_match = re.match(r'(\w+)\[(\d+)\]', part)
            if array_match:
                segments.append((array_match.group(1), int(array_match.group(2))))
            else:
                segments.append(part)
        return segments

    def _find_field_in_class(
        self, class_name: str, file_path: str, json_field_name: str
    ) -> Optional[Dict[str, Any]]:
        """在 Java 类中根据 JSON 字段名找到对应的 Java 字段"""
        content = self._read_file(file_path)
        if not content:
            return None

        # 搜索所有字段定义
        field_pattern = re.compile(
            r'(@\w+(?:\([^)]*\))?\s*)*'           # 注解
            r'private\s+([\w<>,\s]+?)\s+(\w+)\s*;'  # 类型 + 字段名
        )

        for match in field_pattern.finditer(content):
            annotations_block = match.group(1) or ''
            field_type = match.group(2).strip()
            field_name = match.group(3)

            # 检查 @JsonProperty
            json_prop = re.search(r'@JsonProperty\s*\(\s*["\']([^"\']+)["\']', annotations_block)
            if json_prop and json_prop.group(1) == json_field_name:
                return {
                    'field': field_name,
                    'field_type': field_type,
                    'json_name': json_prop.group(1),
                    'line_number': content[:match.start()].count('\n') + 1,
                    'annotations': annotations_block.strip() if annotations_block.strip() else None
                }

            # 检查 @JSONField
            json_field = re.search(r'@JSONField\s*\(\s*name\s*=\s*["\']([^"\']+)["\']', annotations_block)
            if json_field and json_field.group(1) == json_field_name:
                return {
                    'field': field_name,
                    'field_type': field_type,
                    'json_name': json_field.group(1),
                    'line_number': content[:match.start()].count('\n') + 1,
                    'annotations': annotations_block.strip() if annotations_block.strip() else None
                }

            # 驼峰转下划线匹配 (userId ↔ user_id)
            if json_field_name and field_name and json_field_name.lower() == field_name.lower():
                return {
                    'field': field_name,
                    'field_type': field_type,
                    'json_name': json_field_name,
                    'line_number': content[:match.start()].count('\n') + 1,
                    'annotations': annotations_block.strip() if annotations_block.strip() else None,
                    'match_type': 'case_insensitive'
                }

            # 下划线 ↔ 驼峰 转换匹配
            snake_name = self._camel_to_snake(field_name)
            if snake_name == json_field_name:
                return {
                    'field': field_name,
                    'field_type': field_type,
                    'json_name': json_field_name,
                    'line_number': content[:match.start()].count('\n') + 1,
                    'annotations': annotations_block.strip() if annotations_block.strip() else None,
                    'match_type': 'snake_case'
                }

        return None

    @staticmethod
    def _camel_to_snake(name: str) -> str:
        """驼峰转下划线 userId → user_id"""
        result = []
        for i, ch in enumerate(name):
            if ch.isupper():
                if i > 0:
                    result.append('_')
                result.append(ch.lower())
            else:
                result.append(ch)
        return ''.join(result)

    # ── Step 4: 搜索字段赋值 ───────────────────────────────────

    @staticmethod
    def _parse_query_params(query_string: str) -> Dict[str, str]:
        """解析 URL 查询参数 typeCode=4&tagType=follow → {'typeCode': '4', 'tagType': 'follow'}"""
        params = {}
        for pair in query_string.split('&'):
            if '=' in pair:
                k, v = pair.split('=', 1)
                params[k.strip()] = v.strip()
            else:
                params[pair.strip()] = ''
        return params

    def _filter_body_by_params(
        self, body: str, params: Dict[str, str]
    ) -> str:
        """根据查询参数值裁剪方法体，只保留匹配的条件分支内的代码

        处理逻辑:
        - if (cond) { ... } → 匹配则保留，不匹配则丢弃
        - else if (cond) { ... } → 同上
        - else { ... } → 只有前面所有 if/else-if 都不匹配时才保留（兜底分支）
        - 分支外的代码始终保留
        """
        if not params or not body:
            return body

        # 同时匹配 if/else-if 和 plain else
        conditional_pattern = re.compile(
            r'\b(if|else\s+if)\s*\(([^)]*)\)\s*(\{)'
            r'|\b(else)\s*(\{)',
            re.DOTALL
        )

        filtered_parts = []
        last_end = 0
        chain_matched = False  # 当前 if/else-if/else 链中是否有匹配

        for m in conditional_pattern.finditer(body):
            if m.group(1):  # if (...) or else if (...)
                keyword = m.group(1)
                condition = m.group(2)
                brace_pos = m.start(3)

                # 收集之前的代码
                if last_end < m.start():
                    filtered_parts.append(body[last_end:m.start()])

                block_end = self._find_matching_brace(body, brace_pos)
                block_content = body[brace_pos + 1:block_end]

                if self._condition_matches_params(condition, params):
                    filtered_parts.append(block_content)
                    chain_matched = True

                last_end = block_end + 1

            elif m.group(4):  # else { ... }
                brace_pos = m.start(5)

                if last_end < m.start():
                    filtered_parts.append(body[last_end:m.start()])

                block_end = self._find_matching_brace(body, brace_pos)
                block_content = body[brace_pos + 1:block_end]

                if not chain_matched:
                    # 前面都没匹配，保留 else 兜底分支
                    filtered_parts.append(block_content)

                last_end = block_end + 1
                chain_matched = False  # 链路结束，重置

        # 追加剩余代码
        if last_end < len(body):
            filtered_parts.append(body[last_end:])

        return '\n'.join(filtered_parts)

    @staticmethod
    def _condition_matches_params(condition: str, params: Dict[str, str]) -> bool:
        """判断条件表达式是否匹配查询参数值

        支持模式:
        - "4".equals(typeCode)  → typeCode == "4"
        - typeCode.equals("4")  → typeCode == "4"
        - typeCode == 4         → typeCode == "4"
        - "follow".equals(tagType) → tagType == "follow"
        """
        # "4".equals(typeCode) or typeCode.equals("4")
        equals_match = re.search(
            r'["\']([^"\']+)["\']\s*\.equals\s*\(\s*(\w+)\s*\)'
            r'|(\w+)\s*\.equals\s*\(\s*["\']([^"\']+)["\']\s*\)',
            condition
        )
        if equals_match:
            str_val = equals_match.group(1) or equals_match.group(4)
            var_name = equals_match.group(2) or equals_match.group(3)
            if var_name in params:
                return params[var_name] == str_val

        # StringUtils.equals("4", typeCode) or similar
        utils_match = re.search(
            r'\w+\.equals\s*\(\s*["\']([^"\']+)["\']\s*,\s*(\w+)\s*\)',
            condition
        )
        if utils_match:
            if utils_match.group(2) in params:
                return params[utils_match.group(2)] == utils_match.group(1)

        # typeCode == 4  or  typeCode == "4"
        compare_match = re.search(
            r'(\w+)\s*==\s*["\']?(\w+)["\']?',
            condition
        )
        if compare_match:
            var_name = compare_match.group(1)
            val = compare_match.group(2)
            if var_name in params:
                return params[var_name] == val

        # typeCode != 4 → 反向匹配，默认当作不匹配
        not_match = re.search(r'(\w+)\s*!=\s*["\']?(\w+)["\']?', condition)
        if not_match:
            var_name = not_match.group(1)
            val = not_match.group(2)
            if var_name in params:
                return params[var_name] != val

        # 无法判断的条件，保守保留
        return True

    @staticmethod
    def _find_matching_brace(text: str, start: int) -> int:
        """从 start 位置的 { 开始，找到匹配的 }"""
        count = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                count += 1
            elif text[i] == '}':
                count -= 1
                if count == 0:
                    return i
        return len(text) - 1

    def _extract_service_calls_from_body(self, body: str) -> List[Dict]:
        """从方法体文本中提取所有 Service/Mapper 调用（纯正则，不依赖大括号计数）

        因为 body 已经是剥离了外层大括号的方法体，不能使用分析器原有的
        大括号计数逻辑（会在第一个嵌套块闭合后提前终止）。
        """
        results = []
        seen = set()

        for m in re.finditer(r'\b(\w+)\.(\w+)\s*\(', body):
            field = m.group(1)
            method = m.group(2)

            # 排除非业务调用
            if field in ('this', 'super', 'log', 'JSON', 'JSONObject', 'Objects',
                         'StringUtils', 'CollectionUtils', 'Collections', 'Lists',
                         'Maps', 'Result', 'String', 'Integer', 'Long', 'List',
                         'Map', 'Set', 'Optional', 'Stream', 'Arrays', 'Math'):
                continue
            if method in ('toString', 'hashCode', 'equals', 'getClass', 'get',
                          'set', 'put', 'add', 'remove', 'size', 'isEmpty',
                          'contains', 'of', 'valueOf', 'parseInt', 'parseLong',
                          'info', 'warn', 'error', 'debug', 'isDebugEnabled',
                          'isInfoEnabled', 'isWarnEnabled'):
                continue

            key = f"{field}.{method}"
            if key in seen:
                continue
            seen.add(key)
            results.append({'class': field, 'method': method, 'line': 0})

        return results

    def _find_field_assignments(
        self,
        dto_class_name: str,
        field_name: str,
        controller_class: str,
        controller_method: str,
        query_params: Dict[str, str] = None
    ) -> tuple:
        """在 Service 层搜索对 DTO 目标字段的赋值，返回 (results, debug_info)"""
        results = []
        query_params = query_params or {}
        debug = {
            'controller_file': None,
            'method_body_extracted': False,
            'query_params_applied': False,
            'service_calls_found': [],
            'searched_files': [],
            'used_fallback': False
        }

        # 从 Controller 方法中找到调用的 Service
        controller_file = self._resolve_class_file(controller_class)
        debug['controller_file'] = controller_file
        if not controller_file:
            return results, debug
        controller_content = self._read_file(controller_file)
        if not controller_content:
            return results, debug

        # 提取 Controller 方法体
        method_body = self._extract_method_body(controller_content, controller_method)
        debug['method_body_extracted'] = bool(method_body)
        if not method_body:
            method_body = controller_content

        # 如果有查询参数，裁剪方法体到匹配的条件分支
        if query_params:
            method_body = self._filter_body_by_params(method_body, query_params)
            debug['query_params_applied'] = True
            debug['query_params'] = query_params

        service_calls = self._extract_service_calls_from_body(method_body)
        debug['service_calls_found'] = [
            f"{c.get('class', '?')}.{c.get('method', '?')}()" for c in service_calls
        ]

        searched = set()
        for call in service_calls:
            impl_path = self._analyzer._find_service_impl(call['class'])
            debug['searched_files'].append({
                'call': f"{call.get('class', '?')}.{call.get('method', '?')}()",
                'impl_path': impl_path
            })
            if not impl_path or impl_path in searched:
                continue
            searched.add(impl_path)
            assignments = self._search_assignments_in_file(
                impl_path, call['method'], dto_class_name, field_name
            )
            results.extend(assignments)

            # 递归搜索调用的子 Service
            self._search_assignments_recursive(
                impl_path, call['method'], dto_class_name, field_name,
                results, searched
            )

        # 回退：如果直接追踪没找到，在整个 ServiceImpl 文件中全局搜索
        if not results and searched:
            debug['used_fallback'] = True
            for impl_path in list(searched):
                broad = self._search_assignments_broad(
                    impl_path, dto_class_name, field_name
                )
                results.extend(broad)

        # 标记推测项
        for r in results:
            if r.get('speculative'):
                r['note'] = '[推测] 基于同名字段匹配，可能与实际来源有差异'

        return results, debug

    def _search_assignments_broad(
        self, file_path: str, dto_class_name: str, field_name: str
    ) -> List[Dict[str, Any]]:
        """全局搜索：在整个文件内容中搜索字段赋值，不限定具体方法"""
        results = []
        content = self._read_file(file_path)
        if not content:
            return results

        class_name = os.path.basename(file_path).replace('.java', '')

        # Setter: anyVar.setXxx(...)
        setter_re = re.compile(
            r'(\w+)\.set(' + re.escape(field_name[0].upper() + field_name[1:]) +
            r')\s*\((.+?)\)\s*;',
            re.DOTALL
        )
        for m in setter_re.finditer(content):
            param = self._clean_param(m.group(3))
            results.append({
                'pattern': 'setter',
                'code': m.group(0).strip(),
                'var_name': m.group(1),
                'param': param,
                'param_source': self._resolve_param_source(param, content),
                'file_path': file_path,
                'class_name': class_name,
                'method_name': '(broad search)',
                'speculative': False,
                'note': '全局搜索匹配（非精确方法体追踪）'
            })

        # Builder: .fieldName(...)
        builder_re = re.compile(
            r'\.' + re.escape(field_name) + r'\s*\(([^)]*)\)',
            re.DOTALL
        )
        builder_ctx = re.compile(
            r'(\w+)\.builder\(\)[\s\S]*?\.build\(\)',
            re.DOTALL
        )
        for ctx_match in builder_ctx.finditer(content):
            ctx = ctx_match.group(0)
            for bm in builder_re.finditer(ctx):
                param = self._clean_param(bm.group(1))
                if 'build' in param:
                    continue
                results.append({
                    'pattern': 'builder',
                    'code': bm.group(0).strip(),
                    'var_name': ctx_match.group(1),
                    'param': param,
                    'param_source': self._resolve_param_source(param, content),
                    'file_path': file_path,
                    'class_name': class_name,
                    'method_name': '(broad search)',
                    'speculative': False,
                    'note': '全局搜索匹配（非精确方法体追踪）'
                })

        # Direct assignment: var.field = ...
        direct_re = re.compile(
            r'(\w+)\.' + re.escape(field_name) + r'\s*=\s*([^;]+);'
        )
        for m in direct_re.finditer(content):
            results.append({
                'pattern': 'direct',
                'code': m.group(0).strip(),
                'var_name': m.group(1),
                'param': self._clean_param(m.group(2)),
                'param_source': self._resolve_param_source(m.group(2).strip(), content),
                'file_path': file_path,
                'class_name': class_name,
                'method_name': '(broad search)',
                'speculative': False,
                'note': '全局搜索匹配（非精确方法体追踪）'
            })

        # BeanUtils.copyProperties
        cp_re = re.compile(
            r'BeanUtils\.copyProperties\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)',
            re.DOTALL
        )
        for m in cp_re.finditer(content):
            src_var = m.group(1)
            tgt_var = m.group(2)
            results.append({
                'pattern': 'copyProperties',
                'code': m.group(0).strip(),
                'source_var': src_var,
                'target_var': tgt_var,
                'file_path': file_path,
                'class_name': class_name,
                'method_name': '(broad search)',
                'speculative': True,
                'speculative_match': self._speculative_match(
                    content, src_var, field_name, dto_class_name
                ),
                'note': '全局搜索匹配（非精确方法体追踪）'
            })

        return results

    def _search_assignments_recursive(
        self, file_path: str, method_name: str,
        dto_class_name: str, field_name: str,
        results: List[Dict], searched: set
    ):
        """递归搜索子 Service 中的赋值"""
        content = self._read_file(file_path)
        if not content:
            return

        # 找到 method 内的子调用
        method_info = self._analyzer._find_method_in_content(content, method_name)
        if not method_info:
            return

        sub_calls = list(
            self._analyzer._extract_method_calls(
                content, method_info['name'], method_info['line']
            )
        )

        for sub_call in sub_calls:
            sub_impl = self._analyzer._find_service_impl(sub_call['class'])
            if not sub_impl or sub_impl in searched:
                continue
            searched.add(sub_impl)
            assigns = self._search_assignments_in_file(
                sub_impl, sub_call['method'], dto_class_name, field_name
            )
            results.extend(assigns)
            self._search_assignments_recursive(
                sub_impl, sub_call['method'], dto_class_name, field_name,
                results, searched
            )

    def _search_assignments_in_file(
        self, file_path: str, method_name: str,
        dto_class_name: str, field_name: str,
        visited_internal: set = None
    ) -> List[Dict[str, Any]]:
        """在指定文件的方法中搜索对 DTO.field 的赋值，并递归追踪 this. 内部方法调用"""
        if visited_internal is None:
            visited_internal = set()

        # 防止循环
        method_key = f"{file_path}::{method_name}"
        if method_key in visited_internal:
            return []
        visited_internal.add(method_key)

        results = []
        content = self._read_file(file_path)
        if not content:
            return results

        # 提取方法体
        method_body = self._extract_method_body(content, method_name)
        if not method_body:
            return results

        class_name = os.path.basename(file_path).replace('.java', '')

        # 1. Setter 模式: dtoVar.setXxx(...)
        setter_re = re.compile(
            r'(\w+)\.set(' + re.escape(field_name[0].upper() + field_name[1:]) +
            r')\s*\((.+?)\)\s*;',
            re.DOTALL
        )
        for m in setter_re.finditer(method_body):
            var_name = m.group(1)
            param = self._clean_param(m.group(3))
            results.append({
                'pattern': 'setter',
                'code': m.group(0).strip(),
                'var_name': var_name,
                'param': param,
                'param_source': self._resolve_param_source(param, content),
                'file_path': file_path,
                'class_name': class_name,
                'method_name': method_name,
                'speculative': False
            })

        # 2. Builder 模式: .fieldName(...)
        builder_re = re.compile(
            r'\.' + re.escape(field_name) + r'\s*\(([^)]*)\)',
            re.DOTALL
        )
        builder_context = re.compile(
            r'(\w+)\.builder\(\)[\s\S]*?\.build\(\)',
            re.DOTALL
        )
        for ctx_match in builder_context.finditer(method_body):
            ctx = ctx_match.group(0)
            var_name = ctx_match.group(1)
            for bm in builder_re.finditer(ctx):
                param = self._clean_param(bm.group(1))
                if 'build' in param:
                    continue
                results.append({
                    'pattern': 'builder',
                    'code': bm.group(0).strip(),
                    'var_name': var_name,
                    'param': param,
                    'param_source': self._resolve_param_source(param, content),
                    'file_path': file_path,
                    'class_name': class_name,
                    'method_name': method_name,
                    'speculative': False
                })

        # 3. 直接赋值: dto.fieldName = ...
        direct_re = re.compile(
            r'(\w+)\.' + re.escape(field_name) + r'\s*=\s*([^;]+);'
        )
        for m in direct_re.finditer(method_body):
            results.append({
                'pattern': 'direct',
                'code': m.group(0).strip(),
                'var_name': m.group(1),
                'param': self._clean_param(m.group(2)),
                'param_source': self._resolve_param_source(m.group(2).strip(), content),
                'file_path': file_path,
                'class_name': class_name,
                'method_name': method_name,
                'speculative': False
            })

        # 4. 构造函数模式: new XxxVO(...)
        constructor_re = re.compile(
            r'new\s+' + re.escape(dto_class_name) + r'\s*\(([^)]*)\)',
            re.DOTALL
        )
        for m in constructor_re.finditer(method_body):
            args = m.group(1)
            # 解析构造参数位置 → 需要和 DTO 字段顺序匹配
            results.append({
                'pattern': 'constructor',
                'code': m.group(0).strip(),
                'args': args,
                'file_path': file_path,
                'class_name': class_name,
                'method_name': method_name,
                'speculative': True,
                'note': '构造函数参数需手动确认位置对应关系'
            })

        # 5. BeanUtils.copyProperties
        cp_re = re.compile(
            r'BeanUtils\.copyProperties\s*\(\s*(\w+)\s*,\s*(\w+)\s*\)',
            re.DOTALL
        )
        for m in cp_re.finditer(method_body):
            src_var = m.group(1)
            tgt_var = m.group(2)
            results.append({
                'pattern': 'copyProperties',
                'code': m.group(0).strip(),
                'source_var': src_var,
                'target_var': tgt_var,
                'file_path': file_path,
                'class_name': class_name,
                'method_name': method_name,
                'speculative': True,
                'speculative_match': self._speculative_match(
                    content, src_var, field_name, dto_class_name
                )
            })

        # 6. MapStruct: mapper.toXxxVO(source)
        ms_re = re.compile(
            r'(\w+)\.to(\w+)\s*\((\w+)\)',
            re.DOTALL
        )
        for m in ms_re.finditer(method_body):
            mapper_name = m.group(1)
            to_method = m.group(2)
            src_var = m.group(3)
            if dto_class_name.lower() in to_method.lower():
                results.append({
                    'pattern': 'mapstruct',
                    'code': m.group(0).strip(),
                    'mapper': mapper_name,
                    'source_var': src_var,
                    'file_path': file_path,
                    'class_name': class_name,
                    'method_name': method_name,
                    'speculative': True,
                    'speculative_match': self._speculative_match(
                        content, src_var, field_name, dto_class_name
                    )
                })

        # 7. 追踪 this. 内部方法调用（含带 this. 前缀和不带前缀的）
        #    例如 getDashboard() 中调用了 this.buildDashboardFromStatData()
        #    或直接调用 buildDashboardFromStatData()，都需递归进入搜索
        all_methods_in_file = self._list_methods_in_file(content)
        # 收集方法体中所有的裸方法调用
        bare_call_re = re.compile(r'(?:this\.)?(\w+)\s*\(')
        traced = set()
        for bm in bare_call_re.finditer(method_body):
            internal_method = bm.group(1)
            if internal_method == method_name:
                continue
            if internal_method not in all_methods_in_file:
                continue
            if internal_method in traced:
                continue
            traced.add(internal_method)
            inner_results = self._search_assignments_in_file(
                file_path, internal_method, dto_class_name, field_name,
                visited_internal
            )
            results.extend(inner_results)

        return results

    @staticmethod
    def _list_methods_in_file(content: str) -> set:
        """列出文件中所有方法名"""
        methods = set()
        for m in re.finditer(
            r'(?:public|private|protected)\s+(?:static\s+)?(?:<[^>]+>\s*)?[\w<>\[\],\s.]+?\s+(\w+)\s*\(',
            content
        ):
            methods.add(m.group(1))
        return methods

    def _speculative_match(
        self, content: str, src_var: str,
        field_name: str, dto_class_name: str
    ) -> Optional[Dict[str, Any]]:
        """对 BeanUtils/MapStruct 场景做同名推测匹配"""
        # 尝试找到 src_var 的类型
        type_pattern = re.compile(
            r'(\w+(?:VO|Entity|DTO|Bo|BO|Do|DO|Model))\s+' + re.escape(src_var) + r'\b'
        )
        type_match = type_pattern.search(content)

        # 也搜索方法参数
        if not type_match:
            param_pattern = re.compile(
                r'(\w+(?:VO|Entity|DTO|Bo|BO|Do|DO|Model))\s+' + re.escape(src_var) + r'\s*[,)]'
            )
            type_match = param_pattern.search(content)

        src_type = type_match.group(1) if type_match else None
        if not src_type:
            return None

        # 找到 src class 的字段
        src_file = self._resolve_class_file(src_type)
        if not src_file:
            return {'source_type': src_type, 'matched_fields': [], 'note': f'找不到源类 {src_type} 的定义'}

        src_content = self._read_file(src_file)
        if not src_content:
            return {'source_type': src_type, 'matched_fields': []}

        # 找同名字段
        field_def = re.compile(
            r'private\s+([\w<>,\s]+?)\s+(\w+)\s*;'
        )
        matched = []
        for m in field_def.finditer(src_content):
            sf_type = m.group(1).strip()
            sf_name = m.group(2)
            if sf_name.lower() == field_name.lower():
                # 也尝试找该字段在 Mapper 中的 SQL
                sql_info = self._find_sql_for_entity_field(src_type, sf_name)
                matched.append({
                    'source_field': sf_name,
                    'source_type': sf_type,
                    'sql_info': sql_info
                })

        return {
            'source_type': src_type,
            'source_file': src_file,
            'matched_fields': matched,
            'note': '推测：源类型和 DTO 中有同名字段，展示匹配结果'
        }

    # ── Step 5: 追踪到数据库 ────────────────────────────────────

    def _trace_to_source(self, assignment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """从赋值点追踪数据来源到 Entity/DB 字段/SQL"""
        if assignment.get('speculative') and assignment.get('speculative_match'):
            return assignment['speculative_match']

        param_source = assignment.get('param_source', {})
        if not param_source:
            return None

        source_class = param_source.get('source_class')
        source_field = param_source.get('source_field')

        if not source_class or not source_field:
            return param_source

        # 找 source 类的文件
        source_file = self._resolve_class_file(source_class)
        if not source_file:
            return {'source_class': source_class, 'source_field': source_field, 'note': '找不到类文件'}

        # 找 DB 映射
        db_info = self._find_db_mapping(source_file, source_field)
        sql_info = self._find_sql_for_entity_field(source_class, source_field)

        return {
            'source_class': source_class,
            'source_file': source_file,
            'source_field': source_field,
            'db_mapping': db_info,
            'sql_info': sql_info
        }

    def _resolve_param_source(
        self, param: str, content: str
    ) -> Dict[str, Any]:
        """解析赋值参数的来源"""
        # entity.getXxx() → Entity 字段
        getter_match = re.match(r'(\w+)\.get(\w+)\(\)', param)
        if getter_match:
            var_name = getter_match.group(1)
            getter_field = self._uncapitalize(getter_match.group(2))
            # 查找 var_name 的类型
            type_match = re.search(
                r'(\w+(?:Entity|DTO|VO|Bo|BO|Do|DO|Model|Info))\s+' +
                re.escape(var_name) + r'\b',
                content
            )
            return {
                'source_class': type_match.group(1) if type_match else None,
                'source_field': getter_field,
                'source_var': var_name,
                'expression': param
            }

        # 方法调用链 entity.getA().getB()
        chained = re.match(r'(\w+)\.(\w+)\(\)(.+)', param)
        if chained:
            return {
                'expression': param,
                'root_var': chained.group(1),
                'note': '链式调用，需手动追踪'
            }

        # 变量
        if re.match(r'^[a-z]\w*$', param):
            # 在 content 中搜索该变量的定义
            var_def = re.search(
                r'(\w+(?:Entity|DTO|VO|Bo|BO|Do|DO|Model|Info|String|Integer|Long|int|long))\s+' +
                re.escape(param) + r'\s*=', content
            )
            if var_def:
                return {
                    'source_class': var_def.group(1),
                    'source_var': param,
                    'expression': param,
                    'note': '局部变量'
                }
            return {'expression': param, 'note': '无法追踪的变量'}

        # 计算表达式
        return {
            'expression': param,
            'note': '计算表达式/字面量'
        }

    def _find_db_mapping(
        self, entity_file: str, field_name: str
    ) -> Optional[Dict[str, Any]]:
        """找到 Entity 字段对应的 DB 表字段"""
        content = self._read_file(entity_file)
        if not content:
            return None

        # @TableName
        table_match = re.search(r'@TableName\s*\(\s*["\']([^"\']+)["\']', content)
        table_name = table_match.group(1) if table_match else None

        # @TableField
        field_pattern = re.compile(
            r'(@\w+(?:\([^)]*\))?\s*)*\s*private\s+([\w<>,\s]+?)\s+' +
            re.escape(field_name) + r'\s*;'
        )
        m = field_pattern.search(content)
        if not m:
            return {'table': table_name, 'column': field_name, 'note': f'未找到字段 {field_name} 的注解'}

        annotations_block = m.group(1) or ''

        # @TableField("column_name")
        tf_match = re.search(r'@TableField\s*\(\s*["\']([^"\']+)["\']', annotations_block)
        column = tf_match.group(1) if tf_match else field_name

        # 下划线转换
        if column == field_name and not tf_match:
            column = self._camel_to_snake(field_name)

        # @TableId
        is_pk = '@TableId' in annotations_block

        return {
            'table': table_name,
            'column': column,
            'field': field_name,
            'is_primary_key': is_pk
        }

    def _find_sql_for_entity_field(
        self, entity_class: str, field_name: str
    ) -> Optional[Dict[str, Any]]:
        """找到涉及 Entity 字段的 Mapper SQL"""
        # 找对应的 Mapper
        mapper_name = entity_class
        for suffix in ['Entity', 'DO', 'Model', 'PO']:
            if mapper_name.endswith(suffix):
                mapper_name = mapper_name[:-len(suffix)]
                break
        mapper_name += 'Mapper'

        mapper_path = self._analyzer._find_mapper_file(mapper_name)
        if not mapper_path:
            return None

        # 获取所有 SQL
        sql_cache_key = mapper_name
        mapper_content = self._read_file(mapper_path)
        if not mapper_content:
            return None

        # 从 MyBatis XML 获取所有 SQL
        mapper_xml_sqls = self._get_all_sql_from_xml(mapper_name)
        # 从注解获取 SQL
        annotation_sqls = self._get_sql_from_annotations(mapper_content)

        all_sqls = {**mapper_xml_sqls, **annotation_sqls}

        # 筛选包含目标字段的 SQL
        result = {}
        for method, sql in all_sqls.items():
            if field_name in sql or self._camel_to_snake(field_name) in sql:
                result[method] = sql

        return {
            'mapper': mapper_name,
            'mapper_path': mapper_path,
            'related_sqls': result if result else all_sqls
        }

    def _get_all_sql_from_xml(self, mapper_name: str) -> Dict[str, str]:
        """从 MyBatis XML 获取所有 SQL"""
        if not self._analyzer._use_remote:
            return {}

        sql_map = {}
        config_dir = 'web/config'
        xml_files = self._analyzer._git_fetcher.list_files(config_dir)

        class_name = mapper_name
        for suffix in ['Mapper', 'DAO', 'Manager']:
            if class_name.endswith(suffix):
                class_name = class_name[:-len(suffix)]
                break
        class_name += 'Mapper'

        for xml_path in xml_files:
            if not xml_path.endswith('.xml'):
                continue
            xml_content = self._read_file(xml_path)
            if not xml_content:
                continue

            ns_match = re.search(r'namespace\s*=\s*["\']([^"\']+)["\']', xml_content)
            if not ns_match:
                continue

            full_ns = ns_match.group(1)
            mn_lower = mapper_name.lower()
            cn_lower = class_name.lower()
            fn_lower = full_ns.lower()

            if not (fn_lower.endswith('.' + mn_lower) or fn_lower.endswith('.' + cn_lower)):
                continue

            for sql_match in re.finditer(
                r'<(?:select|insert|update|delete)\s+id\s*=\s*["\'](\w+)["\']\s*[^>]*>\s*(.*?)\s*</(?:select|insert|update|delete)>',
                xml_content, re.DOTALL | re.IGNORECASE
            ):
                sql_map[sql_match.group(1)] = self._clean_sql(sql_match.group(2))

        return sql_map

    def _get_sql_from_annotations(self, mapper_content: str) -> Dict[str, str]:
        """从 Mapper 注解提取 SQL"""
        sqls = {}

        # @Select("SQL")
        for m in re.finditer(
            r'@(?:Select|Insert|Update|Delete)\s*\(\s*["\']([^"\']+)["\']',
            mapper_content
        ):
            sql = m.group(1)
            # 找到对应的方法名
            before = mapper_content[:m.start()]
            method_match = re.search(
                r'(?:public\s+)?[\w<>\[\],\s]+\s+(\w+)\s*\([^)]*\)\s*$',
                before.split('{')[-1] if '{' in before else before
            )
            method = method_match.group(1) if method_match else 'unknown'
            sqls[method] = self._clean_sql(sql)

        return sqls

    @staticmethod
    def _clean_sql(sql: str) -> str:
        """清理 SQL 文本"""
        sql = re.sub(r'<[^>]+>', '', sql)
        sql = re.sub(r'\s+', ' ', sql).strip()
        return sql

    # ── 工具方法 ────────────────────────────────────────────────

    def _read_file(self, file_path: str) -> Optional[str]:
        """读取文件（委托给 analyzer）"""
        return self._analyzer._read_file(file_path)

    def _resolve_class_file(self, class_name: str) -> Optional[str]:
        """根据类名找到文件路径"""
        if class_name in self._class_path_cache:
            return self._class_path_cache[class_name]

        filename = class_name + '.java'

        if self._analyzer._use_remote:
            java_dir = 'web/src/main/java'
            result = self._analyzer._search_remote_file(java_dir, filename)
        else:
            if self._analyzer.repo_path:
                web_src = os.path.join(self._analyzer.repo_path, 'web/src/main/java')
                if os.path.exists(web_src):
                    result = self._analyzer._search_local_file(web_src, filename)
                else:
                    result = None
            else:
                result = None

        if result:
            self._class_path_cache[class_name] = result
        return result

    def _extract_method_body(self, content: str, method_name: str) -> Optional[str]:
        """提取方法体，支持 public/private/protected 方法"""
        # 先找方法签名（支持注解、泛型、多种返回类型和修饰符）
        pattern = re.compile(
            rf'(?:public|private|protected)\s+'
            rf'(?:static\s+)?'
            rf'(?:<[^>]+>\s*)?'
            rf'[\w<>\[\],\s.?]+?\s+'
            rf'{re.escape(method_name)}\s*\(',
            re.DOTALL
        )
        match = pattern.search(content)
        if not match:
            return None

        # 从方法签名后找第一个 {
        pos = match.end()
        # 跳过参数列表，找到 )
        paren_count = 1
        for i in range(pos, min(pos + 2000, len(content))):
            if content[i] == '(':
                paren_count += 1
            elif content[i] == ')':
                paren_count -= 1
                if paren_count == 0:
                    pos = i + 1
                    break

        # 跳过 throws 子句和空格，找到 {
        for i in range(pos, min(pos + 500, len(content))):
            if content[i] == '{':
                brace_start = i
                break
        else:
            return None

        brace_count = 0
        for i in range(brace_start, len(content)):
            if content[i] == '{':
                brace_count += 1
            elif content[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    return content[brace_start + 1:i]

        return None

    @staticmethod
    def _uncapitalize(s: str) -> str:
        """首字母小写"""
        if not s:
            return s
        return s[0].lower() + s[1:]

    @staticmethod
    def _clean_param(param: str) -> str:
        """清理参数文本"""
        return param.strip().rstrip(';').strip()

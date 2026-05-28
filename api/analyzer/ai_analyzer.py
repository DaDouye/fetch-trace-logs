#!/usr/bin/env python3
"""
AI-powered cause analysis using Anthropic Claude
"""

import os
import json
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

load_dotenv()


class AIAnalyzer:
    """AI analyzer using Anthropic Claude API"""

    def __init__(self):
        self.api_key = os.getenv('ANTHROPIC_API_KEY')
        self.api_url = os.getenv('ANTHROPIC_API_URL', 'https://api.minimaxi.com/anthropic/v1/messages')
        self.model = os.getenv('ANTHROPIC_MODEL', 'claude-3-5-sonnet-20241022')
        self.verify_ssl = os.getenv('ANTHROPIC_VERIFY_SSL', 'true').lower() != 'false'

    def analyze(
        self,
        jira_content: Dict[str, Any],
        code_context: Dict[str, Any],
        trace_data: Optional[Dict[str, Any]] = None,
        rag_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze JIRA issue using AI and provide cause analysis

        :param jira_content: JIRA issue content
        :param code_context: Code search results and call chains
        :param trace_data: Optional trace data
        :param rag_context: Optional RAG context from LightRAG
        :return: Analysis result with possible causes
        """
        if not self.api_key:
            return {
                'error': 'ANTHROPIC_API_KEY not configured',
                'possible_causes': []
            }

        # Build prompt with optional RAG context
        prompt = self._build_prompt(jira_content, code_context, trace_data, rag_context)

        try:
            response = self._call_claude(prompt)
            return self._parse_response(response)
        except Exception as e:
            return {
                'error': str(e),
                'possible_causes': []
            }

    def _build_prompt(
        self,
        jira_content: Dict[str, Any],
        code_context: Dict[str, Any],
        trace_data: Optional[Dict[str, Any]],
        rag_context: Optional[str] = None
    ) -> str:
        """Build analysis prompt for Claude"""

        # Extract key information
        summary = jira_content.get('summary', '')
        description = jira_content.get('description', '')
        custom_field = jira_content.get('customfield_19900', '')
        issue_key = jira_content.get('key', '')
        issue_type = jira_content.get('issue_type', '')
        priority = jira_content.get('priority', '')

        # Build code context info
        code_files = code_context.get('files', [])
        call_chains = code_context.get('call_chains', [])
        keywords = code_context.get('search_keywords', {})

        prompt = f"""你是一个资深的Java后端问题排查专家。请分析以下JIRA问题并给出可能的原因分析。

## JIRA 信息
- 问题编号: {issue_key}
- 问题类型: {issue_type}
- 优先级: {priority}
- 摘要: {summary}
- 描述: {description or '无'}
- 线上问题描述: {custom_field or '无'}
"""

        # Add RAG context if available
        if rag_context:
            prompt += f"\n## RAG检索到的相关上下文\n{rag_context}\n"

        prompt += """
## 代码上下文
### 搜索到的相关代码文件:
"""

        # Add code files
        if code_files:
            prompt += "\n### 搜索到的相关代码文件:\n"
            for i, file in enumerate(code_files[:10], 1):
                prompt += f"\n{i}. {file.get('file_path', 'Unknown')}"
                matches = file.get('matches', [])
                if matches:
                    for match in matches[:3]:
                        prompt += f"\n   - Line {match.get('line_number', 0)}: {match.get('content', '')[:200]}"
        else:
            prompt += "\n### 搜索到的相关代码文件: 无"

        # Add call chains
        if call_chains:
            prompt += "\n\n### API调用链:\n"
            for chain in call_chains:
                prompt += f"\n{chain.get('api_path', 'Unknown')}:\n"
                call_chain_data = chain.get('call_chain', {})
                call_chain_list = call_chain_data.get('call_chain', [])
                for node in call_chain_list[:20]:
                    layer = node.get('layer', '')
                    class_name = node.get('class_name', '')
                    method_name = node.get('method_name', '')
                    sql = node.get('sql', '')
                    prompt += f"  [{layer}] {class_name}.{method_name}()"
                    if sql:
                        prompt += f" -> SQL: {sql[:100]}"
                    prompt += "\n"
        else:
            prompt += "\n### API调用链: 未提供"

        # Add trace data
        if trace_data and not trace_data.get('error'):
            prompt += f"\n\n### Trace链路数据:\n"
            prompt += f"- Trace ID: {trace_data.get('trace_id', 'N/A')}\n"
            prompt += f"- Span数量: {trace_data.get('span_count', 0)}\n"
            prompt += f"- 包含SQL: {'是' if trace_data.get('has_sql') else '否'}\n"
            if trace_data.get('error_nodes'):
                prompt += "- 异常节点:\n"
                for node in trace_data.get('error_nodes', [])[:5]:
                    prompt += (
                        f"  - {node.get('service_name', 'Unknown')}."
                        f"{node.get('operation_name', 'Unknown')}: "
                        f"{str(node.get('error_text', ''))[:200]}\n"
                    )
            if trace_data.get('api_paths'):
                prompt += f"- Trace API: {', '.join(trace_data.get('api_paths', [])[:5])}\n"
        else:
            prompt += "\n### Trace链路数据: 无"

        files = code_context.get('files') or []
        if files:
            prompt += "\n\n### 代码搜索命中:\n"
            for item in files[:8]:
                prompt += f"- {item.get('file_path')} keyword={item.get('keyword')} source={item.get('source', 'unknown')}\n"
                for match in (item.get('matches') or [])[:2]:
                    prompt += f"  L{match.get('line_number')}: {str(match.get('content', ''))[:180]}\n"

        # Add log data
        log_data = code_context.get('logs')
        if log_data and log_data.get('success'):
            prompt += f"\n\n### 日志数据:\n"
            prompt += f"- 涉及服务: {', '.join(log_data.get('services', []))}\n"
            prompt += f"- 日志总数: {log_data.get('total_entries', 0)}\n"
            prompt += f"- ERROR日志: {log_data.get('error_count', 0)}\n"
            if log_data.get('error_messages'):
                prompt += f"\n错误日志片段:\n"
                for i, msg in enumerate(log_data.get('error_messages', [])[:5], 1):
                    prompt += f"{i}. {msg[:200]}\n"
            if log_data.get('evidence_summary'):
                prompt += f"\n日志摘要: {log_data.get('evidence_summary')}\n"
        else:
            prompt += "\n### 日志数据: 无"

        prompt += """

## 分析要求
请根据以上信息，分析最可能的问题原因，要求：
1. 列出3-5个最可能的原因
2. 每个原因说明：原因分类、具体分析、建议的排查方向
3. 如果有相关代码，给出具体的代码位置和问题点
4. 如果是业务问题，指出可能的问题流程或状态

请用JSON格式返回结果：
{
  "possible_causes": [
    {
      "category": "原因分类",
      "analysis": "具体分析",
      "suggestion": "排查建议",
      "confidence": 0.9,
      "related_code": "相关代码文件:行号"
    }
  ],
  "summary": "总体分析结论"
}
"""

        return prompt

    def _call_claude(self, prompt: str) -> str:
        """Call Claude API"""
        import urllib.request
        import urllib.error
        import ssl

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}',
            'anthropic-version': '2023-06-01'
        }

        data = {
            'model': self.model,
            'max_tokens': 4096,
            'messages': [
                {
                    'role': 'user',
                    'content': prompt
                }
            ]
        }

        req = urllib.request.Request(
            self.api_url,
            data=json.dumps(data).encode('utf-8'),
            headers=headers,
            method='POST'
        )

        ctx = ssl.create_default_context()
        if not self.verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        try:
            with urllib.request.urlopen(req, timeout=300, context=ctx) as response:
                response_body = response.read().decode('utf-8')
                if not response_body:
                    raise Exception("Empty response from API")
                result = json.loads(response_body)
                # 获取content列表中的text类型内容
                content_list = result.get('content', [])
                for item in content_list:
                    if item.get('type') == 'text':
                        return item.get('text', '')
                # 如果没有text类型，返回第一个非thinking的内容
                for item in content_list:
                    if item.get('type') != 'thinking':
                        return item.get('text', item.get('content', ''))
                return ''
        except urllib.error.HTTPError as e:
            error_body = e.read().decode('utf-8') if e.fp else str(e)
            raise Exception(f"HTTP Error {e.code}: {error_body}")
        except json.JSONDecodeError as e:
            raise Exception(f"JSON Decode Error: {str(e)}")
        except Exception as e:
            raise Exception(f"API Error: {str(e)}")

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse Claude response to structured result"""
        if not response or not response.strip():
            return {
                'possible_causes': [],
                'summary': '',
                'error': 'Empty response from AI'
            }

        try:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                causes = result.get('possible_causes', [])
                # 过滤掉空的分析
                causes = [c for c in causes if c.get('analysis')]
                return {
                    'possible_causes': causes,
                    'summary': result.get('summary', ''),
                    'ai_enhanced': True
                }
        except json.JSONDecodeError:
            pass

        # Fallback: return raw response as a cause
        return {
            'possible_causes': [
                {
                    'category': 'AI分析',
                    'analysis': response[:2000] if len(response) > 2000 else response,
                    'suggestion': '请查看AI分析结果',
                    'confidence': 0.8
                }
            ],
            'summary': response[:500],
            'ai_enhanced': True
        }


def main():
    """Test AI analyzer"""
    analyzer = AIAnalyzer()

    test_jira = {
        'key': 'TEST-123',
        'summary': '用户无法下单',
        'description': '点击下单按钮后提示系统错误',
        'issue_type': 'Bug',
        'priority': 'High'
    }

    test_code_context = {
        'files': [],
        'call_chains': [],
        'search_keywords': {}
    }

    result = analyzer.analyze(test_jira, test_code_context)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

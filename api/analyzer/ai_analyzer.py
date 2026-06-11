





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
            import traceback
            print(f"[AIError] API call failed: {e}")
            print(f"[AIError] Traceback: {traceback.format_exc()}")
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
        comments = jira_content.get('comments') or []

        # Build code context info
        code_files = code_context.get('files', [])
        call_chains = code_context.get('call_chains', [])
        method_snippets = code_context.get('method_snippets', [])

        # Build prompt in sections, collecting code for the end
        sections = []

        # Section 1: JIRA context
        sections.append(f"""你是一个资深的Java后端问题排查专家。以下是问题背景：

## 问题背景
- 问题编号: {issue_key}
- 问题类型: {issue_type}
- 优先级: {priority}
- 摘要: {summary}
- 描述: {description or '无'}
- 线上问题描述: {custom_field or '无'}
""")

        if comments:
            comments_text = "\n## 评论摘要\n"
            for comment in comments[-5:]:
                body = str(comment.get('body') or '').replace('\r', ' ').replace('\n', ' ')
                comments_text += f"- {comment.get('author', 'Unknown')}: {body[:300]}\n"
            sections.append(comments_text)

        if rag_context:
            sections.append(f"\n## RAG上下文\n{rag_context}\n")

        # Section 2: Error evidence (trace + logs)
        error_section = "\n## 错误证据\n"
        if trace_data and not trace_data.get('error'):
            error_section += f"- Trace ID: {trace_data.get('trace_id', 'N/A')}\n"
            error_section += f"- Span数量: {trace_data.get('span_count', 0)}\n"
            if trace_data.get('api_paths'):
                error_section += f"- Trace API: {', '.join(trace_data.get('api_paths', [])[:5])}\n"
            if trace_data.get('error_nodes'):
                error_section += "- 异常节点:\n"
                for node in trace_data.get('error_nodes', [])[:5]:
                    error_section += (
                        f"  - {node.get('service_name', 'Unknown')}."
                        f"{node.get('operation_name', 'Unknown')}: "
                        f"{str(node.get('error_text', ''))[:300]}\n"
                    )
            if trace_data.get('has_sql'):
                error_section += "- 包含 SQL 查询\n"
        else:
            error_section += "- Trace链路数据: 无\n"

        log_data = code_context.get('logs')
        if log_data and log_data.get('success'):
            error_section += f"\n### 日志\n"
            error_section += f"- 服务: {', '.join(log_data.get('services', []))}\n"
            error_section += f"- ERROR日志数: {log_data.get('error_count', 0)}\n"
            if log_data.get('error_messages'):
                error_section += "\n错误日志:\n"
                for i, msg in enumerate(log_data.get('error_messages', [])[:5], 1):
                    error_section += f"{i}. {msg[:300]}\n"
        sections.append(error_section)

        # Section 3: Call chain summary (brief)
        if call_chains:
            chain_section = "\n## API调用链\n"
            for chain in call_chains:
                chain_section += f"\n{chain.get('api_path', 'Unknown')}:\n"
                call_chain_data = chain.get('call_chain', {})
                if call_chain_data.get('error'):
                    chain_section += f"  [调用链分析失败: {call_chain_data.get('error')}]\n"
                else:
                    call_chain_list = call_chain_data.get('call_chain', [])
                    for node in call_chain_list[:20]:
                        layer = node.get('layer', '')
                        class_name = node.get('class_name', '')
                        method_name = node.get('method_name', '')
                        sql = node.get('sql', '')
                        chain_section += f"  [{layer}] {class_name}.{method_name}()"
                        if sql:
                            chain_section += f" -> SQL: {sql[:100]}"
                        chain_section += "\n"
            sections.append(chain_section)

        # Section 4: Relevant files list (brief)
        if code_files:
            file_section = "\n## 相关代码文件\n"
            # Deduplicate and show top files
            seen_files = set()
            count = 0
            for f in code_files:
                fp = f.get('file_path', '')
                if fp in seen_files or count >= 15:
                    continue
                seen_files.add(fp)
                count += 1
                keyword = f.get('keyword', '')
                file_section += f"- {fp}"
                if keyword:
                    file_section += f" (匹配: {keyword})"
                file_section += "\n"
            sections.append(file_section)

        # ============================================================
        # KEY: Put source code RIGHT BEFORE analysis instructions
        # ============================================================

        prompt = ''.join(sections)

        # Source code section - the most critical part
        if method_snippets:
            prompt += "\n---\n\n## 需要分析的源码（必须逐方法阅读）\n\n"
            prompt += "以下是相关的方法体源码。你必须在分析中引用具体的行号、方法名、变量名和条件判断。\n\n"
            for i, snippet in enumerate(method_snippets[:15], 1):
                file_path = snippet.get('file_path', '')
                class_name = snippet.get('class_name', '')
                method_name = snippet.get('method_name', '')
                line_number = snippet.get('line_number', 0)
                body = snippet.get('body', '')
                prompt += f"### 方法 {i}: {class_name}.{method_name}()\n"
                prompt += f"文件: {file_path}:{line_number}\n"
                prompt += f"```java\n{body[:2500]}\n```\n\n"
        else:
            prompt += "\n---\n\n## 需要分析的源码\n\n"
            prompt += "**警告：未获取到方法体源码。** 请基于上述代码搜索命中的文件路径，在排查建议中明确列出需要人工查看的文件。\n\n"

        # Analysis instructions
        prompt += """---


## 分析要求

你必须按照以下步骤进行结构化分析。最重要的是：**每个可能的原因都必须深入到代码层面**，不能停留在"可能是XX问题"的笼统描述。

### 第一步：定位异常点
- 从日志数据中提取所有 ERROR 日志，确定异常类型和抛出位置
- 从 Trace 链路数据中定位异常节点，明确是哪个服务、哪个方法出错
- 从 API 调用链中找到对应的入口接口和调用路径

### 第二步：代码路径追踪（核心步骤，必须完成）
- 从异常点出发，沿着调用链逆向追踪代码执行路径
- 在「调用链方法体源码」中逐方法阅读代码，找到关键逻辑点
- 分析该路径上的：参数校验、状态判断、异常处理、事务边界、锁竞争、远程调用
- 如果代码上下文中没有直接匹配的代码，需明确说明缺失了哪些模块

### 第三步：交叉验证
- 将代码逻辑与日志错误对照，确认代码中是否真的会抛出该异常
- 将 Trace 链路中的慢节点/SQL 与代码中的数据库操作对照
- 将 JIRA 描述的业务现象与代码中的业务流程对照

### 第四步：输出分析结果

列出 3-5 个最可能的原因。每个原因必须包含具体的代码分析，格式如下：

1. **原因分类**：代码缺陷 / 配置问题 / 数据异常 / 依赖服务故障 / 并发问题 / 业务逻辑错误
2. **代码位置**（必填，不可为空）：文件路径:行号 - 方法名
3. **代码分析**（必填，不可为空）：逐行分析关键代码逻辑，引用具体的方法名、变量名、条件分支，说明为什么这段代码会导致该问题
4. **证据链**：日志/Trace 证据 → 代码逻辑 → 业务现象的因果链
5. **排查建议**：可直接验证的具体排查步骤

---

## 输出示例（Few-shot）

以下是一个合格的代码分析示例，请注意代码分析的深度和具体程度：

```json
{
  "possible_causes": [
    {
      "category": "代码缺陷 - 空指针",
      "code_location": "CustomerServiceImpl.java:156 - assignToEvaluator()",
      "code_analysis": "该方法在第 156 行调用 evaluatorMapper.selectById(evaluatorId) 获取评估师信息，但未对返回结果做 null 检查。第 158 行直接使用 evaluator.getName() 赋值给客户记录。当 evaluatorId 对应的评估师已被禁用或删除时，selectById 返回 null，导致 NullPointerException。调用链显示该方法由 CustomerController.saveCustomer() (L42) → CustomerService.assignEvaluator() (L120) 触发，请求参数 evaluatorId 来自前端下拉框，该下拉框包含了已禁用的评估师选项。",
      "evidence_chain": "Trace 异常节点显示 CustomerServiceImpl.assignToEvaluator:156 抛出 NullPointerException → 代码确认该行未做 null 检查 → JIRA 反馈「分配评估师时报系统错误」，与空指针现象一致",
      "suggestion": "1. 在 CustomerServiceImpl.java:157 添加 if (evaluator == null) 判断；2. 检查前端评估师下拉框的数据源是否过滤了 status='DISABLED' 的记录；3. 排查 evaluatorId 参数来源，确认是前端传入还是后端默认值",
      "confidence": 0.85
    },
    {
      "category": "数据异常 - 状态不一致",
      "code_location": "OrderStateMachine.java:89 - transition()",
      "code_analysis": "transition() 方法在第 89 行校验当前状态是否允许转换到目标状态。该方法使用 stateConfig Map 维护状态转换规则（第 45 行初始化）。Trace 链路显示该订单在 50ms 内连续收到两次状态变更请求：第一次由 PaymentCallback.onSuccess() 触发（支付回调），第二次由用户手动点击「确认收款」触发。由于两次请求并发执行，都读取到了转换前的状态，第一次成功后第二次因状态已变更而失败，抛出 IllegalStateException。代码未对状态转换加锁或使用乐观锁。",
      "evidence_chain": "Trace 链路显示两次请求间隔仅 50ms → 代码确认 transition() 无并发控制 → 日志 ERROR: IllegalStateException: 订单状态不允许从 PAID 转换到 CONFIRMED → JIRA 反馈「支付成功后点击确认收款提示状态错误」",
      "suggestion": "1. 在 OrderStateMachine.transition() 方法上添加 @Transactional 并使用 SELECT FOR UPDATE 锁定订单行；2. 前端在支付成功后禁用「确认收款」按钮；3. 确认收款接口增加幂等性判断，如果已经是 CONFIRMED 状态直接返回成功",
      "confidence": 0.75
    }
  ],
  "summary": "最可能的原因是 CustomerServiceImpl.assignToEvaluator() 未对 evaluatorMapper.selectById() 的返回值做 null 检查。建议优先排查 evaluatorId 的数据来源和评估师状态。",
  "code_coverage": "已覆盖：Controller → Service → Mapper 完整调用链上的 5 个方法。未覆盖：前端评估师下拉框的数据查询逻辑、评估师表结构定义。"
}
```

**关键要求：code_analysis 必须引用代码中的具体行号、方法名、变量名、条件判断，不能写成「可能是空指针」这种笼统描述。**

请以 JSON 格式返回分析结果。
"""

        # Debug: log what code data the AI actually receives
        files_count = len(code_context.get('files', []))
        snippets_count = len(code_context.get('method_snippets', []))
        chains_count = len(code_context.get('call_chains', []))
        evidence_count = len(code_context.get('business_evidence', []))
        total_matches = sum(len(f.get('matches', [])) for f in (code_context.get('files') or []))
        total_snippet_chars = sum(len(s.get('body', '')) for s in (code_context.get('method_snippets') or []))
        print(f"[AIPrompt] Building prompt - files: {files_count}, matches: {total_matches}, "
              f"method_snippets: {snippets_count} ({total_snippet_chars} chars), "
              f"call_chains: {chains_count}, business_evidence: {evidence_count}, "
              f"prompt_length: {len(prompt)} chars")

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
            'max_tokens': 8192,
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

                # Debug: log raw response structure
                content_list = result.get('content', [])
                print(f"[AIResponse] content blocks: {len(content_list)}, "
                      f"types: {[item.get('type') for item in content_list]}, "
                      f"stop_reason: {result.get('stop_reason', 'N/A')}, "
                      f"model: {result.get('model', 'N/A')}")

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

        print(f"[AIParse] Response length: {len(response)}, first 300 chars: {response[:300]}")

        try:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                causes = result.get('possible_causes', [])
                # 过滤掉空的分析
                causes = [c for c in causes if c.get('code_analysis') or c.get('analysis')]
                print(f"[AIParse] JSON parsed OK, {len(causes)} causes")
                return {
                    'possible_causes': causes,
                    'summary': result.get('summary', ''),
                    'ai_enhanced': True
                }
            else:
                print(f"[AIParse] No JSON found in response, using fallback")
        except json.JSONDecodeError as e:
            print(f"[AIParse] JSON decode error: {e}")

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

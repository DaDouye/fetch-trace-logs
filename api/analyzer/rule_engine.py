#!/usr/bin/env python3
"""
Rule-based cause analysis engine
"""

import re
from typing import List, Dict, Any


class RuleEngine:
    """
    Rule-based engine for analyzing JIRA issues and identifying possible causes
    """

    # Predefined rule patterns for common error categories
    RULES = [
        {
            'id': 'null_pointer',
            'category': '空指针',
            'patterns': [
                r'NullPointerException',
                r'NPE',
                r'NullPointer',
                r'null\s*(?:pointer|reference)',
                r'cannot\s+invoke\s+.*because\s+.*is\s+null',
                r'.*\.execute\(\)\s+on\s+null'
            ],
            'keywords': ['null', 'NPE', '空对象'],
            'suggestion': '检查对象是否为空，在调用方法前进行 null 检查'
        },
        {
            'id': 'sql_exception',
            'category': '数据库异常',
            'patterns': [
                r'SQLException',
                r'SQLError',
                r'SQL\s*Exception',
                r'Database\s*error',
                r'connection\s+(?:refused|timeout|failed)',
                r'could\s+not\s+(?:execute|prepare|commit)',
                r'违反\s*唯一\s*约束'
            ],
            'keywords': ['sql', '数据库', '连接', 'SQLException', 'connection'],
            'suggestion': '检查数据库连接是否正常，SQL 语句是否正确，是否违反唯一约束'
        },
        {
            'id': 'timeout',
            'category': '超时问题',
            'patterns': [
                r'TimeoutException',
                r'SocketTimeoutException',
                r'timeout',
                r'超时',
                r'read\s+timeout',
                r'connect\s+timeout',
                r'request\s+timeout',
                r'Read\s+timed\s+out'
            ],
            'keywords': ['timeout', '超时', 'timed out'],
            'suggestion': '检查接口响应时间，优化慢查询，增加超时配置'
        },
        {
            'id': 'out_of_memory',
            'category': '内存溢出',
            'patterns': [
                r'OutOfMemoryError',
                r'OOM',
                r'Java\s+heap\s+space',
                r'Unable\s+to\s+create',
                r'GC\s+(?:overhead|limit)',
                r'Metspace'
            ],
            'keywords': ['OOM', 'outofmemory', 'heap', '内存'],
            'suggestion': '检查是否存在内存泄漏，增加 JVM 堆内存配置'
        },
        {
            'id': 'index_out_of_bounds',
            'category': '数组越界',
            'patterns': [
                r'IndexOutOfBoundsException',
                r'ArrayIndexOutOfBoundsException',
                r'StringIndexOutOfBounds',
                r'index\s+\d+\s+size\s+\d+',
                r'list\s+size'
            ],
            'keywords': ['index', 'bounds', 'size', '数组'],
            'suggestion': '检查数组或集合索引是否越界，循环条件是否正确'
        },
        {
            'id': 'concurrent_modification',
            'category': '并发修改异常',
            'patterns': [
                r'ConcurrentModificationException',
                r'ConcurrentModification',
                r'同时\s*(?:修改|操作)'
            ],
            'keywords': ['concurrent', 'modification', '并发'],
            'suggestion': '使用线程安全的集合类，或在迭代时避免修改集合'
        },
        {
            'id': 'illegal_argument',
            'category': '参数错误',
            'patterns': [
                r'IllegalArgumentException',
                r'IllegalArgument',
                r'Invalid\s+(?:argument|parameter)',
                r'参数\s*(?:错误|异常|无效)',
                r'cannot\s+be\s+null',
                r'must\s+not\s+be\s+null'
            ],
            'keywords': ['argument', 'parameter', '参数', 'invalid'],
            'suggestion': '检查传入参数是否合法，是否为空或格式错误'
        },
        {
            'id': 'illegal_state',
            'category': '状态异常',
            'patterns': [
                r'IllegalStateException',
                r'IllegalState',
                r'state\s+(?:error|invalid|invalid)',
                r'invalid\s+state',
                r'状态\s*(?:异常|错误|非法)'
            ],
            'keywords': ['state', 'status', '状态'],
            'suggestion': '检查对象状态是否允许当前操作'
        },
        {
            'id': 'connection_refused',
            'category': '连接被拒绝',
            'patterns': [
                r'Connection\s+refused',
                r'connect\s+refused',
                r'连接\s*被\s*拒绝',
                r'Connection\s+reset',
                r'connect\s+failed'
            ],
            'keywords': ['connection', 'refused', '连接'],
            'suggestion': '检查目标服务是否启动，网络是否通畅，端口是否正确'
        },
        {
            'id': 'business_logic',
            'category': '业务逻辑错误',
            'patterns': [
                r'业务\s*(?:异常|错误|失败)',
                r'logic\s*error',
                r'业务\s*处理\s*失败',
                r'操作\s*失败',
                r'流程\s*异常',
                r'状态\s*不对'
            ],
            'keywords': ['业务', 'logic', '流程', '操作'],
            'suggestion': '检查业务流程是否正确，状态转换是否符合预期'
        },
        {
            'id': 'permission_denied',
            'category': '权限问题',
            'patterns': [
                r'Permission\s+denied',
                r'Access\s+denied',
                r'权限\s*(?:不足|被拒绝|异常)',
                r'Unauthorized',
                r'Forbidden',
                r'无权限'
            ],
            'keywords': ['permission', 'access', '权限', 'authorized'],
            'suggestion': '检查用户权限是否足够，是否已登录认证'
        },
        {
            'id': 'serialization',
            'category': '序列化错误',
            'patterns': [
                r'SerializationException',
                r'Serializable',
                r'not\s+serializable',
                r'JSON\s*(?:parse|encode)\s*error',
                r'ObjectMapper',
                r'反序列化'
            ],
            'keywords': ['serial', 'json', 'serialize', '反序列化'],
            'suggestion': '检查对象是否实现了序列化接口，JSON 格式是否正确'
        }
    ]

    def __init__(self, custom_rules: List[Dict] = None):
        """
        Initialize rule engine

        :param custom_rules: Optional list of custom rules to add
        """
        self.rules = list(self.RULES)
        if custom_rules:
            self.rules.extend(custom_rules)

    def analyze(self, text: str) -> List[Dict[str, Any]]:
        """
        Analyze text and identify possible problem causes

        :param text: Text to analyze (JIRA description, comments, etc.)
        :return: List of identified causes with details
        """
        causes = []
        text_lower = text.lower()

        for rule in self.rules:
            # Check if any pattern matches
            matched_patterns = []
            for pattern in rule['patterns']:
                if re.search(pattern, text, re.IGNORECASE):
                    matched_patterns.append(pattern)

            if matched_patterns:
                cause = {
                    'id': rule['id'],
                    'category': rule['category'],
                    'matched_patterns': matched_patterns,
                    'keywords': rule['keywords'],
                    'suggestion': rule['suggestion'],
                    'confidence': self._calculate_confidence(text, rule)
                }
                causes.append(cause)

        # Sort by confidence (highest first)
        causes.sort(key=lambda x: x['confidence'], reverse=True)

        return causes

    def _calculate_confidence(self, text: str, rule: Dict) -> float:
        """
        Calculate confidence score based on keyword frequency

        :param text: Text to analyze
        :param rule: Rule definition
        :return: Confidence score 0.0 - 1.0
        """
        text_lower = text.lower()
        keyword_count = 0

        for keyword in rule.get('keywords', []):
            # Count occurrences of each keyword
            count = len(re.findall(r'\b' + re.escape(keyword.lower()) + r'\b', text_lower))
            keyword_count += count

        # Base confidence on pattern match, increase with keyword frequency
        base_confidence = 0.6 if rule['patterns'] else 0.3

        # Increase confidence for each keyword found (capped at 0.95)
        confidence = min(0.95, base_confidence + (keyword_count * 0.05))

        return confidence

    def get_categories(self) -> List[str]:
        """Get list of all available categories"""
        return [rule['category'] for rule in self.rules]

    def get_rule_by_id(self, rule_id: str) -> Dict:
        """Get rule definition by ID"""
        for rule in self.rules:
            if rule['id'] == rule_id:
                return rule
        return None


def main():
    """Test rule engine"""
    engine = RuleEngine()

    test_texts = [
        "NullPointerException at CustomerService.java:42",
        "SQLException: Connection refused to database",
        "接口超时，响应时间超过 30 秒",
        "用户反馈无法保存订单，提示业务逻辑错误"
    ]

    print("Rule Engine Test")
    print("=" * 60)

    for text in test_texts:
        print(f"\nText: {text}")
        causes = engine.analyze(text)
        for cause in causes:
            print(f"  Category: {cause['category']}")
            print(f"  Confidence: {cause['confidence']:.2f}")
            print(f"  Suggestion: {cause['suggestion']}")


if __name__ == "__main__":
    main()
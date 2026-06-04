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
            'id': 'org_role_visibility',
            'category': '权限/组织/角色配置',
            'patterns': [
                r'权限包', r'自定义权限', r'角色', r'组织', r'门店', r'集团',
                r'按钮.*(?:没有|看不到|不显示|隐藏)',
                r'(?:没有|看不到|不显示).*按钮',
                r'归属部门', r'管理员'
            ],
            'keywords': ['权限', '权限包', '角色', '组织', '门店', '集团', '按钮'],
            'suggestion': '核对账号角色、权限包、组织/门店归属和按钮可见性规则'
        },
        {
            'id': 'data_config_dirty_data',
            'category': '数据/配置/缓存问题',
            'patterns': [
                r'apollo', r'配置', r'缓存', r'脏数据', r'历史数据',
                r'数据.*(?:为空|缺失|订正|不一致|对不上)',
                r'(?:字段|表|数据库).*为空',
                r'已订正', r'数据已处理'
            ],
            'keywords': ['配置', '缓存', '脏数据', '历史数据', '数据库', '字段', '订正'],
            'suggestion': '检查线上配置、缓存、历史数据和关键表字段是否符合业务前置条件'
        },
        {
            'id': 'third_party_platform',
            'category': '第三方平台/授权问题',
            'patterns': [
                r'闲鱼', r'汽车之家', r'高德', r'58', r'懂车帝', r'抖音', r'快手',
                r'第三方', r'授权', r'绑定', r'解绑', r'审核', r'平台返回'
            ],
            'keywords': ['闲鱼', '汽车之家', '高德', '第三方', '授权', '绑定', '平台'],
            'suggestion': '核对第三方账号绑定关系、授权有效期、平台审核状态和外部接口返回'
        },
        {
            'id': 'product_logic_non_bug',
            'category': '产品逻辑/非缺陷',
            'patterns': [
                r'不是\s*bug', r'非\s*bug', r'不属于\s*bug',
                r'符合预期', r'产品逻辑', r'需求逻辑', r'规则如此',
                r'正常(?:展示|返回|逻辑)?'
            ],
            'keywords': ['不是bug', '非bug', '符合预期', '产品逻辑', '规则', '正常'],
            'suggestion': '确认当前现象是否符合产品规则，必要时补充前端提示或转产品优化'
        },
        {
            'id': 'sync_consistency',
            'category': '同步/数据一致性',
            'patterns': [
                r'同步', r'不一致', r'对不上', r'不更新', r'未更新',
                r'重复', r'丢失', r'数量.*(?:不对|对不上)', r'状态.*(?:不一致|不对)'
            ],
            'keywords': ['同步', '不一致', '对不上', '不更新', '重复', '丢失', '数量', '状态'],
            'suggestion': '检查同步链路、消息重复消费、异步延迟、排序条件和跨表状态聚合逻辑'
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

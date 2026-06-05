#!/usr/bin/env python3
"""
Utilities for extracting structured signals from Jira comments and ONLINEBUG history.
"""

import html
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class CommentInsightExtractor:
    """Extract conclusion-style signals from tester/developer Jira comments."""

    CATEGORY_RULES = [
        ("代码/接口异常", ("接口", "代码", "bug", "异常", "报错", "空指针", "超时", "返回", "入参", "服务")),
        ("数据/配置/缓存", ("配置", "apollo", "缓存", "数据问题", "脏数据", "数据库", "字段", "为空", "历史数据", "订正")),
        ("权限/角色/组织", ("权限", "权限包", "角色", "员工", "管理员", "组织", "门店", "集团", "按钮", "看不到", "隐藏")),
        ("第三方/外部平台", ("第三方", "闲鱼", "汽车之家", "高德", "58", "懂车帝", "抖音", "快手", "授权", "平台")),
        ("产品逻辑/非缺陷", ("正常", "符合预期", "产品逻辑", "逻辑", "规则", "不是bug", "非bug", "不属于bug", "没有问题")),
        ("用户操作/使用方式", ("操作", "使用", "误操作", "看错", "刷新", "重新登录", "清缓存", "需要先", "未操作")),
        ("需求/优化", ("需求", "优化", "后续", "待优化", "产品确认", "排期", "转需求")),
        ("无法复现/信息不足", ("无法复现", "未复现", "复现不了", "缺少", "需要提供", "麻烦提供", "没有截图", "没有日志")),
        ("重复问题", ("重复", "duplicate", "已有", "同一个问题", "关联")),
    ]

    RESOLUTION_RULES = [
        ("已修复/已发布", ("已修复", "修复了", "已发", "已发布", "发版", "上线", "已优化发布")),
        ("数据订正/配置调整", ("已订正", "数据已处理", "订正数据库", "修改配置", "发布apollo", "配置调整")),
        ("按规则正常/非缺陷", ("不是bug", "非bug", "正常", "符合预期", "规则", "产品逻辑", "没有问题")),
        ("第三方处理/限制", ("第三方", "已联系", "平台", "审核", "解绑", "授权")),
        ("转需求/后续优化", ("转需求", "后续优化", "待优化", "产品确认", "排期")),
        ("无法复现/待补充", ("无法复现", "未复现", "需要提供", "麻烦提供", "补充")),
    ]

    IMPORTANT_PHRASES = (
        "根本原因", "直接原因", "原因", "解决方案", "解决办法", "处理方案", "影响范围",
        "已发", "已修复", "已发布", "已处理", "已订正", "正常", "不是bug", "非bug",
        "无法复现", "权限", "配置", "第三方", "需求", "优化"
    )

    def extract(self, jira: Dict[str, Any]) -> Dict[str, Any]:
        comments = jira.get("comments") or []
        bodies = [self._normalize(c.get("body", "")) for c in comments if self._normalize(c.get("body", ""))]
        text = "\n".join(bodies)
        final_comment = bodies[-1] if bodies else ""

        category_scores = []
        lowered = text.lower()
        for category, keywords in self.CATEGORY_RULES:
            hits = [kw for kw in keywords if kw.lower() in lowered]
            if hits:
                category_scores.append({
                    "category": category,
                    "score": len(hits),
                    "evidence": hits[:6],
                })
        category_scores.sort(key=lambda item: item["score"], reverse=True)

        resolution = self._resolve_resolution(lowered, jira.get("status", ""))
        is_real_bug = self._infer_real_bug(jira.get("status", ""), lowered, resolution)

        return {
            "comment_count": len(comments),
            "has_comments": bool(comments),
            "first_comment": bodies[0][:300] if bodies else "",
            "final_comment": final_comment[:500],
            "root_cause_category": category_scores[0]["category"] if category_scores else "未识别",
            "category_scores": category_scores[:5],
            "resolution_action": resolution,
            "is_real_bug": is_real_bug,
            "evidence_phrases": [phrase for phrase in self.IMPORTANT_PHRASES if phrase.lower() in lowered],
        }

    def _resolve_resolution(self, text: str, status: str) -> str:
        for resolution, keywords in self.RESOLUTION_RULES:
            if any(kw.lower() in text for kw in keywords):
                return resolution
        if status == "Fixed":
            return "已修复/已发布"
        if status == "REJECTED":
            return "按规则正常/非缺陷"
        if status == "DUPLICATE":
            return "重复问题"
        if status == "LATER":
            return "转需求/后续优化"
        return "未明确"

    @staticmethod
    def _infer_real_bug(status: str, text: str, resolution: str) -> Optional[bool]:
        if status == "Fixed" or resolution == "已修复/已发布":
            return True
        if status in {"REJECTED", "DUPLICATE"}:
            return False
        if any(token in text for token in ("不是bug", "非bug", "符合预期", "没有问题", "无法复现")):
            return False
        if any(token in text for token in ("已修复", "修复了", "已发布", "已发")):
            return True
        return None

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()


class ProblemDomainClassifier:
    """Classify ONLINEBUG issues into reusable business troubleshooting domains."""

    DOMAIN_RULES = [
        (
            "渠道接入/授权/同步",
            ("闲鱼", "抖音", "快手", "汽车之家", "懂车帝", "易车", "58同城", "企微", "企业微信", "微信", "小程序", "微店"),
            ("绑定", "授权", "同步", "入驻", "挂载", "分享", "账号", "登录", "无法", "报错", "审核", "上架", "下架"),
        ),
        (
            "线索分配/归属/公海",
            ("自动分配", "客户分配", "线索分配", "分配", "归属", "公海", "认领", "转交", "回收"),
            ("线索", "客户", "商机", "公海", "分配", "归属", "回收"),
        ),
        (
            "线索生成/来源/轨迹",
            ("线索", "商机", "留资", "客资", "进线", "来源", "轨迹"),
            ("不生成", "没有", "无", "不显示", "异常", "不更新", "错误", "来源", "轨迹", "重复", "推送"),
        ),
        (
            "客户管理/跟进",
            ("客户档案", "客户跟进", "跟进", "回访", "邀约", "意向", "客户详情", "客户来源", "客户搜索", "添加客户", "导入客户", "创建客户"),
            (),
        ),
        (
            "数据展示/统计/查询",
            ("统计", "报表", "看板", "导出", "数量", "列表", "筛选", "搜索", "数据", "不一致", "对不上", "不对", "经营分析", "排名"),
            (),
        ),
        (
            "权限/配置/规则",
            ("权限", "权限包", "角色", "配置", "设置", "开关", "白名单", "组织架构", "管理员"),
            (),
        ),
        (
            "车辆/车源/订单合同",
            ("车辆", "车源", "库存", "车型", "车架号", "上架", "下架", "关联车辆", "检测报告", "销售订单", "采购订单", "合同"),
            (),
        ),
        (
            "页面/操作异常",
            ("报错", "打不开", "白屏", "按钮", "页面", "无法", "失败", "异常", "卡住", "闪退"),
            (),
        ),
    ]

    DIAGNOSIS_CHECKLIST = {
        "渠道接入/授权/同步": [
            "核对渠道账号绑定关系、授权有效期和平台审核状态",
            "检查同步任务、平台返回码以及车辆/线索是否满足同步条件",
            "确认是否存在第三方平台限制、账号复用或店铺绑定冲突",
        ],
        "线索分配/归属/公海": [
            "核查客户当前归属、历史分配记录和是否已有重复客户",
            "核对自动分配规则、公海回收规则、员工/评估师是否在规则范围内",
            "检查分配轨迹是否重复触发，是否存在异步延迟或规则配置变更",
        ],
        "线索生成/来源/轨迹": [
            "核查渠道留资是否入库、来源字段和轨迹生成延迟",
            "检查同客户/同手机号判重、重复推送和来源覆盖逻辑",
            "确认页面展示口径与线索/轨迹表记录是否一致",
        ],
        "客户管理/跟进": [
            "核查客户归属、跟进任务、回收状态和筛选条件",
            "检查客户档案、跟进计划、任务中心的数据口径是否一致",
            "确认当前账号权限和组织/门店范围是否覆盖该客户",
        ],
        "数据展示/统计/查询": [
            "对比页面查询、导出和报表是否使用同一筛选条件",
            "核查统计口径、缓存、异步计算和历史数据订正情况",
            "保留接口入参、SQL 条件和实际返回数量作为证据",
        ],
        "权限/配置/规则": [
            "核对账号角色、权限包、组织/门店归属和功能开关",
            "检查配置中心、白名单、灰度范围和前端按钮可见性规则",
            "确认当前现象是否符合产品规则，必要时补充提示或转需求",
        ],
        "车辆/车源/订单合同": [
            "核查车辆状态、销售/采购订单状态、合同审批和收付款状态",
            "检查车辆上架/下架、渠道同步、检测报告和库存状态变更记录",
            "对比订单/收支/车辆列表之间的数据来源和状态聚合逻辑",
        ],
        "页面/操作异常": [
            "补充复现路径、账号、浏览器/App 版本和报错截图",
            "检查接口返回、前端入参、权限状态和最近发布记录",
            "确认是否仅特定账号、门店或数据状态下触发",
        ],
        "其他/需人工复核": [
            "补充业务对象、复现步骤、时间窗口和相关账号",
            "优先从历史相似案例中确认是否存在规则解释或数据处理结论",
        ],
    }

    @classmethod
    def classify(cls, text: str) -> str:
        value = str(text or "")
        for domain, primary, secondary in cls.DOMAIN_RULES:
            if not any(word in value for word in primary):
                continue
            if secondary and not any(word in value for word in secondary):
                continue
            return domain
        return "其他/需人工复核"

    @classmethod
    def checklist(cls, domain: str) -> List[str]:
        return cls.DIAGNOSIS_CHECKLIST.get(domain) or cls.DIAGNOSIS_CHECKLIST["其他/需人工复核"]


class HistoricalIssueIndex:
    """Small in-memory index over ONLINEBUG XML exports."""

    STOPWORDS = {
        "问题", "异常", "无法", "不能", "没有", "系统", "客户", "车辆", "账号", "页面",
        "显示", "操作", "数据", "查看", "一下", "这个", "目前", "需要", "反馈",
        "大风", "大风车", "线上", "车商"
    }

    def __init__(self, xml_path: Optional[str] = None):
        root = Path(__file__).resolve().parents[2]
        configured = xml_path or os.getenv("ONLINEBUG_HISTORY_XML")
        if configured:
            self.xml_paths = [
                Path(item.strip())
                for item in str(configured).split(",")
                if item.strip()
            ]
        else:
            self.xml_paths = [
                root / "data/jira_online_issue_2025.xml",
                root / "data/jira_online_issue_2026_up.xml",
            ]
        self._mtime: Optional[Tuple[Tuple[str, Optional[float]], ...]] = None
        self._items: List[Dict[str, Any]] = []
        self._extractor = CommentInsightExtractor()
        self._domain_classifier = ProblemDomainClassifier()

    def search(self, jira: Dict[str, Any], comment_insights: Dict[str, Any], limit: int = 5) -> List[Dict[str, Any]]:
        self._load_if_needed()
        if not self._items:
            return []

        query_text = " ".join([
            str(jira.get("summary") or ""),
            str(jira.get("description") or ""),
            str(jira.get("customfield_19900") or ""),
        ])
        query_terms = self._terms(query_text)
        if not query_terms:
            return []

        target_category = comment_insights.get("root_cause_category")
        target_domain = self._domain_classifier.classify(query_text)
        current_key = jira.get("key")
        scored = []
        for item in self._items:
            if item.get("id") == current_key:
                continue
            overlap = query_terms & item["terms"]
            if not overlap:
                continue
            score = len(overlap) / max(8, len(query_terms))
            if target_domain and item.get("problem_domain") == target_domain:
                score += 0.22
            if target_category and item.get("root_cause_category") == target_category:
                score += 0.18
            if item.get("status") == jira.get("status"):
                score += 0.05
            if score >= 0.18:
                scored.append((score, overlap, item))

        scored.sort(key=lambda row: row[0], reverse=True)
        results = []
        for score, overlap, item in scored[:limit]:
            results.append({
                "issue_key": item.get("id"),
                "summary": item.get("summary"),
                "status": item.get("status"),
                "created_date": item.get("created_date"),
                "problem_domain": item.get("problem_domain"),
                "root_cause_category": item.get("root_cause_category"),
                "resolution_action": item.get("resolution_action"),
                "final_comment": item.get("final_comment"),
                "diagnosis_checklist": item.get("diagnosis_checklist") or [],
                "score": round(score, 3),
                "matched_terms": sorted(overlap)[:8],
            })
        return results

    def _load_if_needed(self) -> None:
        existing_paths = [path for path in self.xml_paths if path.exists()]
        if not existing_paths:
            self._items = []
            return
        mtime = tuple((str(path), path.stat().st_mtime if path.exists() else None) for path in self.xml_paths)
        if self._mtime == mtime:
            return

        items = []
        seen = set()
        for path in existing_paths:
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in re.finditer(r"<row>(.*?)</row>", text, re.S):
                row = {}
                for name, value in re.findall(r'<field name="([^"]+)">(.*?)</field>', match.group(1), re.S):
                    row[name] = html.unescape(value).strip()
                issue_id = row.get("id")
                if not issue_id or issue_id in seen:
                    continue
                seen.add(issue_id)
                comments = self._parse_comments(row.get("comments", ""))
                jira_like = {
                    "key": issue_id,
                    "summary": row.get("summary", ""),
                    "description": row.get("online_desc", ""),
                    "customfield_19900": row.get("online_desc", ""),
                    "status": row.get("status", ""),
                    "comments": comments,
                }
                insights = self._extractor.extract(jira_like)
                combined_text = " ".join([
                    row.get("summary", ""),
                    row.get("online_desc", ""),
                    " ".join(c.get("body", "") for c in comments),
                ])
                problem_domain = self._domain_classifier.classify(combined_text)
                items.append({
                    "id": issue_id,
                    "summary": row.get("summary", ""),
                    "status": row.get("status", ""),
                    "created_date": row.get("created_date", ""),
                    "problem_domain": problem_domain,
                    "root_cause_category": insights.get("root_cause_category"),
                    "resolution_action": insights.get("resolution_action"),
                    "final_comment": insights.get("final_comment"),
                    "diagnosis_checklist": self._domain_classifier.checklist(problem_domain),
                    "terms": self._terms(combined_text),
                })
        self._items = items
        self._mtime = mtime

    @classmethod
    def _terms(cls, text: str) -> Set[str]:
        text = cls._mask_noise(text)
        terms: Set[str] = set()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_/-]{2,}|[\u4e00-\u9fff]{2,}", text):
            if re.match(r"[\u4e00-\u9fff]+$", token):
                for size in (2, 3, 4):
                    for index in range(0, max(0, len(token) - size + 1)):
                        gram = token[index:index + size]
                        if gram not in cls.STOPWORDS:
                            terms.add(gram)
            else:
                terms.add(token.lower())
        return terms

    @staticmethod
    def _mask_noise(text: str) -> str:
        text = re.sub(r"https?://\S+", " ", str(text or ""))
        text = re.sub(r"1[3-9]\d{9}", " ", text)
        return text

    @staticmethod
    def _parse_comments(value: str) -> List[Dict[str, Any]]:
        try:
            parsed = json.loads(value or "[]")
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []

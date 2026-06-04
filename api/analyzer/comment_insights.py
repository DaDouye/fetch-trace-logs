#!/usr/bin/env python3
"""
Utilities for extracting structured signals from Jira comments and 2025 ONLINEBUG history.
"""

import html
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


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


class HistoricalIssueIndex:
    """Small in-memory index over docs/jira_online_issue_2025.xml."""

    STOPWORDS = {
        "问题", "异常", "无法", "不能", "没有", "系统", "客户", "车辆", "账号", "页面",
        "显示", "操作", "数据", "查看", "一下", "这个", "目前", "需要", "反馈"
    }

    def __init__(self, xml_path: Optional[str] = None):
        root = Path(__file__).resolve().parents[2]
        self.xml_path = Path(xml_path or os.getenv("ONLINEBUG_HISTORY_XML", root / "docs/jira_online_issue_2025.xml"))
        self._mtime = None
        self._items: List[Dict[str, Any]] = []
        self._extractor = CommentInsightExtractor()

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
        current_key = jira.get("key")
        scored = []
        for item in self._items:
            if item.get("id") == current_key:
                continue
            overlap = query_terms & item["terms"]
            if not overlap:
                continue
            score = len(overlap) / max(8, len(query_terms))
            if target_category and item.get("root_cause_category") == target_category:
                score += 0.18
            if item.get("status") == jira.get("status"):
                score += 0.05
            scored.append((score, overlap, item))

        scored.sort(key=lambda row: row[0], reverse=True)
        results = []
        for score, overlap, item in scored[:limit]:
            results.append({
                "issue_key": item.get("id"),
                "summary": item.get("summary"),
                "status": item.get("status"),
                "created_date": item.get("created_date"),
                "root_cause_category": item.get("root_cause_category"),
                "resolution_action": item.get("resolution_action"),
                "final_comment": item.get("final_comment"),
                "score": round(score, 3),
                "matched_terms": sorted(overlap)[:8],
            })
        return results

    def _load_if_needed(self) -> None:
        if not self.xml_path.exists():
            self._items = []
            return
        mtime = self.xml_path.stat().st_mtime
        if self._mtime == mtime:
            return

        text = self.xml_path.read_text(encoding="utf-8", errors="replace")
        items = []
        for match in re.finditer(r"<row>(.*?)</row>", text, re.S):
            row = {}
            for name, value in re.findall(r'<field name="([^"]+)">(.*?)</field>', match.group(1), re.S):
                row[name] = html.unescape(value).strip()
            comments = self._parse_comments(row.get("comments", ""))
            jira_like = {
                "key": row.get("id"),
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
            items.append({
                "id": row.get("id"),
                "summary": row.get("summary", ""),
                "status": row.get("status", ""),
                "created_date": row.get("created_date", ""),
                "root_cause_category": insights.get("root_cause_category"),
                "resolution_action": insights.get("resolution_action"),
                "final_comment": insights.get("final_comment"),
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

#!/usr/bin/env python3
"""
FastAPI 服务入口
提供 REST API 接口用于分析 Java 接口调用链
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import json
from datetime import datetime
from dotenv import load_dotenv

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# 加载 .env 文件
load_dotenv()

from api.analyze import JavaCallChainAnalyzer
from api.analyzer.field_tracer import FieldTracer
from config_manager import get_all_git_repos

app = FastAPI(
    title="Fetch Trace Logs API",
    description="Java 接口调用链分析服务",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    """分析请求模型"""
    api_path: Optional[str] = None  # 如 "/v1/customerAction/saveOrUpdateCustomer"，可由 Trace ID 自动识别
    repo_key: Optional[str] = None   # 仓库键名 (可选，与 repo_url 二选一)
    repo_url: Optional[str] = None    # Git 仓库 URL (可选，直接指定远程仓库)
    ref: str = "master"               # Git 分支/ commit (配合 repo_url 使用)
    trace_id: Optional[str] = None   # 可选，用于获取运行时数据
    date: Optional[str] = None       # 可选，如 "2026-04-23"
    cookies: Optional[str] = None     # 可选，trace API 认证 cookies


class RepoInfo(BaseModel):
    """单个仓库信息"""
    repo_url: str
    ref: str = "master"


class AnalyzeJiraRequest(BaseModel):
    """JIRA 问题分析请求模型"""
    jira_url: str                    # JIRA URL (必填)
    repo_key: Optional[str] = None   # 仓库键名 (可选，与 repo_urls 二选一)
    repo_url: Optional[str] = None    # Git 仓库 URL (可选，直接指定远程仓库) - 兼容旧版
    ref: str = "master"               # Git 分支/ commit (配合 repo_url 使用)
    repo_urls: Optional[List[RepoInfo]] = None  # Git 仓库 URL 列表 (支持多仓库)
    api_paths: Optional[List[str]] = None  # API 路径列表 (可选)
    trace_id: Optional[str] = None    # Trace ID (可选)
    trace_date: Optional[str] = None  # Trace 日期 (可选)
    cookies: Optional[str] = None     # Trace API 认证 cookies (可选)
    use_ai: bool = True              # 是否使用 AI 增强 (可选)
    environment: Optional[str] = None
    problem_type: Optional[str] = None
    services: Optional[List[str]] = None
    time_window: Optional[Dict[str, Any]] = None
    extra_clues: Optional[str] = None


class AnalysisFeedbackRequest(BaseModel):
    """人工反馈请求模型"""
    issue_key: Optional[str] = None
    jira_url: Optional[str] = None
    helpful: Optional[str] = None
    hit_root_cause: Optional[str] = None
    root_cause: Optional[str] = None
    note: Optional[str] = None
    predicted_causes: Optional[List[Dict[str, Any]]] = None


class AnalyzeTraceRequest(BaseModel):
    """链路 SQL 分析请求模型"""
    trace_id: str                    # Trace ID (必填)
    cookies: str                     # Trace API 认证 cookies (必填)
    date: Optional[str] = None       # 可选，如 "2026-04-23"，不提供则从 trace_id 推断


class FieldAnalysisRequest(BaseModel):
    """字段溯源分析请求模型"""
    project_name: str                 # 项目名（必填）
    api_path: Optional[str] = None    # 接口路径（与 method_name 至少填一个）
    method_name: Optional[str] = None # Java 方法名（与 api_path 至少填一个）
    field_path: Optional[str] = None  # 响应字段路径，如 "data.userId"


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "Fetch Trace Logs API",
        "version": "1.0.0",
        "endpoints": {
            "analyze": "POST /api/analyze",
            "analyze_jira": "POST /api/analyze-jira",
            "analyze_trace": "POST /api/analyze-trace",
            "analysis": "POST /api/analysis",
            "repos": "GET /api/repos"
        }
    }


@app.get("/api/repos")
async def list_repos():
    """获取可用的代码仓库列表"""
    repos = get_all_git_repos()
    result = []
    for key, url in repos.items():
        name = url.split('/')[-1].replace('.git', '')
        result.append({
            "key": key,
            "url": url,
            "name": name
        })
    return {"repos": result}


@app.post("/api/analyze")
async def analyze_api(req: AnalyzeRequest):
    """
    分析 API 接口的调用链

    Request Body:
    - api_path: API 路径
    - repo_key: 仓库键名 (可选，与 repo_url 二选一)
    - repo_url: Git 仓库 URL (可选，直接指定远程仓库)
    - ref: 分支/ commit (默认 main)
    - trace_id: (可选) Trace ID
    - date: (可选) 日期
    - cookies: (可选) Trace API 认证 cookies
    """
    try:
        if req.repo_url:
            analyzer = JavaCallChainAnalyzer(repo_url=req.repo_url, ref=req.ref)
        elif req.repo_key:
            analyzer = JavaCallChainAnalyzer(repo_key=req.repo_key)
        else:
            raise HTTPException(
                status_code=400,
                detail="repo_key or repo_url is required"
            )
        api_path = (req.api_path or '').strip()
        if api_path:
            result = analyzer.analyze(
                api_path,
                req.trace_id,
                req.date,
                req.cookies
            )
            return result

        if not req.trace_id:
            raise HTTPException(
                status_code=400,
                detail="未提供 API 路径，且无 Trace ID 可用于自动识别"
            )

        return analyzer.analyze_from_trace(
            req.trace_id,
            req.date,
            req.cookies
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"仓库不存在: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@app.post("/api/analyze-jira")
async def analyze_jira(req: AnalyzeJiraRequest):
    """
    分析 JIRA 问题并提供问题原因分析

    Request Body:
    - jira_url: JIRA URL (必填)
    - repo_key: (可选) 仓库键名，与 repo_urls 二选一
    - repo_url: Git 仓库 URL (可选，直接指定远程仓库) - 兼容旧版
    - repo_urls: (可选) Git 仓库 URL 列表，支持多仓库
    - api_path: (可选) API 路径
    - trace_id: (可选) Trace ID
    - trace_date: (可选) Trace 日期
    - cookies: (可选) Trace API 认证 cookies
    - use_ai: (可选) 是否使用 AI 增强
    """
    try:
        from api.analyzer.jira_analyzer import JiraAnalyzer

        # 如果提供了 api_paths 但没有任何仓库，返回错误
        if req.api_paths and not req.repo_key and not req.repo_url and not req.repo_urls:
            raise HTTPException(
                status_code=400,
                detail="repo_key or repo_url or repo_urls is required when api_paths is provided"
            )

        # 支持多仓库
        if req.repo_urls:
            analyzer = JiraAnalyzer(repo_urls=req.repo_urls)
        elif req.repo_url:
            analyzer = JiraAnalyzer(repo_url=req.repo_url, ref=req.ref)
        else:
            analyzer = JiraAnalyzer(repo_key=req.repo_key)
        result = analyzer.analyze(
            jira_url=req.jira_url,
            api_paths=req.api_paths,
            trace_id=req.trace_id,
            trace_date=req.trace_date,
            cookies=req.cookies,
            use_ai=req.use_ai,
            environment=req.environment,
            time_window=req.time_window,
            problem_type=req.problem_type,
            services=req.services,
            extra_clues=req.extra_clues
        )
        result["request_context"] = {
            "environment": req.environment,
            "time_window": req.time_window,
            "problem_type": req.problem_type,
            "services": req.services or [],
            "extra_clues": req.extra_clues,
            "trace_id": result.get("trace_id") or req.trace_id,
            "trace_id_source": result.get("trace_id_source", "manual" if req.trace_id else "none"),
            "trace_id_candidates": result.get("trace_id_candidates", []),
            "trace_id_note": result.get("trace_id_note"),
            "trace_date": req.trace_date
        }
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"仓库不存在: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"JIRA 分析失败: {str(e)}")


@app.post("/api/analyze-trace")
async def analyze_trace(req: AnalyzeTraceRequest):
    """
    分析链路中的 SQL 语句

    Request Body:
    - trace_id: Trace ID (必填)
    - cookies: Trace API 认证 cookies (必填)
    - date: (可选) 日期，不提供则从 trace_id 推断
    """
    try:
        from scripts.fetch_trace_souche import TraceFetcher
        from datetime import timezone, timedelta
        import re

        # 推断日期
        date = req.date
        if not date:
            match = re.match(r'^(\d{13})_', req.trace_id or '')
            if match:
                try:
                    ts = int(match.group(1)) / 1000
                    date = datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
                except Exception:
                    pass

        if not date:
            raise HTTPException(
                status_code=400,
                detail="未提供日期，且无法从 Trace ID 推断日期。请填写日期（YYYY-MM-DD）"
            )

        verify_ssl = os.getenv("TRACE_VERIFY_SSL", "false").lower() == "true"
        fetcher = TraceFetcher(cookies=req.cookies, verify_ssl=verify_ssl)
        trace_data = fetcher.fetch_trace(req.trace_id, date)

        if not trace_data:
            return {"sql_list": [], "trace_id": req.trace_id, "message": "未获取到 Trace 数据"}

        if trace_data.get('error'):
            return {"sql_list": [], "trace_id": req.trace_id, "error": trace_data['error']}

        # 提取 SQL 数据
        sql_entries = TraceFetcher.extract_sql_data(trace_data)

        sql_list = []
        seen = set()

        for entry in sql_entries[:20]:  # 最多处理20条
            rid = entry.get('rid')
            sql_text = None

            # 尝试获取详细 SQL（复用现有逻辑）
            if rid:
                try:
                    detail = fetcher.fetch_sql_detail(rid)
                    sql_text = fetcher.format_complete_sql(detail)
                except Exception:
                    sql_text = None

            # 如果没拿到详细 SQL，尝试从 entry 本身获取
            if not sql_text:
                raw_sql = entry.get('sql') or entry.get('path') or entry.get('statement')
                if raw_sql:
                    sql_text = ' '.join(str(raw_sql).split())

            if not sql_text or sql_text in seen:
                continue

            seen.add(sql_text)
            sql_list.append({
                "rid": rid,
                "service_name": entry.get('app') or entry.get('serviceName') or 'Unknown',
                "duration_ms": entry.get('cost') or entry.get('duration') or 0,
                "sql": sql_text,
                "is_batch": entry.get('is_batch', False),
                "result_size": entry.get('size', 0)
            })

        return {"sql_list": sql_list, "trace_id": req.trace_id, "total": len(sql_list)}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"链路 SQL 分析失败: {str(e)}")


@app.post("/api/analysis")
async def analyze_field(req: FieldAnalysisRequest):
    """
    字段溯源分析：根据项目名、接口路径（或方法名）、响应字段路径，
    追溯该字段的完整实现逻辑（JSON路径 → DTO → Service → Entity → DB → SQL）

    Request Body:
    - project_name: 项目名（必填）
    - api_path: 接口路径（与 method_name 至少填一个）
    - method_name: Java 方法名（与 api_path 至少填一个）
    - field_path: 响应字段 JSON 路径，如 "data.userId" 或 "data.list[0].name"
    """
    # 参数校验
    if not req.project_name or not req.project_name.strip():
        raise HTTPException(status_code=400, detail="project_name 为必填参数")
    if not req.api_path and not req.method_name:
        raise HTTPException(status_code=400, detail="api_path 或 method_name 至少需要提供一个")
    if not req.field_path or not req.field_path.strip():
        raise HTTPException(status_code=400, detail="field_path 为必填参数")

    try:
        tracer = FieldTracer(repo_key=req.project_name.strip())
        result = tracer.trace(
            api_path=req.api_path.strip() if req.api_path else None,
            method_name=req.method_name.strip() if req.method_name else None,
            field_path=req.field_path.strip()
        )
        if result.get('error') and not result.get('_partial'):
            raise HTTPException(status_code=404, detail=result['error'])
        return result

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"项目不存在: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"字段溯源分析失败: {str(e)}")


@app.post("/api/analysis-feedback")
async def save_analysis_feedback(req: AnalysisFeedbackRequest):
    """保存人工反馈，供后续评估和规则优化使用"""
    try:
        feedback_dir = os.getenv("ANALYSIS_FEEDBACK_DIR", "data")
        os.makedirs(feedback_dir, exist_ok=True)
        feedback_path = os.path.join(feedback_dir, "analysis_feedback.jsonl")
        record = req.model_dump()
        record["saved_at"] = datetime.now().isoformat(timespec="seconds")
        with open(feedback_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return {
            "success": True,
            "saved_at": record["saved_at"],
            "path": feedback_path
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存反馈失败: {str(e)}")


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok"}


def main():
    """启动服务"""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()

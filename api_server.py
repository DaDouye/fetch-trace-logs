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
from dotenv import load_dotenv

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# 加载 .env 文件
load_dotenv()

from api.analyze import JavaCallChainAnalyzer
from api.analyzer.claude_code_service import ClaudeCodeAnalysisError
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


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "Fetch Trace Logs API",
        "version": "1.0.0",
        "endpoints": {
            "analyze": "POST /api/analyze",
            "analyze_jira": "POST /api/analyze-jira",
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
    except ClaudeCodeAnalysisError as e:
        raise HTTPException(status_code=502, detail={
            "message": str(e),
            "analysis_engine": "claude_code_cli",
            "details": e.details
        })
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
    except ClaudeCodeAnalysisError as e:
        raise HTTPException(status_code=502, detail={
            "message": str(e),
            "analysis_engine": "claude_code_cli",
            "details": e.details
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"仓库不存在: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"JIRA 分析失败: {str(e)}")


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

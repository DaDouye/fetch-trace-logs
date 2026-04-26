#!/usr/bin/env python3
"""
FastAPI 服务入口
提供 REST API 接口用于分析 Java 接口调用链
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import os

from api.analyze import JavaCallChainAnalyzer
from config_manager import get_all_git_repos

app = FastAPI(
    title="Fetch Trace Logs API",
    description="Java 接口调用链分析服务",
    version="1.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    """分析请求模型"""
    api_path: str               # 如 "/v1/customerAction/saveOrUpdateCustomer"
    repo_key: str               # 如 "super_mario" (从 config 获取仓库路径)
    trace_id: Optional[str] = None   # 可选，用于获取运行时数据
    date: Optional[str] = None       # 可选，如 "2026-04-23"
    cookies: Optional[str] = None     # 可选，trace API 认证 cookies


class RepoInfo(BaseModel):
    """仓库信息模型"""
    key: str
    url: str
    name: str


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "Fetch Trace Logs API",
        "version": "1.0.0",
        "endpoints": {
            "analyze": "POST /api/analyze",
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
    - repo_key: 仓库键名
    - trace_id: (可选) Trace ID
    - date: (可选) 日期
    - cookies: (可选) Trace API 认证 cookies
    """
    try:
        analyzer = JavaCallChainAnalyzer(repo_key=req.repo_key)
        result = analyzer.analyze(
            req.api_path,
            req.trace_id,
            req.date,
            req.cookies
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"仓库不存在: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


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

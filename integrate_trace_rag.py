#!/usr/bin/env python3
"""
整合 trace 日志获取与 RAG 知识库分析的示例
"""

import json
import os
from datetime import datetime
from rag_log_analyzer import GitLogRAG
from scripts.fetch_trace_souche import TraceFetcher
import argparse
from config_manager import get_git_repo_url


def integrate_trace_with_rag(trace_id, date, repo_path=None, repo_key=None, cookies=None):
    """
    整合 trace 日志获取与 RAG 分析

    Args:
        trace_id (str): 链路追踪ID
        date (str): 日期 (YYYY-MM-DD)
        repo_path (str): 代码仓库路径
        repo_key (str): 配置文件中的仓库键名
        cookies (str): 用于认证的cookies
    """

    # 如果提供了repo_key，则从配置中获取仓库路径
    if repo_key:
        repo_url = get_git_repo_url(repo_key)
        if not repo_url:
            raise ValueError(f"在配置中找不到键名为 '{repo_key}' 的Git仓库地址")
        # 如果是远程仓库URL，GitLogRAG内部会处理克隆
        effective_repo_path = repo_url
    elif repo_path:
        effective_repo_path = repo_path
    else:
        raise ValueError("必须提供 repo_path 或 repo_key 参数")

    print(f"正在获取链路追踪数据: {trace_id}")

    # 使用现有的TraceFetcher获取链路数据
    fetcher = TraceFetcher(cookies=cookies, verify_ssl=False)

    # 获取完整的链路数据
    trace_data = fetcher.fetch_trace(trace_id, date)

    # 提取SQL相关的错误信息
    sql_data = TraceFetcher.extract_sql_data(trace_data)

    print(f"发现 {len(sql_data)} 个SQL相关条目")

    # 为每个SQL条目获取详细信息
    sql_details = []
    for i, sql_entry in enumerate(sql_data, 1):
        rid = sql_entry.get("rid") or sql_entry.get("id")
        if rid:
            print(f"  [{i}/{len(sql_data)}] 正在获取RID详情: {rid}")
            detail = fetcher.fetch_sql_detail(rid)
            formatted_sql = TraceFetcher.format_complete_sql(detail)

            if formatted_sql:
                detail = {"sql": formatted_sql}
            else:
                detail = {"sql": None}

            sql_details.append({
                "rid": rid,
                "detail": detail
            })

    # 保存trace数据到临时文件，供RAG系统分析
    current_time = datetime.now().strftime("%Y%m%d%H%M%S")
    trace_file_path = f"./trace_{trace_id}_{current_time}_for_rag.json"

    trace_summary = {
        "summary": {
            "trace_id": trace_id,
            "date": date,
            "sql_count": len(sql_data),
            "detail_count": len([d for d in sql_details if d["detail"] is not None]),
            "generated_at": datetime.now().isoformat()
        },
        "sql_details": sql_details,
        "full_trace_data": trace_data
    }

    with open(trace_file_path, 'w', encoding='utf-8') as f:
        json.dump(trace_summary, f, indent=2, ensure_ascii=False)

    print(f"链路数据已保存至: {trace_file_path}")

    # 使用RAG系统分析trace数据
    print("\n开始使用RAG系统分析trace数据...")

    # 根据是否有repo_key创建RAG系统实例
    if repo_key:
        rag_system = GitLogRAG(repo_key=repo_key, log_file_path=trace_file_path)
    else:
        rag_system = GitLogRAG(repo_path=effective_repo_path, log_file_path=trace_file_path)

    # 处理仓库和日志
    rag_system.process_repo_and_logs()

    # 分析可能的性能问题或错误
    for detail in sql_details:
        if detail["detail"]["sql"]:
            query = f"""
            分析以下SQL查询的性能问题：
            {detail["detail"]["sql"]}

            请提供优化建议，包括可能的索引策略、查询重构等。
            """

            print(f"\n分析SQL: {detail['detail']['sql'][:100]}...")
            result = rag_system.analyze_log_issue(query)
            print("分析结果:", result["answer"][:500] + "..." if len(result["answer"]) > 500 else result["answer"])

    return trace_summary


def analyze_existing_trace_file(trace_file_path, repo_path=None, repo_key=None):
    """
    分析已有的trace文件

    Args:
        trace_file_path (str): 已有trace文件的路径
        repo_path (str): 代码仓库路径
        repo_key (str): 配置文件中的仓库键名
    """

    # 如果提供了repo_key，则从配置中获取仓库路径
    if repo_key:
        repo_url = get_git_repo_url(repo_key)
        if not repo_url:
            raise ValueError(f"在配置中找不到键名为 '{repo_key}' 的Git仓库地址")
        # 如果是远程仓库URL，GitLogRAG内部会处理克隆
        effective_repo_path = repo_url
    elif repo_path:
        effective_repo_path = repo_path
    else:
        raise ValueError("必须提供 repo_path 或 repo_key 参数")

    print(f"正在分析已有的trace文件: {trace_file_path}")

    # 读取trace文件
    with open(trace_file_path, 'r', encoding='utf-8') as f:
        trace_data = json.load(f)

    # 根据是否有repo_key创建RAG系统实例
    if repo_key:
        rag_system = GitLogRAG(repo_key=repo_key, log_file_path=trace_file_path)
    else:
        rag_system = GitLogRAG(repo_path=effective_repo_path, log_file_path=trace_file_path)

    # 处理仓库和日志
    rag_system.process_repo_and_logs()

    # 根据trace数据生成分析查询
    summary_info = trace_data.get("summary", {})
    sql_details = trace_data.get("sql_details", [])

    print(f"分析 {len(sql_details)} 个SQL详情")

    # 分析第一个SQL作为示例
    if sql_details:
        first_sql = sql_details[0]
        if first_sql.get("detail", {}).get("sql"):
            query = f"""
            对于链路ID {summary_info.get('trace_id', 'unknown')} 中的以下SQL查询：
            {first_sql["detail"]["sql"]}

            请分析可能存在的性能瓶颈或问题，并提出修复方案。
            同时，请检查代码库中处理此类型查询的相关代码。
            """

            print(f"\n分析SQL: {first_sql['detail']['sql'][:100]}...")
            result = rag_system.analyze_log_issue(query)
            print("AI分析结果:")
            print(result["answer"])

            # 提供具体的代码定位
            print("\n相关代码片段:")
            relevant_codes = rag_system.search_similar_code(first_sql["detail"]["sql"], k=3)
            for i, code in enumerate(relevant_codes, 1):
                print(f"{i}. {code[:200]}...")

    return trace_data


def main():
    parser = argparse.ArgumentParser(description="集成Trace获取与RAG分析")
    parser.add_argument("--trace-id", help="链路追踪ID")
    parser.add_argument("--date", help="日期 (YYYY-MM-DD)")
    parser.add_argument("--repo-key", help="配置文件中的仓库键名（优先级高于repo-path）")
    parser.add_argument("--repo-path", help="代码仓库路径")
    parser.add_argument("--trace-file", help="已有trace文件路径（可选）")
    parser.add_argument("--cookies", help="认证cookies")

    args = parser.parse_args()

    if args.repo_key and args.repo_path:
        print("警告: 同时提供了 --repo-key 和 --repo-path，使用 --repo-key")

    if args.trace_file:
        # 分析已有的trace文件
        if args.repo_key:
            analyze_existing_trace_file(args.trace_file, repo_key=args.repo_key)
        else:
            if not args.repo_path:
                print("请提供 --repo-path 或 --repo-key")
                parser.print_help()
                return
            analyze_existing_trace_file(args.trace_file, repo_path=args.repo_path)
    elif args.trace_id and args.date:
        # 获取新的trace数据并分析
        if args.repo_key:
            integrate_trace_with_rag(args.trace_id, args.date, repo_key=args.repo_key, cookies=args.cookies)
        else:
            if not args.repo_path:
                print("请提供 --repo-path 或 --repo-key")
                parser.print_help()
                return
            integrate_trace_with_rag(args.trace_id, args.date, repo_path=args.repo_path, cookies=args.cookies)
    else:
        print("请提供 --trace-id 和 --date，或提供 --trace-file")
        parser.print_help()


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
综合工具入口脚本
提供对所有功能的统一访问接口
"""

import argparse
import subprocess
import sys
import os


def run_fetch_trace(args):
    """运行链路追踪获取功能"""
    cmd = [
        sys.executable, "scripts/fetch_trace_souche.py",
        "--trace-id", args.trace_id,
        "--date", args.date
    ]

    if args.cookies:
        cmd.extend(["--cookies", args.cookies])

    if args.output_dir:
        cmd.extend(["--output-dir", args.output_dir])

    subprocess.run(cmd)


def run_rag_analysis(args):
    """运行 RAG 分析功能"""
    # 检查是否需要使用集成trace分析
    if hasattr(args, 'trace_file') and args.trace_file:
        cmd = [sys.executable, "integrate_trace_rag.py"]

        # 优先使用repo_key，如果没有提供再使用repo_path
        if hasattr(args, 'repo_key') and args.repo_key:
            cmd.extend(["--repo-key", args.repo_key])
        elif hasattr(args, 'repo_path') and args.repo_path:
            cmd.extend(["--repo-path", args.repo_path])
        else:
            print("错误: 必须提供 --repo-key 或 --repo-path")
            return

        cmd.extend(["--trace-file", args.trace_file])
    else:
        cmd = [sys.executable, "rag_log_analyzer.py"]

        # 优先使用repo_key，如果没有提供再使用repo_path
        if hasattr(args, 'repo_key') and args.repo_key:
            cmd.extend(["--repo-key", args.repo_key])
        elif hasattr(args, 'repo_path') and args.repo_path:
            cmd.extend(["--repo-path", args.repo_path])
        else:
            print("错误: 必须提供 --repo-key 或 --repo-path")
            return

        if hasattr(args, 'log_file') and args.log_file:
            cmd.extend(["--log-file", args.log_file])

    subprocess.run(cmd)


def run_jira_fetch(args):
    """运行 JIRA 获取功能"""
    cmd = [sys.executable, "scripts/jira_fetcher.py", args.issue_key]
    subprocess.run(cmd)


def run_demo(args):
    """运行演示"""
    subprocess.run([sys.executable, "demo_rag.py"])


def main():
    parser = argparse.ArgumentParser(description="综合工具集 - 链路追踪、RAG分析、JIRA获取")
    subparsers = parser.add_subparsers(dest="command", help="可用的命令")

    # 链路追踪子命令
    trace_parser = subparsers.add_parser("trace", help="获取链路追踪数据")
    trace_parser.add_argument("--trace-id", required=True, help="链路追踪ID")
    trace_parser.add_argument("--date", required=True, help="日期 (YYYY-MM-DD)")
    trace_parser.add_argument("--cookies", help="认证cookies")
    trace_parser.add_argument("--output-dir", help="输出目录")

    # RAG分析子命令
    rag_parser = subparsers.add_parser("rag", help="RAG知识库分析")
    rag_parser.add_argument("--repo-key", help="配置文件中的仓库键名（优先级高于repo-path）")
    rag_parser.add_argument("--repo-path", help="代码仓库路径")
    rag_parser.add_argument("--log-file", help="日志文件路径")
    rag_parser.add_argument("--trace-file", help="已有的trace数据文件路径")

    # JIRA获取子命令
    jira_parser = subparsers.add_parser("jira", help="获取JIRA问题详情")
    jira_parser.add_argument("issue_key", help="JIRA问题键")

    # 演示子命令
    demo_parser = subparsers.add_parser("demo", help="运行RAG演示")

    args = parser.parse_args()

    if args.command == "trace":
        run_fetch_trace(args)
    elif args.command == "rag":
        run_rag_analysis(args)
    elif args.command == "jira":
        run_jira_fetch(args)
    elif args.command == "demo":
        run_demo(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
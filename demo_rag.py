#!/usr/bin/env python3
"""
RAG 系统使用示例
"""

import os
from rag_log_analyzer import GitLogRAG
from config_manager import get_git_repo_url, get_all_git_repos


def demo_basic_usage():
    """基本使用示例"""
    print("=== RAG 系统基本使用示例 ===\n")

    print("检测配置中的Git仓库:")
    repos = get_all_git_repos()
    if repos:
        print("在配置中找到以下Git仓库:")
        for key, url in repos.items():
            print(f"  - {key}: {url}")
        print()

    use_config = input("是否使用配置中的仓库? (y/n): ").strip().lower()

    if use_config == 'y':
        repo_key = input("请输入仓库键名 (例如: super_mario): ").strip()
        repo_url = get_git_repo_url(repo_key)
        if not repo_url:
            print(f"错误: 在配置中找不到键名为 '{repo_key}' 的Git仓库地址")
            return
        print(f"将使用配置中的仓库: {repo_url}")
    else:
        # 用户直接输入路径
        repo_path = input("请输入您的 Git 仓库路径: ").strip()

        if not os.path.exists(repo_path):
            print(f"错误: 仓库路径 {repo_path} 不存在")
            return

    # 创建 RAG 系统实例
    print("初始化 RAG 系统...")
    if use_config == 'y':
        rag_system = GitLogRAG(repo_key=repo_key)  # 使用配置键
    else:
        rag_system = GitLogRAG(repo_path=repo_path)  # 使用路径

    # 加载代码库
    print("加载代码库...")
    code_docs = rag_system.load_codebase()
    print(f"加载了 {len(code_docs)} 个代码文件\n")

    # 模拟一些日志内容（实际使用中可以从文件加载）
    sample_logs = [
        "ERROR: Database connection failed",
        "CRITICAL: Memory overflow in processing module",
        "WARNING: Slow query detected in user service"
    ]

    print("处理示例日志...")
    for log in sample_logs:
        print(f"- {log}")

    print("\n创建向量存储...")
    from langchain.schema import Document
    all_docs = [Document(page_content=doc, metadata={"source": "codebase"}) for doc in code_docs] + \
               [Document(page_content=log, metadata={"source": "logs"}) for log in sample_logs]

    rag_system.create_vector_store(all_docs)

    print("构建问答系统...")
    rag_system.build_qa_system()

    print("\n系统准备就绪！现在可以分析问题了。")


def demo_trace_integration():
    """Trace 集成示例"""
    print("\n=== Trace 集成示例 ===\n")

    print("该示例展示了如何将 trace 日志获取与 RAG 分析相结合:")
    print("1. 使用现有的 fetch_trace_souche.py 获取链路数据")
    print("2. 将获取的数据输入到 RAG 系统进行分析")
    print("3. 获得 AI 驱动的问题定位和修复建议")

    print("\n使用命令示例:")
    print("python integrate_trace_rag.py --trace-id YOUR_TRACE_ID --date 2023-01-01 --repo-key super_mario")
    print("或")
    print("python integrate_trace_rag.py --trace-id YOUR_TRACE_ID --date 2023-01-01 --repo-path /path/to/repo")


def demo_custom_analysis():
    """自定义分析示例"""
    print("\n=== 自定义分析示例 ===\n")

    print("检测配置中的Git仓库:")
    repos = get_all_git_repos()
    if repos:
        print("在配置中找到以下Git仓库:")
        for key, url in repos.items():
            print(f"  - {key}: {url}")
        print()

    use_config = input("是否使用配置中的仓库? (y/n): ").strip().lower()

    if use_config == 'y':
        repo_key = input("请输入仓库键名 (例如: super_mario): ").strip()
        repo_url = get_git_repo_url(repo_key)
        if not repo_url:
            print(f"错误: 在配置中找不到键名为 '{repo_key}' 的Git仓库地址")
            return
        print(f"将使用配置中的仓库: {repo_url}")
    else:
        repo_path = input("请输入您的 Git 仓库路径: ").strip()

        if not os.path.exists(repo_path):
            print(f"错误: 仓库路径 {repo_path} 不存在")
            return

    # 创建 RAG 系统
    if use_config == 'y':
        rag_system = GitLogRAG(repo_key=repo_key)  # 使用配置键
    else:
        rag_system = GitLogRAG(repo_path=repo_path)  # 使用路径

    # 这里可以指定一个真实的日志文件
    log_content = """
    ERROR:root:Exception occurred in API endpoint
    Traceback (most recent call last):
      File "app.py", line 123, in handle_request
        result = process_data(user_input)
      File "utils.py", line 45, in process_data
        return json.loads(user_input)
      File "/usr/local/lib/python3.8/json/__init__.py", line 341, in loads
        raise JSONDecodeError("Expecting value", s, err.value) from None
    json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
    """

    # 将日志写入临时文件
    with open("./temp_log.txt", "w") as f:
        f.write(log_content)

    # 更新 rag_system 的日志文件路径
    rag_system.log_file_path = "./temp_log.txt"

    # 处理仓库和日志
    print("处理仓库和日志...")
    rag_system.process_repo_and_logs()

    # 分析问题
    print("分析日志问题...")
    problem_description = """
    应用程序在处理用户输入时发生 JSON 解析错误。
    错误信息显示 'Expecting value: line 1 column 1 (char 0)'，
    表明尝试解析空字符串或无效 JSON。
    请分析可能的代码问题并提供修复建议。
    """

    result = rag_system.analyze_log_issue(problem_description)

    print("\nAI 分析结果:")
    print("=" * 50)
    print(result["answer"])
    print("=" * 50)

    # 清理临时文件
    os.remove("./temp_log.txt")


if __name__ == "__main__":
    print("RAG 系统使用示例")
    print("请选择要运行的示例:")
    print("1. 基本使用示例")
    print("2. Trace 集成示例")
    print("3. 自定义分析示例")

    choice = input("\n请输入选择 (1-3): ").strip()

    if choice == "1":
        demo_basic_usage()
    elif choice == "2":
        demo_trace_integration()
    elif choice == "3":
        demo_custom_analysis()
    else:
        print("无效选择")
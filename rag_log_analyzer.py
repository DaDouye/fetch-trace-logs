#!/usr/bin/env python3
"""
基于 GitHub/Git 项目代码 + 日志文件的 RAG 知识库系统
用于分析日志并自动定位代码、分析问题、给出修复方案
"""

import os
import json
import re
from api.analyzer.repository_context import resolve_local_code_dir
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain_community.llms import HuggingFaceHub
from sentence_transformers import SentenceTransformer
import pickle
from pathlib import Path
import logging
from config_manager import get_git_repo_url, load_config


class GitLogRAG:
    def __init__(self, repo_path=None, repo_key=None, log_file_path=None, model_name="sentence-transformers/all-MiniLM-L6-v2"):
        """
        初始化 RAG 系统

        Args:
            repo_path (str): 本地代码目录
            repo_key (str): 配置文件中的代码目录键名
            log_file_path (str): 日志文件路径
            model_name (str): 嵌入模型名称
        """
        self.local_code_context = resolve_local_code_dir(repo_path=repo_path, repo_key=repo_key)
        self.repo_path = self.local_code_context.local_path

        self.log_file_path = log_file_path
        self.model_name = model_name
        self.embeddings = HuggingFaceEmbeddings(model_name=model_name)
        self.vector_store = None
        self.qa_chain = None
        self.setup_logging()

    def setup_logging(self):
        """设置日志记录"""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def load_codebase(self):
        """加载代码库内容"""
        self.logger.info("Loading codebase...")
        code_content = []
        allowed_exts = {'.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h', '.html', '.css', '.json', '.yaml', '.yml', '.md', '.txt'}

        for file_path in Path(self.repo_path).rglob('*'):
            if not file_path.is_file() or file_path.suffix.lower() not in allowed_exts:
                continue
            if '.git' in file_path.parts or 'node_modules' in file_path.parts:
                continue
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                rel_path = file_path.relative_to(self.repo_path)
                code_content.append(f"File: {rel_path}\n\n{content}")
            except Exception as e:
                self.logger.warning(f"Could not read file {file_path}: {e}")

        self.logger.info(f"Loaded {len(code_content)} files from codebase")
        return code_content

    def load_logs(self, log_file_path=None):
        """加载日志文件内容"""
        if log_file_path:
            self.log_file_path = log_file_path

        if not self.log_file_path or not os.path.exists(self.log_file_path):
            self.logger.warning("Log file path not provided or file does not exist")
            return []

        self.logger.info(f"Loading log file: {self.log_file_path}")
        with open(self.log_file_path, 'r', encoding='utf-8') as f:
            log_content = f.read()

        # 将日志按行分割成块，每块代表一条日志
        log_entries = log_content.split('\n')

        # 过滤出可能包含错误信息的日志条目
        error_log_entries = []
        for entry in log_entries:
            if any(keyword in entry.lower() for keyword in ['error', 'exception', 'traceback', 'failed', 'critical']):
                error_log_entries.append(f"Log Entry:\n{entry}")

        self.logger.info(f"Loaded {len(error_log_entries)} error-related log entries")
        return error_log_entries

    def create_vector_store(self, documents):
        """创建向量存储"""
        self.logger.info("Creating vector store...")

        # 使用递归字符分割器将文档分割成块
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", " ", ""]
        )

        texts = text_splitter.split_documents(documents)

        # 创建FAISS向量存储
        self.vector_store = FAISS.from_documents(texts, self.embeddings)
        self.logger.info("Vector store created successfully")

    def build_qa_system(self, llm_model="google/flan-t5-base"):
        """构建问答系统"""
        self.logger.info("Building QA system...")

        # 使用本地模型进行推理，避免网络问题
        from langchain_huggingface import HuggingFacePipeline

        llm = HuggingFacePipeline.from_model_id(
            model_id=llm_model,
            task="text2text-generation",
            pipeline_kwargs={"temperature": 0.1, "max_new_tokens": 512}
        )

        # 创建提示模板，专门用于代码和日志分析
        prompt_template = """
        你是一个专业的软件开发和调试助手。
        请根据提供的上下文信息，分析日志中的错误，并定位可能的代码问题。

        日志信息：
        {context}

        问题：
        {question}

        请按照以下格式回答：
        1. 错误分析：描述错误的可能原因
        2. 代码定位：指出最可能出错的文件和代码行
        3. 解决方案：提供具体的修复建议
        4. 相关代码：如果上下文中有相关代码，请引用

        回答：
        """

        PROMPT = PromptTemplate(
            template=prompt_template,
            input_variables=["context", "question"]
        )

        # 创建检索问答链
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=self.vector_store.as_retriever(search_kwargs={"k": 5}),
            return_source_documents=True,
            chain_type_kwargs={"prompt": PROMPT}
        )

        self.logger.info("QA system built successfully")

    def process_repo_and_logs(self):
        """处理整个仓库和日志文件"""
        # 加载代码库和日志
        code_docs = self.load_codebase()
        log_docs = self.load_logs()

        # 合并所有文档
        all_docs = code_docs + log_docs

        # 创建Document对象（假设我们使用langchain Document类）
        from langchain.schema import Document
        documents = [Document(page_content=doc, metadata={"source": "codebase"}) for doc in code_docs] + \
                   [Document(page_content=log, metadata={"source": "logs"}) for log in log_docs]

        # 创建向量存储
        self.create_vector_store(documents)

        # 构建问答系统
        self.build_qa_system()

    def analyze_log_issue(self, log_message):
        """分析日志中的问题并返回解决方案"""
        if not self.qa_chain:
            raise ValueError("QA system not built yet. Call process_repo_and_logs() first.")

        question = f"""
        根据提供的代码库和日志信息，请分析以下错误日志：

        {log_message}

        请详细解释错误的原因，定位可能的代码位置，并提供修复建议。
        """

        result = self.qa_chain({"query": question})

        return {
            "answer": result['result'],
            "source_documents": [doc.page_content for doc in result['source_documents']]
        }

    def save_index(self, index_path="./vector_store_index"):
        """保存索引以便后续使用"""
        if self.vector_store:
            self.vector_store.save_local(index_path)
            self.logger.info(f"Index saved to {index_path}")

    def load_index(self, index_path="./vector_store_index"):
        """加载已保存的索引"""
        self.vector_store = FAISS.load_local(
            index_path,
            self.embeddings,
            allow_dangerous_deserialization=True
        )
        self.logger.info(f"Index loaded from {index_path}")

    def search_similar_code(self, query, k=5):
        """搜索与查询相似的代码"""
        if not self.vector_store:
            raise ValueError("Vector store not created yet.")

        docs = self.vector_store.similarity_search(query, k=k)
        return [doc.page_content for doc in docs]


def main():
    """主函数 - 示例用法"""
    import argparse

    parser = argparse.ArgumentParser(description="Git Log RAG Analyzer")
    parser.add_argument("--repo-key", help="配置文件中的仓库键名（优先级高于repo-path）")
    parser.add_argument("--repo-path", help="Git仓库路径")
    parser.add_argument("--log-file", required=True, help="Path to the log file")
    parser.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2", help="Embedding model name")
    parser.add_argument("--index-path", default="./vector_store_index", help="Path to save/load index")

    args = parser.parse_args()

    # 根据是否有repo_key来决定如何初始化
    if args.repo_key:
        # 使用配置键初始化
        rag_system = GitLogRAG(repo_key=args.repo_key, log_file_path=args.log_file, model_name=args.model)
    elif args.repo_path:
        # 使用路径初始化
        rag_system = GitLogRAG(repo_path=args.repo_path, log_file_path=args.log_file, model_name=args.model)
    else:
        print("错误: 必须提供 --repo-key 或 --repo-path")
        parser.print_help()
        return

    # 处理仓库和日志
    print("Processing repository and logs...")
    rag_system.process_repo_and_logs()

    # 保存索引
    rag_system.save_index(args.index_path)

    # 示例：分析特定错误日志
    sample_error_log = """
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

    print("\nAnalyzing sample error log:")
    print(sample_error_log)

    result = rag_system.analyze_log_issue(sample_error_log)

    print("\nAnalysis Result:")
    print(result["answer"])

    # 显示源文档
    print(f"\nTop {len(result['source_documents'])} relevant code/log snippets:")
    for i, doc in enumerate(result['source_documents'], 1):
        print(f"\n{i}. {doc[:200]}...")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
LightRAG Indexer Module - Lightweight RAG using FAISS + LangChain

Provides incremental indexing and similarity search for:
- JIRA issues
- Trace data (SQL, API paths)
- Code search results
"""

import os
import json
import ssl
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

try:
    from langchain_community.vectorstores import FAISS
    from langchain.schema import Document
except ImportError:
    FAISS = None
    Document = None

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    try:
        from langchain_community.embeddings import HuggingFaceEmbeddings
    except ImportError:
        HuggingFaceEmbeddings = None


class LightRAGIndexer:
    """
    Lightweight RAG indexer using FAISS vector store.

    Supports:
    - Incremental indexing of JIRA issues, Trace data, and code
    - Similarity search for context retrieval
    - Local filesystem storage
    """

    def __init__(self, storage_path: str = "./lightrag_data"):
        """
        Initialize LightRAG indexer.

        Args:
            storage_path: Directory to store vector index files
        """
        self.storage_path = storage_path
        self.embedding_model = os.getenv("MINIMAXI_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        self.embedding_api_url = os.getenv("MINIMAXI_EMBEDDING_API_URL", "https://api.minimaxi.com/embedding")
        self.trust_local_index = os.getenv("LIGHTRAG_TRUST_LOCAL_INDEX", "false").lower() == "true"

        # Initialize embeddings (using HuggingFace local model as primary)
        if HuggingFaceEmbeddings:
            self.embeddings = HuggingFaceEmbeddings(model_name=self.embedding_model)
        else:
            self.embeddings = None

        self.vector_store = None
        self._load_or_create_store()

    def _load_or_create_store(self):
        """Load existing vector store or create new one"""
        os.makedirs(self.storage_path, exist_ok=True)
        index_file = os.path.join(self.storage_path, "faiss_index")

        if os.path.exists(index_file) and self.embeddings and self.trust_local_index:
            try:
                self.vector_store = FAISS.load_local(
                    index_file,
                    self.embeddings,
                    allow_dangerous_deserialization=True
                )
                print(f"[LightRAG] Loaded existing index from {index_file}")
            except Exception as e:
                print(f"[LightRAG] Failed to load index: {e}, creating new one")
                self.vector_store = None
        elif os.path.exists(index_file) and self.embeddings:
            print("[LightRAG] Existing index skipped. Set LIGHTRAG_TRUST_LOCAL_INDEX=true to load it.")

        if self.vector_store is None and self.embeddings:
            # Create empty vector store with a placeholder
            self.vector_store = FAISS.from_texts(
                ["__placeholder__"],
                self.embeddings,
                metadatas=[{"source": "init"}]
            )
            # Remove the placeholder document if it exists
            try:
                self.vector_store.delete(["__placeholder__"])
            except ValueError:
                pass  # Ignore if already deleted

    def _ensure_vector_store(self):
        """Ensure vector store is available"""
        if self.vector_store is None and self.embeddings:
            self._load_or_create_store()
        return self.vector_store is not None and self.embeddings is not None

    def index_jira_issue(self, issue_key: str, content: Dict[str, Any]) -> bool:
        """
        Index a JIRA issue.

        Args:
            issue_key: JIRA issue key (e.g., 'PROJ-123')
            content: JIRA issue content with summary, description, customfield_19900, keywords

        Returns:
            True if indexing succeeded
        """
        if not self._ensure_vector_store():
            return False

        try:
            texts = []
            metadatas = []

            # Combine all text fields
            text_parts = []
            if content.get("summary"):
                text_parts.append(content["summary"])
            if content.get("description"):
                text_parts.append(content["description"])
            if content.get("customfield_19900"):
                text_parts.append(content["customfield_19900"])

            # Add keywords
            keywords = content.get("keywords", {})
            for key, values in keywords.items():
                if values:
                    text_parts.extend(values)

            if not text_parts:
                print(f"[LightRAG] No text content to index for {issue_key}")
                return False

            text = "\n".join(text_parts)
            texts.append(text)
            metadatas.append({
                "source": "jira",
                "issue_key": issue_key,
                "type": "jira_issue"
            })

            self.vector_store.add_texts(texts, metadatas=metadatas)
            self._save_index()
            print(f"[LightRAG] Indexed JIRA issue: {issue_key}")
            return True

        except Exception as e:
            print(f"[LightRAG] Failed to index JIRA issue {issue_key}: {e}")
            return False

    def index_trace_data(self, trace_id: str, data: Dict[str, Any]) -> bool:
        """
        Index trace data including SQL statements and API paths.

        Args:
            trace_id: Trace ID
            data: Trace data with sql_entries, api_paths, etc.

        Returns:
            True if indexing succeeded
        """
        if not self._ensure_vector_store():
            return False

        try:
            texts = []
            metadatas = []

            # Index SQL statements
            sql_entries = data.get("sql_entries", [])
            for i, sql in enumerate(sql_entries):
                if isinstance(sql, dict):
                    sql_text = sql.get("sql", "") or sql.get("path", "")
                else:
                    sql_text = str(sql)
                if sql_text:
                    texts.append(sql_text)
                    metadatas.append({
                        "source": "trace",
                        "trace_id": trace_id,
                        "type": "sql",
                        "index": i
                    })

            # Index API paths
            api_paths = data.get("api_paths", [])
            for path in api_paths:
                if path:
                    texts.append(path)
                    metadatas.append({
                        "source": "trace",
                        "trace_id": trace_id,
                        "type": "api_path"
                    })

            if not texts:
                print(f"[LightRAG] No trace content to index for {trace_id}")
                return False

            self.vector_store.add_texts(texts, metadatas=metadatas)
            self._save_index()
            print(f"[LightRAG] Indexed trace data: {trace_id} ({len(texts)} items)")
            return True

        except Exception as e:
            print(f"[LightRAG] Failed to index trace data {trace_id}: {e}")
            return False

    def index_code_files(self, files: List[Dict[str, Any]]) -> bool:
        """
        Index code search results.

        Args:
            files: List of file results from code search

        Returns:
            True if indexing succeeded
        """
        if not self._ensure_vector_store():
            return False

        try:
            texts = []
            metadatas = []

            for file in files:
                file_path = file.get("file_path", "")
                matches = file.get("matches", [])

                # Create text from matches
                for match in matches[:5]:  # Limit matches per file
                    line_num = match.get("line_number", 0)
                    content = match.get("content", "")
                    if content:
                        texts.append(content)
                        metadatas.append({
                            "source": "code",
                            "file_path": file_path,
                            "line_number": line_num,
                            "type": "code_match"
                        })

            if not texts:
                print(f"[LightRAG] No code content to index")
                return False

            self.vector_store.add_texts(texts, metadatas=metadatas)
            self._save_index()
            print(f"[LightRAG] Indexed {len(files)} code files ({len(texts)} matches)")
            return True

        except Exception as e:
            print(f"[LightRAG] Failed to index code files: {e}")
            return False

    def query(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Query the vector store for similar documents.

        Args:
            query_text: Query text
            top_k: Number of results to return

        Returns:
            List of retrieved documents with metadata
        """
        if not self._ensure_vector_store():
            return []

        try:
            docs_and_scores = self.vector_store.similarity_search_with_score(
                query_text,
                k=top_k
            )

            results = []
            for doc, score in docs_and_scores:
                # Filter out dummy/empty documents and placeholders
                content = doc.page_content.strip()
                if content and content != "" and content != "__placeholder__":
                    results.append({
                        "content": content,
                        "metadata": doc.metadata,
                        "score": float(score)
                    })

            print(f"[LightRAG] Query '{query_text[:50]}...' returned {len(results)} results")
            return results

        except Exception as e:
            print(f"[LightRAG] Query failed: {e}")
            return []

    def query_by_type(self, query_text: str, source_type: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Query for similar documents of a specific type.

        Args:
            query_text: Query text
            source_type: Type filter ('jira', 'trace', 'code')
            top_k: Number of results to return

        Returns:
            List of filtered results
        """
        all_results = self.query(query_text, top_k * 2)  # Over-fetch to allow filtering
        filtered = [r for r in all_results if r["metadata"].get("source") == source_type]
        return filtered[:top_k]

    def get_context_for_analysis(self, jira_content: Dict[str, Any], code_context: Dict[str, Any]) -> str:
        """
        Get enhanced context for AI analysis by querying relevant documents.

        Args:
            jira_content: JIRA issue content
            code_context: Code search results

        Returns:
            Context string to inject into AI prompt
        """
        context_parts = []

        # Build query text from JIRA content
        query_parts = []
        if jira_content.get("summary"):
            query_parts.append(jira_content["summary"])
        if jira_content.get("description"):
            query_parts.append(jira_content["description"])
        if jira_content.get("customfield_19900"):
            query_parts.append(jira_content["customfield_19900"])
        query_text = " ".join(query_parts)

        if query_text:
            # Get similar JIRA issues
            jira_results = self.query_by_type(query_text, "jira", top_k=3)
            if jira_results:
                context_parts.append("### 类似的JIRA问题案例:")
                for r in jira_results:
                    ctx = r["content"][:300] if len(r["content"]) > 300 else r["content"]
                    context_parts.append(f"- [{r['metadata'].get('issue_key', 'unknown')}]: {ctx}")

            # Get related code
            code_results = self.query_by_type(query_text, "code", top_k=3)
            if code_results:
                context_parts.append("\n### 相关代码:")
                for r in code_results:
                    fp = r["metadata"].get("file_path", "unknown")
                    ln = r["metadata"].get("line_number", "?")
                    context_parts.append(f"- {fp}:{ln} - {r['content'][:150]}")

            # Get related trace patterns
            trace_results = self.query_by_type(query_text, "trace", top_k=2)
            if trace_results:
                context_parts.append("\n### 相关的Trace模式:")
                for r in trace_results:
                    ctx = r["content"][:200] if len(r["content"]) > 200 else r["content"]
                    context_parts.append(f"- {ctx}")

        return "\n".join(context_parts) if context_parts else ""

    def _save_index(self):
        """Save vector store to disk"""
        if self.vector_store:
            try:
                index_file = os.path.join(self.storage_path, "faiss_index")
                self.vector_store.save_local(index_file)
                print(f"[LightRAG] Index saved to {index_file}")
            except Exception as e:
                print(f"[LightRAG] Failed to save index: {e}")

    def clear_index(self):
        """Clear all indexed data"""
        self.vector_store = None
        index_file = os.path.join(self.storage_path, "faiss_index")
        if os.path.exists(index_file):
            import shutil
            shutil.rmtree(index_file)
            print(f"[LightRAG] Index cleared")

    def get_stats(self) -> Dict[str, int]:
        """Get index statistics"""
        if not self.vector_store:
            return {"total_documents": 0}

        try:
            # Get all documents and filter out placeholders
            all_docs = list(self.vector_store.docstore._docstore.values())
            doc_count = sum(1 for d in all_docs if d.page_content != "__placeholder__")
            return {"total_documents": doc_count}
        except Exception:
            return {"total_documents": 0}


def main():
    """Test LightRAG indexer"""
    indexer = LightRAGIndexer()

    # Test indexing
    test_jira = {
        "summary": "用户无法下单",
        "description": "点击下单按钮后提示系统错误",
        "customfield_19900": "故障时间: 2024-01-01",
        "keywords": {"class_names": ["OrderService"]}
    }

    indexer.index_jira_issue("TEST-123", test_jira)

    # Test query
    results = indexer.query("订单 下单 失败", top_k=5)
    print(f"Query results: {len(results)}")
    for r in results:
        print(f"  - {r['content'][:100]}")

    # Test context retrieval
    context = indexer.get_context_for_analysis(test_jira, {})
    print(f"\nContext for analysis:\n{context}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Local Claude Code CLI analysis service."""

import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class ClaudeCodeAnalysisError(RuntimeError):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.details = details or {}


class ClaudeCodeAnalysisService:
    DEFAULT_CALL_CHAIN_TIMEOUT = 15 * 60
    DEFAULT_JIRA_TIMEOUT = 30 * 60
    MAX_PROMPT_CHARS = 60000
    MAX_DIAGNOSTIC_CHARS = 4000

    def __init__(self, repo_path: str):
        self.repo_path = self._validate_repo_path(repo_path)
        self.command = self._resolve_command()

    def analyze_call_chain(
        self,
        api_path: str,
        trace_context: Optional[Dict[str, Any]] = None,
        ref: Optional[str] = None
    ) -> Dict[str, Any]:
        prompt = self._build_call_chain_prompt(api_path, trace_context, ref)
        result = self._run(prompt, timeout=self._timeout("CLAUDE_CODE_CALL_CHAIN_TIMEOUT", self.DEFAULT_CALL_CHAIN_TIMEOUT))
        result.setdefault("api_path", api_path)
        result.setdefault("metadata", {})
        result["metadata"].update({
            "analysis_engine": "claude_code_cli",
            "source": "claude_code_cli"
        })
        return result

    def build_jira_code_context(
        self,
        jira: Dict[str, Any],
        api_paths: List[str],
        trace_context: Optional[Dict[str, Any]],
        logs: Optional[Dict[str, Any]],
        search_keywords: Dict[str, Any],
        user_context: Dict[str, Any],
        ref: Optional[str] = None
    ) -> Dict[str, Any]:
        prompt = self._build_jira_code_context_prompt(
            jira=jira,
            api_paths=api_paths,
            trace_context=trace_context,
            logs=logs,
            search_keywords=search_keywords,
            user_context=user_context,
            ref=ref
        )
        result = self._run(prompt, timeout=self._timeout("CLAUDE_CODE_JIRA_TIMEOUT", self.DEFAULT_JIRA_TIMEOUT))
        result.setdefault("files", [])
        result.setdefault("call_chains", [])
        result.setdefault("metadata", {})
        result["metadata"].update({
            "analysis_engine": "claude_code_cli",
            "source": "claude_code_cli"
        })
        return result

    def analyze_jira_causes(
        self,
        jira: Dict[str, Any],
        code_context: Dict[str, Any],
        trace_context: Optional[Dict[str, Any]],
        rule_causes: List[Dict[str, Any]],
        user_context: Dict[str, Any],
        rag_context: Optional[str] = None,
        ref: Optional[str] = None
    ) -> Dict[str, Any]:
        prompt = self._build_jira_cause_prompt(
            jira=jira,
            code_context=code_context,
            trace_context=trace_context,
            rule_causes=rule_causes,
            user_context=user_context,
            rag_context=rag_context,
            ref=ref
        )
        result = self._run(prompt, timeout=self._timeout("CLAUDE_CODE_JIRA_TIMEOUT", self.DEFAULT_JIRA_TIMEOUT))
        result.setdefault("possible_causes", [])
        result.setdefault("summary", "")
        result.setdefault("metadata", {})
        result["metadata"].update({
            "analysis_engine": "claude_code_cli",
            "source": "claude_code_cli"
        })
        return result

    def _run(self, prompt: str, timeout: int) -> Dict[str, Any]:
        prompt = self._truncate_prompt(prompt)
        cmd = [*self.command, "--bare", "-p", prompt, "--output-format", "json"]
        started = time.time()
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                shell=False
            )
        except FileNotFoundError as exc:
            raise ClaudeCodeAnalysisError("本地 Claude Code CLI 不可用，请确认 claude 命令已安装并在 PATH 中。") from exc
        except subprocess.TimeoutExpired as exc:
            raise ClaudeCodeAnalysisError(
                f"本地 Claude Code CLI 分析超时（{timeout} 秒）。",
                {"timeout_seconds": timeout, "stderr": self._truncate_diagnostic(exc.stderr)}
            ) from exc

        duration_ms = int((time.time() - started) * 1000)
        if completed.returncode != 0:
            raise ClaudeCodeAnalysisError(
                "本地 Claude Code CLI 分析失败。",
                {
                    "exit_code": completed.returncode,
                    "duration_ms": duration_ms,
                    "stderr": self._truncate_diagnostic(completed.stderr),
                    "stdout": self._truncate_diagnostic(completed.stdout)
                }
            )

        parsed = self._parse_cli_stdout(completed.stdout, completed.stderr, duration_ms)
        metadata = parsed.setdefault("metadata", {})
        metadata.setdefault("duration_ms", duration_ms)
        metadata.setdefault("exit_code", completed.returncode)
        return parsed

    def _parse_cli_stdout(self, stdout: str, stderr: str, duration_ms: int) -> Dict[str, Any]:
        text = (stdout or "").strip()
        if not text:
            raise ClaudeCodeAnalysisError(
                "本地 Claude Code CLI 返回空输出。",
                {"duration_ms": duration_ms, "stderr": self._truncate_diagnostic(stderr)}
            )

        try:
            envelope = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ClaudeCodeAnalysisError(
                "本地 Claude Code CLI 输出不是合法 JSON。",
                {"stdout": self._truncate_diagnostic(text), "stderr": self._truncate_diagnostic(stderr)}
            ) from exc

        if isinstance(envelope, dict) and isinstance(envelope.get("structured_output"), dict):
            return envelope["structured_output"]

        result_text = envelope.get("result") if isinstance(envelope, dict) else None
        if isinstance(result_text, dict):
            return result_text
        if not isinstance(result_text, str):
            if isinstance(envelope, dict) and any(key in envelope for key in ("summary", "call_chains", "possible_causes", "code_context")):
                return envelope
            raise ClaudeCodeAnalysisError(
                "本地 Claude Code CLI JSON 中缺少 result 字段。",
                {"stdout": self._truncate_diagnostic(text), "stderr": self._truncate_diagnostic(stderr)}
            )

        return self._parse_result_json(result_text, stderr)

    def _parse_result_json(self, result_text: str, stderr: str) -> Dict[str, Any]:
        stripped = result_text.strip()
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", stripped)
            if not match:
                raise ClaudeCodeAnalysisError(
                    "本地 Claude Code CLI result 中未找到 JSON 对象。",
                    {"result": self._truncate_diagnostic(stripped), "stderr": self._truncate_diagnostic(stderr)}
                )
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError as exc:
                raise ClaudeCodeAnalysisError(
                    "本地 Claude Code CLI result 中的 JSON 无法解析。",
                    {"result": self._truncate_diagnostic(stripped), "stderr": self._truncate_diagnostic(stderr)}
                ) from exc
        if not isinstance(parsed, dict):
            raise ClaudeCodeAnalysisError("本地 Claude Code CLI result JSON 必须是对象。")
        return parsed

    def _build_call_chain_prompt(
        self,
        api_path: str,
        trace_context: Optional[Dict[str, Any]],
        ref: Optional[str]
    ) -> str:
        payload = {
            "task": "analyze_java_api_call_chain",
            "api_path": api_path,
            "ref": ref,
            "trace_context": self._sanitize(trace_context),
            "requirements": [
                "在当前工作目录的 Java/Spring 项目中定位该 API 的入口 Controller。",
                "沿 Controller、Service、DAO/Mapper、SQL/XML 追踪主要调用链。",
                "返回结构化 JSON，不要 Markdown，不要解释性前后缀。"
            ],
            "schema": {
                "api_path": "string",
                "method": "string|null",
                "controller": "string|null",
                "controller_method": "string|null",
                "call_chain": "array",
                "ascii_graph": "string",
                "summary": "string",
                "warnings": "array",
                "metadata": "object"
            }
        }
        return self._json_prompt(payload)

    def _build_jira_code_context_prompt(
        self,
        jira: Dict[str, Any],
        api_paths: List[str],
        trace_context: Optional[Dict[str, Any]],
        logs: Optional[Dict[str, Any]],
        search_keywords: Dict[str, Any],
        user_context: Dict[str, Any],
        ref: Optional[str]
    ) -> str:
        payload = {
            "task": "build_jira_code_context",
            "ref": ref,
            "jira": self._summarize_jira(jira),
            "api_paths": api_paths,
            "trace_context": self._sanitize(trace_context),
            "logs": self._sanitize(logs),
            "search_keywords": self._sanitize(search_keywords),
            "user_context": self._sanitize(user_context),
            "requirements": [
                "在当前工作目录中搜索与 Jira、Trace、日志和 API paths 相关的代码。",
                "返回最相关文件、行号片段、符号和必要调用链。",
                "返回结构化 JSON，不要 Markdown，不要解释性前后缀。"
            ],
            "schema": {
                "files": "array of {file_path,line_number,keyword,matches,reason}",
                "call_chains": "array of {api_path,call_chain}",
                "summary": "string",
                "warnings": "array",
                "metadata": "object"
            }
        }
        return self._json_prompt(payload)

    def _build_jira_cause_prompt(
        self,
        jira: Dict[str, Any],
        code_context: Dict[str, Any],
        trace_context: Optional[Dict[str, Any]],
        rule_causes: List[Dict[str, Any]],
        user_context: Dict[str, Any],
        rag_context: Optional[str],
        ref: Optional[str]
    ) -> str:
        payload = {
            "task": "analyze_jira_possible_causes",
            "ref": ref,
            "jira": self._summarize_jira(jira),
            "code_context": self._sanitize(code_context),
            "trace_context": self._sanitize(trace_context),
            "rule_causes": self._sanitize(rule_causes),
            "user_context": self._sanitize(user_context),
            "rag_context": self._truncate_text(rag_context or "", 12000),
            "requirements": [
                "结合 Jira、Trace、日志、规则分析和当前仓库代码，给出最可能原因。",
                "原因必须尽量关联具体代码位置、Trace 节点或日志证据。",
                "返回结构化 JSON，不要 Markdown，不要解释性前后缀。"
            ],
            "schema": {
                "possible_causes": "array of {category,analysis,suggestion,confidence,related_code,evidence}",
                "summary": "string",
                "metadata": "object"
            }
        }
        return self._json_prompt(payload)

    def _json_prompt(self, payload: Dict[str, Any]) -> str:
        return (
            "你是本地 Claude Code CLI 代码分析引擎。请只输出一个合法 JSON 对象，不要 Markdown，不要代码块，不要前后解释。\n"
            "输入如下：\n"
            f"{json.dumps(payload, ensure_ascii=False, default=str)}"
        )

    def _validate_repo_path(self, repo_path: str) -> Path:
        if not repo_path:
            raise ClaudeCodeAnalysisError("缺少本地仓库路径，无法调用 Claude Code CLI。")
        path = Path(repo_path).resolve()
        if not path.exists() or not path.is_dir():
            raise ClaudeCodeAnalysisError(f"本地仓库路径不存在: {repo_path}")

        allowed_roots = self._allowed_roots()
        if not any(self._is_relative_to(path, root) for root in allowed_roots):
            raise ClaudeCodeAnalysisError(
                f"仓库路径不在允许的 Claude Code CLI 分析目录内: {path}",
                {"allowed_roots": [str(root) for root in allowed_roots]}
            )
        return path

    def _allowed_roots(self) -> List[Path]:
        roots = [Path("./repos").resolve()]
        configured = os.getenv("CLAUDE_CODE_ALLOWED_REPO_ROOTS", "")
        for item in configured.split(os.pathsep):
            item = item.strip()
            if item:
                roots.append(Path(item).resolve())
        return roots

    @staticmethod
    def _is_relative_to(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    def _resolve_command(self) -> List[str]:
        configured = os.getenv("CLAUDE_CODE_CLI_COMMAND", "claude")
        return shlex.split(configured) or ["claude"]

    @staticmethod
    def _timeout(env_name: str, default: int) -> int:
        try:
            return int(os.getenv(env_name, str(default)))
        except ValueError:
            return default

    def _truncate_prompt(self, prompt: str) -> str:
        return self._truncate_text(prompt, self.MAX_PROMPT_CHARS)

    def _truncate_diagnostic(self, value: Any) -> str:
        return self._truncate_text(value or "", self.MAX_DIAGNOSTIC_CHARS)

    @staticmethod
    def _truncate_text(value: Any, limit: int) -> str:
        text = str(value or "")
        if len(text) <= limit:
            return text
        half = max(limit // 2, 1)
        return f"{text[:half]}\n...[truncated]...\n{text[-half:]}"

    def _sanitize(self, value: Any) -> Any:
        if isinstance(value, dict):
            sanitized = {}
            for key, item in value.items():
                lower_key = str(key).lower()
                if any(secret in lower_key for secret in ("cookie", "token", "authorization", "password", "secret")):
                    sanitized[key] = "[REDACTED]"
                else:
                    sanitized[key] = self._sanitize(item)
            return sanitized
        if isinstance(value, list):
            return [self._sanitize(item) for item in value[:100]]
        if isinstance(value, str):
            return self._truncate_text(value, 8000)
        return value

    def _summarize_jira(self, jira: Dict[str, Any]) -> Dict[str, Any]:
        comments = jira.get("comments") or []
        return {
            "key": jira.get("key"),
            "summary": jira.get("summary"),
            "description": self._truncate_text(jira.get("description") or "", 6000),
            "customfield_19900": self._truncate_text(jira.get("customfield_19900") or "", 6000),
            "issue_type": jira.get("issue_type"),
            "priority": jira.get("priority"),
            "keywords": jira.get("keywords"),
            "comments": [
                {
                    "author": comment.get("author"),
                    "body": self._truncate_text(comment.get("body") or "", 2000),
                    "created": comment.get("created")
                }
                for comment in comments[:10]
            ]
        }

#!/usr/bin/env python3
"""Local code directory context utilities for code analysis."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse


class RepositoryContextError(ValueError):
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.details = details or {}


class LocalCodeDirNotFoundError(RepositoryContextError):
    pass


class LocalCodeDirNotDirectoryError(RepositoryContextError):
    pass


class LocalCodeDirNotReadableError(RepositoryContextError):
    pass


@dataclass
class LocalCodeDirContext:
    local_path: str
    source: str
    requested_value: str
    is_git_repo: bool
    head_commit: Optional[str] = None


def resolve_local_code_dir(
    repo_path: Optional[str] = None,
    repo_key: Optional[str] = None,
    repo_url: Optional[str] = None,
    use_default: bool = False
) -> LocalCodeDirContext:
    if repo_path:
        return _context_from_path(repo_path, "repo_path", repo_path)

    if repo_key:
        from config_manager import get_git_repo_url
        configured = get_git_repo_url(repo_key)
        if not configured:
            raise LocalCodeDirNotFoundError(
                f"在配置中找不到键名为 '{repo_key}' 的代码目录配置。",
                {"repo_key": repo_key, "source": "repo_key"}
            )
        return _context_from_value(configured, "repo_key", repo_key)

    if repo_url:
        return _context_from_value(repo_url, "repo_url", repo_url)

    if use_default:
        from config_manager import get_default_code_dir
        default_code_dir = get_default_code_dir()
        if default_code_dir:
            return _context_from_value(default_code_dir, "default_code_dir", default_code_dir)
        raise LocalCodeDirNotFoundError(
            "未配置默认本地代码目录，请在 .config 中配置 DEFAULT_CODE_DIR。",
            {"source": "default_code_dir"}
        )

    raise LocalCodeDirNotFoundError(
        "必须提供 repo_path、repo_key 或 repo_url 参数。",
        {"source": "none"}
    )


def build_code_dir_metadata(context: Optional[LocalCodeDirContext]) -> dict:
    if not context:
        return {}
    return {
        "local_path": context.local_path,
        "source": context.source,
        "requested_value": context.requested_value,
        "is_git_repo": context.is_git_repo,
        "head_commit": context.head_commit
    }


def _context_from_value(value: str, source: str, requested_value: str) -> LocalCodeDirContext:
    if _is_repo_url(value):
        repo_name = _repo_name_from_url(value)
        return _context_from_path(os.path.join("./repos", repo_name), source, requested_value)
    return _context_from_path(value, source, requested_value)


def _context_from_path(path_value: str, source: str, requested_value: str) -> LocalCodeDirContext:
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        raise LocalCodeDirNotFoundError(
            "本地代码目录不存在，请先由人工准备该目录。",
            {"local_path": str(path), "source": source, "requested_value": requested_value}
        )
    if not path.is_dir():
        raise LocalCodeDirNotDirectoryError(
            "本地代码路径不是目录。",
            {"local_path": str(path), "source": source, "requested_value": requested_value}
        )
    if not os.access(path, os.R_OK):
        raise LocalCodeDirNotReadableError(
            "本地代码目录不可读。",
            {"local_path": str(path), "source": source, "requested_value": requested_value}
        )

    head_commit = _read_git_head(path)
    return LocalCodeDirContext(
        local_path=str(path),
        source=source,
        requested_value=requested_value,
        is_git_repo=head_commit is not None,
        head_commit=head_commit
    )


def _read_git_head(path: Path) -> Optional[str]:
    try:
        git_dir = path / ".git"
        if not git_dir.exists():
            return None
        head = (git_dir / "HEAD").read_text(encoding="utf-8", errors="ignore").strip()
        if head.startswith("ref:"):
            ref_path = git_dir / head.split(" ", 1)[1].strip()
            if ref_path.exists():
                return ref_path.read_text(encoding="utf-8", errors="ignore").strip() or None
            packed_refs = git_dir / "packed-refs"
            if packed_refs.exists():
                ref_name = head.split(" ", 1)[1].strip()
                for line in packed_refs.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if line and not line.startswith("#") and line.endswith(f" {ref_name}"):
                        return line.split(" ", 1)[0]
            return None
        return head or None
    except Exception:
        return None


def _is_repo_url(value: str) -> bool:
    text = (value or "").strip()
    return (
        text.startswith("http://")
        or text.startswith("https://")
        or text.startswith("git@")
        or text.startswith("ssh://")
    )


def _repo_name_from_url(value: str) -> str:
    text = value.strip()
    if text.startswith("git@"):
        name = text.rsplit("/", 1)[-1]
    else:
        parsed = urlparse(text)
        name = parsed.path.rsplit("/", 1)[-1]
    return name[:-4] if name.endswith(".git") else name

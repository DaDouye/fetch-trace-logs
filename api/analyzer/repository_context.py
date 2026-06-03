#!/usr/bin/env python3
"""Repository version locking utilities for code analysis."""

import hashlib
import os
import re
from dataclasses import dataclass
from typing import Optional

import git


class RepositoryContextError(ValueError):
    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.details = details or {}


class MissingLockedRefError(RepositoryContextError):
    pass


class MutableRefNotAllowedError(RepositoryContextError):
    pass


class LockedRefNotFoundError(RepositoryContextError):
    pass


class RepoCheckoutMismatchError(RepositoryContextError):
    pass


@dataclass
class LockedRepoContext:
    repo_url: str
    locked_ref: str
    resolved_commit: str
    local_path: str
    fetched_missing_commit: bool = False


_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,40}$")
_FULL_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")


def normalize_locked_ref(locked_ref: Optional[str] = None, ref: Optional[str] = None) -> str:
    candidate = (locked_ref or ref or "").strip()
    if not candidate:
        raise MissingLockedRefError("缺少固定代码版本，请提供 locked_ref commit SHA。")
    if not _SHA_PATTERN.match(candidate):
        raise MutableRefNotAllowedError(
            "代码分析必须使用固定 commit SHA，不允许使用分支名、tag 或 HEAD。",
            {"requested_ref": candidate}
        )
    return candidate.lower()


def prepare_locked_repo(
    repo_url: str,
    locked_ref: str,
    allow_fetch_missing: bool = False,
    repos_root: str = "./repos"
) -> LockedRepoContext:
    target_ref = normalize_locked_ref(locked_ref)
    repo_name = repo_url.split('/')[-1].replace('.git', '')
    repo_hash = hashlib.sha1(repo_url.encode('utf-8')).hexdigest()[:8]
    local_path = os.path.join(repos_root, f"{repo_name}-{target_ref}-{repo_hash}")
    fetched_missing_commit = False

    if os.path.exists(local_path):
        repo = git.Repo(local_path)
        resolved_commit = _resolve_local_commit(repo, target_ref)
        if not resolved_commit:
            if not allow_fetch_missing:
                raise LockedRefNotFoundError(
                    "本地仓库缓存缺少目标 locked_ref，且未允许补充获取。",
                    {"repo_url": repo_url, "locked_ref": target_ref, "local_path": local_path}
                )
            _fetch_locked_ref(repo, target_ref)
            fetched_missing_commit = True
            resolved_commit = _resolve_local_commit(repo, target_ref)
            if not resolved_commit:
                raise LockedRefNotFoundError(
                    "补充获取后仍无法找到目标 locked_ref。",
                    {"repo_url": repo_url, "locked_ref": target_ref, "local_path": local_path}
                )
    else:
        os.makedirs(local_path, exist_ok=True)
        repo = git.Repo.init(local_path)
        repo.create_remote('origin', repo_url)
        _fetch_locked_ref(repo, target_ref, allow_ref_discovery=True)
        fetched_missing_commit = True
        resolved_commit = _resolve_local_commit(repo, target_ref)
        if not resolved_commit:
            raise LockedRefNotFoundError(
                "无法获取目标 locked_ref。",
                {"repo_url": repo_url, "locked_ref": target_ref, "local_path": local_path}
            )

    repo.git.checkout(resolved_commit)
    actual_head = repo.head.commit.hexsha
    if actual_head != resolved_commit:
        raise RepoCheckoutMismatchError(
            "仓库 checkout 后的 HEAD 与 locked_ref 不一致。",
            {
                "repo_url": repo_url,
                "locked_ref": target_ref,
                "resolved_commit": resolved_commit,
                "actual_head": actual_head,
                "local_path": local_path
            }
        )

    return LockedRepoContext(
        repo_url=repo_url,
        locked_ref=target_ref,
        resolved_commit=resolved_commit,
        local_path=local_path,
        fetched_missing_commit=fetched_missing_commit
    )


def _resolve_local_commit(repo: git.Repo, locked_ref: str) -> Optional[str]:
    try:
        commit = repo.commit(locked_ref)
    except Exception:
        return None
    if _FULL_SHA_PATTERN.match(locked_ref) and commit.hexsha != locked_ref:
        return None
    if not commit.hexsha.startswith(locked_ref):
        return None
    return commit.hexsha


def _fetch_locked_ref(repo: git.Repo, locked_ref: str, allow_ref_discovery: bool = False) -> None:
    try:
        repo.remotes.origin.fetch(locked_ref)
    except Exception as exc:
        if allow_ref_discovery:
            try:
                repo.remotes.origin.fetch()
                return
            except Exception:
                pass
        raise LockedRefNotFoundError(
            "无法从远端获取目标 locked_ref。",
            {"locked_ref": locked_ref, "error": str(exc)}
        ) from exc

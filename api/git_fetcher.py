#!/usr/bin/env python3
"""
Remote Git Fetcher - 按需从远程 Git 仓库获取代码文件
支持 git archive 协议和 GitHub/GitLab API
"""

import os
import io
import re
import subprocess
import urllib.request
import urllib.error
import ssl
from typing import Optional, Dict, List, Tuple
from pathlib import Path

from api.analyzer.repository_context import MutableRefNotAllowedError, normalize_locked_ref


class GitFetcher:
    """
    按需从远程 Git 仓库获取文件内容
    支持 git archive 协议和 GitHub/GitLab raw API
    """

    def __init__(self, repo_url: str, ref: str):
        """
        初始化 GitFetcher

        :param repo_url: Git 仓库 URL (如 https://github.com/user/repo.git)
        :param ref: 固定 commit SHA
        """
        self.repo_url = repo_url
        self.ref = normalize_locked_ref(ref)
        self.verify_ssl = os.getenv("GIT_FETCHER_VERIFY_SSL", "true").lower() != "false"
        self._cache: Dict[str, bytes] = {}  # path -> content
        self._list_cache: Dict[str, List[str]] = {}  # dir -> files

        # 检测仓库类型
        self._repo_type = self._detect_repo_type()

    def _ssl_context(self):
        ctx = ssl.create_default_context()
        if not self.verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _detect_repo_type(self) -> str:
        """检测仓库类型：github, gitlab, 或 generic"""
        url_lower = self.repo_url.lower()
        if 'github.com' in url_lower:
            return 'github'
        elif 'gitlab' in url_lower or 'souche-inc' in url_lower:
            return 'gitlab'
        return 'generic'

    def _get_cache_key(self, path: str, ref: str = None) -> str:
        return f"{ref or self.ref}:{path}"

    def file_exists(self, file_path: str, ref: str = None) -> bool:
        """检查文件是否存在"""
        try:
            content = self.get_file(file_path, ref)
            return content is not None
        except Exception:
            return False

    def get_file(self, file_path: str, ref: str = None) -> Optional[str]:
        """
        获取文件内容

        :param file_path: 文件路径 (如 web/src/main/java/com/example/Class.java)
        :param ref: 分支或 commit
        :return: 文件内容字符串，失败返回 None
        """
        key = self._get_cache_key(file_path, ref)
        if key in self._cache:
            return self._cache[key].decode('utf-8', errors='ignore')

        content = self._fetch_file(file_path, ref)
        if content:
            self._cache[key] = content
            return content.decode('utf-8', errors='ignore')
        return None

    def get_file_bytes(self, file_path: str, ref: str = None) -> Optional[bytes]:
        """获取文件原始字节内容"""
        key = self._get_cache_key(file_path, ref)
        if key in self._cache:
            return self._cache[key]

        content = self._fetch_file(file_path, ref)
        if content:
            self._cache[key] = content
        return content

    def list_files(self, directory: str, ref: str = None) -> List[str]:
        """
        列出目录下的所有文件

        :param directory: 目录路径 (如 web/src/main/java)
        :param ref: 分支或 commit
        :return: 文件路径列表
        """
        key = self._get_cache_key(directory, ref)
        if key in self._list_cache:
            return self._list_cache[key]

        files = self._list_directory(directory, ref)
        if files is not None:
            self._list_cache[key] = files
        return files

    def _fetch_file(self, file_path: str, ref: str = None) -> Optional[bytes]:
        """实际获取文件"""
        target_ref = normalize_locked_ref(ref or self.ref)

        # 尝试 git archive 方式
        content = self._fetch_via_git_archive(file_path, target_ref)
        if content:
            return content

        # 回退到 API 方式
        content = self._fetch_via_api(file_path, target_ref)
        return content

    def _fetch_via_git_archive(self, file_path: str, ref: str) -> Optional[bytes]:
        """通过 git archive --remote 获取文件"""
        try:
            # git archive --remote=url ref path
            cmd = [
                'git', 'archive',
                f'--remote={self.repo_url}',
                ref,
                '--',
                file_path
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=30
            )

            if result.returncode == 0 and result.stdout:
                # git archive 返回的是 tar 格式，需要解压
                import tarfile
                with tarfile.open(fileobj=io.BytesIO(result.stdout)) as tar:
                    members = tar.getmembers()
                    if members:
                        member = tar.extractfile(members[0])
                        if member:
                            return member.read()

        except subprocess.TimeoutExpired:
            print(f"[GitFetcher] git archive timeout for {file_path}")
        except Exception as e:
            print(f"[GitFetcher] git archive failed: {e}")

        return None

    def _fetch_via_api(self, file_path: str, ref: str) -> Optional[bytes]:
        """通过 GitHub/GitLab API 获取文件"""
        if self._repo_type == 'github':
            return self._fetch_github_raw(file_path, ref)
        elif self._repo_type == 'gitlab':
            return self._fetch_gitlab_raw(file_path, ref)
        return None

    def _fetch_github_raw(self, file_path: str, ref: str) -> Optional[bytes]:
        """GitHub raw content API"""
        # 解析 URL: https://github.com/user/repo.git -> user/repo
        match = re.match(r'https://github\.com/([^/]+)/([^/]+?)(?:\.git)?$', self.repo_url, re.IGNORECASE)
        if not match:
            return None

        owner, repo = match.groups()
        # 去除 .git 后缀
        repo = repo.rstrip('.git')

        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
        params = f"?ref={ref}"


        headers = {
            'Accept': 'application/vnd.github.v3.raw',
            'User-Agent': 'GitFetcher/1.0'
        }

        try:
            req = urllib.request.Request(api_url + params, headers=headers)
            with urllib.request.urlopen(req, timeout=30, context=self._ssl_context()) as response:
                return response.read()

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            print(f"[GitFetcher] GitHub API error: {e.code}")
        except Exception as e:
            print(f"[GitFetcher] GitHub fetch failed: {e}")

        return None

    def _fetch_gitlab_raw(self, file_path: str, ref: str) -> Optional[bytes]:
        """GitLab raw content API"""
        # 解析 URL 提取 project path
        # https://git.souche-inc.com/gourd/super-mario.git -> gourd/super-mario
        match = re.match(r'https://[^/]+/([^/]+)/([^/]+?)(?:\.git)?$', self.repo_url, re.IGNORECASE)
        if not match:
            return None

        project_path = f"{match.group(1)}/{match.group(2)}".rstrip('.git')
        encoded_path = urllib.request.quote(file_path, safe='')
        api_url = f"https://git.souche-inc.com/api/v4/projects/{urllib.request.quote(project_path, safe='')}/repository/files/{encoded_path}/raw?ref={ref}"

        headers = {
            'User-Agent': 'GitFetcher/1.0'
        }

        try:
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=30, context=self._ssl_context()) as response:
                return response.read()

        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            print(f"[GitFetcher] GitLab API error: {e.code}")
        except Exception as e:
            print(f"[GitFetcher] GitLab fetch failed: {e}")

        return None

    def _list_directory(self, directory: str, ref: str = None) -> List[str]:
        """列出目录内容"""
        target_ref = normalize_locked_ref(ref or self.ref)

        if self._repo_type == 'github':
            return self._list_github_directory(directory, target_ref)
        elif self._repo_type == 'gitlab':
            return self._list_gitlab_directory(directory, target_ref)

        return []

    def _list_github_directory(self, directory: str, ref: str) -> List[str]:
        """通过 GitHub API 列出目录"""
        match = re.match(r'https://github\.com/([^/]+)/([^/]+?)(?:\.git)?$', self.repo_url, re.IGNORECASE)
        if not match:
            return []

        owner, repo = match.groups()
        repo = repo.rstrip('.git')

        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{directory}"
        api_url += f"?ref={ref}"

        headers = {'User-Agent': 'GitFetcher/1.0'}

        try:
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=30, context=self._ssl_context()) as response:
                import json
                items = json.loads(response.read().decode('utf-8'))
                return [item['path'] for item in items if item['type'] == 'file']

        except Exception:
            return []

    def _list_gitlab_directory(self, directory: str, ref: str) -> List[str]:
        """通过 GitLab API 列出目录"""
        match = re.match(r'https://[^/]+/([^/]+)/([^/]+?)(?:\.git)?$', self.repo_url, re.IGNORECASE)
        if not match:
            return []

        project_path = f"{match.group(1)}/{match.group(2)}".rstrip('.git')
        encoded_dir = urllib.request.quote(directory, safe='')
        api_url = f"https://git.souche-inc.com/api/v4/projects/{urllib.request.quote(project_path, safe='')}/repository/tree?path={encoded_dir}&ref={ref}"

        headers = {'User-Agent': 'GitFetcher/1.0'}

        try:
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=30, context=self._ssl_context()) as response:
                import json
                items = json.loads(response.read().decode('utf-8'))
                return [item['path'] for item in items if item['type'] == 'blob']

        except Exception:
            return []


class GitRepoManager:
    """
    Git 仓库管理器 - 管理多个远程仓库的按需访问
    """

    def __init__(self):
        self._fetchers: Dict[str, GitFetcher] = {}
        self._default_refs: Dict[str, str] = {}  # repo_url -> default ref

    def get_fetcher(self, repo_url: str, ref: str) -> GitFetcher:
        """
        获取仓库的 fetcher，自动缓存

        :param repo_url: 仓库 URL
        :param ref: 固定 commit SHA
        """
        locked_ref = normalize_locked_ref(ref)
        cache_key = f"{repo_url}@{locked_ref}"
        if cache_key not in self._fetchers:
            self._fetchers[cache_key] = GitFetcher(repo_url, locked_ref)
        return self._fetchers[cache_key]

    def set_default_ref(self, repo_url: str, ref: str):
        """设置仓库默认固定 commit SHA"""
        self._default_refs[repo_url] = normalize_locked_ref(ref)

    def clear_cache(self, repo_url: str = None):
        """清除缓存"""
        if repo_url:
            if repo_url in self._fetchers:
                del self._fetchers[repo_url]
        else:
            self._fetchers.clear()


# 全局单例
_git_manager = GitRepoManager()


def get_git_fetcher(repo_url: str, ref: str) -> GitFetcher:
    """获取 GitFetcher 全局实例"""
    return _git_manager.get_fetcher(repo_url, ref)


def clear_git_cache(repo_url: str = None):
    """清除缓存"""
    _git_manager.clear_cache(repo_url)

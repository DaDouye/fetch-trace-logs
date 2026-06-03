"""
配置管理模块
用于读取和管理各种配置参数
"""
import os
from pathlib import Path


def load_config(config_file_path=None):
    """
    从配置文件加载配置

    Args:
        config_file_path (str): 配置文件路径，默认为项目根目录下的.config文件

    Returns:
        dict: 配置字典
    """
    if config_file_path is None:
        # 尝试在不同位置查找配置文件
        possible_paths = [
            "./.config",
            "./scripts/.config",
            os.path.expanduser("~/.qoder/skills/fetch-trace-logs/scripts/.config"),
            Path(__file__).parent.parent / "scripts" / ".config"
        ]

        for path in possible_paths:
            if os.path.exists(path):
                config_file_path = path
                break

    if config_file_path is None or not os.path.exists(config_file_path):
        return {}

    config = {}
    with open(config_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):  # 跳过注释和空行
                if '=' in line:
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()

    return config


def get_git_repo_url(key):
    """
    根据键值获取Git仓库URL

    Args:
        key (str): 配置键名

    Returns:
        str: Git仓库URL，如果找不到则返回None
    """
    config = load_config()
    return config.get(key)


def get_default_code_dir():
    """
    获取默认本地代码目录配置

    Returns:
        str: 默认本地代码目录或仓库配置，找不到则返回None
    """
    config = load_config()

    for key in ("DEFAULT_CODE_DIR", "DEFAULT_REPO_PATH", "DEFAULT_REPO", "default_code_dir", "default_repo_path", "default_repo"):
        value = config.get(key)
        if value:
            return value

    repos = get_all_git_repos()
    if len(repos) == 1:
        return next(iter(repos.values()))

    return None


def get_all_git_repos():
    """
    获取所有代码目录/仓库配置

    Returns:
        dict: 所有可能作为代码目录配置的项目
    """
    config = load_config()
    repos = {}

    for key, value in config.items():
        if value.endswith('.git') or os.path.isdir(os.path.expanduser(value)):
            repos[key] = value

    return repos
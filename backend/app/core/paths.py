import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent


def is_frozen() -> bool:
    """判断是否为PyInstaller打包环境。"""
    return bool(getattr(sys, "frozen", False))


def get_project_dir() -> Path:
    """获取源码项目根目录。"""
    return PROJECT_DIR


def get_runtime_root() -> Path:
    """获取运行时根目录。"""
    configured_dir = os.getenv("BOM_RUNTIME_DIR", "").strip()
    if configured_dir:
        return Path(configured_dir).resolve()
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return get_project_dir()


def get_bundle_root() -> Path:
    """获取打包资源根目录。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass).resolve()
    return get_project_dir()


def get_env_file() -> Path:
    """获取.env配置文件路径。"""
    return get_runtime_root() / ".env"


def get_data_dir() -> Path:
    """获取运行数据目录。"""
    if is_frozen() or os.getenv("BOM_RUNTIME_DIR", "").strip():
        return get_runtime_root() / "data"
    return BACKEND_DIR / "data"


def get_frontend_dist_dir() -> Path:
    """获取前端静态文件目录。"""
    if is_frozen():
        return get_bundle_root() / "frontend_dist"
    return get_project_dir() / "frontend" / "dist"

import os
import sys

def get_writable_path(relative_path: str = "") -> str:
    """获取可写目录（用户数据目录），通常是可执行文件所在目录"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包环境
        base_path = os.path.dirname(sys.executable)
    elif "__compiled__" in globals():
        # Nuitka 打包环境
        base_path = os.path.dirname(os.path.abspath(sys.argv[0]))
    else:
        # 开发环境
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_path = os.path.abspath(os.path.join(current_dir, "..", ".."))
    
    return os.path.join(base_path, relative_path)

def get_bundled_resource_path(relative_path: str) -> str:
    """获取打包在程序内部的只读资源路径"""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller OneFile 临时目录
        base_path = sys._MEIPASS
    elif "__compiled__" in globals():
        # Nuitka Onefile 临时目录 (__file__ 确实就在 Temp 当中)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_path = os.path.abspath(os.path.join(current_dir, "..", ".."))
    elif getattr(sys, 'frozen', False):
        # 兼容备用方案
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_path = os.path.abspath(os.path.join(current_dir, "..", ".."))
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        base_path = os.path.abspath(os.path.join(current_dir, "..", ".."))
    
    return os.path.join(base_path, relative_path)

def get_resource_path(relative_path: str) -> str:
    """
    默认获取资源路径 (向后兼容)
    默认行为: 指向可写目录 (配置, 下载, Logs)
    """
    return get_writable_path(relative_path)

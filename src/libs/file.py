import os
import shutil
from pathlib import Path


class File:
    """文件操作类"""

    def __init__(self):
        pass

    def exists(self, file_path: str) -> bool:
        """判断文件或目录是否存在"""
        return Path(file_path).exists()

    def remove(self, file_path: str) -> None:
        """删除文件"""
        if self.exists(file_path):
            os.remove(file_path)

    def create(self, file_path: str) -> None:
        """创建文件"""
        path = Path(file_path)
        # 确保父目录存在
        path.parent.mkdir(parents=True, exist_ok=True)
        # 创建文件
        path.touch()

    def read(self, file_path: str) -> str:
        """读取文件内容"""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def write(self, file_path: str, content: str) -> None:
        """写入文件内容"""
        path = Path(file_path)
        # 确保父目录存在
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

    def append(self, file_path: str, content: str) -> None:
        """追加文件内容"""
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(content)

    def mkdir(self, dir_path: str) -> None:
        """创建目录"""
        Path(dir_path).mkdir(parents=True, exist_ok=True)

    def rmdir(self, dir_path: str) -> None:
        """删除目录"""
        if self.exists(dir_path):
            shutil.rmtree(dir_path)

    def copy_file(self, src: str, dst: str) -> None:
        """复制文件"""
        dst_path = Path(dst)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    def move_file(self, src: str, dst: str) -> None:
        """移动文件"""
        dst_path = Path(dst)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src, dst)

    def get_file_size(self, file_path: str) -> int:
        """获取文件大小"""
        return os.path.getsize(file_path)

    def list_files(self, dir_path: str, pattern: str = "*") -> list:
        """列出目录下的文件"""
        path = Path(dir_path)
        if path.is_dir():
            return [str(p) for p in path.glob(pattern) if p.is_file()]
        return []

    def list_dirs(self, dir_path: str) -> list:
        """列出目录下的子目录"""
        path = Path(dir_path)
        if path.is_dir():
            return [str(p) for p in path.iterdir() if p.is_dir()]
        return []

import json
import os
import time
from pathlib import Path
from typing import Optional, List

from .constants import (
    GLOBAL_CONFIG, LocalCookiesInfo,  # UserCliConfig已移除
    LocalCacheUserInfo, YuqueLoginUserInfo, BookItem
)
from .file import File
from .log import Log


def gen_timestamp() -> int:
    """生成当前时间戳（毫秒）"""
    return int(time.time() * 1000)


def get_local_cookies() -> str:
    """获取本地有效cookies，如果cookies过期就返回空字符串"""
    f = File()
    try:
        if f.exists(GLOBAL_CONFIG.cookies_file):
            cookie_info_str = f.read(GLOBAL_CONFIG.cookies_file)
            cookie_info_dict = json.loads(cookie_info_str)
            cookie_info = LocalCookiesInfo(**cookie_info_dict)

            if cookie_info.expire_time < gen_timestamp():
                return ""
            else:
                return cookie_info.cookies
        else:
            return ""
    except Exception:
        return ""


def get_cache_books_info() -> Optional[List[BookItem]]:
    """获取本地缓存的知识库信息，如果已过期就返回None"""
    books_info_file = GLOBAL_CONFIG.books_info_file

    if Path(books_info_file).exists():
        try:
            f = File()
            data = f.read(books_info_file)
            config_dict = json.loads(data)

            # 检查是否过期
            expire_time = config_dict.get('expire_time', 0)
            if expire_time < gen_timestamp():
                return None

            books_info_list = config_dict.get('books_info', [])
            books = []
            for book_dict in books_info_list:
                # 处理docs字段
                docs_data = book_dict.get('docs', [])
                book_dict['docs'] = docs_data  # 保持原始数据结构
                books.append(BookItem(**book_dict))
            return books
        except Exception:
            return None
    else:
        return None


def get_cache_user_info() -> Optional[YuqueLoginUserInfo]:
    """获取缓存的用户信息"""
    user_info_file = GLOBAL_CONFIG.user_info_file

    if Path(user_info_file).exists():
        try:
            f = File()
            data = f.read(user_info_file)
            config_dict = json.loads(data)
            cache_info = LocalCacheUserInfo(**config_dict)
            return cache_info.user_info
        except Exception:
            return None
    else:
        return None


def is_personal() -> bool:
    """判断是否为个人知识库（CLI配置已移除，默认返回True）"""
    return True


def save_cookies(cookies: str, expire_time: Optional[int] = None) -> bool:
    """保存cookies到本地"""
    try:
        f = File()
        if expire_time is None:
            expire_time = gen_timestamp() + GLOBAL_CONFIG.local_expire

        cookie_info = LocalCookiesInfo(
            expire_time=expire_time,
            cookies=cookies
        )

        cookie_data = {
            'expire_time': cookie_info.expire_time,
            'cookies': cookie_info.cookies
        }

        f.write(GLOBAL_CONFIG.cookies_file, json.dumps(cookie_data, ensure_ascii=False, indent=2))
        return True
    except Exception:
        return False


def save_user_info(user_info: dict) -> bool:
    """保存用户信息到本地"""
    try:
        f = File()
        cache_info = {
            'expire_time': gen_timestamp() + GLOBAL_CONFIG.local_expire,
            'user_info': user_info
        }

        f.write(GLOBAL_CONFIG.user_info_file, json.dumps(cache_info, ensure_ascii=False, indent=2))
        return True
    except Exception:
        return False


def save_books_info(books_info: List[dict]) -> bool:
    """保存知识库信息到本地"""
    try:
        f = File()
        cache_info = {
            'expire_time': gen_timestamp() + GLOBAL_CONFIG.local_expire,
            'books_info': books_info
        }

        f.write(GLOBAL_CONFIG.books_info_file, json.dumps(cache_info, ensure_ascii=False, indent=2))
        return True
    except Exception:
        return False


def format_filename(filename: str) -> str:
    """格式化文件名，移除非法字符"""
    # 移除或替换Windows文件名中的非法字符
    illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for char in illegal_chars:
        filename = filename.replace(char, '_')

    # 移除前后空格和点
    filename = filename.strip(' .')

    # 如果文件名为空，使用默认名称
    if not filename:
        filename = 'untitled'

    return filename


def ensure_dir_exists(dir_path: str) -> bool:
    """确保目录存在"""
    try:
        f = File()
        if not f.exists(dir_path):
            f.mkdir(dir_path)
        return True
    except Exception:
        return False


def save_docs_cache(namespace: str, docs: List[dict]) -> bool:
    """保存文章列表缓存到本地"""
    try:
        f = File()
        cache_info = {
            'expire_time': gen_timestamp() + GLOBAL_CONFIG.local_expire,
            'docs': docs
        }

        # 创建缓存目录
        cache_dir = os.path.join(GLOBAL_CONFIG.meta_dir, "Article_list_caching")
        if not f.exists(cache_dir):
            f.mkdir(cache_dir)

        # 创建文档缓存文件名，使用namespace作为文件名
        docs_cache_file = os.path.join(cache_dir, f"docs_{namespace.replace('/', '_')}.json")

        f.write(docs_cache_file, json.dumps(cache_info, ensure_ascii=False, indent=2))
        return True
    except Exception:
        return False


def get_docs_cache(namespace: str) -> Optional[List[dict]]:
    """获取本地缓存的文章列表，如果已过期就返回None"""
    try:
        f = File()
        cache_dir = os.path.join(GLOBAL_CONFIG.meta_dir, "Article_list_caching")
        docs_cache_file = os.path.join(cache_dir, f"docs_{namespace.replace('/', '_')}.json")

        if f.exists(docs_cache_file):
            data = f.read(docs_cache_file)
            cache_dict = json.loads(data)

            # 检查是否过期
            expire_time = cache_dict.get('expire_time', 0)
            if expire_time < gen_timestamp():
                return None

            return cache_dict.get('docs', [])
        else:
            return None
    except Exception:
        return None


def clean_cache() -> bool:
    """清理本地缓存，保留cookies.json和user_info.json"""
    try:
        import os
        import shutil

        meta_dir = GLOBAL_CONFIG.meta_dir
        if os.path.exists(meta_dir):
            # 需要保留的文件
            preserve_files = ['cookies.json', 'user_info.json']

            # 遍历.meta目录下的所有文件和文件夹
            for filename in os.listdir(meta_dir):
                if filename not in preserve_files:
                    file_path = os.path.join(meta_dir, filename)
                    try:
                        if os.path.isfile(file_path) or os.path.islink(file_path):
                            os.unlink(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                    except Exception as e:
                        Log.error(f"删除 {file_path} 时出错: {e}")
        return True
    except Exception:
        return False

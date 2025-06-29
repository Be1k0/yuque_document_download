import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


def get_resource_path(relative_path):
    """获取资源文件的绝对路径，兼容PyInstaller打包"""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller打包后，使用可执行文件所在目录
        return os.path.join(os.path.dirname(sys.executable), relative_path)
    else:
        # 开发环境，使用脚本所在目录的上级目录
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(base_path, relative_path)


@dataclass
class GlobalConfig:
    """全局配置类"""
    yuque_host: str = "https://www.yuque.com"
    yuque_referer: str = "https://www.yuque.com/login"
    yuque_login: str = "/api/accounts/login"
    mobile_login: str = "/api/mobile_app/accounts/login?language=zh-cn"
    user_agent: str = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/20G81 YuqueMobileApp/1.0.2 (AppBuild/650 Device/Phone Locale/zh-cn Theme/light YuqueType/public)"
    yuque_book_stacks: str = "/api/mine/book_stacks"
    yuque_books_info: str = ""
    yuque_space_books_info: str = "/api/mine/user_books?user_type=Group"
    yuque_collab_books_info: str = "/api/mine/raw_collab_books"
    group_resource_base_info: str = "/api/mine/group_quick_links"
    yuque_export_markdown: str = ""
    meta_dir: str = get_resource_path(".meta")
    target_output_dir: str = get_resource_path("./docs")
    target_resource_dir: str = get_resource_path("./resources")
    cookies_file: str = get_resource_path(".meta/cookies.json")
    user_info_file: str = get_resource_path(".meta/user_info.json")
    books_info_file: str = get_resource_path(".meta/books_info.json")
    local_expire: int = 86400000  # 1天过期时间
    duration: int = 500  # 下载频率
    article_limit: int = 0  # 文章下载数量限制，0表示不限制


@dataclass
class LocalCookiesInfo:
    """缓存cookies信息"""
    expire_time: int
    cookies: str


@dataclass
class YuqueAccount:
    """语雀账号信息"""
    username: str
    password: str


# @dataclass
# class UserCliConfig:
#     """用户的CLI配置（已移除CLI支持）"""
#     username: str = ""
#     password: str = ""
#     toc_range: List[str] = field(default_factory=list)
#     skip: bool = True
#     line_break: bool = True
#     host: str = ""
#     output: str = ""

@dataclass
class YuqueLoginUserInfo:
    """语雀登录用户信息"""
    name: str
    login: str


@dataclass
class LocalCacheUserInfo:
    """本地缓存用户信息"""
    expire_time: int
    user_info: YuqueLoginUserInfo


@dataclass
class MutualAnswer:
    """交互信息"""
    toc_range: List[str]
    skip: bool
    line_break: bool
    download_range: str = "all"  # 'all' - 所有文章, 'recent' - 最近文章, 'custom' - 自定义范围, 'selected' - 选择特定文章
    selected_docs: Dict[str, List[str]] = field(default_factory=dict)  # 知识库名称 -> 选中的文章ID列表


@dataclass
class TreeNode:
    """树形节点"""
    parent_id: str
    uuid: str
    full_path: str
    node_type: str  # 对应rust中的type字段
    children: List['TreeNode']
    title: str
    name: str
    child_uuid: str
    visible: int
    p_slug: str  # 父级slug
    user: str  # 文档所属user
    url: str  # 文档地址


@dataclass
class DocItem:
    """文档项目"""
    id: str
    slug: str
    title: str
    description: str
    creator_id: str
    public: int
    created_at: str
    updated_at: str
    published_at: str
    first_published_at: str
    draft_version: int
    last_editor_id: str
    word_count: int
    cover: str
    custom_description: str
    status: int
    view_status: int
    read_status: int
    likes_count: int
    comments_count: int
    content_updated_at: str
    deleted_at: Optional[str]
    created_at_timestamp: int
    updated_at_timestamp: int
    published_at_timestamp: int
    first_published_at_timestamp: int
    content_updated_at_timestamp: int
    hits: int
    namespace: str
    user: Dict[str, Any]
    book: Dict[str, Any]
    last_editor: Dict[str, Any]


@dataclass
class BookItem:
    """知识库项目"""
    id: str
    type: str
    slug: str
    name: str
    user_id: str
    description: str
    creator_id: str
    public: int
    items_count: int
    likes_count: int
    watches_count: int
    content_updated_at: str
    updated_at: str
    created_at: str
    namespace: str
    user: Dict[str, Any]
    toc: str
    toc_yml: str
    gitbook_token: str
    export_pdf_token: str
    export_epub_token: str
    abilities: Dict[str, Any]
    book_type: str
    docs: List[DocItem] = field(default_factory=list)


@dataclass
class BookInfo:
    """知识库缓存信息"""
    expire_time: int
    books_info: List[BookItem]


@dataclass
class ResourceItem:
    """资源项目"""
    id: str
    name: str
    url: str
    description: str
    created_at: str
    updated_at: str


# 全局配置实例
GLOBAL_CONFIG = GlobalConfig()


def load_config() -> GlobalConfig:
    """加载配置"""
    return GLOBAL_CONFIG

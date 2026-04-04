import threading
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Callable
from .path_utils import get_resource_path

class ThreadSafeCounter:
    """线程安全的计数器类,用于并发环境下的计数操作"""
    
    def __init__(self, initial_value: int = 0):
        self._value = initial_value
        self._lock = threading.Lock()
    
    def increment(self, amount: int = 1) -> int:
        """增加计数并返回新值
        
        Args:
            amount: 增加的数量,默认为1
            
        Returns:
            增加后的新值
        """
        with self._lock:
            self._value += amount
            return self._value
    
    def get(self) -> int:
        """获取当前计数值
        
        Returns:
            当前计数值
        """
        with self._lock:
            return self._value
    
    def reset(self):
        """重置计数器为0"""
        with self._lock:
            self._value = 0
    
    def __repr__(self):
        """返回计数器的字符串表示"""
        return f"ThreadSafeCounter(value={self.get()})"

@dataclass
class GlobalConfig:
    """全局配置类"""
    yuque_host: str = "https://www.yuque.com" # 语雀地址
    yuque_referer: str = "https://www.yuque.com/login" # 登录页
    yuque_login: str = "/api/accounts/login" # 登录接口
    mobile_login: str = "/api/mobile_app/accounts/login?language=zh-cn" # 手机登录接口
    user_agent: str = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/20G81 YuqueMobileApp/1.0.2 (AppBuild/650 Device/Phone Locale/zh-cn Theme/light YuqueType/public)"
    yuque_book_stacks: str = "/api/mine/book_stacks" # 我的知识库接口
    yuque_books_info: str = "" 
    yuque_space_books_info: str = "/api/mine/user_books?user_type=Group" # 团队空间知识库接口
    yuque_collab_books_info: str = "/api/mine/raw_collab_books" # 协作知识库接口
    group_resource_base_info: str = "/api/mine/group_quick_links" # 团队知识库接口
    yuque_article_info: str = "/api/docs?book_id=" # 知识库文章列表接口
    meta_dir: str = get_resource_path(".meta") # 程序临时文件目录
    target_output_dir: str = get_resource_path("./docs") # 默认下载目录
    target_resource_dir: str = get_resource_path("./resources") # 资源文件目录
    cookies_file: str = get_resource_path(".meta/cookies.json") # Cookies信息
    user_info_file: str = get_resource_path(".meta/user_info.json") # 登录用户信息
    books_info_file: str = get_resource_path(".meta/books_info.json") # 知识库信息
    local_expire: int = 86400000  # 1天过期时间
    duration: int = 500  # 下载频率
    disable_ssl: bool = False  # 是否禁用 SSL 证书检验
    github_repo_url: str = "https://github.com/Be1k0/yuque_document_download"  # 项目仓库地址
    github_latest_release_api: str = "https://api.github.com/repos/Be1k0/yuque_document_download/releases/latest"  # 最新版本接口
    enable_update_proxy: bool = True  # 是否启用程序更新下载加速
    update_proxy_base_url: str = "https://gh-proxy.org/"  # 程序更新下载加速地址
    update_temp_dir: str = get_resource_path(".meta/updater")  # 更新临时目录
    web_login_timeout_ms: int = 300000  # 网页端登录超时时间
    web_login_poll_interval_ms: int = 1000  # 网页端登录轮询间隔
    web_login_profile_dir: str = get_resource_path(".meta/browser_profiles")  # 网页端登录临时浏览器目录
    web_login_success_cookie_names: tuple[str, ...] = ("_yuque_session", "yuque_ctoken")  # 登录成功关键Cookie
    yuque_request_cookie_names: tuple[str, ...] = (
        "aliyungf_tc",
        "acw_tc",
        "yuque_ctoken",
        "receive-cookie-deprecation",
        "lang",
        "_yuque_session",
    )  # 请求语雀接口时允许携带的Cookie


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

    selected_docs: Dict[str, List[str]] = field(default_factory=dict)
    progress_callback: Optional[Callable] = None
    
    # 使用线程安全计数器代替普通int,确保并发环境下计数准确
    skipped_count: ThreadSafeCounter = field(default_factory=ThreadSafeCounter)
    downloaded_count: ThreadSafeCounter = field(default_factory=ThreadSafeCounter)
    failed_count: ThreadSafeCounter = field(default_factory=ThreadSafeCounter)

    # 记录当前任务中被成功下载或覆写的文档绝对路径
    downloaded_files: List[str] = field(default_factory=list)


@dataclass
class TreeNode:
    """树形节点"""
    parent_id: str
    uuid: str
    full_path: str
    node_type: str 
    children: List['TreeNode']
    title: str
    name: str
    child_uuid: str
    visible: int
    p_slug: str 
    user: str 
    url: str


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
    namespace: str = ""
    user: Dict[str, Any] = field(default_factory=dict)
    toc: str = ""
    toc_yml: str = ""
    gitbook_token: str = ""
    export_pdf_token: str = ""
    export_epub_token: str = ""
    abilities: Dict[str, Any] = field(default_factory=dict)
    book_type: str = ""
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

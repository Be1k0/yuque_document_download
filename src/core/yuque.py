import sys
import aiohttp
from typing import Dict, Any, List, Optional
from ..libs.constants import GLOBAL_CONFIG
from ..libs.encrypt import encrypt_password
from ..libs.log import Log
from ..libs.request import Request
from ..libs.tools import (
    is_personal, save_user_info, save_books_info,
    get_cache_books_info
)
from .parsers import YuqueParser
from ..libs.exceptions import (
    CookiesExpiredError, NetworkError
)

# 导入调试日志模块
try:
    from ..libs.debug_logger import DebugLogger
    _has_debug_logger = True
except ImportError:
    _has_debug_logger = False


class YuqueClient:
    """语雀API客户端类
    
    提供登录、获取用户信息、获取知识库列表、获取文档列表和导出Markdown等功能
    """

    def __init__(self, config=None):
        self.config = config or GLOBAL_CONFIG
        self.session: Optional[aiohttp.ClientSession] = None
        self._cookies: Optional[str] = None

    async def __aenter__(self):
        """异步上下文管理器入口，创建 aiohttp ClientSession"""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口，关闭 aiohttp ClientSession"""
        if self.session:
            await self.session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取 aiohttp ClientSession"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def login(self, username: str, password: str) -> bool:
        """登录语雀并存储cookies
        
        Args:
            username: 账号用户名
            password: 账号密码
        """
        try:
            encrypted_password = encrypt_password(password)

            params = {
                "login": username,
                "password": encrypted_password,
                "loginType": "password"
            }

            if _has_debug_logger:
                safe_params = params.copy()
                safe_params["password"] = "******"
                DebugLogger.log_info(f"尝试登录账号: {username}")
                DebugLogger.log_data("登录参数", safe_params)

            # 传递 session
            resp = await Request.post(self.config.mobile_login, params, session=self.session)

            if _has_debug_logger:
                DebugLogger.log_data("登录响应", resp)

            if resp.get("data"):
                user_info = resp["data"]["me"]
                if save_user_info(user_info):
                    if _has_debug_logger:
                        safe_user_info = user_info.copy() if isinstance(user_info, dict) else user_info
                        DebugLogger.log_data("用户信息", safe_user_info)
                    return True
                else:
                    Log.error("缓存目录创建失败")
                    return False
            else:
                return False

        except Exception as e:
            Log.error(f"登录失败: {str(e)}")
            if _has_debug_logger:
                DebugLogger.log_error(f"登录过程发生异常: {str(e)}")
            return False

    async def get_user_info(self) -> bool:
        """获取当前登录用户信息并存储"""
        try:
            if _has_debug_logger:
                DebugLogger.log_info("开始获取用户信息")

            resp = await Request.get("/api/mine", session=self.session)

            if _has_debug_logger:
                DebugLogger.log_data("获取用户信息响应", resp)

            if resp.get("data"):
                user_info = resp["data"]
                if save_user_info(user_info):
                    if _has_debug_logger:
                        safe_user_info = user_info.copy() if isinstance(user_info, dict) else user_info
                        DebugLogger.log_data("用户信息", safe_user_info)
                    return True
                else:
                    Log.error("缓存目录创建失败")
                    return False
            else:
                Log.error("获取用户信息失败")
                return False

        except CookiesExpiredError:
            raise
        except Exception as e:
            Log.error(f"获取用户信息失败: {str(e)}")
            raise NetworkError(f"获取用户信息失败: {str(e)}")

    async def get_user_bookstacks(self) -> Optional[Dict[str, Any]]:
        """获取个人知识库/团队知识库列表数据"""
        try:
            personal = is_personal()
            Log.info("开始获取知识库")

            target_api = self.config.yuque_book_stacks if personal else self.config.yuque_space_books_info
            
            resp = await Request.get(target_api, session=self.session)

            if resp.get("data"):
                data_wrap = resp["data"]

                if personal:
                    filtered_books_data = await self._gen_books_data_for_cache(data_wrap)
                else:
                    temp_books_data = [{"books": data_wrap}]
                    filtered_books_data = await self._gen_books_data_for_cache(temp_books_data)

                merged_books_data = []

                # 获取协作知识库
                try:
                    collab_books = await self.get_collab_books()
                    if collab_books:
                        merged_books_data.extend(collab_books)
                except Exception as e:
                    Log.warn(f"获取协作知识库失败: {str(e)}")

                merged_books_data.extend(filtered_books_data)

                if save_books_info(merged_books_data):
                    Log.success("知识库信息保存成功")
                    return {"books_info": merged_books_data}
                else:
                    Log.error("文件创建失败")
                    sys.exit(1)
            else:
                Log.error("获取知识库数据失败")
                return None

        except CookiesExpiredError:
            raise
        except Exception as e:
            Log.error(f"获取知识库失败: {str(e)}")
            raise NetworkError(f"获取知识库失败: {str(e)}")

    async def _gen_books_data_for_cache(self, data_wrap: Any) -> List[Dict[str, Any]]:
        """处理知识库数据，生成缓存数据
        
        Args:
            data_wrap (Any): 知识库数据
        """
        books_data = []
        try:
            if isinstance(data_wrap, list):
                for group in data_wrap:
                    if "books" in group:
                        for book in group["books"]:
                            book_item = self._format_book_item(book, "team")
                            books_data.append(book_item)
            else:
                for book in data_wrap:
                    book_item = self._format_book_item(book, "owner")
                    books_data.append(book_item)
        except Exception as e:
            Log.error(f"处理知识库数据失败: {str(e)}")
        return books_data

    def _format_book_item(self, book: Dict[str, Any], book_type: str) -> Dict[str, Any]:
        """格式化知识库数据"""
        return {
            "id": book.get("id", ""),
            "type": book.get("type", ""),
            "slug": book.get("slug", ""),
            "name": book.get("name", ""),
            "user_id": book.get("user_id", ""),
            "description": book.get("description", ""),
            "creator_id": book.get("creator_id", ""),
            "public": book.get("public", 0),
            "items_count": book.get("items_count", 0),
            "likes_count": book.get("likes_count", 0),
            "watches_count": book.get("watches_count", 0),
            "content_updated_at": book.get("content_updated_at", ""),
            "updated_at": book.get("updated_at", ""),
            "created_at": book.get("created_at", ""),
            "namespace": book.get("namespace", ""),
            "user": book.get("user", {}),
            "book_type": book_type,
        }

    async def get_collab_books(self) -> Optional[List[Dict[str, Any]]]:
        """获取协作知识库列表"""
        try:
            resp = await Request.get(self.config.yuque_collab_books_info, session=self.session)
            if resp.get("data"):
                collab_books = []
                for book in resp["data"]:
                    book_item = self._format_book_item(book, "collab")
                    collab_books.append(book_item)
                return collab_books
            return []
        except Exception as e:
            Log.warn(f"获取协作知识库失败: {str(e)}")
            return []

    async def get_book_docs(self, namespace: str) -> Optional[List[Dict[str, Any]]]:
        """获取知识库文档列表
        
        Args:
            namespace (str): 知识库命名空间
        """
        try:
            url = f"/{namespace}"
            text_content = await Request.get_text(url, is_html=True, session=self.session)
            
            # 使用 Parser 解析
            book_data = YuqueParser.parse_book_toc(text_content)

            if book_data and "book" in book_data and "toc" in book_data["book"]:
                toc_data = book_data["book"]["toc"]
                doc_list = []
                for item in toc_data:
                    slug = item.get('slug', '')
                    url_path = item.get('url', '')
                    
                    if not slug and url_path:
                        slug = YuqueParser.extract_slug_from_url(url_path) or ''
                    
                    if not slug and ('doc_uuid' in item or 'uuid' in item):
                         slug = item.get('doc_uuid') or item.get('uuid')

                    doc = {
                        "id": item.get("id", ""),
                        "slug": slug,
                        "title": item.get("title", ""),
                        "url": url_path,
                        "uuid": item.get("uuid", ""),
                        "type": item.get("type", "doc"),
                        "parent_uuid": item.get("parent_uuid", ""),
                        "level": item.get("level", 0),
                    }
                    doc_list.append(doc)
                
                # 请求获取额外 type信息
                try:
                    books_info = get_cache_books_info()
                    book_id = None
                    if books_info:
                        for b in books_info:
                            b_namespace = getattr(b, 'namespace', '')
                            b_user_login = b.user.get('login', '') if hasattr(b, 'user') and isinstance(b.user, dict) else ''
                            b_slug = getattr(b, 'slug', '')
                            # 尝试通过 namespace 或 user_login/slug 匹配
                            if b_namespace == namespace or (b_user_login and b_slug and f"{b_user_login}/{b_slug}" == namespace) or (not b_namespace and hasattr(b, 'user_login') and getattr(b, 'user_login') and b_slug and f"{getattr(b, 'user_login')}/{b_slug}" == namespace):
                                book_id = b.id
                                break
                    
                    if book_id:
                        docs_resp = await Request.get(f"{self.config.yuque_article_info}{book_id}", session=self.session)
                        if docs_resp and "data" in docs_resp and isinstance(docs_resp["data"], list):
                            type_map = {}
                            for d in docs_resp["data"]:
                                t = d.get("type")
                                if t:
                                    if d.get("slug"):
                                        type_map[str(d["slug"])] = t
                                    if d.get("id"):
                                        type_map[str(d["id"])] = t
                            
                            for doc in doc_list:
                                t = None
                                doc_id = doc.get("id")
                                doc_url = doc.get("url")
                                doc_slug = doc.get("slug")
                                
                                if doc_id: 
                                    t = t or type_map.get(str(doc_id))
                                if doc_url: 
                                    t = t or type_map.get(str(doc_url).strip('/'))
                                if doc_slug: 
                                    t = t or type_map.get(str(doc_slug))
                                    
                                if t:
                                    # 将从接口获取到的实际类型覆盖原有的 type
                                    doc["type"] = t

                except Exception as e:
                    Log.warn(f"获取知识库文档真实类型失败: {str(e)}")
                        
                return doc_list


        except CookiesExpiredError:
            raise
        except Exception as e:
            Log.error(f"获取知识库文档列表失败: {str(e)}")
            raise NetworkError(f"获取文档列表失败: {str(e)}")

    async def export_markdown(self, namespace: str, doc_identifier: str, line_break: bool = True) -> Optional[str]:
        """导出 Markdown
        
        Args:
            namespace: 知识库命名空间
            doc_identifier: 文档标识符
            line_break: 是否保留换行
        """
        try:
            parts = namespace.split('/')
            if len(parts) != 2:
                return None
            
            user_login, repo_slug = parts
            query = f"attachment=true&latexcode=false&anchor=false&linebreak={str(line_break).lower()}"
            
            target_doc_url = ""
            if doc_identifier.startswith('/'):
                target_doc_url = doc_identifier
            elif doc_identifier.startswith(user_login + '/' + repo_slug):
                target_doc_url = '/' + doc_identifier
            elif '/' in doc_identifier and not doc_identifier.startswith('/'):
                 target_doc_url = f"/{doc_identifier}"
            else:
                 target_doc_url = f"/{user_login}/{repo_slug}/{doc_identifier}"

            markdown_url = f"{target_doc_url}/markdown?{query}"
            
            try:
                # 尝试主要 URL
                resp = await Request.get_text(markdown_url, session=self.session)
                if resp and len(resp) > 10:
                    return resp
                
                # 尝试替代 URL
                if not target_doc_url.startswith(f"/{user_login}/{repo_slug}/"):
                    alt_url = f"/{user_login}/{repo_slug}/{doc_identifier}/markdown?{query}"
                    alt_resp = await Request.get_text(alt_url, session=self.session)
                    if alt_resp and len(alt_resp) > 10:
                        return alt_resp

                # 尝试 API URL
                api_url = f"/api/docs/{namespace}/{doc_identifier}/markdown"
                api_resp = await Request.get_text(api_url, session=self.session)
                if api_resp and len(api_resp) > 10:
                    return api_resp

            except Exception as e:
                Log.warn(f"获取Markdown失败")
            
            return None
        except Exception as e:
            Log.error(f"导出Markdown异常: {str(e)}")
            raise NetworkError(f"导出Markdown异常: {str(e)}")
    
    async def export_markdown_with_cookies(self, namespace: str, doc_identifier: str, cookies_str: str, line_break: bool = True) -> Optional[str]:
        """使用自定义Cookie导出 Markdown
        
        Args:
            namespace: 知识库命名空间
            doc_identifier: 文档标识符
            cookies_str: Cookie字符串,格式为 "name1=value1; name2=value2"
            line_break: 是否保留换行
        """
        try:
            parts = namespace.split('/')
            if len(parts) != 2:
                return None
            
            user_login, repo_slug = parts
            query = f"attachment=true&latexcode=false&anchor=false&linebreak={str(line_break).lower()}"
            
            target_doc_url = ""
            if doc_identifier.startswith('/'):
                target_doc_url = doc_identifier
            elif doc_identifier.startswith(user_login + '/' + repo_slug):
                target_doc_url = '/' + doc_identifier
            elif '/' in doc_identifier and not doc_identifier.startswith('/'):
                 target_doc_url = f"/{doc_identifier}"
            else:
                 target_doc_url = f"/{user_login}/{repo_slug}/{doc_identifier}"

            markdown_url = f"{target_doc_url}/markdown?{query}"
            
            try:
                # 使用自定义Cookie请求
                resp = await Request.get_text_with_cookies(markdown_url, cookies_str, session=self.session)
                if resp and len(resp) > 10:
                    return resp
                
                # 尝试替代 URL
                if not target_doc_url.startswith(f"/{user_login}/{repo_slug}/"):
                    alt_url = f"/{user_login}/{repo_slug}/{doc_identifier}/markdown?{query}"
                    alt_resp = await Request.get_text_with_cookies(alt_url, cookies_str, session=self.session)
                    if alt_resp and len(alt_resp) > 10:
                        return alt_resp

                # 尝试 API URL
                api_url = f"/api/docs/{namespace}/{doc_identifier}/markdown"
                api_resp = await Request.get_text_with_cookies(api_url, cookies_str, session=self.session)
                if api_resp and len(api_resp) > 10:
                    return api_resp

            except Exception as e:
                Log.warn(f"获取Markdown失败")
            
            return None
        except Exception as e:
            Log.error(f"导出Markdown异常: {str(e)}")
            raise NetworkError(f"导出Markdown异常: {str(e)}")


# 全局默认客户端
default_client = YuqueClient()

class YuqueApi:
    """语雀API静态方法封装类
    
    提供语雀API的静态方法调用，方便全局使用
    """
    
    @staticmethod
    async def login(username: str, password: str) -> bool:
        """登录账号"""
        return await default_client.login(username, password)

    @staticmethod
    async def get_user_info() -> bool:
        """获取用户信息"""
        return await default_client.get_user_info()

    @staticmethod
    async def get_user_bookstacks() -> Optional[Dict[str, Any]]:
        """获取用户知识库列表"""
        return await default_client.get_user_bookstacks()

    @staticmethod
    async def get_book_docs(namespace: str) -> Optional[List[Dict[str, Any]]]:
        """获取知识库文档列表"""
        return await default_client.get_book_docs(namespace)

    @staticmethod
    async def export_markdown(namespace: str, doc_identifier: str, line_break: bool = True) -> Optional[str]:
        """导出Markdown"""
        return await default_client.export_markdown(namespace, doc_identifier, line_break)

    @staticmethod
    async def get_collab_books() -> Optional[List[Dict[str, Any]]]:
        """获取协作知识库列表"""
        return await default_client.get_collab_books()
    
    @staticmethod
    async def crawl_book_toc_info(url: str) -> Optional[Dict[str, Any]]:
        """爬取知识库目录信息"""
        try:
             text_content = await Request.get_text(url, is_html=True)
             return YuqueParser.parse_book_toc(text_content)
        except:
             return None

import aiohttp
from typing import Dict, Any, List, Optional
from ..libs.constants import GLOBAL_CONFIG
from ..libs.encrypt import encrypt_password
from ..libs.log import Log
from ..libs.request import Request
from ..libs.tools import (
    is_personal, save_user_info, save_books_info,
    get_cache_books_info, resolve_book_namespace
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
                    Log.error("知识库缓存写入失败")
                    return {"books_info": merged_books_data, "cache_saved": False}
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
        namespace = resolve_book_namespace(book)
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
            "namespace": namespace,
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
                            b_namespace = resolve_book_namespace(b)
                            if b_namespace == namespace:
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



    async def export_excel(self, doc_id: str, file_path: str, cookies_str: str = "", is_table: bool = False) -> bool:
        """导出 Excel"""
        import asyncio
        import re
        import urllib.parse
        
        base_url = "https://www.yuque.com"
        export_url = f"{base_url}/api/docs/{doc_id}/export"
        
        cookies_dict = {}
        if cookies_str:
            for item in cookies_str.split('; '):
                if '=' in item:
                    name, value = item.split('=', 1)
                    cookies_dict[name] = value
        
        yuque_ctoken = ""
        loc_cookies = ""
        if cookies_dict:
            yuque_ctoken = cookies_dict.get("yuque_ctoken", "")
        else:
            from ..libs.tools import get_local_cookies
            loc_cookies = get_local_cookies()
            if loc_cookies:
                for item in loc_cookies.split('; '):
                    if '=' in item:
                        name, value = item.split('=', 1)
                        if name == "yuque_ctoken":
                            yuque_ctoken = value
        
        yuque_headers = {
            "Connection": "keep-alive",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": base_url,
            "Referer": "https://www.yuque.com/dashboard",
            "X-CSRF-Token": yuque_ctoken
        }
        
        if cookies_str:
            yuque_headers["Cookie"] = cookies_str
        elif loc_cookies:
            yuque_headers["Cookie"] = loc_cookies
        
        payload = {"type": "excel", "force": 0}
        
        session = await self._get_session()
        download_url_path = ""
        
        while True:
            try:
                req_kwargs = {"json": payload, "headers": yuque_headers}
                if cookies_dict:
                     req_kwargs["cookies"] = cookies_dict
                     
                async with session.post(export_url, **req_kwargs) as response:
                    response.raise_for_status()
                    res_data = await response.json()
                    state = res_data.get("data", {}).get("state")
                    
                    if state == "pending":
                        await asyncio.sleep(3)
                    elif state == "success":
                        download_url_path = res_data.get("data", {}).get("url")
                        break
                    else:
                        Log.error(f"Excel 导出未知状态: {res_data}")
                        return False
            except Exception as e:
                Log.error(f"Excel 导出请求错误: {e}")
                return False

        if download_url_path:
            full_download_url = base_url + download_url_path
            oss_direct_url = ""
            
            try:
                req_kwargs = {"allow_redirects": False, "headers": yuque_headers}
                if cookies_dict:
                    req_kwargs["cookies"] = cookies_dict
                async with session.get(full_download_url, **req_kwargs) as yuque_dl_resp:
                    if yuque_dl_resp.status in (301, 302):
                        oss_direct_url = yuque_dl_resp.headers.get("Location")
                    else:
                        Log.error(f"预期返回 302 跳转，但返回了 {yuque_dl_resp.status}")
                        return False
            except Exception as e:
                Log.error(f"获取 OSS 链接失败: {e}")
                return False

        if oss_direct_url:
            clean_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
                "Referer": "https://www.yuque.com/"
            }
            
            try:
                async with aiohttp.request("GET", oss_direct_url, headers=clean_headers) as dl_response:
                    dl_response.raise_for_status()
                    
                    with open(file_path, 'wb') as f:
                        async for chunk in dl_response.content.iter_chunked(8192):
                            if chunk:
                                f.write(chunk)
                return True
            except Exception as e:
                Log.error(f"写入 Excel 文件错误: {e}")
                return False
        return False

    async def export_board_png(self, url: str, file_path: str, cookies_str: str = "") -> bool:
        """使用 Playwright 导出 Board 画板为图片"""
        import asyncio
        import os
        from playwright.async_api import async_playwright
        
        parsed_cookies = []
        if cookies_str:
            for item in cookies_str.split('; '):
                if '=' in item:
                    name, value = item.split('=', 1)
                    parsed_cookies.append({
                        "name": name, "value": value, "domain": ".yuque.com", "path": "/"
                    })
        else:
            from ..libs.tools import get_local_cookies
            loc_cookies = get_local_cookies()
            if loc_cookies:
                 for item in loc_cookies.split('; '):
                    if '=' in item:
                        name, value = item.split('=', 1)
                        parsed_cookies.append({
                            "name": name, "value": value, "domain": ".yuque.com", "path": "/"
                        })

        async def intercept_assets(route):
            excluded_types = ["image", "media", "font", "tracking", "websocket"]
            if route.request.resource_type in excluded_types:
                await route.abort()
            else:
                await route.continue_()

        try:
            async with async_playwright() as p:
                browser_channel = None
                for ch in ["msedge", "chrome"]:
                    try:
                        temp_b = await p.chromium.launch(channel=ch)
                        await temp_b.close()
                        browser_channel = ch
                        break
                    except: continue

                browser = await p.chromium.launch(headless=True, channel=browser_channel)
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    device_scale_factor=1
                )
                if parsed_cookies:
                    await context.add_cookies(parsed_cookies)

                page = await context.new_page()
                
                try:
                    await page.goto(url, wait_until="networkidle", timeout=60000)
                    
                    svg_selector = ".lake-diagram-viewport-container svg"
                    await page.wait_for_selector(svg_selector, state="visible", timeout=40000)

                    rect = await page.evaluate('''
                        () => {
                            const svg = document.querySelector('.lake-diagram-viewport-container svg');
                            const rootGroup = document.querySelector('g[data-element="root_group"]');
                            if (!svg || !rootGroup) return null;

                            const bbox = rootGroup.getBBox();
                            const pad = 20; 
                            
                            const rect = {
                                x: bbox.x - pad,
                                y: bbox.y - pad,
                                w: Math.ceil(bbox.width + pad * 2),
                                h: Math.ceil(bbox.height + pad * 2)
                            };

                            document.body.innerHTML = '';
                            document.body.style.margin = '0';
                            document.body.style.padding = '0';
                            document.body.style.background = '#ffffff';
                            
                            svg.id = 'my-unique-export-target';
                            
                            svg.setAttribute('viewBox', `${rect.x} ${rect.y} ${rect.w} ${rect.h}`);
                            svg.style.width = `${rect.w}px`;
                            svg.style.height = `${rect.h}px`;
                            svg.style.display = 'block';
                            
                            document.body.appendChild(svg);
                            
                            return rect;
                        }
                    ''')

                    if not rect or rect['w'] <= 0 or rect['h'] <= 0:
                        return False

                    await page.set_viewport_size({"width": int(rect['w']), "height": int(rect['h'])})
                    await asyncio.sleep(0.5)

                    await page.locator("#my-unique-export-target").screenshot(path=file_path, animations="disabled")
                    return True

                except Exception as e:
                    Log.error(f"截图出错: {e}")
                    return False
                finally:
                    await page.close()
                    await browser.close()
        except Exception as e:
            Log.error(f"Playwright 启动失败: {e}")
            return False
        return False

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

    @staticmethod
    async def export_excel(doc_id: str, output_path: str, cookies_str: str = "", is_table: bool = False) -> bool:
        """导出 Excel"""
        return await default_client.export_excel(doc_id, output_path, cookies_str, is_table)

    @staticmethod
    async def export_board_png(url: str, output_path: str, cookies_str: str = "") -> bool:
        """导出 Board 画板为图片"""
        return await default_client.export_board_png(url, output_path, cookies_str)

import json
import re
import sys
import urllib.parse
from typing import Dict, Any, List, Optional

from ..libs.constants import GLOBAL_CONFIG
from ..libs.encrypt import encrypt_password
from ..libs.log import Log
from ..libs.request import Request
from ..libs.tools import (
    get_cache_user_info, is_personal,
    save_user_info, save_books_info
)

# 导入调试日志模块（如果启用调试模式）
try:
    from ..libs.debug_logger import DebugLogger

    _has_debug_logger = True
except ImportError:
    _has_debug_logger = False


class YuqueApi:
    """语雀API类"""

    @staticmethod
    async def login(username: str, password: str) -> bool:
        """登录语雀并存储cookies"""
        try:
            encrypted_password = encrypt_password(password)

            params = {
                "login": username,
                "password": encrypted_password,
                "loginType": "password"
            }

            if _has_debug_logger:
                # 不记录密码
                safe_params = params.copy()
                safe_params["password"] = "******"
                DebugLogger.log_info(f"尝试登录账号: {username}")
                DebugLogger.log_data("登录参数", safe_params)

            resp = await Request.post(GLOBAL_CONFIG.mobile_login, params)

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
                    sys.exit(1)
            else:
                return False

        except Exception as e:
            Log.error(f"登录失败: {str(e)}")
            if _has_debug_logger:
                DebugLogger.log_error(f"登录过程发生异常: {str(e)}")
            return False

    @staticmethod
    async def get_user_bookstacks() -> Optional[Dict[str, Any]]:
        """获取个人知识库/团队知识库列表数据"""
        try:
            personal = is_personal()
            Log.info("开始获取知识库")

            if _has_debug_logger:
                DebugLogger.log_info(f"获取知识库类型: {'个人' if personal else '团队'}")

            # 显示加载动画
            Log.info("正在获取知识库数据，请稍后...")

            target_api = GLOBAL_CONFIG.yuque_book_stacks if personal else GLOBAL_CONFIG.yuque_space_books_info

            if _has_debug_logger:
                DebugLogger.log_info(f"请求知识库API: {target_api}")

            resp = await Request.get(target_api)

            if _has_debug_logger:
                DebugLogger.log_data("知识库响应", resp)

            if resp.get("data"):
                data_wrap = resp["data"]

                if personal:
                    filtered_books_data = await YuqueApi._gen_books_data_for_cache(data_wrap)
                else:
                    # 构造一个 [{books:[...]}] 结构的数据
                    temp_books_data = [{"books": data_wrap}]
                    filtered_books_data = await YuqueApi._gen_books_data_for_cache(temp_books_data)

                if _has_debug_logger:
                    DebugLogger.log_data("过滤后的知识库数据", filtered_books_data)

                merged_books_data = []

                # 获取协作知识库
                try:
                    collab_books = await YuqueApi.get_collab_books()
                    if collab_books:
                        merged_books_data.extend(collab_books)
                        if _has_debug_logger:
                            DebugLogger.log_info(f"成功获取 {len(collab_books)} 个协作知识库")
                except Exception as e:
                    Log.warn(f"获取协作知识库失败: {str(e)}")
                    if _has_debug_logger:
                        DebugLogger.log_error(f"获取协作知识库异常: {str(e)}")

                # 添加主要知识库
                merged_books_data.extend(filtered_books_data)

                # 保存知识库信息
                if save_books_info(merged_books_data):
                    Log.success("知识库信息保存成功")
                    if _has_debug_logger:
                        DebugLogger.log_info(f"总共保存 {len(merged_books_data)} 个知识库")
                    return {"books_info": merged_books_data}
                else:
                    Log.error("文件创建失败")
                    sys.exit(1)
            else:
                Log.error("获取知识库数据失败")
                return None

        except Exception as e:
            Log.error(f"获取知识库失败: {str(e)}")
            if _has_debug_logger:
                DebugLogger.log_error(f"获取知识库异常: {str(e)}")
            return None

    @staticmethod
    async def _gen_books_data_for_cache(data_wrap: Any) -> List[Dict[str, Any]]:
        """生成用于缓存的知识库数据"""
        books_data = []

        try:
            if isinstance(data_wrap, list):
                # 处理团队知识库格式
                for group in data_wrap:
                    if "books" in group:
                        for book in group["books"]:
                            book_item = YuqueApi._format_book_item(book, "team")
                            books_data.append(book_item)
            else:
                # 处理个人知识库格式
                for book in data_wrap:
                    book_item = YuqueApi._format_book_item(book, "owner")
                    books_data.append(book_item)

        except Exception as e:
            Log.error(f"处理知识库数据失败: {str(e)}")

        return books_data

    @staticmethod
    def _format_book_item(book: Dict[str, Any], book_type: str) -> Dict[str, Any]:
        """格式化知识库项目"""
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
            "toc": book.get("toc", ""),
            "toc_yml": book.get("toc_yml", ""),
            "gitbook_token": book.get("gitbook_token", ""),
            "export_pdf_token": book.get("export_pdf_token", ""),
            "export_epub_token": book.get("export_epub_token", ""),
            "abilities": book.get("abilities", {}),
            "book_type": book_type,
            "docs": []
        }

    @staticmethod
    async def get_collab_books() -> Optional[List[Dict[str, Any]]]:
        """获取协作知识库"""
        try:
            resp = await Request.get(GLOBAL_CONFIG.yuque_collab_books_info)

            if resp.get("data"):
                collab_books = []
                for book in resp["data"]:
                    book_item = YuqueApi._format_book_item(book, "collab")
                    collab_books.append(book_item)
                return collab_books
            else:
                return []

        except Exception as e:
            Log.warn(f"获取协作知识库失败: {str(e)}")
            return []

    @staticmethod
    async def crawl_book_toc_info(url: str) -> Optional[Dict[str, Any]]:
        """爬取知识库页面获取目录信息"""
        try:
            # 打印调试信息
            Log.info(f"爬取页面 URL: {url}")

            try:
                text_content = await Request.get_text(url, is_html=True)
                Log.debug(f"页面内容长度: {len(text_content)}")
            except Exception as e:
                Log.error(f"获取页面内容失败: {str(e)}")
                return None

            # 尝试不同的正则表达式模式
            patterns = [
                r'decodeURIComponent\("([^"]+)"\)',
                r'window\.bookData\s*=\s*({.*?})\s*;',
                r'JSON\.parse\(decodeURIComponent\("([^"]+)"\)\)',
                r'window\.__INITIAL_STATE__\s*=\s*({.*?});',
                r'var\s+bookInfo\s*=\s*({.*?})\s*;'
            ]

            data = None
            for i, pattern in enumerate(patterns, 1):
                try:
                    matches = re.search(pattern, text_content, re.DOTALL)
                    if matches:
                        Log.debug(f"使用模式{i}找到匹配内容")

                        if "decodeURIComponent" in pattern:
                            # 需要URL解码
                            encoded_data = matches.group(1)
                            Log.debug(f"找到编码数据，长度: {len(encoded_data)}")
                            decoded_data = urllib.parse.unquote(encoded_data)
                            data = json.loads(decoded_data)
                        else:
                            # 直接是JSON字符串
                            json_str = matches.group(1)
                            Log.debug(f"找到JSON数据，长度: {len(json_str)}")
                            data = json.loads(json_str)

                        # 如果找到并解析成功，跳出循环
                        if data:
                            Log.debug(f"成功使用模式{i}解析知识库数据")
                            break
                except Exception as e:
                    Log.warn(f"模式{i}解析失败: {str(e)}", detailed=True)
                    continue

            if data:
                # 检查不同的数据结构格式
                if "book" in data and "toc" in data["book"]:
                    toc_count = len(data["book"]["toc"])
                    Log.debug(f"找到标准格式TOC，共 {toc_count} 个条目")
                    return data
                elif "toc" in data:
                    # 构造标准格式
                    toc_count = len(data["toc"])
                    Log.debug(f"找到替代格式TOC，共 {toc_count} 个条目")
                    return {"book": {"toc": data["toc"]}}
                elif "data" in data and "book" in data["data"]:
                    # API响应格式
                    Log.debug(f"找到API格式TOC")
                    if "toc" in data["data"]["book"]:
                        toc_data = data["data"]["book"]["toc"]
                        toc_count = len(toc_data)
                        Log.debug(f"共 {toc_count} 个条目")
                        return {"book": {"toc": toc_data}}

            # 如果所有模式都失败，尝试查找文档列表的替代方式
            try:
                # 使用HTML解析寻找目录结构
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(text_content, 'html.parser')

                # 查找侧边栏目录
                sidebar_items = soup.select('.catalog-item, .sidebar-item, .doc-catalog-item')
                if sidebar_items:
                    count = len(sidebar_items)
                    Log.debug(f"通过HTML解析找到 {count} 个目录项")
                    Log.info(f"通过HTML解析找到 {count} 个目录项")
                    toc = []
                    for item in sidebar_items:
                        link = item.select_one('a')
                        if link:
                            href = link.get('href', '')
                            title = link.text.strip()
                            # 提取slug
                            slug_match = re.search(r'/([^/]+)$', href)
                            slug = slug_match.group(1) if slug_match else ''

                            toc.append({
                                "title": title,
                                "slug": slug,
                                "type": "doc",
                                "url": href
                            })

                    if toc:
                        return {"book": {"toc": toc}}
            except ImportError:
                Log.warn("BeautifulSoup未安装，无法通过HTML解析查找目录", detailed=True)
            except Exception as e:
                Log.warn(f"HTML解析失败: {str(e)}", detailed=True)

            Log.warn(f"无法在页面中找到知识库数据: {url}")

            # 打印页面内容的一部分以便于调试
            preview_length = min(500, len(text_content))
            Log.debug(f"页面内容预览: {text_content[:preview_length]}...")

            return None

        except Exception as e:
            Log.error(f"爬取知识库页面失败: {str(e)}")
            return None

    @staticmethod
    async def get_book_docs(namespace: str) -> Optional[List[Dict[str, Any]]]:
        """获取知识库中的文档列表"""
        try:
            # 构建URL
            url = f"/{namespace}"

            Log.debug(f"获取知识库文档列表: {namespace}")
            Log.debug(f"请求URL: {url}")

            # 获取HTML页面内容
            response_text = await Request.get_text(url, is_html=True)

            Log.debug(f"爬取页面内容长度: {len(response_text)}")

            # 先尝试从页面中提取TOC数据
            book_data = await YuqueApi.crawl_book_toc_info(url)

            if book_data and "book" in book_data and "toc" in book_data["book"]:
                toc_data = book_data["book"]["toc"]

                if _has_debug_logger:
                    DebugLogger.log_data("解析得到的TOC数据", toc_data)

                # 转换TOC数据为文档列表格式
                doc_list = []
                for item in toc_data:
                    # 提取slug，有些情况下可能需要从URL中提取
                    slug = item.get('slug', '')
                    url_path = item.get('url', '')

                    Log.debug(f"处理文档项: 标题: {item.get('title', '')}, 原始slug: {slug}, 原始URL: {url_path}")

                    # 尝试从各种可能的字段获取slug
                    if not slug and url_path:
                        # 尝试从URL中提取slug
                        slug_match = re.search(r'/([^/]+)$', url_path)
                        if slug_match:
                            slug = slug_match.group(1)
                            Log.debug(f"从URL提取到slug: {slug}")

                    # 尝试从doc_uuid或者uuid字段构建slug
                    if not slug and ('doc_uuid' in item or 'uuid' in item):
                        doc_uuid = item.get('doc_uuid', '') or item.get('uuid', '')
                        if doc_uuid:
                            slug = doc_uuid
                            Log.debug(f"使用UUID作为slug: {slug}")

                    # 尝试从标题生成slug
                    if not slug and 'title' in item:
                        title = item.get('title', '')
                        if title:
                            # 使用标题转换为URL安全的字符串作为slug
                            import hashlib
                            slug = hashlib.md5(title.encode('utf-8')).hexdigest()[:8]
                            Log.debug(f"从标题生成slug: {slug}")

                    doc = {
                        "id": item.get("id", ""),
                        "slug": slug,
                        "title": item.get("title", ""),
                        "url": url_path,  # 确保使用原始URL
                        "uuid": item.get("uuid", ""),
                        "type": item.get("type", "doc"),
                        "parent_uuid": item.get("parent_uuid", ""),
                    }

                    if _has_debug_logger:
                        DebugLogger.log_data(f"处理后的文档项", doc)

                    doc_list.append(doc)

                return doc_list

            # 如果从页面提取失败，尝试从API获取
            Log.warn("从页面提取TOC失败，尝试从API获取", detailed=True)

            # 根据namespace构建API请求URL
            parts = namespace.split('/')
            if len(parts) != 2:
                Log.error(f"无效的知识库命名空间: {namespace}")
                return None

            api_url = f"/api/repos/{namespace}/toc"

            Log.debug(f"尝试从API获取TOC: {api_url}")

            try:
                api_response = await Request.get(api_url)

                if _has_debug_logger:
                    DebugLogger.log_data("API响应", api_response)

                if api_response and "data" in api_response:
                    raw_toc_data = api_response["data"]

                    Log.debug(f"API返回文档数量: {len(raw_toc_data)}")

                    # 转换API响应数据为所需格式
                    doc_list = []
                    for item in raw_toc_data:
                        doc = {
                            "id": item.get("id", ""),
                            "slug": item.get("slug", ""),
                            "title": item.get("title", ""),
                            "url": item.get("url", ""),
                            "uuid": item.get("uuid", ""),
                            "type": item.get("type", "doc"),
                            "parent_uuid": item.get("parent_uuid", ""),
                        }
                        doc_list.append(doc)

                    return doc_list
            except Exception as e:
                Log.error(f"API获取TOC失败: {str(e)}", detailed=True)
                if _has_debug_logger:
                    DebugLogger.log_error(f"API获取TOC异常: {str(e)}")

            Log.error(f"无法获取知识库 {namespace} 的文档列表")
            return None

        except Exception as e:
            Log.error(f"获取知识库文档列表失败: {str(e)}")
            if _has_debug_logger:
                DebugLogger.log_error(f"获取知识库文档列表异常: {str(e)}")
            return None

    @staticmethod
    async def get_doc_detail(namespace: str, slug: str) -> Optional[Dict[str, Any]]:
        """获取文档详情"""
        try:
            url = f"/api/repos/{namespace}/docs/{slug}"
            resp = await Request.get(url)

            if resp.get("data"):
                return resp["data"]
            else:
                Log.error(f"获取文档 {namespace}/{slug} 详情失败")
                return None

        except Exception as e:
            Log.error(f"获取文档详情失败: {str(e)}")
            return None

    @staticmethod
    async def export_markdown(namespace: str, doc_identifier: str, line_break: bool = True) -> Optional[str]:
        """导出文档为Markdown格式
        
        Args:
            namespace: 知识库命名空间，格式为 "user/repo"
            doc_identifier: 文档标识符，可以是完整URL路径或简单的slug
            line_break: 是否保留换行标识
        """
        try:
            if _has_debug_logger:
                DebugLogger.log_info(f"导出Markdown文档: {namespace}/{doc_identifier}")
                DebugLogger.log_info(
                    f"参数 - namespace: {namespace}, doc_identifier: {doc_identifier}, line_break: {line_break}")

            # 构建文档URL - 分解namespace以获取user和repo
            parts = namespace.split('/')
            if len(parts) != 2:
                Log.error(f"无效的知识库命名空间: {namespace}")
                if _has_debug_logger:
                    DebugLogger.log_error(f"无效的知识库命名空间: {namespace}")
                return None

            user_login, repo_slug = parts

            # 构建查询参数，与Rust版本保持一致
            query = f"attachment=true&latexcode=false&anchor=false&linebreak={str(line_break).lower()}"

            # 处理文档标识符 - 可能是URL路径或者slug
            target_doc_url = ""

            # 如果doc_identifier已经是完整的URL路径（如/xxx），直接使用
            if doc_identifier.startswith('/'):
                target_doc_url = doc_identifier
                Log.debug(f"使用完整URL路径: {target_doc_url}")

            # 如果包含完整的文档部分路径但缺少前导斜杠
            elif doc_identifier.startswith(user_login + '/' + repo_slug):
                target_doc_url = '/' + doc_identifier
                Log.debug(f"补全URL路径前导斜杠: {target_doc_url}")

            # 如果是相对路径但不以斜杠开头
            elif '/' in doc_identifier and not doc_identifier.startswith('/'):
                target_doc_url = f"/{doc_identifier}"
                Log.debug(f"转换相对路径为绝对路径: {target_doc_url}")

            # 如果只是简单的slug/标识符
            else:
                target_doc_url = f"/{user_login}/{repo_slug}/{doc_identifier}"
                Log.debug(f"构建完整URL: {target_doc_url}")

            # 构建完整的markdown导出URL
            markdown_url = f"{target_doc_url}/markdown?{query}"

            Log.debug(f"最终Markdown URL: {markdown_url}")

            try:
                resp = await Request.get_text(markdown_url)

                if _has_debug_logger:
                    preview = resp[:200] + "..." if len(resp) > 200 else resp
                    DebugLogger.log_info(f"Markdown内容长度: {len(resp)}")
                    DebugLogger.log_data("Markdown内容预览", preview)

                if resp and len(resp) > 10:  # 内容至少有一定长度才算有效
                    # 对内容进行后处理
                    # 1. 处理图片链接
                    resp = YuqueApi._process_image_links(resp)

                    # 2. 处理附件链接
                    resp = YuqueApi._process_attachment_links(resp)

                    return resp
                else:
                    Log.warn(f"获取到的Markdown内容可能为空: {markdown_url}", detailed=True)
                    if _has_debug_logger:
                        DebugLogger.log_warning(f"获取到的Markdown内容长度不足: {len(resp)}")

                    # 如果失败，尝试使用替代方法构建URL
                    if not target_doc_url.startswith(f"/{user_login}/{repo_slug}/"):
                        alt_url = f"/{user_login}/{repo_slug}/{doc_identifier}/markdown?{query}"

                        Log.debug(f"尝试替代URL: {alt_url}")

                        alt_resp = await Request.get_text(alt_url)

                        if _has_debug_logger:
                            alt_preview = alt_resp[:200] + "..." if len(alt_resp) > 200 else alt_resp
                            DebugLogger.log_info(f"替代URL响应长度: {len(alt_resp)}")
                            DebugLogger.log_data("替代URL响应预览", alt_preview)

                        if alt_resp and len(alt_resp) > 10:
                            # 处理图片和附件链接
                            alt_resp = YuqueApi._process_image_links(alt_resp)
                            alt_resp = YuqueApi._process_attachment_links(alt_resp)
                            return alt_resp
            except Exception as e:
                Log.warn(f"获取Markdown失败: {str(e)}", detailed=True)
                if _has_debug_logger:
                    DebugLogger.log_error(f"获取Markdown异常: {str(e)}")

            # 最后尝试API直接路径
            try:
                api_url = f"/api/docs/{namespace}/{doc_identifier}/markdown"

                Log.debug(f"尝试API直接路径: {api_url}")

                api_resp = await Request.get_text(api_url)

                if _has_debug_logger:
                    api_preview = api_resp[:200] + "..." if len(api_resp) > 200 else api_resp
                    DebugLogger.log_info(f"API路径响应长度: {len(api_resp)}")
                    DebugLogger.log_data("API路径响应预览", api_preview)

                if api_resp and len(api_resp) > 10:
                    # 处理图片和附件链接
                    api_resp = YuqueApi._process_image_links(api_resp)
                    api_resp = YuqueApi._process_attachment_links(api_resp)
                    return api_resp
            except Exception as e:
                Log.warn(f"API路径获取失败: {str(e)}", detailed=True)
                if _has_debug_logger:
                    DebugLogger.log_error(f"API路径获取异常: {str(e)}")

            Log.error(f"无法导出文档 {namespace}/{doc_identifier} 的Markdown内容")
            return "无法获取文档内容，可能需要登录后才能访问或文档已被删除。"

        except Exception as e:
            Log.error(f"导出Markdown失败: {str(e)}")
            if _has_debug_logger:
                DebugLogger.log_error(f"导出Markdown异常: {str(e)}")
            return None

    @staticmethod
    async def download_attachment(url: str, file_path: str) -> bool:
        """下载附件"""
        try:
            return await Request.download_file(url, file_path)
        except Exception as e:
            Log.error(f"下载附件失败: {str(e)}")
            return False

    @staticmethod
    async def get_user_info() -> Optional[Dict[str, Any]]:
        """获取用户信息"""
        try:
            # 先尝试从缓存获取
            cached_user = get_cache_user_info()
            if cached_user:
                return {
                    "name": cached_user.name,
                    "login": cached_user.login
                }

            # 如果缓存没有，从API获取
            resp = await Request.get("/api/user")
            if resp.get("data"):
                user_info = resp["data"]
                save_user_info(user_info)
                return user_info
            else:
                return None

        except Exception as e:
            Log.error(f"获取用户信息失败: {str(e)}")
            return None

    @staticmethod
    def _process_image_links(content: str) -> str:
        """处理Markdown中的图片链接，保留原始链接"""
        if not content:
            return content

        # 使用正则表达式识别并替换图片链接
        # 标准Markdown格式：![alt](url)
        # 实现时保留原始URL，不做下载处理

        return content

    @staticmethod
    def _process_attachment_links(content: str) -> str:
        """处理Markdown中的附件链接，保留原始链接"""
        if not content:
            return content

        # 使用正则表达式识别并替换附件链接
        # 标准Markdown格式：[name](url)
        # 实现时保留原始URL，不做下载处理

        return content

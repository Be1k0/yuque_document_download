import os
import asyncio
from PyQt6.QtCore import pyqtSignal
from src.core.yuque import YuqueClient
from src.core.scheduler import Scheduler
from src.core.parsers import YuqueParser
from src.libs.request import Request
from src.libs.file import File
from src.libs.tools import format_filename, ensure_dir_exists, save_cookies
from src.libs.log import Log
from gui.controllers.base_controller import BaseController

class CustomUrlController(BaseController):
    """公开知识库导出解析控制器
    
    负责处理用户输入公开知识库链接的解析和下载流程。
    """
    
    # 信号
    parse_started = pyqtSignal()
    browser_launched = pyqtSignal()
    parse_finished = pyqtSignal(list)
    parse_failed = pyqtSignal(str)
    
    download_started = pyqtSignal()
    download_progress = pyqtSignal(str)
    download_progress_update = pyqtSignal(int, int)
    download_finished = pyqtSignal()
    
    
    def __init__(self):
        super().__init__()
        self.scheduler = Scheduler()
        self.browser = None
        self.playwright = None
        self.context = None
        self.page = None
        self._waiting_for_user = False
        self._temp_cookies = None
        
        # 下载统计
        self._downloaded_count = 0
        self._skipped_count = 0
        self._failed_count = 0

    async def start_parse(self, url: str, password: str = ""):
        """开始解析流程
        
        Args:
            url: 知识库链接
            password: 知识库密码 (4位a-z0-9)，如果为空则表示需要作为无密码获取
        """
        self.parse_started.emit()
        
        if not url:
            self.parse_failed.emit("URL不能为空")
            return

        try:
            if password:
                # 提供了密码，走接口自动验证流程
                await self._fetch_with_password(url, password)
            else:
                # 无密码，直接获取公开知识库内容
                await self._fetch_without_login(url)
        except Exception as e:
            self.log_error("启动解析失败", e)
            self.parse_failed.emit(f"启动解析失败: {str(e)}")

    async def _launch_browser(self, url: str):
        """启动浏览器并访问URL
                
        Args:
            url: 要访问的知识库链接
        """
        try:
            from playwright.async_api import async_playwright
            
            # 设置浏览器路径
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
            
            self.playwright = await async_playwright().start()
            
            # 按优先级尝试不同的浏览器
            browser_channels = ["msedge", "chrome", "360chrome", "qqbrowser", "brave", None]
            
            for channel in browser_channels:
                try:
                    if channel:
                        self.browser = await self.playwright.chromium.launch(headless=False, channel=channel)
                    else:
                        self.browser = await self.playwright.chromium.launch(headless=False)
                    
                    if self.browser:
                        self.log_info(f"成功启动浏览器: {channel or '默认'}")
                        break
                except:
                    continue
            
            if not self.browser:
                self.parse_failed.emit("未检测到适配的浏览器,请安装Edge或Chrome")
                await self._cleanup_browser()
                return

            self.context = await self.browser.new_context()
            self.page = await self.context.new_page()
            
            try:
                await self.page.goto(url, timeout=60000)
            except Exception as e:
                self.log_error(f"访问页面出错: {e}")
            
            self._waiting_for_user = True
            self.log_info("浏览器已启动，请在浏览器中输入知识库密码...")
            self.browser_launched.emit() 
            
            # 自动检测状态
            max_retries = 30 # 5分钟超时
            check_interval = 10 # 10秒检测一次
            
            for _ in range(max_retries):
                if not self.context or not self.page:
                    self.log_info("浏览器已关闭，停止检测")
                    return

                try:
                    if self.page.is_closed():
                        self.log_info("页面已关闭")
                        break
                        
                    # 进行简单的URL匹配
                    current_url = self.page.url
                    
                    # 尝试解析TOC结构来判断是否成功加载了知识库内容
                    if "login" not in current_url and "account" not in current_url:
                        content = await self.page.content()
                        book_data = YuqueParser.parse_book_toc(content)
                        if book_data:
                            self.log_success("检测到知识库内容，加载成功！")

                            # 获取 Cookies
                            cookies = await self.context.cookies()
                            cookies_dict = {c['name']: c['value'] for c in cookies}
                            self._temp_cookies = cookies_dict
                            self.log_info("已在缓存Cookie")
                            
                            await self._cleanup_browser()
                            await self._parse_content(content, cookies_dict, url)

                            return
                        
                except Exception as e:
                    self.log_error(f"发生错误: {e}")
                    pass
                
                await asyncio.sleep(check_interval)
            
            if self.browser:
                self.log_error("输入密码超时或未检测到有效内容")
                self.parse_failed.emit("输入密码超时或未检测到有效内容")
                await self._cleanup_browser()

        except ImportError:
             self.parse_failed.emit("未安装 playwright，请先安装: pip install playwright")
        except Exception as e:
             self.parse_failed.emit(f"浏览器启动失败: {str(e)}")
             await self._cleanup_browser()

    async def continue_after_login(self, source_url: str):
        """用户输入密码后继续
        
        Args:            
            source_url: 用户输入密码的知识库链接,用于提取namespace
        """
        if not self._waiting_for_user or not self.page:
            return

        try:
            self._waiting_for_user = False
            
            # 获取 Cookies
            cookies = await self.context.cookies()
            cookies_dict = {c['name']: c['value'] for c in cookies}
            self._temp_cookies = cookies_dict
            self.log_info("已在缓存Cookie")

            # 获取页面内容
            content = await self.page.content()
            
            await self._cleanup_browser()
            await self._parse_content(content, cookies_dict, source_url)
            
        except Exception as e:
            self.parse_failed.emit(f"获取数据失败: {str(e)}")
            await self._cleanup_browser()

    async def _fetch_without_login(self, url: str):
        """不登录直接解析失败公开知识库内容
        
        Args:
            url: 知识库链接
        """
        try:
            # 使用空 Cookie 获取页面内容
            self.log_info("正在解析公开知识库内容...")
            content = await Request.get_text_with_cookies(url, "", is_html=True)
            self._temp_cookies = {}
            
            await self._parse_content(content, {}, url)
        except Exception as e:
            error_msg = str(e)
            if "<html>" in error_msg.lower() or "<body" in error_msg.lower():
                error_msg = "解析失败,可能是无效链接或知识库需要密码"
            
            self.log_error("解析失败", error_msg)
            self.parse_failed.emit(f"解析失败: {error_msg}")

    async def _fetch_with_password(self, url: str, password: str):
        """带密码自动接口解析
        
        使用接口校验密码并获取 Cookie 来进行解析
        
        Args:
            url: 知识库链接
            password: 4位数的密码
        """
        try:
            # 发起初始GET获取需要知识库ID
            import re
            import json
            from src.libs.encrypt import encrypt_password
            
            content = await Request.get_text_with_cookies(url, "", is_html=True)
            
            target_id = None
            
            # 使用正则解析 window.appData 提取 targetId 
            match = re.search(r'window\.appData\s*=\s*JSON\.parse\(decodeURIComponent\("([^"]+)"\)\);', content)
            if match:
                app_data_str = __import__('urllib.parse').parse.unquote(match.group(1))
                app_data = json.loads(app_data_str)
                
                # 从匹配条件中获取
                target_id = app_data.get('matchCondition', {}).get('needVerifyTargetId')
                
                if not target_id:
                    target_id = app_data.get('book', {}).get('id') or app_data.get('needVerifyTargetId')
            
            if not target_id:
                raise Exception("无法提取知识库ID。该分享内容可能已失效。")

            # RSA 加密用户提供的密码
            self.log_info(f"提取知识库ID成功: {target_id}")
            encrypted_password = encrypt_password(password)

            # 发送验证请求
            self.log_info("发起密码验证请求...")
            verify_url = f"/api/books/{target_id}/verify"
            payload = {"password": encrypted_password}
            
            try:
                verify_resp, response_cookies = await Request.put(verify_url, payload, persist_cookies=False, return_cookies=True)
            except Exception as req_e:
                error_body = str(req_e)
                if "400" in error_body:
                    raise Exception("知识库密码错误或验证不通过")
                else:
                    raise req_e
            
            self._temp_cookies = {}
            if response_cookies:
                for k, v in response_cookies.items():
                    k = k.strip()
                    # 过滤 _yuque_session，因为带密码的公开知识库一旦携带该字段会导致解析失败
                    if k != '_yuque_session':
                         self._temp_cookies[k] = v.strip()

            filtered_cookies_str = "; ".join([f"{k}={v}" for k, v in self._temp_cookies.items()])

            self.log_info("密码验证通过")
            final_content = await Request.get_text_with_cookies(url, filtered_cookies_str, is_html=True)
            
            await self._parse_content(final_content, self._temp_cookies, url)

        except Exception as e:
            error_msg = str(e)
            self.log_error("带密码知识库解析失败", error_msg)
            self.parse_failed.emit(f"密码解析失败: {error_msg}")

    async def _cleanup_browser(self):
        """清理浏览器资源"""
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
        self.context = None
        self.page = None

    async def _parse_content(self, content: str, cookies: dict, source_url: str):
        """解析页面内容,提取文档列表
        
        Args:
            content: 页面HTML内容
            cookies: Cookie字典
            source_url: 源URL,用于提取namespace
        """
        try:
            self.log_info("正在解析知识库目录...")
            book_data = YuqueParser.parse_book_toc(content)
            
            # 从URL中提取namespace
            from urllib.parse import urlparse
            parsed = urlparse(source_url)
            path_parts = parsed.path.strip('/').split('/')
            namespace = "unknown/unknown"
            if len(path_parts) >= 2:
                namespace = f"{path_parts[0]}/{path_parts[1]}"
            
            doc_list = []
            # 从解析结果中提取文档列表
            if book_data and "book" in book_data and "toc" in book_data["book"]:
                toc = book_data["book"]["toc"]
                
                for item in toc:
                    # 提取文档slug
                    slug = item.get('slug', '')
                    url_path = item.get('url', '')
                    
                    # 如果没有slug,尝试从URL中提取
                    if not slug and url_path:
                        slug = YuqueParser.extract_slug_from_url(url_path) or ''
                    
                    if not slug and ('doc_uuid' in item or 'uuid' in item):
                            slug = item.get('doc_uuid') or item.get('uuid')

                    # 构建文档信息
                    doc = {
                        "id": item.get("id", ""),
                        "slug": slug,
                        "title": item.get("title", ""),
                        "url": url_path,
                        "uuid": item.get("uuid", ""),
                        "type": item.get("type", "doc"),
                        "parent_uuid": item.get("parent_uuid", ""),
                        "level": item.get("level", 0),
                        "namespace": namespace,
                        "_cookies": cookies
                    }
                    doc_list.append(doc)
                
                # 获取文档真实类型
                book_id = book_data["book"].get("id")
                if book_id:
                    try:
                        import json
                        cookies_str = "; ".join([f"{k}={v}" for k, v in cookies.items()]) if cookies else ""
                        api_url = f"/api/docs?book_id={book_id}"
                        docs_resp_text = await Request.get_text_with_cookies(api_url, cookies_str, is_html=False)
                        docs_resp = json.loads(docs_resp_text)
                        
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
                                
                                if doc_id: t = t or type_map.get(str(doc_id))
                                if doc_url: t = t or type_map.get(str(doc_url).strip('/'))
                                if doc_slug: t = t or type_map.get(str(doc_slug))
                                
                                if t:
                                    doc["type"] = t
                    except Exception as e:
                        self.log_error(f"获取知识库文档真实类型失败: {e}")
                
                self.log_success(f"成功解析 {len(doc_list)} 篇文档")
                self.parse_finished.emit(doc_list)
            else:
                self.log_error("解析失败,未能解析出目录结构")
                self.parse_failed.emit("解析失败,请检查知识库是否需要密码或链接失效")
                
        except Exception as e:
            error_msg = str(e)
            # 截断过长的错误信息
            if len(error_msg) > 200:
                error_msg = error_msg[:200] + "..."
                
            self.log_error("解析内容失败", error_msg)
            self.parse_failed.emit(f"解析内容失败: {error_msg}")

    async def download_docs(self, docs: list, output_dir: str, options: dict = None):
        """下载选中的文档
        
        Args:
            docs: 文档列表
            output_dir: 输出目录
            options: 导出选项字典
                - skip: 是否跳过已存在的文件
                - linebreak: 是否保留换行标识
                - download_images: 是否下载图片
        """
        options = options or {}
        skip_existing = options.get("skip", True)
        linebreak = options.get("linebreak", True)
        download_images = options.get("download_images", True)
        
        # 重置统计计数器
        self._downloaded_count = 0
        self._skipped_count = 0
        self._failed_count = 0

        self.download_started.emit()
        self.log_info(f"开始下载 {len(docs)} 篇文档到 {output_dir}")
        self.download_progress.emit(f"开始下载 {len(docs)} 篇文档...")
        self.download_progress_update.emit(0, len(docs))
        
        try:
            ensure_dir_exists(output_dir)
            
            # 构建文档层级映射表
            level_map = {}
            for doc in docs:
                uuid = doc.get('uuid', '')
                if uuid:
                    level_map[uuid] = {
                        'title': doc.get('title', ''),
                        'level': doc.get('level', 0),
                        'type': doc.get('type', 'DOC'),
                        'parent_uuid': doc.get('parent_uuid', '')
                    }

            # 准备图片下载器
            image_downloader = None
            if download_images:
                from src.libs.threaded_image_downloader import ThreadedImageDownloader
                image_downloader = ThreadedImageDownloader(max_workers=10, progress_callback=None)

            # 使用 YuqueClient 下载文档内容
            if self._temp_cookies is not None:
                if self._temp_cookies:
                    self.log_info("使用缓存Cookie进行下载")
                else:
                    self.log_info("使用空Cookie进行下载")
                    
                cookies_str = "; ".join([f"{name}={value}" for name, value in self._temp_cookies.items()])
                
                async with YuqueClient() as client:
                    await self._download_docs_with_custom_cookies(client, docs, output_dir, skip_existing, linebreak, download_images, image_downloader, cookies_str, level_map)
            else:
                async with YuqueClient() as client:
                    await self._download_docs_with_client(client, docs, output_dir, skip_existing, linebreak, download_images, image_downloader, level_map)

        except Exception as e:
            self.log_error(f"下载过程出错: {str(e)}")
            self.download_progress.emit(f"下载过程出错: {str(e)}")
            self.download_finished.emit()
    
    async def _download_docs_with_client(self, client, docs, output_dir, skip_existing, linebreak, download_images, image_downloader, level_map):
        """使用指定的client下载文档
        
        Args:
            client: 已登录的YuqueClient实例
            docs: 文档列表
            output_dir: 输出目录
            skip_existing: 是否跳过已存在的文件
            linebreak: 是否保留换行标识
            download_images: 是否下载图片
            image_downloader: 图片下载器实例
            level_map: 层级映射表
        """
        total = len(docs)
        for i, doc in enumerate(docs, 1):
            title = doc.get("title", "Untitled")
            slug = doc.get("slug", "")
            url = doc.get("url", "")
            
            identifier = url if url else slug
            if not identifier:
                continue
                
            doc_type = doc.get('type', '')
            if doc_type and doc_type.upper() != 'DOC' and doc_type.lower() != 'document':
                self.log_info(f"跳过非文档条目: {title}")
                self.download_progress.emit(f"跳过非文档 ({i}/{total}): {title}")
                self.download_progress_update.emit(i, total)
                self._skipped_count += 1
                continue
                
            # 根据层级计算目标文件夹
            target_dir = output_dir
            parent_uuid = doc.get('parent_uuid', '')
            if parent_uuid and parent_uuid in level_map:
                path_parts = self._build_doc_path(parent_uuid, level_map)
                if path_parts:
                    target_dir = os.path.join(output_dir, *path_parts)
                    ensure_dir_exists(target_dir)

            filename = format_filename(title) + ".md"
            file_path = os.path.join(target_dir, filename)

            # 跳过已存在的文件
            if skip_existing:
                skip_it = False
                if os.path.exists(file_path):
                    skip_it = True
                else:
                    folder_name = os.path.splitext(filename)[0]
                    subdir_file_path = os.path.join(target_dir, folder_name, filename)
                    if os.path.exists(subdir_file_path):
                        skip_it = True
                
                if skip_it:
                    self.log_info(f"跳过已存在: {title}")
                    self.download_progress.emit(f"跳过 ({i}/{total}): {title}")
                    self.download_progress_update.emit(i, total)
                    self._skipped_count += 1  # 更新跳过计数
                    continue

            # 获取namespace
            namespace = doc.get("namespace", "unknown/unknown")

            try:
                self.download_progress.emit(f"正在下载 ({i}/{total}): {title}")
                
                # 导出 Markdown
                content = await client.export_markdown(namespace, identifier, line_break=linebreak)
                
                if content:
                    # 保存文件
                    File().write(file_path, content)
                    self.log_success(f"已保存: {title}")
                    self._downloaded_count += 1  # 更新成功计数
                    
                    # 下载图片
                    if download_images and image_downloader:
                        self.download_progress.emit(f"正在处理图片 ({i}/{total}): {title}")
                        await asyncio.to_thread(
                            image_downloader.process_single_file,
                            md_file_path=file_path,
                            image_url_prefix='',
                            image_rename_mode='asc'
                        )
                    
                    self.download_progress.emit(f"完成 ({i}/{total}): {title}")
                else:
                    self.log_error(f"导出失败: {title}")
                    self.download_progress.emit(f"失败 ({i}/{total}): {title}")
                    self._failed_count += 1  # 更新失败计数
                    
            except Exception as e:
                self.log_error(f"处理文档失败: {title}", e)
                self.download_progress.emit(f"错误 ({i}/{total}): {title}")
                self._failed_count += 1  # 更新失败计数
            
            self.download_progress_update.emit(i, total)
        
        self.log_success("所有任务处理完成")
        self.download_progress.emit("下载完成!")
        self.download_progress_update.emit(total, total)
        
        # 发送统计信息
        self._emit_download_stats()
    
    async def _download_docs_with_custom_cookies(self, client, docs, output_dir, skip_existing, linebreak, download_images, image_downloader, cookies_str, level_map):
        """使用自定义Cookie字符串下载文档
        
        Args:
            client: 已登录的YuqueClient实例
            docs: 文档列表
            output_dir: 输出目录
            skip_existing: 是否跳过已存在的文件
            linebreak: 是否保留换行标识
            download_images: 是否下载图片
            image_downloader: 图片下载器实例
            cookies_str: 自定义Cookie字符串
            level_map: 层级映射表
        """
        total = len(docs)
        for i, doc in enumerate(docs, 1):
            title = doc.get("title", "Untitled")
            slug = doc.get("slug", "")
            url = doc.get("url", "")
            
            identifier = url if url else slug
            if not identifier:
                continue
                
            doc_type = doc.get('type', '')
            if doc_type and doc_type.upper() != 'DOC' and doc_type.lower() != 'document':
                self.log_info(f"跳过非文档条目: {title}")
                self.download_progress.emit(f"跳过非文档 ({i}/{total}): {title}")
                self.download_progress_update.emit(i, total)
                self._skipped_count += 1
                continue
                
            # 根据层级计算目标文件夹
            target_dir = output_dir
            parent_uuid = doc.get('parent_uuid', '')
            if parent_uuid and parent_uuid in level_map:
                path_parts = self._build_doc_path(parent_uuid, level_map)
                if path_parts:
                    target_dir = os.path.join(output_dir, *path_parts)
                    ensure_dir_exists(target_dir)

            filename = format_filename(title) + ".md"
            file_path = os.path.join(target_dir, filename)

            # 跳过已存在的文件
            if skip_existing:
                skip_it = False
                if os.path.exists(file_path):
                    skip_it = True
                else:
                    folder_name = os.path.splitext(filename)[0]
                    subdir_file_path = os.path.join(target_dir, folder_name, filename)
                    if os.path.exists(subdir_file_path):
                        skip_it = True
                
                if skip_it:
                    self.log_info(f"跳过已存在: {title}")
                    self.download_progress.emit(f"跳过 ({i}/{total}): {title}")
                    self.download_progress_update.emit(i, total)
                    self._skipped_count += 1  # 更新跳过计数
                    continue

            # 获取namespace
            namespace = doc.get("namespace", "unknown/unknown")

            try:
                self.download_progress.emit(f"正在下载 ({i}/{total}): {title}")
                
                # 使用自定义Cookie导出 Markdown
                content = await client.export_markdown_with_cookies(namespace, identifier, cookies_str, line_break=linebreak)
                
                if content:
                    # 保存文件
                    File().write(file_path, content)
                    self.log_success(f"已保存: {title}")
                    self._downloaded_count += 1  # 更新成功计数
                    
                    # 下载图片
                    if download_images and image_downloader:
                        self.download_progress.emit(f"正在处理图片 ({i}/{total}): {title}")
                        await asyncio.to_thread(
                            image_downloader.process_single_file,
                            md_file_path=file_path,
                            image_url_prefix='',
                            image_rename_mode='asc'
                        )
                    
                    self.download_progress.emit(f"完成 ({i}/{total}): {title}")
                else:
                    self.log_error(f"导出失败: {title}")
                    self.download_progress.emit(f"失败 ({i}/{total}): {title}")
                    self._failed_count += 1  # 更新失败计数
                    
            except Exception as e:
                self.log_error(f"处理文档失败: {title}", e)
                self.download_progress.emit(f"错误 ({i}/{total}): {title}")
                self._failed_count += 1  # 更新失败计数
            
            self.download_progress_update.emit(i, total)
        
        self.log_success("所有任务处理完成")
        self.download_progress.emit("下载完成!")
        self.download_progress_update.emit(total, total)
        
        # 发送统计信息
        self._emit_download_stats()
    
    def _emit_download_stats(self):
        """发送下载统计信息"""
        stats_msg = f"下载完成!\n成功: {self._downloaded_count}\n跳过: {self._skipped_count}\n失败: {self._failed_count}"
        self.log_info(stats_msg.replace('\n', ', '))
        self.download_finished.emit()

    def _build_doc_path(self, uuid: str, level_map: dict) -> list:
        """根据 parent_uuid 递归构建文档的相对路径列表"""
        if uuid not in level_map:
            return []
        doc_info = level_map[uuid]
        doc_type = doc_info.get('type', 'DOC')
        if doc_type.upper() not in ['TITLE', 'DOC']:
            return []
        
        title = format_filename(doc_info['title'])
        parent_uuid = level_map.get(uuid, {}).get('parent_uuid', '')
        parent_path = self._build_doc_path(parent_uuid, level_map)
        return parent_path + [title]

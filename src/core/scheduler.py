import asyncio
import os
from typing import Dict, Any
from .yuque import default_client, YuqueClient
from ..libs.constants import GLOBAL_CONFIG, MutualAnswer
from ..libs.file import File
from ..libs.log import Log
from ..libs.tools import (
    get_cache_books_info, format_filename, ensure_dir_exists
)
from ..libs.error_handler import ErrorHandler

class Scheduler:
    """下载调度器类
    
    提供下载任务调度功能，管理下载流程和并发控制
    """
    
    def __init__(self, client: YuqueClient = None):
        self.client = client or default_client
        self.concurrency = 5

    async def start_download_task(self, answer: MutualAnswer) -> None:
        """开始下载任务
        
        Args:
            answer: 包含下载选项和回调的 MutualAnswer 对象
        """
        try:
            books_info = get_cache_books_info()
            if not books_info:
                Log.error("无法获取知识库信息")
                return

            # 过滤选中的知识库
            selected_books = []
            for book in books_info:
                if book.name in answer.toc_range:
                    selected_books.append(book)

            if not selected_books:
                Log.error("未找到选中的知识库")
                return

            Log.info(f"开始下载 {len(selected_books)} 个知识库")

            # 确保输出目录存在
            output_dir = GLOBAL_CONFIG.target_output_dir
            ensure_dir_exists(output_dir)

            # 下载每个知识库 (知识库之间串行，文档并行)
            for book in selected_books:
                await self._download_book(book, output_dir, answer)

            Log.success("所有知识库下载完成！")

        except Exception as e:
            Log.error(f"下载任务失败: {str(e)}")
            if type(e).__name__ == "CookiesExpiredError":
                raise

    @ErrorHandler.async_error_handler("下载知识库", reraise=False)
    async def _download_book(self, book: Any, output_dir: str, answer: MutualAnswer) -> None:
        """下载单个知识库
        
        Args:
            book: 知识库对象
            output_dir: 输出目录路径
            answer: 包含下载选项和回调的 MutualAnswer 对象
        """
        Log.info(f"开始下载知识库: {book.name}")

        # 创建知识库目录
        book_dir = os.path.join(output_dir, format_filename(book.name))
        ensure_dir_exists(book_dir)

        namespace = ""

        # 获取知识库的命名空间
        if hasattr(book, 'namespace') and book.namespace:
            namespace = book.namespace
        elif hasattr(book, 'user_login') and hasattr(book, 'slug'):
            namespace = f"{book.user_login}/{book.slug}"
        
        # 兼容旧版本数据结构
        if not namespace and hasattr(book, 'user') and hasattr(book, 'slug'):
            if isinstance(book.user, dict) and 'login' in book.user:
                namespace = f"{book.user['login']}/{book.slug}"

        if not namespace:
            Log.error(f"知识库 {book.name} 缺少必要的命名空间信息")
            return

        Log.info(f"知识库命名空间: {namespace}")

        # 获取知识库的文档列表
        docs = await self.client.get_book_docs(namespace)
        if not docs:
            Log.warn(f"知识库 {book.name} 没有文档")
            return

        Log.info(f"知识库 {book.name} 共有 {len(docs)} 个文档")

        # 构建层级映射表
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

        # 筛选文档
        filtered_docs = docs
        if answer.selected_docs and book.name in answer.selected_docs:
            selected_ids = answer.selected_docs[book.name]
            filtered_docs = [doc for doc in docs if doc.get('id', '') in selected_ids]
            Log.info(f"下载范围: 选择的 {len(filtered_docs)} 篇特定文档")
        else:
            Log.info("下载范围: 所有文档")

        # 并发下载
        semaphore = asyncio.Semaphore(self.concurrency)
        
        async def semaphore_download(idx, doc):
            async with semaphore:
                await self._process_doc_download(idx, len(filtered_docs), doc, namespace, book_dir, answer, level_map)

        tasks = [semaphore_download(i, doc) for i, doc in enumerate(filtered_docs, 1)]
        
        # 使用 gather 并发执行
        await asyncio.gather(*tasks)

        Log.success(f"知识库 {book.name} 下载完成")

    @ErrorHandler.async_error_handler("处理文档下载", reraise=False)
    async def _process_doc_download(self, index, total, doc, namespace, book_dir, answer, level_map):
        """处理单个文档下载逻辑
        
        Args:
            index: 文档在列表中的索引
            total: 总文档数
            doc: 文档对象
            namespace: 知识库命名空间
            book_dir: 知识库输出目录
            answer: 包含下载选项和回调的 MutualAnswer 对象
            level_map: 层级映射表
        """
        doc_title = doc.get('title', 'Untitled')
        doc_slug = doc.get('slug', '')
        doc_url = doc.get('url', '')

        # 检查文档标识符
        if not doc_slug and not doc_url:
            Log.info(f"跳过无标识符条目: {doc_title}")
            return

        doc_type = doc.get('type', '')
        if doc_type and doc_type.upper() != 'DOC' and doc_type.lower() != 'document':
            Log.info(f"跳过非文档条目: {doc_title}")
            if answer.progress_callback:
                answer.progress_callback(f"跳过非文档 ({index}/{total}): {doc_title}")
            answer.skipped_count.increment()
            return

        # 构建路径
        target_dir = book_dir
        parent_uuid = doc.get('parent_uuid', '')
        if parent_uuid and parent_uuid in level_map:
            path_parts = self._build_doc_path(parent_uuid, level_map)
            if path_parts:
                target_dir = os.path.join(book_dir, *path_parts)

        filename = format_filename(doc_title) + '.md'
        file_path = os.path.join(target_dir, filename)

        # 跳过逻辑
        if answer.skip:
            if os.path.exists(file_path):
                answer.skipped_count.increment()
                Log.info(f"跳过已存在: {filename}")
                return
            
            folder_name = os.path.splitext(filename)[0]
            subdir_file_path = os.path.join(target_dir, folder_name, filename)
            if os.path.exists(subdir_file_path):
                    answer.skipped_count.increment()
                    Log.info(f"跳过已存在(子目录): {folder_name}/{filename}")
                    return

        if answer.progress_callback:
            answer.progress_callback(f"正在下载 ({index}/{total}): {doc_title}")

        Log.info(f"下载文档 ({index}/{total}): {doc_title}")

        success = await self._download_doc(namespace, doc, book_dir, answer, level_map)
        
        if success:
            answer.downloaded_count.increment()
        else:
            answer.failed_count.increment()
        

    @ErrorHandler.async_error_handler("下载文档IO", reraise=True)
    async def _download_doc(self, namespace: str, doc: Dict[str, Any], book_dir: str, answer: MutualAnswer, level_map: Dict[str, Dict]) -> bool:
        """下载单个文档的具体实现
        
        Args:
            namespace: 知识库命名空间
            doc: 文档对象
            book_dir: 知识库输出目录
            answer: 包含下载选项和回调的 MutualAnswer 对象
            level_map: 层级映射表
        """
        doc_title = doc.get('title', 'Untitled')
        doc_slug = doc.get('slug', '')
        doc_url = doc.get('url', '')
        parent_uuid = doc.get('parent_uuid', '')

        # 提取slug
        if not doc_url:
            doc_url = doc_slug

        target_dir = book_dir
        if parent_uuid and parent_uuid in level_map:
            path_parts = self._build_doc_path(parent_uuid, level_map)
            if path_parts:
                target_dir = os.path.join(book_dir, *path_parts)
                ensure_dir_exists(target_dir)

        filename = format_filename(doc_title) + '.md'
        file_path = os.path.join(target_dir, filename)

        # 下载文档
        markdown_content = await self.client.export_markdown(namespace, doc_url, answer.line_break)
        if markdown_content is None:
            Log.warn(f"无法获取内容: {doc_title}")
            return False

        if not markdown_content:
            markdown_content = "\n"

        if not answer.line_break:
            markdown_content = markdown_content.replace('</br>', '').replace('<br>', '').replace('<br/>', '')

        f = File()
        f.write(file_path, markdown_content)

        # 记录已下载或更新的文件，给后续图片下载定界使用
        answer.downloaded_files.append(file_path)

        rel_path = os.path.relpath(file_path, book_dir)
        Log.success(f"保存成功: {rel_path}")
        return True

    def _build_doc_path(self, uuid: str, level_map: Dict[str, Dict]) -> list:
        """构建文档路径
        
        Args:
            uuid: 文档UUID
            level_map: 层级映射表
        """
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

    @staticmethod
    def clean_cache() -> bool:
        """清理缓存数据"""
        try:
            from ..libs.tools import clean_cache
            return clean_cache()
        except Exception as e:
            Log.error(f"清理缓存失败: {str(e)}")
            return False

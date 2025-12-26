import asyncio
import os
import sys
from typing import Dict, Any, Optional

from .yuque import YuqueApi
from ..libs import inquiry
from ..libs.constants import (
    GLOBAL_CONFIG, MutualAnswer, YuqueAccount
)
from ..libs.file import File
from ..libs.log import Log
from ..libs.tools import (
    get_local_cookies, get_cache_books_info, 
    format_filename, ensure_dir_exists
)


class Scheduler:
    """调度器类"""

    @staticmethod
    async def start() -> None:
        """知识库启动程序"""
        try:
            cookies = get_local_cookies()

            # 没有cookie缓存，进入登录环节
            if not cookies:
                await Scheduler._start_program(None)
            else:
                # 有cookie，不走登录
                books_info = get_cache_books_info()

                if books_info:
                    await Scheduler._handle_inquiry()
                else:
                    books_result = await YuqueApi.get_user_bookstacks()
                    if books_result:
                        Log.success("获取知识库成功")
                        await Scheduler._handle_inquiry()
                    else:
                        Log.error("获取知识库失败")
                        sys.exit(1)

        except Exception as e:
            Log.error(f"程序启动失败: {str(e)}")
            sys.exit(1)

    @staticmethod
    async def _start_program(account: Optional[YuqueAccount]) -> None:
        """所有环节进入问询程序"""
        if account is None:
            account = inquiry.ask_user_account()

        try:
            login_result = await YuqueApi.login(account.username, account.password)
            if login_result:
                Log.success("登录成功!")
                books_result = await YuqueApi.get_user_bookstacks()
                if books_result:
                    Log.success("获取知识库成功")
                    await Scheduler._handle_inquiry()
                else:
                    Log.error("获取知识库失败")
                    sys.exit(1)
            else:
                Log.error("登录失败，请检查用户名和密码")
                sys.exit(1)

        except Exception as e:
            Log.error(f"登录过程失败: {str(e)}")
            sys.exit(1)

    @staticmethod
    async def _handle_inquiry() -> None:
        """处理用户询问"""
        try:
            answer = inquiry.ask_user_toc_options()
            await Scheduler._start_download_task(answer)

        except Exception as e:
            Log.error(f"处理用户询问失败: {str(e)}")
            sys.exit(1)

    @staticmethod
    async def _start_download_task(answer: MutualAnswer) -> None:
        """开始下载任务"""
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

            # 确保输出目录存在 - 直接使用全局配置的输出目录
            output_dir = GLOBAL_CONFIG.target_output_dir

            ensure_dir_exists(output_dir)

            # 下载每个知识库
            for book in selected_books:
                await Scheduler._download_book(book, output_dir, answer)

            Log.success("所有知识库下载完成！")

        except Exception as e:
            Log.error(f"下载任务失败: {str(e)}")

    @staticmethod
    async def _download_book(book: Any, output_dir: str, answer: MutualAnswer) -> None:
        """下载单个知识库"""
        try:
            Log.info(f"开始下载知识库: {book.name}")

            # 创建知识库目录
            book_dir = os.path.join(output_dir, format_filename(book.name))
            ensure_dir_exists(book_dir)

            namespace = ""

            if hasattr(book, 'namespace') and book.namespace:
                namespace = book.namespace
            # 如果没有namespace，就从其他字段构建
            elif hasattr(book, 'user_login') and hasattr(book, 'slug'):
                namespace = f"{book.user_login}/{book.slug}"

            # 如果还是没有namespace，尝试从user字段获取
            if not namespace and hasattr(book, 'user') and hasattr(book, 'slug'):
                if isinstance(book.user, dict) and 'login' in book.user:
                    namespace = f"{book.user['login']}/{book.slug}"

            if not namespace:
                Log.error(f"知识库 {book.name} 缺少必要的命名空间信息")
                return

            Log.info(f"知识库命名空间: {namespace}")

            # 获取知识库的文档列表
            docs = await YuqueApi.get_book_docs(namespace)
            if not docs:
                Log.warn(f"知识库 {book.name} 没有文档")
                return

            Log.info(f"知识库 {book.name} 共有 {len(docs)} 个文档")
            Log.info(answer.download_range)

            # 构建层级映射表：uuid -> (title, level, type, parent_uuid)
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

            # 根据下载范围处理文档列表
            filtered_docs = docs
            if answer.download_range == "recent" and GLOBAL_CONFIG.article_limit > 0:
                # 按更新时间排序文档（如果有更新时间字段）
                if all('updated_at' in doc for doc in docs):
                    sorted_docs = sorted(docs, key=lambda x: x.get('updated_at', ''), reverse=True)
                    filtered_docs = sorted_docs[:GLOBAL_CONFIG.article_limit]
                    Log.info(f"下载范围: 最近更新的 {len(filtered_docs)} 篇文档")
                else:
                    filtered_docs = docs[:GLOBAL_CONFIG.article_limit]
                    Log.info(f"下载范围: 前 {len(filtered_docs)} 篇文档（无法按更新时间排序）")
            elif answer.download_range == "custom" and GLOBAL_CONFIG.article_limit > 0:
                # 自定义范围: 直接取前N篇文档
                filtered_docs = docs[:GLOBAL_CONFIG.article_limit]
                Log.info(f"下载范围: 自定义范围，前 {len(filtered_docs)} 篇文档")
            elif answer.download_range == "selected" and hasattr(answer,
                                                                 'selected_docs') and book.name in answer.selected_docs:
                # 选择特定文章: 根据ID过滤文档
                selected_ids = answer.selected_docs[book.name]
                filtered_docs = [doc for doc in docs if doc.get('id', '') in selected_ids]
                Log.info(f"下载范围: 选择的 {len(filtered_docs)} 篇特定文档")
            else:
                Log.info("下载范围: 所有文档")

            # 下载每个文档
            for i, doc in enumerate(filtered_docs, 1):
                try:
                    doc_title = doc.get('title', 'Untitled')
                    doc_slug = doc.get('slug', '')
                    doc_url = doc.get('url', '')

                    # 调试：记录URL和slug信息
                    Log.debug(f"文档: {doc_title}, URL: {doc_url}, Slug: {doc_slug}")

                    # 检查是否有有效的标识符 (url或slug)
                    if not doc_slug and not doc_url:
                        Log.info(f"跳过没有有效标识符的条目: {doc_title}")
                        continue

                    # 只跳过明确标记为非文档的条目
                    doc_type = doc.get('type', '')
                    if doc_type and doc_type.upper() != 'DOC' and doc_type.lower() != 'document':
                        Log.info(f"跳过非文档条目: {doc_title} (类型: {doc_type})")
                        continue

                    # 调用进度回调，显示正在下载的文章
                    if answer.progress_callback:
                        answer.progress_callback(f"正在下载文章 ({i}/{len(filtered_docs)}): {doc_title}")

                    Log.info(f"下载文档 ({i}/{len(filtered_docs)}): {doc_title}")

                    # 直接传递完整的doc对象
                    await Scheduler._download_doc(namespace, doc, book_dir, answer, level_map)

                    # 添加延迟避免请求过快
                    await asyncio.sleep(GLOBAL_CONFIG.duration / 1000)

                except Exception as e:
                    Log.error(f"下载文档失败: {str(e)}")
                    continue

            Log.success(f"知识库 {book.name} 下载完成")

        except Exception as e:
            Log.error(f"下载知识库失败: {str(e)}")
            sys.exit(1)

    @staticmethod
    async def _download_doc(namespace: str, doc: Dict[str, Any], book_dir: str, answer: MutualAnswer, level_map: Dict[str, Dict]) -> None:
        """下载单个文档"""
        try:
            doc_title = doc.get('title', 'Untitled')
            doc_slug = doc.get('slug', '')
            doc_url = doc.get('url', '')  # 获取URL
            doc_uuid = doc.get('uuid', '')
            parent_uuid = doc.get('parent_uuid', '')

            # 如果URL为空，尝试使用slug作为备选
            if not doc_url:
                doc_url = doc_slug
                Log.info(f"文档没有URL，使用slug作为URL: {doc_slug}")

            # 根据层级结构构建目录路径
            target_dir = book_dir
            if parent_uuid and parent_uuid in level_map:
                # 递归构建父级路径
                path_parts = Scheduler._build_doc_path(parent_uuid, level_map)
                if path_parts:
                    target_dir = os.path.join(book_dir, *path_parts)
                    ensure_dir_exists(target_dir)
                    Log.debug(f"文档层级路径: {path_parts}")

            # 生成文件名
            filename = format_filename(doc_title) + '.md'
            file_path = os.path.join(target_dir, filename)

            # 检查是否跳过已存在的文件
            # 不仅检查原始路径，还要检查图片下载后可能移动到的子目录
            if answer.skip:
                # 检查原始文件路径
                if os.path.exists(file_path):
                    Log.info(f"跳过已存在的文件: {filename}")
                    return

                # 检查图片下载后可能移动到的子目录中的文件
                # 图片下载功能会将文章移动到以文章名命名的子目录中
                folder_name = os.path.splitext(filename)[0]  # 去掉.md扩展名
                subdir_file_path = os.path.join(target_dir, folder_name, filename)
                if os.path.exists(subdir_file_path):
                    Log.info(f"跳过已存在的文件（在子目录中）: {folder_name}/{filename}")
                    return

            # 获取文档内容
            markdown_content = await YuqueApi.export_markdown(namespace, doc_url, answer.line_break)
            if not markdown_content:
                Log.warn(f"无法获取文档内容: {doc_title}")
                return

            # 处理换行标识
            if not answer.line_break:
                markdown_content = markdown_content.replace('</br>', '')
                markdown_content = markdown_content.replace('<br>', '')
                markdown_content = markdown_content.replace('<br/>', '')

            # 保存文档
            f = File()
            f.write(file_path, markdown_content)

            # 计算相对路径用于日志显示
            rel_path = os.path.relpath(file_path, book_dir)
            Log.success(f"文档保存成功: {rel_path}")

        except Exception as e:
            Log.error(f"下载文档失败: {str(e)}")

    @staticmethod
    def _build_doc_path(uuid: str, level_map: Dict[str, Dict]) -> list:
        """递归构建文档的层级路径"""
        if uuid not in level_map:
            return []

        doc_info = level_map[uuid]
        doc_type = doc_info.get('type', 'DOC')

        # 处理TITLE和DOC类型的父级
        # DOC类型的文档也可以作为父级（比如"动态场景生成"有子文档"开发文档"）
        if doc_type.upper() not in ['TITLE', 'DOC']:
            return []

        title = format_filename(doc_info['title'])
        parent_uuid = level_map.get(uuid, {}).get('parent_uuid', '')

        # 递归获取父级路径
        parent_path = Scheduler._build_doc_path(parent_uuid, level_map)

        # 将当前文档添加到路径末尾
        return parent_path + [title]

    @staticmethod
    def clean_cache() -> bool:
        """清理缓存"""
        try:
            from ..libs.tools import clean_cache
            return clean_cache()
        except Exception as e:
            Log.error(f"清理缓存失败: {str(e)}")
            return False

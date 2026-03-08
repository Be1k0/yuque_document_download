import asyncio
import os
import functools
from typing import List
from PyQt6.QtCore import pyqtSignal
from gui.controllers.base_controller import BaseController
from src.core.scheduler import Scheduler
from src.libs.threaded_image_downloader import ThreadedImageDownloader
from src.libs.constants import MutualAnswer

class ExportController(BaseController):
    """导出控制器
    
    负责处理知识库导出和图片下载任务。
    继承自 BaseController ，支持信号机制。
    """
    
    # 信号定义
    export_progress = pyqtSignal(str)    # 导出进度
    image_download_progress = pyqtSignal(int, int, str)  # 图片下载进度
    image_download_finished = pyqtSignal(int, int)   # 图片下载完成
    image_download_error = pyqtSignal(str)   # 图片下载错误
    
    def __init__(self, client=None):
        super().__init__()
        self.client = client 
        
    async def export_books(self, answer: MutualAnswer):
        """执行导出任务
        
        Args:
            answer: 导出配置对象
        """
        # 设置进度回调
        answer.progress_callback = self.export_progress.emit
        
        # 创建调度器并开始任务
        scheduler = Scheduler(self.client)
        await scheduler.start_download_task(answer)
        
    async def download_images(self, md_files: List[str], download_threads: int, doc_image_prefix: str, image_rename_mode: str, image_file_prefix: str, yuque_cdn_domain: str):
        """并发下载图片
        
        Args:
            md_files: Markdown文件列表
            download_threads: 线程数
            doc_image_prefix: 文档图片前缀
            image_rename_mode: 图片重命名模式
            image_file_prefix: 图片文件前缀
            yuque_cdn_domain: 语雀CDN域名
        """
        try:
            loop = asyncio.get_event_loop()

            # 创建下载器实例
            downloader = ThreadedImageDownloader(
                max_workers=download_threads,
                progress_callback=None 
            )
            
            total_images = 0
            processed_files = 0

            # 实例化下载器
            current_filename = ""
            
            def on_downloader_progress(downloaded, total):
                """下载进度回调函数，发出信号更新UI
                
                Args:
                    downloaded: 已下载的图片数量
                    total: 总图片数量
                """
                self.image_download_progress.emit(downloaded, total, current_filename)

            downloader.progress_callback = on_downloader_progress
            
            for md_file in md_files:
                current_filename = os.path.basename(md_file)
                
                # 调用下载器处理单个文件
                func = functools.partial(
                    downloader.process_single_file,
                    md_file_path=md_file,
                    image_url_prefix=doc_image_prefix,
                    image_rename_mode=image_rename_mode,
                    image_file_prefix=image_file_prefix,
                    yuque_cdn_domain=yuque_cdn_domain
                )
                
                # 异步执行下载任务
                image_count = await loop.run_in_executor(None, func)
                total_images += image_count
                processed_files += 1
                                
            self.image_download_finished.emit(processed_files, total_images)
            
        except Exception as e:
            self.log_error(f"图片下载过程出错: {e}")
            self.image_download_error.emit(str(e))

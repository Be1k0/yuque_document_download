import os
import asyncio
from PyQt5.QtWidgets import QMessageBox, QFileDialog, QTabWidget
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal

from src.libs.constants import GLOBAL_CONFIG, MutualAnswer
from src.libs.log import Log
from src.core.scheduler import Scheduler
from src.libs.threaded_image_downloader import ThreadedImageDownloader
from utils import AsyncWorker


class ImageDownloadWorker(QThread):
    """图片下载工作线程"""
    progress_signal = pyqtSignal(int, int, str)  # downloaded, total, current_filename
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(int, int)  # processed_files, total_images
    error_signal = pyqtSignal(str)

    def __init__(self, md_files, download_threads, doc_image_prefix, image_rename_mode,
                 image_file_prefix, yuque_cdn_domain):
        super().__init__()
        self.md_files = md_files
        self.download_threads = download_threads
        self.doc_image_prefix = doc_image_prefix
        self.image_rename_mode = image_rename_mode
        self.image_file_prefix = image_file_prefix
        self.yuque_cdn_domain = yuque_cdn_domain
        self.total_images = 0
        self.processed_files = 0
        self.current_filename = ""

    def run(self):
        """执行图片下载任务"""
        try:
            downloader = ThreadedImageDownloader(
                max_workers=self.download_threads,
                progress_callback=self._on_progress_update
            )

            for md_file in self.md_files:
                try:
                    # 设置当前正在处理的文件名
                    self.current_filename = os.path.basename(md_file)

                    image_count = downloader.process_single_file(
                        md_file_path=md_file,
                        image_url_prefix=self.doc_image_prefix,
                        image_rename_mode=self.image_rename_mode,
                        image_file_prefix=self.image_file_prefix,
                        yuque_cdn_domain=self.yuque_cdn_domain
                    )
                    self.total_images += image_count
                    self.processed_files += 1

                    if image_count > 0:
                        self.log_signal.emit(f"处理文件 {os.path.basename(md_file)}，下载了 {image_count} 张图片")

                except Exception as e:
                    self.log_signal.emit(f"处理文件 {md_file} 时出错: {str(e)}")
                    continue

            self.finished_signal.emit(self.processed_files, self.total_images)

        except Exception as e:
            self.error_signal.emit(str(e))

    def _on_progress_update(self, downloaded, total):
        """进度回调"""
        self.progress_signal.emit(downloaded, total, self.current_filename)

class ExportManagerMixin:
    def select_output_dir(self):
        """选择输出目录"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择输出目录",
            self.output_input.text() or os.path.expanduser("~")
        )

        if dir_path:
            self.output_input.setText(dir_path)
            GLOBAL_CONFIG.target_output_dir = dir_path

    def start_export(self):
        """开始导出知识库"""
        # 获取选中的知识库
        selected_items = self.book_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "错误", "请先选择要导出的知识库")
            return

        try:
            # 检查是否有选择的文章
            has_selected_articles = hasattr(self, '_current_answer') and hasattr(self._current_answer,
                                                                                 'selected_docs') and self._current_answer.selected_docs

            # 创建并配置MutualAnswer对象
            answer = MutualAnswer(
                toc_range=[],  # 稍后根据选择设置
                skip=self.skip_local_checkbox.isChecked(),
                line_break=self.keep_linebreak_checkbox.isChecked(),
                download_range="selected" if has_selected_articles else "all"  # 根据是否选择了具体文章来决定
            )

            # 设置知识库列表
            if has_selected_articles:
                # 使用已选择的文章
                answer.selected_docs = self._current_answer.selected_docs
                # 知识库列表应该是所有包含选中文章的知识库
                answer.toc_range = list(answer.selected_docs.keys())
            else:
                # 导出整个知识库
                answer.toc_range = [item.data(Qt.UserRole + 1) for item in selected_items]

            if not answer.toc_range:
                QMessageBox.warning(self, "错误", "无法确定选中的知识库")
                return

            # 计算总文章数量提示信息
            if has_selected_articles:
                total_articles = sum(len(ids) for ids in answer.selected_docs.values())
                export_info = f"{total_articles} 篇选定文章，来自 {len(answer.toc_range)} 个知识库"
            else:
                total_articles = 0  # 未知总数，会在导出过程中更新
                export_info = f"{len(answer.toc_range)} 个完整知识库"

            # 设置输出目录
            output_dir = self.output_input.text()
            if output_dir:
                GLOBAL_CONFIG.target_output_dir = output_dir

            # 设置进度回调函数
            answer.progress_callback = self._on_export_progress

            # 设置调试模式
            debug_mode = self.enable_debug_checkbox.isChecked()
            Log.set_debug_mode(debug_mode)

            if debug_mode:
                try:
                    from src.libs.debug_logger import DebugLogger
                    # 确保初始化调试日志
                    DebugLogger.initialize()
                    self.log_handler.emit_log("调试模式已启用，详细日志将被记录到文件")

                    # 记录当前导出设置
                    DebugLogger.log_info(f"导出设置: {export_info}")
                    DebugLogger.log_info(f"跳过本地文件: {answer.skip}")
                    DebugLogger.log_info(f"保留语雀换行标识: {answer.line_break}")
                    DebugLogger.log_info(f"输出目录: {GLOBAL_CONFIG.target_output_dir}")
                except ImportError as e:
                    self.log_handler.emit_log(f"无法导入调试日志模块: {str(e)}")

            # 重置进度条
            self.progress_bar.setValue(0)
            self.progress_bar.setMaximum(total_articles if total_articles > 0 else 100)  # 如果未选定具体文章，先使用100作为最大值
            self.progress_bar.setFormat(f"准备导出: {export_info}")

            # 禁用UI元素
            self.export_button.setEnabled(False)
            self.export_button.setText("导出中...")
            self.book_list.setEnabled(False)
            self.skip_local_checkbox.setEnabled(False)
            self.keep_linebreak_checkbox.setEnabled(False)
            self.clean_button.setEnabled(False)
            self.article_list.setEnabled(False)
            self.article_search_input.setEnabled(False)
            self.select_all_articles_btn.setEnabled(False)
            self.deselect_all_articles_btn.setEnabled(False)

            # 启动导出线程
            self.export_worker = AsyncWorker(self.safe_export_task, answer)
            self.export_worker.taskFinished.connect(self.on_export_finished)
            self.export_worker.taskError.connect(self.on_export_error)
            self.export_worker.start()

            # 更新日志
            self.log_handler.emit_log(f"正在导出 {export_info}...")
        except Exception as e:
            error_msg = str(e)
            self.log_handler.emit_log(f"准备导出任务时出错: {error_msg}")
            QMessageBox.critical(self, "导出错误", f"准备导出任务时出错: {error_msg}")

    async def safe_export_task(self, answer):
        """安全执行导出任务，添加错误处理和恢复机制"""
        try:
            # 使用Scheduler执行下载任务
            result = await Scheduler._start_download_task(answer)
            return result
        except Exception as e:
            error_msg = str(e)
            Log.error(f"导出任务失败: {error_msg}")

            # 检查是否为cookies过期问题
            if "cookies已过期" in error_msg:
                return {"error": "cookies_expired", "message": "登录已过期，请重新登录"}

            # 其他错误直接返回错误信息
            return {"error": "export_failed", "message": f"导出失败: {error_msg}"}

    def on_export_finished(self, result):
        """导出完成后的回调"""
        # 启用UI元素
        self.export_button.setEnabled(True)
        self.export_button.setText("开始导出")
        self.book_list.setEnabled(True)
        self.skip_local_checkbox.setEnabled(True)
        self.keep_linebreak_checkbox.setEnabled(True)
        self.clean_button.setEnabled(True)

        # 启用文章面板控件
        self.article_list.setEnabled(True)
        self.article_search_input.setEnabled(True)
        self.select_all_articles_btn.setEnabled(True)
        self.deselect_all_articles_btn.setEnabled(True)

        # 检查是否有错误信息
        if isinstance(result, dict) and "error" in result:
            error_msg = result.get("message", "未知错误")
            self.log_handler.emit_log(f"导出出错: {error_msg}")

            # 进度条显示错误状态
            self.progress_bar.setFormat("导出出错")

            # 如果是登录过期，提示用户重新登录
            if result.get("error") == "cookies_expired":
                QMessageBox.warning(self, "登录已过期", "您的登录已过期，请重新登录")

                # 切换到登录标签页
                tabs = self.findChild(QTabWidget)
                if tabs:
                    tabs.setCurrentIndex(0)
            else:
                QMessageBox.critical(self, "导出错误", f"导出过程出错: {error_msg}")

            return

        # 更新进度条为完成状态
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.progress_bar.setFormat("导出完成! (100%)")

        # 记录到日志
        self.log_handler.emit_log("导出完成!")
        self.status_label.setText("导出完成!")

        # 检查是否需要下载图片
        if self.download_images_checkbox.isChecked():
            self.process_images_after_export()
        else:
            # 显示导出完成消息
            QMessageBox.information(self, "导出完成", "所有文章导出完成！")

    def process_images_after_export(self):
        """导出完成后处理图片下载（使用独立线程）"""
        try:
            output_dir = self.output_input.text() or GLOBAL_CONFIG.target_output_dir

            # 更新进度条状态
            self.progress_bar.setFormat("正在扫描图片...")
            self.log_handler.emit_log("开始下载图片到本地...")

            # 查找所有Markdown文件
            md_files = []
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    if file.endswith('.md'):
                        md_files.append(os.path.join(root, file))

            if not md_files:
                self.log_handler.emit_log("未找到Markdown文件，跳过图片下载")
                QMessageBox.information(self, "导出完成", "所有文章导出完成！\n未找到Markdown文件，跳过图片下载。")
                return

            self.log_handler.emit_log(
                f"找到 {len(md_files)} 个Markdown文件，使用 {self.download_threads} 个线程下载图片")

            # 创建并启动图片下载工作线程
            self.image_download_worker = ImageDownloadWorker(
                md_files=md_files,
                download_threads=self.download_threads,
                doc_image_prefix=self.doc_image_prefix,
                image_rename_mode=self.image_rename_mode,
                image_file_prefix=self.image_file_prefix,
                yuque_cdn_domain=self.yuque_cdn_domain
            )

            # 连接信号
            self.image_download_worker.progress_signal.connect(self._on_image_download_progress)
            self.image_download_worker.log_signal.connect(self.log_handler.emit_log)
            self.image_download_worker.finished_signal.connect(self._on_image_download_finished)
            self.image_download_worker.error_signal.connect(self._on_image_download_error)

            # 启动下载线程
            self.image_download_worker.start()

        except Exception as e:
            error_msg = str(e)
            self.log_handler.emit_log(f"图片下载过程中出错: {error_msg}")
            QMessageBox.warning(self, "图片下载错误",
                                f"导出完成，但图片下载过程中出错：\n{error_msg}")

    def _on_image_download_progress(self, downloaded, total, current_filename):
        """图片下载进度更新回调"""
        if total > 0:
            progress = int((downloaded / total) * 100)
            self.progress_bar.setValue(downloaded)
            self.progress_bar.setMaximum(total)
            # 去掉.md扩展名
            article_name = current_filename.replace('.md', '') if current_filename.endswith('.md') else current_filename
            self.progress_bar.setFormat(f"文章：{article_name} 正在下载图片 （{downloaded}/{total}）{progress}%")

    def _on_image_download_finished(self, processed_files, total_images):
        """图片下载完成回调"""
        # 更新进度条为完成状态
        self.progress_bar.setFormat("图片下载完成! (100%)")
        self.progress_bar.setValue(self.progress_bar.maximum())

        # 记录完成信息
        self.log_handler.emit_log(f"图片下载完成！共处理 {processed_files} 个文件，下载了 {total_images} 张图片")

        # 显示完成消息
        QMessageBox.information(self, "导出完成",
                                f"所有文章导出完成！\n\n图片下载统计：\n" +
                                f"处理文件数：{processed_files}\n" +
                                f"下载图片数：{total_images}\n" +
                                f"下载线程数：{self.download_threads}")

    def _on_export_progress(self, message):
        """导出进度回调"""
        self.progress_bar.setFormat(message)

    def _on_image_download_error(self, error_msg):
        """图片下载错误回调"""
        self.log_handler.emit_log(f"图片下载过程中出错: {error_msg}")
        QMessageBox.warning(self, "图片下载错误",
                            f"导出完成，但图片下载过程中出错：\n{error_msg}")

    def on_export_error(self, error_msg):
        """导出出错的回调"""
        # 启用UI元素
        self.export_button.setEnabled(True)
        self.export_button.setText("开始导出")
        self.book_list.setEnabled(True)
        self.skip_local_checkbox.setEnabled(True)
        self.keep_linebreak_checkbox.setEnabled(True)
        self.clean_button.setEnabled(True)
        self.article_list.setEnabled(True)
        self.article_search_input.setEnabled(True)
        self.select_all_articles_btn.setEnabled(True)
        self.deselect_all_articles_btn.setEnabled(True)

        # 进度条显示错误状态
        self.progress_bar.setFormat("导出出错")

        # 记录错误到日志
        self.log_handler.emit_log(f"导出出错: {error_msg}")

        # 检查是否为cookies过期问题
        if "cookies已过期" in error_msg:
            QMessageBox.warning(self, "登录已过期", "您的登录已过期，请重新登录")

            # 切换到登录标签页
            tabs = self.findChild(QTabWidget)
            if tabs:
                tabs.setCurrentIndex(0)
        else:
            QMessageBox.critical(self, "导出错误", f"导出过程出错: {error_msg}")

    def clean_cache(self):
        """清理缓存"""
        from src.libs.tools import clean_cache
        
        confirm = QMessageBox.question(
            self, "确认清理", "确定要清理本地缓存吗？\n注意：这将清除知识库和文章缓存，但保留登录信息。",
            QMessageBox.Yes | QMessageBox.No
        )

        if confirm == QMessageBox.Yes:
            try:
                if clean_cache():
                    # 清空知识库列表和文章列表
                    self.book_list.clear()
                    self.article_list.clear()

                    # 重新加载知识库信息
                    self.load_books()

                    QMessageBox.information(self, "清理完成", "缓存清理完成，知识库信息已重新加载")
                else:
                    QMessageBox.warning(self, "清理失败", "缓存清理失败或无缓存文件")
            except Exception as e:
                QMessageBox.critical(self, "清理出错", f"清理缓存出错: {str(e)}")

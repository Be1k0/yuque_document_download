import os
from PyQt6.QtWidgets import QMessageBox, QFileDialog, QTabWidget
from PyQt6.QtCore import Qt
from src.libs.constants import GLOBAL_CONFIG, MutualAnswer
from src.libs.log import Log
from qasync import asyncSlot

class ExportManagerMixin:
    """导出管理器类
    
    提供导出知识库的功能，包括选择输出目录、开始导出、显示进度和处理错误等。
    """
    @property
    def export_controller(self):
        """获取 ExportController 实例，使用懒加载方式"""
        if not hasattr(self, '_export_controller'):
            from gui.controllers.export_controller import ExportController
            self._export_controller = ExportController()
        return self._export_controller

    def select_output_dir(self):
        """选择输出目录"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择输出目录",
            self.output_input.text() or os.path.expanduser("~")
        )

        if dir_path:
            self.output_input.setText(dir_path)
            GLOBAL_CONFIG.target_output_dir = dir_path

    @asyncSlot()
    async def start_export(self):
        """开始导出知识库"""
        selected_items = self.book_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "错误", "请先选择要导出的知识库")
            return

        try:
            selected_namespaces = [
                item.data(Qt.ItemDataRole.UserRole) for item in selected_items if item.data(Qt.ItemDataRole.UserRole)
            ]
            has_selected_articles = (
                hasattr(self, '_current_answer')
                and hasattr(self._current_answer, 'selected_docs')
                and bool(self._current_answer.selected_docs)
                and set(self._current_answer.selected_docs.keys()).issubset(set(selected_namespaces))
            )

            # 创建并配置MutualAnswer对象
            answer = MutualAnswer(
                toc_range=[],
                skip=self.skip_local_checkbox.isChecked(),
                line_break=self.keep_linebreak_checkbox.isChecked()
            )

            # 设置知识库列表
            if has_selected_articles:
                answer.selected_docs = self._current_answer.selected_docs
                answer.toc_range = list(answer.selected_docs.keys())
            else:
                answer.toc_range = selected_namespaces

            if not answer.toc_range:
                QMessageBox.warning(self, "错误", "无法确定选中的知识库")
                return

            # 计算总文章数量提示信息
            if has_selected_articles:
                total_articles = sum(len(ids) for ids in answer.selected_docs.values())
                export_info = f"{total_articles} 篇选定文章，来自 {len(answer.toc_range)} 个知识库"
            else:
                total_articles = 0
                export_info = f"{len(answer.toc_range)} 个完整知识库"

            # 设置输出目录
            output_dir = self.output_input.text()
            if output_dir:
                GLOBAL_CONFIG.target_output_dir = output_dir

            # 保存answer对象
            self._current_answer = answer

            selected_books_log = []
            for item in selected_items:
                selected_books_log.append(
                    f"{item.data(Qt.ItemDataRole.UserRole + 1)} -> {item.data(Qt.ItemDataRole.UserRole)}"
                )
            Log.info(f"导出目标知识库: {', '.join(selected_books_log)}")
            if has_selected_articles:
                for namespace, doc_ids in answer.selected_docs.items():
                    Log.info(f"导出指定文章: {namespace}, 数量: {len(doc_ids)}")

            # 设置调试模式
            debug_mode = self.enable_debug_checkbox.isChecked()
            Log.set_debug_mode(debug_mode)
            if debug_mode:
                try:
                    from src.libs.debug_logger import DebugLogger
                    DebugLogger.initialize()
                    self.log_handler.emit_log("调试模式已启用")
                except:
                    pass

            # 连接信号
            try:
                self.export_controller.export_progress.disconnect()
                self.export_controller.image_download_progress.disconnect()
            except:
                pass
            
            self.export_controller.export_progress.connect(self._on_export_progress)
            self.export_controller.image_download_progress.connect(self._on_image_download_progress)
            self.export_controller.image_download_finished.connect(self._on_image_download_finished)

            # 重置进度条
            self.progress_bar.setValue(0)
            self.progress_bar.setMaximum(total_articles if total_articles > 0 else 100) 
            self.progress_bar.setFormat(f"准备导出: {export_info}")

            # 初始化下载图片总数
            self._total_downloaded_images = 0

            # 禁用UI
            self._set_ui_enabled(False)
            
            self.log_handler.emit_log(f"正在导出 {export_info}...")

            # 执行导出
            await self.export_controller.export_books(answer)
            
            # 导出完成后，进度条设为100%
            self.progress_bar.setValue(self.progress_bar.maximum())
            self.progress_bar.setFormat("文档导出完成")

            # 图片下载
            if self.download_images_checkbox.isChecked():
                self.progress_bar.setFormat("正在准备下载图片...")
                self.log_handler.emit_log("开始处理文章中的图片...")
                
                md_files = getattr(answer, 'downloaded_files', [])
                
                if md_files:
                    count = len(md_files)
                    self.log_handler.emit_log(f"本次共导出 {count} 个Markdown文件，开始下载这些文件中的图片...")
                    self.progress_bar.setFormat("正在下载图片...")
                    
                    await self.export_controller.download_images(
                        md_files=md_files,
                        download_threads=self.download_threads,
                        doc_image_prefix=self.doc_image_prefix,
                        image_rename_mode=self.image_rename_mode,
                        image_file_prefix=self.image_file_prefix,
                        yuque_cdn_domain=self.yuque_cdn_domain
                    )
                else:
                    self.log_handler.emit_log("未找到Markdown文件，跳过图片下载")

            self._on_all_finished(answer)

        except Exception as e:
            self.on_export_error(str(e))

    def _set_ui_enabled(self, enabled):
        """启用或禁用UI控件
        
        Args:
            enabled: 是否启用
        """
        self.export_button.setEnabled(enabled)
        self.export_button.setText("开始导出" if enabled else "导出中...")
        self.book_list.setEnabled(enabled)
        self.skip_local_checkbox.setEnabled(enabled)
        self.keep_linebreak_checkbox.setEnabled(enabled)
        self.clean_button.setEnabled(enabled)
        self.article_list.setEnabled(enabled)
        self.article_search_input.setEnabled(enabled)
        self.select_all_articles_btn.setEnabled(enabled)
        self.deselect_all_articles_btn.setEnabled(enabled)

    def _on_image_download_finished(self, processed_files, total_images):
        """图片下载完成回调
        
        Args:
            processed_files: 已处理的Markdown文件数
            total_images: 下载的图片总数
        """
        self._total_downloaded_images = total_images

    def _on_all_finished(self, answer):
        """所有任务完成
        
        Args:
            answer: 导出结果
        """
        self._set_ui_enabled(True)
        self.progress_bar.setFormat("全部完成!")
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.status_label.setText("任务完成!")
        
        # 统计信息
        downloaded = answer.downloaded_count.get()
        skipped = answer.skipped_count.get()
        
        msg = f"下载文档数：{downloaded}\n跳过文档数：{skipped}"
        if self.download_images_checkbox.isChecked():
            msg += f"\n图片下载数: {self._total_downloaded_images}"
            
        self.log_handler.emit_log(f"任务完成! 下载: {downloaded}, 跳过: {skipped}, 图片: {self._total_downloaded_images}")
        QMessageBox.information(self, "导出完成", msg)

    def _on_image_download_progress(self, downloaded, total, current_filename):
        """图片下载进度更新回调
        
        Args:
            downloaded: 已下载的图片数
            total: 总图片数
            current_filename: 当前下载的图片文件名
        """
        if total > 0:
            progress = int((downloaded / total) * 100)
            self.progress_bar.setValue(downloaded)
            self.progress_bar.setMaximum(total)
            article_name = current_filename.replace('.md', '') if current_filename.endswith('.md') else current_filename
            self.progress_bar.setFormat(f"文章：{article_name} 正在下载图片 （{downloaded}/{total}）{progress}%")

    def _on_export_progress(self, message):
        """导出进度回调
        
        Args:
            message: 进度信息
        """
        self.progress_bar.setFormat(message)

    def on_export_error(self, error_msg):
        """导出出错的回调
        
        Args:
            error_msg: 错误信息
        """
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

        self.progress_bar.setFormat("导出出错")
        self.log_handler.emit_log(f"导出出错: {error_msg}")

        # 检查是否为cookies过期问题
        if "cookies已过期" in error_msg or "登录已过期" in error_msg or "CookiesExpiredError" in error_msg:
            QMessageBox.warning(self, "登录已过期", "您的登录已过期，请重新登录")

            if hasattr(self, "logout"):
                self.logout(force=True)
            else:
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
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if confirm == QMessageBox.StandardButton.Yes:
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

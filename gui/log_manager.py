import time
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QGroupBox, QTextEdit, 
    QHBoxLayout, QPushButton
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import QMetaObject, Q_ARG, Qt
from src.libs.log import Log
from utils import LogSignalHandler

class LogManagerMixin:
    def init_log_manager(self):
        """Initialize log manager"""
        # 连接信号到更新日志的槽函数
        self.appendLogSignal.connect(self.append_to_log)

        # 初始化日志信号处理程序
        self.log_handler = LogSignalHandler()
        self.log_handler.log_signal.connect(self.update_progress_label)
        self.log_handler.progress_signal.connect(self.update_progress_bar)
        
        # 设置日志拦截
        self.setup_log_interception()

    def create_log_page(self):
        """创建日志页面"""
        log_page = QWidget()
        log_layout = QVBoxLayout(log_page)
        log_layout.setContentsMargins(15, 15, 15, 15)
        log_layout.setSpacing(15)

        log_group = QGroupBox("运行日志")
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(15, 20, 15, 15)
        
        self.log_text_edit = QTextEdit()
        self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setLineWrapMode(QTextEdit.NoWrap)
        self.log_text_edit.setFont(QFont("Consolas", 9))
        
        # 设置日志窗口样式 - 黑色背景，不同日志颜色
        self.log_text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #f8f8f8;
                border: 1px solid #2d2d2d;
                border-radius: 4px;
            }
        """)
        
        group_layout.addWidget(self.log_text_edit)
        
        # 添加日志控制按钮
        log_button_layout = QHBoxLayout()
        log_button_layout.setSpacing(10)

        clear_log_button = QPushButton("清空日志")
        clear_log_button.clicked.connect(self.clear_log)
        clear_log_button.setStyleSheet("""
            background-color: #6c757d;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 6px 12px;
            font-weight: bold;
        """)
        log_button_layout.addWidget(clear_log_button)

        save_log_button = QPushButton("保存日志")
        save_log_button.clicked.connect(self.save_log)
        save_log_button.setStyleSheet("""
            background-color: #198754;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 6px 12px;
            font-weight: bold;
        """)
        log_button_layout.addWidget(save_log_button)
        
        log_button_layout.addStretch() # 按钮靠左
        
        group_layout.addLayout(log_button_layout)
        log_group.setLayout(group_layout)
        
        log_layout.addWidget(log_group)
        
        return log_page

    def append_to_log(self, text):
        """使用信号槽机制安全地追加文本到日志窗口，根据类型设置不同颜色"""
        # 根据日志类型设置不同颜色
        color = "#f8f8f8"  

        if "错误" in text:
            color = "#ff6b6b"  
        elif "成功" in text or "完成" in text:
            color = "#69db7c"  
        elif "警告" in text:
            color = "#ffd43b" 
        elif "调试" in text:
            color = "#a5d8ff"  
        elif "加载" in text or "准备" in text:
            color = "#da77f2"  
        elif "导出" in text:
            color = "#74c0fc"  

        # 使用HTML格式化文本颜色
        formatted_text = f'<span style="color:{color};">{text}</span>'
        self.log_text_edit.append(formatted_text)

        # 同时记录到调试日志文件（如果启用）
        if Log.is_debug_mode():
            try:
                from src.libs.debug_logger import DebugLogger
                if DebugLogger._initialized:
                    DebugLogger.log_info(text)
            except ImportError:
                pass

    def update_progress_label(self, message):
        """Update progress label with message (called from main thread)"""

        # 同时添加到日志文本框，使用信号槽机制
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_text = f"[{timestamp}] {message}"
        self.appendLogSignal.emit(log_text)

        # 同时记录到调试日志文件（如果启用）
        if Log.is_debug_mode():
            try:
                from src.libs.debug_logger import DebugLogger
                if DebugLogger._initialized:
                    DebugLogger.log_info(message)
            except ImportError:
                pass

    def update_progress_bar(self, current, total):
        """更新进度条"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        # 在进度条上直接显示当前状态
        self.progress_bar.setFormat(f"已导出: {current}/{total} ({int(current / total * 100 if total > 0 else 0)}%)")

    def setup_log_interception(self):
        """通过monkey修补log类设置日志拦截"""
        original_info = Log.info
        original_success = Log.success
        original_error = Log.error
        original_debug = Log.debug
        original_warn = Log.warn

        # 尝试导入DebugLogger
        try:
            from src.libs.debug_logger import DebugLogger
            has_debug_logger = True
        except ImportError:
            has_debug_logger = False

        def patched_info(message):
            self.log_handler.emit_log(message)
            if has_debug_logger and Log.is_debug_mode():
                DebugLogger.log_info(message)

        def patched_success(message):
            self.log_handler.emit_log(message)
            if has_debug_logger and Log.is_debug_mode():
                DebugLogger.log_info(message)
            if "下载完成" in message:
                if hasattr(self, 'progress_bar'):
                    self.log_handler.progress_signal.emit(
                        self.progress_bar.maximum(),
                        self.progress_bar.maximum()
                    )

        def patched_error(message, detailed=False):
            self.log_handler.emit_log(f"错误: {message}")
            if has_debug_logger and Log.is_debug_mode():
                DebugLogger.log_error(message)

        def patched_debug(message):
            if Log.is_debug_mode():
                self.log_handler.emit_log(f"调试: {message}")
                if has_debug_logger:
                    DebugLogger.log_debug(message)

        def patched_warn(message, detailed=False):
            self.log_handler.emit_log(f"警告: {message}")
            if has_debug_logger and Log.is_debug_mode():
                DebugLogger.log_warning(message)

        # Apply the patches
        Log.info = staticmethod(patched_info)
        Log.success = staticmethod(patched_success)
        Log.error = staticmethod(patched_error)
        Log.debug = staticmethod(patched_debug)
        Log.warn = staticmethod(patched_warn)

    def clear_log(self):
        """清空日志文本框"""
        self.log_text_edit.clear()

    def save_log(self):
        """保存日志到文件"""
        from PyQt5.QtWidgets import QFileDialog, QMessageBox
        import os
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存日志文件",
            os.path.join(os.path.expanduser("~"), "yuque_export_log.txt"),
            "文本文件 (*.txt);;所有文件 (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.log_text_edit.toPlainText())
                QMessageBox.information(self, "保存成功", f"日志已保存到: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "保存失败", f"保存日志出错: {str(e)}")

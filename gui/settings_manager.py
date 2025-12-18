import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, 
    QRadioButton, QButtonGroup, QCheckBox, QMessageBox, QPushButton
)
from PyQt5.QtGui import QFont, QPixmap, QIntValidator
from PyQt5.QtCore import Qt

from src.libs.log import Log
from utils import static_resource_path, create_circular_pixmap

class SettingsManagerMixin:
    def create_settings_page(self):
        """创建设置页面"""
        settings_page = QWidget()
        settings_layout = QVBoxLayout(settings_page)
        settings_layout.setContentsMargins(15, 15, 15, 15)
        settings_layout.setSpacing(15)

        # 图片设置组
        image_group = QGroupBox("图片设置")
        image_layout = QVBoxLayout()
        image_layout.setContentsMargins(10, 0, 0, 15)
        image_layout.setSpacing(15)

        # 下载线程数设置
        threads_layout = QHBoxLayout()
        threads_label = QLabel("下载线程数:")
        threads_label.setMinimumWidth(100)
        self.threads_input = QLineEdit(str(self.download_threads))
        self.threads_input.setValidator(QIntValidator(1, 30))
        self.threads_input.setMaximumWidth(100)
        self.threads_input.textChanged.connect(self.auto_save_settings)
        threads_help = QLabel("(1-30，默认5)")
        threads_help.setStyleSheet("color: #6c757d; font-size: 12px;")
        threads_layout.addWidget(threads_label)
        threads_layout.addWidget(self.threads_input)
        threads_layout.addWidget(threads_help)
        threads_layout.addStretch()
        image_layout.addLayout(threads_layout)

        # 图片重命名模式设置
        rename_layout = QHBoxLayout()
        rename_label = QLabel("图片重命名模式:")
        rename_label.setMinimumWidth(100)

        # 创建单选按钮组
        self.rename_button_group = QButtonGroup()
        self.rename_radio1 = QRadioButton("递增命名")
        self.rename_radio2 = QRadioButton("保持图片原名")

        # 添加到按钮组
        self.rename_button_group.addButton(self.rename_radio1, 0)
        self.rename_button_group.addButton(self.rename_radio2, 1)

        # 设置默认选中状态
        if self.image_rename_mode == "asc":
            self.rename_radio1.setChecked(True)
        else:
            self.rename_radio2.setChecked(True)

        # 连接信号
        self.rename_button_group.buttonClicked.connect(self.auto_save_settings)

        rename_layout.addWidget(rename_label)
        rename_layout.addWidget(self.rename_radio1)
        rename_layout.addWidget(self.rename_radio2)
        rename_layout.addStretch()
        image_layout.addLayout(rename_layout)

        # 图片文件前缀设置
        file_prefix_layout = QHBoxLayout()
        file_prefix_label = QLabel("图片文件前缀:")
        file_prefix_label.setMinimumWidth(100)
        self.file_prefix_input = QLineEdit(self.image_file_prefix)
        self.file_prefix_input.setMaximumWidth(150)
        self.file_prefix_input.textChanged.connect(self.auto_save_settings)
        file_prefix_help = QLabel("(递增模式下的文件名前缀)")
        file_prefix_help.setStyleSheet("color: #6c757d; font-size: 12px;")
        file_prefix_layout.addWidget(file_prefix_label)
        file_prefix_layout.addWidget(self.file_prefix_input)
        file_prefix_layout.addWidget(file_prefix_help)
        file_prefix_layout.addStretch()
        image_layout.addLayout(file_prefix_layout)

        # CDN域名设置
        cdn_layout = QHBoxLayout()
        cdn_label = QLabel("语雀CDN域名:")
        cdn_label.setMinimumWidth(100)
        self.cdn_input = QLineEdit(self.yuque_cdn_domain)
        self.cdn_input.setMaximumWidth(200)
        self.cdn_input.textChanged.connect(self.auto_save_settings)
        cdn_help = QLabel("(语雀图片CDN域名)")
        cdn_help.setStyleSheet("color: #6c757d; font-size: 12px;")
        cdn_layout.addWidget(cdn_label)
        cdn_layout.addWidget(self.cdn_input)
        cdn_layout.addWidget(cdn_help)
        cdn_layout.addStretch()
        image_layout.addLayout(cdn_layout)

        image_group.setLayout(image_layout)
        settings_layout.addWidget(image_group)

        # 调试设置组
        debug_group = QGroupBox("其他设置")
        debug_layout = QVBoxLayout()
        debug_layout.setContentsMargins(20, 20, 20, 20)
        debug_layout.setSpacing(15)

        self.enable_debug_checkbox = QCheckBox("调试模式")
        self.enable_debug_checkbox.setToolTip("记录详细日志到文件")
        self.enable_debug_checkbox.setChecked(False)
        self.enable_debug_checkbox.stateChanged.connect(self.toggle_debug_mode)
        debug_layout.addWidget(self.enable_debug_checkbox)

        debug_group.setLayout(debug_layout)
        settings_layout.addWidget(debug_group)

        # 按钮区域
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(15)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        
        # 保存按钮
        self.save_settings_btn = QPushButton("保存设置")
        self.save_settings_btn.setMinimumHeight(36)
        self.save_settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #0d6efd;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0b5ed7;
            }
            QPushButton:pressed {
                background-color: #0a58ca;
            }
        """)
        self.save_settings_btn.clicked.connect(self.save_settings)
        buttons_layout.addStretch()
        buttons_layout.addWidget(self.save_settings_btn)
        
        # 重置按钮
        self.reset_settings_btn = QPushButton("重置设置")
        self.reset_settings_btn.setMinimumHeight(36)
        self.reset_settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5c636a;
            }
            QPushButton:pressed {
                background-color: #495057;
            }
        """)
        self.reset_settings_btn.clicked.connect(self.reset_settings)
        buttons_layout.addWidget(self.reset_settings_btn)
        
        settings_layout.addLayout(buttons_layout)
        
        settings_layout.addStretch()
        
        # 加载保存的设置
        self.load_saved_settings()
        
        return settings_page

    def auto_save_settings(self):
        """自动保存设置"""
        try:
            # 验证线程数输入
            threads_text = self.threads_input.text()
            if threads_text:
                threads = int(threads_text)
                if 1 <= threads <= 30:
                    self.download_threads = threads
                else:
                    # 显示错误提示并恢复到有效值
                    QMessageBox.warning(self, "输入错误", "下载线程数必须在1-30之间！")
                    self.threads_input.setText(str(self.download_threads))
                    return  # 无效值，不保存

            # 保存其他设置
            # 获取选中的单选按钮文本并转换为底层代码期望的值
            if self.rename_radio1.isChecked():
                self.image_rename_mode = "asc"  # 递增命名对应asc
            else:
                self.image_rename_mode = "raw"  # 保持图片原名对应raw
            self.image_file_prefix = self.file_prefix_input.text()
            self.yuque_cdn_domain = self.cdn_input.text()

        except ValueError:
            # 输入无效时显示提示并恢复到有效值
            QMessageBox.warning(self, "输入错误", "下载线程数必须是1-30之间的数字！")
            self.threads_input.setText(str(self.download_threads))

    def save_settings(self):
        """保存设置到文件"""
        try:
            import json
            import os
            from utils import resource_path
            
            # 确保.meta文件夹存在
            meta_dir = resource_path('.meta')
            os.makedirs(meta_dir, exist_ok=True)
            
            # 配置文件路径
            config_file = os.path.join(meta_dir, 'settings.json')
            
            # 收集当前设置
            settings = {
                'download_threads': self.download_threads,
                'image_rename_mode': self.image_rename_mode,
                'image_file_prefix': self.image_file_prefix,
                'yuque_cdn_domain': self.yuque_cdn_domain
            }
            
            # 保存到文件
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            
            QMessageBox.information(self, "保存成功", "设置已成功保存！")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存设置时出错: {str(e)}")
            Log.error(f"保存设置时出错: {e}")
    
    def reset_settings(self):
        """重置设置为默认值"""
        reply = QMessageBox.question(self, "确认重置", "确定要将所有设置重置为默认值吗？软件将自动重启。",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                import os
                import sys
                import subprocess
                from utils import resource_path
                
                # 配置文件路径
                config_file = os.path.join(resource_path('.meta'), 'settings.json')
                
                # 删除配置文件
                if os.path.exists(config_file):
                    os.remove(config_file)
                
                # 显示重启提示
                QMessageBox.information(self, "重置成功", "设置已重置，软件将自动重启...")
                
                # 重启软件
                python = sys.executable
                os.execl(python, python, *sys.argv)
            except Exception as e:
                QMessageBox.critical(self, "重置失败", f"重置设置时出错: {str(e)}")
                Log.error(f"重置设置时出错: {e}")
    
    def load_saved_settings(self):
        """从文件加载保存的设置"""
        try:
            import json
            import os
            from utils import resource_path
            
            # 配置文件路径
            config_file = os.path.join(resource_path('.meta'), 'settings.json')
            
            if os.path.exists(config_file):
                # 检查文件是否为空
                if os.path.getsize(config_file) == 0:
                    # 空文件，删除并重新创建默认设置
                    os.remove(config_file)
                    return
                
                with open(config_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                # 应用保存的设置
                if 'download_threads' in settings:
                    self.download_threads = settings['download_threads']
                    self.threads_input.setText(str(self.download_threads))
                
                if 'image_rename_mode' in settings:
                    self.image_rename_mode = settings['image_rename_mode']
                    if self.image_rename_mode == 'asc':
                        self.rename_radio1.setChecked(True)
                    else:
                        self.rename_radio2.setChecked(True)
                
                if 'image_file_prefix' in settings:
                    self.image_file_prefix = settings['image_file_prefix']
                    self.file_prefix_input.setText(self.image_file_prefix)
                
                if 'yuque_cdn_domain' in settings:
                    self.yuque_cdn_domain = settings['yuque_cdn_domain']
                    self.cdn_input.setText(self.yuque_cdn_domain)
        except Exception as e:
            Log.error(f"加载保存的设置时出错: {e}")
            # 如果加载失败，尝试删除损坏的配置文件
            try:
                import os
                from utils import resource_path
                config_file = os.path.join(resource_path('.meta'), 'settings.json')
                if os.path.exists(config_file):
                    os.remove(config_file)
            except:
                pass
    
    def toggle_debug_mode(self, state):
        """处理调试模式切换"""
        debug_enabled = state == Qt.Checked
        Log.set_debug_mode(debug_enabled)

        if debug_enabled:
            try:
                from src.libs.debug_logger import DebugLogger
                # 确保调试日志记录器已初始化
                DebugLogger.initialize()
                self.log_handler.emit_log("调试模式已启用，详细日志将被记录到文件")
            except ImportError as e:
                self.log_handler.emit_log(f"无法导入调试日志模块: {str(e)}")
        else:
            self.log_handler.emit_log("调试模式已关闭")

    def create_about_page(self):
        """创建关于页面"""
        about_page = QWidget()
        about_layout = QVBoxLayout(about_page)
        about_layout.setContentsMargins(20, 15, 20, 15)
        about_layout.setSpacing(15)

        # 页面标题
        title_label = QLabel("关于本软件")
        title_label.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(20)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #0d6efd; margin-bottom: 10px;")
        about_layout.addWidget(title_label)

        # 主要信息區域
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(15)

        # 作者信息部分
        author_section = QWidget()
        author_layout = QHBoxLayout(author_section)
        author_layout.setContentsMargins(0, 0, 0, 0)
        author_layout.setSpacing(15)

        # 作者头像 - 使用程序图标
        author_avatar = QLabel()
        author_avatar.setFixedSize(70, 70)
        author_avatar.setStyleSheet("""
            QLabel {
                border: 2px solid #0d6efd;
                border-radius: 35px;
                background-color: white;
                padding: 3px;
            }
        """)
        author_avatar.setAlignment(Qt.AlignCenter)
        author_avatar.setScaledContents(True)

        # 加载程序图标作为作者头像
        try:
            icon_path = static_resource_path("favicon.ico")
            if os.path.exists(icon_path):
                pixmap = QPixmap(icon_path)
                if not pixmap.isNull():
                    # 缩放图标到合适大小
                    scaled_pixmap = pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    # 创建圆形头像
                    circular_pixmap = create_circular_pixmap(scaled_pixmap, 64)
                    author_avatar.setPixmap(circular_pixmap)
                else:
                    author_avatar.setText("Be1k0")
                    author_avatar.setStyleSheet("""
                        QLabel {
                            border: 2px solid #0d6efd;
                            border-radius: 35px;
                            background-color: white;
                            color: #0d6efd;
                            font-weight: bold;
                            font-size: 12px;
                            padding: 3px;
                        }
                    """)
            else:
                author_avatar.setText("Be1k0")
                author_avatar.setStyleSheet("""
                    QLabel {
                        border: 2px solid #0d6efd;
                        border-radius: 35px;
                        background-color: white;
                        color: #0d6efd;
                        font-weight: bold;
                        font-size: 12px;
                        padding: 3px;
                    }
                """)
        except Exception as e:
            author_avatar.setText("Be1k0")
            author_avatar.setStyleSheet("""
                QLabel {
                    border: 2px solid #0d6efd;
                    border-radius: 35px;
                    background-color: white;
                    color: #0d6efd;
                    font-weight: bold;
                    font-size: 12px;
                    padding: 3px;
                }
            """)

        author_layout.addWidget(author_avatar)

        # 作者信息文本
        author_info_layout = QVBoxLayout()
        author_info_layout.setContentsMargins(0, 5, 0, 0)
        author_info_layout.setSpacing(8)

        # 作者名称
        author_name = QLabel("作者: Be1k0")
        author_name.setFont(QFont("", 15, QFont.Bold))
        author_name.setStyleSheet("color: #333;")
        author_info_layout.addWidget(author_name)

        # 项目地址
        project_url = QLabel(
            "项目地址: <a href='https://github.com/Be1k0/yuque_document_download/' style='color: #0d6efd; text-decoration: none;'>https://github.com/Be1k0/yuque_document_download/</a>")
        project_url.setOpenExternalLinks(True)
        project_url.setWordWrap(False)
        project_url.setFont(QFont("", 14))
        project_url.setStyleSheet("color: #666;")
        author_info_layout.addWidget(project_url)

        author_layout.addLayout(author_info_layout)
        author_layout.addStretch()

        info_layout.addWidget(author_section)

        # 添加一些間距
        info_layout.addSpacing(10)

        # 项目简介
        description_title = QLabel("简介")
        description_title.setFont(QFont("", 15, QFont.Bold))
        description_title.setStyleSheet("color: #333;")
        info_layout.addWidget(description_title)

        description_text = QLabel("一款功能强大的语雀知识库批量导出工具，支持一键导出语雀知识库中的所有文档。")
        description_text.setWordWrap(True)
        description_text.setFont(QFont("", 14))
        description_text.setStyleSheet("color: #666; padding: 5px 0;")
        info_layout.addWidget(description_text)

        about_layout.addWidget(info_widget)

        # 版本信息
        version_label = QLabel("版本: v1.1.0")
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setFont(QFont("", 13))
        version_label.setStyleSheet("color: #6c757d; margin-top: 10px;")
        about_layout.addWidget(version_label)

        about_layout.addStretch()
        return about_page

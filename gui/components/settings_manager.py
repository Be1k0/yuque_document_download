import os
import asyncio
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, 
    QRadioButton, QButtonGroup, QCheckBox, QMessageBox, QPushButton,
    QApplication, QTextBrowser, QSizePolicy, QProgressDialog, QProgressBar
)
from PyQt6.QtGui import QFont, QPixmap, QIntValidator
from PyQt6.QtCore import Qt, QTimer
from qasync import asyncSlot
from src.libs.log import Log
from utils import static_resource_path, create_circular_pixmap
from src.ui.theme_manager import THEME_MANAGER


class CenteredUpdateProgressDialog(QProgressDialog):
    """取消按钮居中的更新进度弹窗"""

    def showEvent(self, event):
        super().showEvent(event)
        self._center_cancel_button()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._center_cancel_button()

    def _center_cancel_button(self):
        button = self.findChild(QPushButton)
        if button is None or not button.isVisible():
            return
        button.move(max((self.width() - button.width()) // 2, 0), button.y())


class SettingsManagerMixin:
    """设置管理器类
    
    提供一个界面让用户调整软件的各种设置，包括主题、下载线程数、图片重命名模式等。
    """
    @property
    def update_controller(self):
        """获取更新控制器实例"""
        if not hasattr(self, '_update_controller'):
            from gui.controllers.update_controller import UpdateController
            self._update_controller = UpdateController()
            self._update_controller.update_error.connect(self.on_update_error)
            self._update_controller.update_cancelled.connect(self.on_update_cancelled)
            self._update_controller.download_progress.connect(self.on_update_download_progress)
        return self._update_controller

    def create_settings_page(self):
        """创建设置页面"""
        settings_page = QWidget()
        settings_layout = QVBoxLayout(settings_page)
        settings_layout.setContentsMargins(15, 15, 15, 15)
        settings_layout.setSpacing(15)

        # 主题设置组
        theme_group = QGroupBox("主题设置")
        theme_layout = QHBoxLayout()
        theme_layout.setContentsMargins(10, 15, 10, 15)
        theme_layout.setSpacing(20)

        theme_label = QLabel("界面主题:")
        theme_layout.addWidget(theme_label)

        self.theme_button_group = QButtonGroup()
        
        self.theme_radio_system = QRadioButton("跟随系统")
        self.theme_radio_light = QRadioButton("浅色模式")
        self.theme_radio_dark = QRadioButton("深色模式")
        
        self.theme_button_group.addButton(self.theme_radio_system, 0)
        self.theme_button_group.addButton(self.theme_radio_light, 1)
        self.theme_button_group.addButton(self.theme_radio_dark, 2)
        
        # 连接信号
        self.theme_button_group.buttonClicked.connect(self.on_theme_changed)
        
        theme_layout.addWidget(self.theme_radio_system)
        theme_layout.addWidget(self.theme_radio_light)
        theme_layout.addWidget(self.theme_radio_dark)
        theme_layout.addStretch()
        
        theme_group.setLayout(theme_layout)
        settings_layout.addWidget(theme_group)

        # 图片设置组
        image_group = QGroupBox("图片设置")
        image_layout = QVBoxLayout()
        image_layout.setContentsMargins(10, 15, 10, 15)
        image_layout.setSpacing(15)

        # 下载线程数设置
        threads_layout = QHBoxLayout()
        threads_label = QLabel("图片下载线程数:")
        threads_label.setMinimumWidth(100)
        self.threads_input = QLineEdit(str(self.download_threads))
        self.threads_input.setValidator(QIntValidator(1, 30))
        self.threads_input.setMaximumWidth(100)
        self.threads_input.textChanged.connect(self.auto_save_settings)
        threads_help = QLabel("(1-50，默认10)")
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
        self.enable_debug_checkbox.setChecked(self.enable_debug)
        self.enable_debug_checkbox.stateChanged.connect(self.toggle_debug_mode)
        debug_layout.addWidget(self.enable_debug_checkbox)

        self.disable_ssl_checkbox = QCheckBox("禁用SSL校验")
        self.disable_ssl_checkbox.setToolTip("禁用SSL证书校验，可能导致安全风险，正常情况下不建议启用")
        self.disable_ssl_checkbox.setChecked(self.disable_ssl)
        self.disable_ssl_checkbox.stateChanged.connect(self.toggle_disable_ssl)
        debug_layout.addWidget(self.disable_ssl_checkbox)

        self.enable_update_proxy_checkbox = QCheckBox("使用程序更新下载加速")
        self.enable_update_proxy_checkbox.setToolTip("仅影响程序更新时的安装包下载，不影响版本检查接口")
        self.enable_update_proxy_checkbox.setChecked(self.enable_update_proxy)
        self.enable_update_proxy_checkbox.stateChanged.connect(self.toggle_update_proxy)
        debug_layout.addWidget(self.enable_update_proxy_checkbox)

        update_proxy_layout = QHBoxLayout()
        update_proxy_label = QLabel("更新加速地址:")
        update_proxy_label.setMinimumWidth(100)
        self.update_proxy_input = QLineEdit(self.update_proxy_base_url)
        self.update_proxy_input.setMaximumWidth(280)
        self.update_proxy_input.textChanged.connect(self.auto_save_settings)
        update_proxy_help = QLabel("(留空则直连 GitHub 下载)")
        update_proxy_help.setStyleSheet("color: #6c757d; font-size: 12px;")
        update_proxy_layout.addWidget(update_proxy_label)
        update_proxy_layout.addWidget(self.update_proxy_input)
        update_proxy_layout.addWidget(update_proxy_help)
        update_proxy_layout.addStretch()
        debug_layout.addLayout(update_proxy_layout)
        self.update_proxy_input.setEnabled(self.enable_update_proxy)

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
        self.reset_settings_btn.setObjectName("SecondaryButton")
        self.reset_settings_btn.clicked.connect(self.reset_settings)
        buttons_layout.addWidget(self.reset_settings_btn)
        
        settings_layout.addLayout(buttons_layout)
        
        settings_layout.addStretch()
        
        # 加载保存的设置
        self.load_saved_settings()
        
        return settings_page

    def on_theme_changed(self):
        """当主题选择改变时"""
        theme = "system"
        if self.theme_radio_light.isChecked():
            theme = "default"
        elif self.theme_radio_dark.isChecked():
            theme = "dark"
        
        Log.info(f"UI 主题已变更为: {theme}")
        
        # 立即应用主题
        THEME_MANAGER.apply_theme(QApplication.instance(), theme)
        self.auto_save_settings()

    def auto_save_settings(self):
        """自动保存设置"""
        try:
            threads_text = self.threads_input.text()
            if threads_text:
                threads = int(threads_text)
                if 1 <= threads <= 50:
                    self.download_threads = threads
                else:
                    QMessageBox.warning(self, "输入错误", "图片下载线程数只能在1-50之间！")
                    self.threads_input.setText(str(self.download_threads))
                    return  

            # 保存其他设置
            # 获取选中的单选按钮文本并转换为底层代码期望的值
            if self.rename_radio1.isChecked():
                new_image_rename_mode = "asc"  
            else:
                new_image_rename_mode = "raw"  
                
            new_image_file_prefix = self.file_prefix_input.text()
            new_yuque_cdn_domain = self.cdn_input.text()
            new_update_proxy_base_url = self.update_proxy_input.text().strip()
            
            # 记录设置变更日志
            if (
                getattr(self, "image_rename_mode", None) != new_image_rename_mode or
                getattr(self, "image_file_prefix", None) != new_image_file_prefix or
                getattr(self, "yuque_cdn_domain", None) != new_yuque_cdn_domain or
                getattr(self, "update_proxy_base_url", None) != new_update_proxy_base_url
            ):
                Log.info(
                    f"设置自动保存触发: 重命名模式={new_image_rename_mode}, 图片前缀={new_image_file_prefix}, "
                    f"CDN={new_yuque_cdn_domain}, 更新加速地址={new_update_proxy_base_url or '直连'}"
                )

            self.image_rename_mode = new_image_rename_mode
            self.image_file_prefix = new_image_file_prefix
            self.yuque_cdn_domain = new_yuque_cdn_domain
            self.update_proxy_base_url = new_update_proxy_base_url

        except ValueError:
            QMessageBox.warning(self, "输入错误", "图片下载线程数只能是1-50之间的数字！")
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
            
            # 获取当前主题选择
            current_theme = "system"
            if self.theme_radio_light.isChecked():
                current_theme = "default"
            elif self.theme_radio_dark.isChecked():
                current_theme = "dark"
            
            # 收集当前设置
            settings = {
                'theme': current_theme,
                'download_threads': self.download_threads,
                'image_rename_mode': self.image_rename_mode,
                'image_file_prefix': self.image_file_prefix,
                'yuque_cdn_domain': self.yuque_cdn_domain,
                'enable_debug': self.enable_debug,
                'disable_ssl': self.disable_ssl,
                'enable_update_proxy': self.enable_update_proxy,
                'update_proxy_base_url': self.update_proxy_base_url,
            }
            
            # 保存到文件
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            
            # 应用调试模式设置
            Log.set_debug_mode(self.enable_debug)
            
            # 更新全局配置
            from src.libs.constants import GLOBAL_CONFIG
            GLOBAL_CONFIG.disable_ssl = self.disable_ssl
            GLOBAL_CONFIG.enable_update_proxy = self.enable_update_proxy
            GLOBAL_CONFIG.update_proxy_base_url = self.update_proxy_base_url

            Log.info(
                f"程序更新设置已保存: 启用加速={self.enable_update_proxy}, "
                f"加速地址={self.update_proxy_base_url or '直连'}"
            )
            
            if self.enable_debug:
                try:
                    from src.libs.debug_logger import DebugLogger
                    DebugLogger.initialize()
                except ImportError as e:
                    self.log_handler.emit_log(f"无法导入调试日志模块: {str(e)}")
            
            QMessageBox.information(self, "保存成功", "设置已成功保存！")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存设置时出错: {str(e)}")
            Log.error(f"保存设置时出错: {e}")
    
    def reset_settings(self):
        """重置设置为默认值"""
        reply = QMessageBox.question(self, "确认重置", "确定要将所有设置重置为默认值吗？软件将自动重启。",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                import os
                import sys
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
            
            theme = "system"
            
            if os.path.exists(config_file):
                # 检查文件是否为空
                if os.path.getsize(config_file) == 0:
                    os.remove(config_file)
                    return
                
                with open(config_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                # 应用保存的设置
                if 'theme' in settings:
                    theme = settings['theme']
                    
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
                
                if 'enable_debug' in settings:
                    self.enable_debug = settings['enable_debug']
                    self.enable_debug_checkbox.setChecked(self.enable_debug)
                    
                    # 应用调试模式设置
                    Log.set_debug_mode(self.enable_debug)
                    
                    if self.enable_debug:
                        try:
                            from src.libs.debug_logger import DebugLogger
                            DebugLogger.initialize()
                        except ImportError:
                            pass
                
                if 'disable_ssl' in settings:
                    self.disable_ssl = settings['disable_ssl']
                    self.disable_ssl_checkbox.setChecked(self.disable_ssl)
                    from src.libs.constants import GLOBAL_CONFIG
                    GLOBAL_CONFIG.disable_ssl = self.disable_ssl

                if 'enable_update_proxy' in settings:
                    self.enable_update_proxy = settings['enable_update_proxy']
                    self.enable_update_proxy_checkbox.setChecked(self.enable_update_proxy)
                    from src.libs.constants import GLOBAL_CONFIG
                    GLOBAL_CONFIG.enable_update_proxy = self.enable_update_proxy

                if 'update_proxy_base_url' in settings:
                    self.update_proxy_base_url = settings['update_proxy_base_url']
                    self.update_proxy_input.setText(self.update_proxy_base_url)
                    from src.libs.constants import GLOBAL_CONFIG
                    GLOBAL_CONFIG.update_proxy_base_url = self.update_proxy_base_url

                self.update_proxy_input.setEnabled(self.enable_update_proxy)

            # 设置主题单选按钮状态
            if theme == "dark":
                self.theme_radio_dark.setChecked(True)
            elif theme == "default":
                self.theme_radio_light.setChecked(True)
            else:
                self.theme_radio_system.setChecked(True)
                theme = "system"
                
            # 应用初始主题
            THEME_MANAGER.apply_theme(QApplication.instance(), theme)
            
        except Exception as e:
            Log.error(f"加载保存的设置时出错: {e}")
            try:
                import os
                from utils import resource_path
                config_file = os.path.join(resource_path('.meta'), 'settings.json')
                if os.path.exists(config_file):
                    os.remove(config_file)
            except:
                pass
    
    def toggle_debug_mode(self, state):
        """处理调试模式切换
        
        Args:
            state: 复选框状态
        """
        self.enable_debug = state == Qt.CheckState.Checked.value or state == Qt.CheckState.Checked

    def toggle_disable_ssl(self, state):
        """处理禁用SSL校验切换
        
        Args:
            state: 复选框状态
        """
        self.disable_ssl = state == Qt.CheckState.Checked.value or state == Qt.CheckState.Checked

    def toggle_update_proxy(self, state):
        """处理更新下载加速切换"""
        self.enable_update_proxy = state == Qt.CheckState.Checked.value or state == Qt.CheckState.Checked
        self.update_proxy_input.setEnabled(self.enable_update_proxy)
        Log.info(f"程序更新下载加速已{'启用' if self.enable_update_proxy else '关闭'}")

    def _close_update_progress_dialog(self):
        """关闭更新进度弹窗"""
        dialog = getattr(self, "_update_progress_dialog", None)
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()
            self._update_progress_dialog = None

    def _show_update_progress_dialog(self, title: str, text: str, allow_cancel: bool = False):
        """显示更新进度弹窗"""
        self._close_update_progress_dialog()
        cancel_text = "取消下载" if allow_cancel else None
        dialog = CenteredUpdateProgressDialog(text, cancel_text, 0, 0, self)
        dialog.setObjectName("UpdateProgressDialog")
        dialog.setWindowTitle(title)
        dialog.setMinimumDuration(0)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setMinimumWidth(460)
        progress_bar = dialog.findChild(QProgressBar)
        if progress_bar is not None:
            progress_bar.setObjectName("UpdateProgressBar")
        if allow_cancel:
            dialog.canceled.connect(self.on_update_dialog_canceled)
        dialog.show()
        self._update_progress_dialog = dialog

    def trigger_startup_update_check(self):
        """触发启动后的自动更新检查"""
        if getattr(self, "_startup_update_check_triggered", False):
            return
        if getattr(self, "_login_action_running", False):
            Log.debug("登录流程进行中，已延后启动自动检查更新")
            QTimer.singleShot(1500, self.trigger_startup_update_check)
            return
        self._startup_update_check_triggered = True
        self._startup_update_check_task = self.auto_check_update_on_startup()

    def _is_update_check_running(self) -> bool:
        """判断当前是否正在执行更新检查"""
        return getattr(self, "_update_check_running", False)

    async def _run_update_check(self, current_version: str, show_progress_dialog: bool = False, silent_error: bool = False):
        """执行更新检查"""
        if self._is_update_check_running():
            Log.info("已有更新检查任务正在执行，已跳过新的检查请求")
            return None

        previous_suppress = getattr(self, "_suppress_update_error_dialog", False)
        self._update_check_running = True
        self._suppress_update_error_dialog = silent_error

        if show_progress_dialog:
            self._show_update_progress_dialog("检查更新", "正在检查最新版本...")

        try:
            return await self.update_controller.check_for_updates(current_version)
        finally:
            if show_progress_dialog:
                self._close_update_progress_dialog()
            self._suppress_update_error_dialog = previous_suppress
            self._update_check_running = False

    async def _prompt_update_for_release(self, release_info, check_source: str):
        """提示用户是否更新到指定版本"""
        source_text = "启动时" if check_source == "startup" else "手动检查时"

        if not self.update_controller.manager.is_packaged_app():
            QMessageBox.information(
                self,
                "发现新版本",
                f"{source_text}检测到新版本 {release_info.tag_name}。\n\n当前为源码运行模式，仅支持检测，不支持自动替换程序。",
            )
            Log.info(f"{source_text}发现新版本，但当前为源码运行模式，更新功能不可用")
            return

        update_reply = QMessageBox.question(
            self,
            "发现新版本",
            f"{source_text}检测到新版本 {release_info.tag_name}，是否立即下载并更新？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if update_reply != QMessageBox.StandardButton.Yes:
            Log.info(f"{source_text}发现新版本后，用户选择暂不更新: {release_info.tag_name}")
            return

        Log.info(f"{source_text}发现新版本后，用户选择立即更新: {release_info.tag_name}")
        await self.start_program_update()

    @asyncSlot()
    async def auto_check_update_on_startup(self):
        """程序启动后自动检查更新"""
        from main import __version__

        if getattr(self, "_login_action_running", False):
            Log.debug("登录流程尚未结束，已重新排队自动检查更新")
            self._startup_update_check_triggered = False
            QTimer.singleShot(1500, self.trigger_startup_update_check)
            return

        if self._is_update_check_running():
            return

        Log.info("检查软件是否为最新版本")
        release_info = await self._run_update_check(__version__, show_progress_dialog=False, silent_error=True)

        if self.update_controller.last_check_failed:
            Log.warn(f"程序启动后自动检查更新失败: {self.update_controller.last_check_error_message}")
            return

        if release_info is None:
            Log.info(f"程序启动后自动检查更新完成: 当前已是最新版本")
            return

        await self._prompt_update_for_release(release_info, "startup")

    @asyncSlot()
    async def on_version_label_clicked(self):
        """点击版本号后检查更新"""
        from main import __version__

        if self._is_update_check_running():
            QMessageBox.information(self, "检查更新", "当前正在检查更新，请稍候。")
            return

        reply = QMessageBox.question(
            self,
            "检查更新",
            f"当前版本为 {__version__}，是否检查最新版本？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        release_info = await self._run_update_check(__version__, show_progress_dialog=True, silent_error=False)

        if release_info is None:
            if self.update_controller.last_check_failed:
                return
            QMessageBox.information(self, "检查更新", f"当前已是最新版本: {__version__}")
            return

        await self._prompt_update_for_release(release_info, "manual")

    async def start_program_update(self):
        """下载并启动更新"""
        from main import __version__

        if not self.update_controller.manager.is_packaged_app():
            QMessageBox.information(self, "提示", "当前为源码运行模式，仅支持检测更新，不支持自动替换程序。")
            return

        self._show_update_progress_dialog("程序更新", "正在下载更新文件...", allow_cancel=True)

        script_path = await self.update_controller.download_and_prepare_update(__version__)
        if script_path:
            dialog = getattr(self, "_update_progress_dialog", None)
            if dialog is not None:
                dialog.setLabelText("更新文件已准备完成，程序即将退出并重启...")
                dialog.setRange(0, 1)
                dialog.setValue(1)
            self.update_controller.launch_update(script_path)
            QApplication.processEvents()
            await asyncio.sleep(0.5)
            QApplication.instance().quit()
            return

        self._close_update_progress_dialog()

    def on_update_error(self, message):
        """处理更新错误"""
        self._close_update_progress_dialog()
        if getattr(self, "_suppress_update_error_dialog", False):
            Log.warn(f"已静默处理更新错误: {message}")
            return
        QMessageBox.warning(self, "更新失败", message)

    def on_update_cancelled(self, message):
        """处理更新取消"""
        self._close_update_progress_dialog()
        QMessageBox.information(self, "已取消", message)

    def on_update_dialog_canceled(self):
        """处理更新弹窗取消动作"""
        dialog = getattr(self, "_update_progress_dialog", None)
        if dialog is not None:
            dialog.setLabelText("正在取消下载，请稍候...")
        self.update_controller.request_cancel()

    def on_update_download_progress(self, current, total, asset_name):
        """更新下载进度显示"""
        dialog = getattr(self, "_update_progress_dialog", None)
        if dialog is None:
            return

        dialog.setRange(0, max(total, 1))
        dialog.setValue(min(current, max(total, 1)))
        if total > 0:
            percent = int(current / total * 100)
            dialog.setLabelText(f"正在下载 {asset_name}\n{percent}% ({current}/{total})")
        else:
            dialog.setLabelText(f"正在下载 {asset_name}")

    def create_about_page(self):
        """创建关于页面"""
        about_page = QWidget()
        about_layout = QVBoxLayout(about_page)
        about_layout.setContentsMargins(20, 15, 20, 15)
        about_layout.setSpacing(15)

        # 页面标题
        title_label = QLabel("关于本软件")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(20)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: @primary_color; margin-bottom: 10px;")
        about_layout.addWidget(title_label)

        # 主要信息部分
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
                border: 2px solid @primary_color;
                border-radius: 35px;
                background-color: white;
                padding: 3px;
            }
        """)
        author_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        author_avatar.setScaledContents(True)

        # 加载程序图标作为作者头像
        try:
            icon_path = static_resource_path("favicon.ico")
            if os.path.exists(icon_path):
                pixmap = QPixmap(icon_path)
                if not pixmap.isNull():
                    scaled_pixmap = pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    circular_pixmap = create_circular_pixmap(scaled_pixmap, 64)
                    author_avatar.setPixmap(circular_pixmap)
                else:
                    author_avatar.setText("Be1k0")
            else:
                author_avatar.setText("Be1k0")
        except Exception as e:
            author_avatar.setText("Be1k0")

        author_layout.addWidget(author_avatar)

        # 作者信息文本
        author_info_layout = QVBoxLayout()
        author_info_layout.setContentsMargins(0, 5, 0, 0)
        author_info_layout.setSpacing(8)

        # 作者名称
        author_name = QLabel("作者: Be1k0")
        author_name.setFont(QFont("", 15, QFont.Weight.Bold))
        author_name.setStyleSheet("color: @text_color;")
        author_info_layout.addWidget(author_name)

        # 项目地址
        primary_color = THEME_MANAGER.get_color("primary_color", "#0d6efd")
        project_url = QLabel(
            f"项目地址: <a href='https://github.com/Be1k0/yuque_document_download/' style='color: {primary_color}; text-decoration: none;'>https://github.com/Be1k0/yuque_document_download/</a>")
        project_url.setOpenExternalLinks(True)
        project_url.setWordWrap(False)
        project_url.setFont(QFont("", 14))
        project_url.setStyleSheet("color: @text_secondary;")
        author_info_layout.addWidget(project_url)

        author_layout.addLayout(author_info_layout)
        author_layout.addStretch()

        info_layout.addWidget(author_section)
        info_layout.addSpacing(10)

        # 项目简介
        description_title = QLabel("简介")
        description_title.setFont(QFont("", 15, QFont.Weight.Bold))
        description_title.setStyleSheet("color: @text_color;")
        info_layout.addWidget(description_title)

        description_text = QLabel("一款针对语雀知识库的批量导出工具，支持一键导出账号内所有知识库中的文档，也支持导出别人公开的知识库。")
        description_text.setWordWrap(True)
        description_text.setFont(QFont("", 14))
        description_text.setStyleSheet("color: @text_secondary; padding: 5px 0;")

        info_layout.addWidget(description_text)
        info_layout.addSpacing(5)

        # 更新日志部分
        changelog_title = QLabel("更新日志")
        changelog_title.setFont(QFont("", 15, QFont.Weight.Bold))
        changelog_title.setStyleSheet("color: @text_color;")
        info_layout.addWidget(changelog_title)

        changelog_browser = QTextBrowser()
        changelog_browser.setOpenExternalLinks(True)
        changelog_browser.setStyleSheet("""
            QTextBrowser {
                background-color: transparent;
                border: 1px solid rgba(128, 128, 128, 0.2);
                border-radius: 4px;
                color: @text_secondary;
                padding: 10px;
            }
        """)
        changelog_browser.setMinimumHeight(300)
        changelog_browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # 读取更新日志文件
        changelog_content = ""
        try:
            changelog_path = static_resource_path("CHANGELOG.md")
            if os.path.exists(changelog_path):
                with open(changelog_path, 'r', encoding='utf-8') as f:
                    changelog_content = f.read()
            else:
                changelog_content = "*未能找到更新日志文件(CHANGELOG.md)*"
        except Exception as e:
            changelog_content = f"*加载更新日志失败: {str(e)}*"
            
        changelog_browser.setMarkdown(changelog_content)
        info_layout.addWidget(changelog_browser)

        about_layout.addWidget(info_widget)

        about_layout.addStretch(1)

        # 版本信息
        from main import __version__
        self.version_button = QPushButton(f"版本: {__version__}")
        self.version_button.setObjectName("VersionButton")
        self.version_button.setFlat(True)
        self.version_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.version_button.clicked.connect(self.on_version_label_clicked)
        about_layout.addWidget(self.version_button, alignment=Qt.AlignmentFlag.AlignCenter)

        return about_page

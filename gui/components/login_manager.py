import os
import json
import shutil
from qasync import asyncSlot
from PyQt6.QtWidgets import QMessageBox, QTabWidget
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QTimer
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from src.libs.log import Log
from utils import resource_path, create_circular_pixmap

class LoginManagerMixin:
    """登录管理器类
    
    提供登录管理功能，包括登录、登出、检查登录状态等。
    """
    web_login_finished = pyqtSignal()
    web_login_error = pyqtSignal(str)

    def _set_login_action_running(self, is_running: bool):
        """设置登录流程运行状态"""
        self._login_action_running = is_running

    def _show_async_message_box(self, icon, title: str, message: str):
        """异步显示消息框，避免阻塞事件循环"""
        def _open_message_box():
            box = QMessageBox(self)
            box.setIcon(icon)
            box.setWindowTitle(title)
            box.setText(message)
            box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            active_boxes = getattr(self, "_active_message_boxes", [])
            active_boxes.append(box)
            self._active_message_boxes = active_boxes
            box.finished.connect(lambda _: self._remove_message_box(box))
            box.open()

        QTimer.singleShot(0, _open_message_box)

    def _remove_message_box(self, box):
        """移除已关闭的消息框引用"""
        active_boxes = getattr(self, "_active_message_boxes", [])
        if box in active_boxes:
            active_boxes.remove(box)
        self._active_message_boxes = active_boxes

    @property
    def login_controller(self):
        """获取登录控制器实例"""
        if not hasattr(self, '_login_controller'):
            from gui.controllers.login_controller import LoginController
            self._login_controller = LoginController()
            self._login_controller.login_failed.connect(self.on_any_login_error)
            self._login_controller.login_expired.connect(self.on_login_expired)
            
        return self._login_controller

    def on_any_login_error(self, message):
        """处理任意登录方式的错误"""
        if hasattr(self, 'login_button'):
            self.login_button.setEnabled(True)
            self.login_button.setText("登录")
        
        if hasattr(self, 'web_login_button'):
            self.web_login_button.setEnabled(True)
            self.web_login_button.setText("网页端登录")

        self._show_async_message_box(QMessageBox.Icon.Critical, "登录错误", message)

    def on_login_expired(self, message):
        """处理登录过期"""
        self._show_async_message_box(QMessageBox.Icon.Warning, "登录已过期", message)
        self.logout(force=True)

    @asyncSlot()
    async def check_login_status(self):
        """检查是否已经登录"""
        is_logged_in = await self.login_controller.check_login_status()
        
        if is_logged_in:
            self.show_user_info()
            tabs = self.findChild(QTabWidget)
            if tabs:
                tabs.setCurrentIndex(1)
            self.load_books()
        else:
            self.show_login_form()

    @asyncSlot()
    async def login(self):
        """处理登录"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "输入错误", "用户名和密码不能为空")
            return

        # 禁用登录按钮并显示状态
        self.login_button.setEnabled(False)
        self.login_button.setText("登录中...")

        self._set_login_action_running(True)
        try:
            # 使用 controller 执行登录
            result = await self.login_controller.login(username, password)
        finally:
            self._set_login_action_running(False)

        # 处理结果
        self.on_login_finished(result)

    @asyncSlot()
    async def web_login(self):
        """网页端登录"""
        # 禁用网页登录按钮并显示状态
        self.web_login_button.setEnabled(False)
        self.web_login_button.setText("正在打开浏览器...")
        self._set_login_action_running(True)
        try:
            result = await self.login_controller.web_login()
        finally:
            self._set_login_action_running(False)
        
        if result:
            self.on_web_login_finished()
        else:
            error_message = getattr(self.login_controller, "last_web_login_error", "") or "网页登录失败，请重试。"
            self.on_web_login_error(error_message)

    def on_web_login_finished(self):
        """网页登录完成后的回调"""
        self.web_login_button.setEnabled(True)
        self.web_login_button.setText("网页端登录")
        self._show_async_message_box(QMessageBox.Icon.Information, "登录成功", "成功登录到语雀账号")

        # 显示用户信息，隐藏登录表单
        self.show_user_info()

        # 切换到知识库选择标签页
        tabs = self.findChild(QTabWidget)
        if tabs:
            tabs.setCurrentIndex(1)
        self.load_books()

    def on_web_login_error(self, error_msg):
        """网页登录出错的回调
        
        Args:
            error_msg: 错误信息
        """
        self.web_login_button.setEnabled(True)
        self.web_login_button.setText("网页端登录")
        self._show_async_message_box(QMessageBox.Icon.Critical, "登录错误", f"网页登录出错: {error_msg}")

    def on_login_finished(self, result):
        """登录完成后的回调
        
        Args:
            result: 登录结果
        """
        self.login_button.setEnabled(True)
        self.login_button.setText("登录")

        if result:
            self._show_async_message_box(QMessageBox.Icon.Information, "登录成功", "成功登录到语雀账号")
            self.show_user_info()
            tabs = self.findChild(QTabWidget)
            if tabs:
                tabs.setCurrentIndex(1)
            self.load_books()
        else:
            self._show_async_message_box(QMessageBox.Icon.Warning, "登录失败", "登录失败，请检查用户名和密码")

    def on_login_error(self, error_msg):
        """登录出错的回调
        
        Args:
            error_msg: 错误信息
        """
        self.login_button.setEnabled(True)
        self.login_button.setText("登录")
        self._show_async_message_box(QMessageBox.Icon.Critical, "登录错误", f"登录过程出错: {error_msg}")

    def show_login_form(self):
        """显示登录表单，隐藏用户信息"""
        self.login_group.show()
        self.user_info_group.hide()

    def show_user_info(self):
        """显示用户信息，隐藏登录表单"""
        self.login_group.hide()
        self.user_info_group.show()
        self.update_user_info_display()

    def update_user_info_display(self):
        """更新用户信息显示"""
        try:
            meta_dir = resource_path('.meta')
            os.makedirs(meta_dir, exist_ok=True)
            
            # 读取用户信息文件
            user_info_path = os.path.join(meta_dir, 'user_info.json')
            if os.path.exists(user_info_path):
                with open(user_info_path, 'r', encoding='utf-8') as f:
                    user_data = json.load(f)
                    user_info = user_data.get('user_info', {})

                    # 更新用户信息显示
                    name = user_info.get('name', '--')
                    login = user_info.get('login', '--')
                    avatar_url = user_info.get('avatar', '')

                    self.user_name_label.setText(f"用户名: {name}")
                    self.user_id_label.setText(f"用户ID: {login}")

                    # 头像文件路径
                    avatar_file = os.path.join(meta_dir, 'avatar.jpg')
                    
                    # 加载头像
                    if avatar_url:
                        if os.path.exists(avatar_file):
                            self.load_avatar_from_local(avatar_file)
                        else:
                            self.load_avatar(avatar_url)
                    else:
                        self.avatar_label.setText("头像")
                        try:
                            from src.ui.theme_manager import THEME_MANAGER
                            theme = THEME_MANAGER.theme_config.get(THEME_MANAGER.current_theme, {})
                            bg_color = theme.get('input_background', '#f8f9fa')
                            text_color = theme.get('secondary_color', '#6c757d')
                            border_color = theme.get('border_color', '#dee2e6')
                            
                            self.avatar_label.setStyleSheet(f"""
                                QLabel {{
                                    border: 2px solid {border_color};
                                    border-radius: 40px;
                                    background-color: {bg_color};
                                    color: {text_color};
                                    font-size: 12px;
                                }}
                            """)
                        except:
                            self.avatar_label.setStyleSheet("""
                                QLabel {
                                    border: 2px solid #ddd;
                                    border-radius: 40px;
                                    background-color: #f8f9fa;
                                    color: #666;
                                    font-size: 12px;
                                }
                            """)
            else:
                self.user_name_label.setText("用户名: --")
                self.user_id_label.setText("用户ID: --")
                self.avatar_label.setText("头像")

        except Exception as e:
            Log.error(f"更新用户信息显示时出错: {e}")
            import traceback
            traceback.print_exc()

    def load_avatar_from_local(self, avatar_path):
        """从本地文件加载头像
        
        Args:
            avatar_path: 头像文件路径
        """
        try:
            Log.debug(f"从本地文件加载头像: {avatar_path}")
            pixmap = QPixmap(avatar_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaled(76, 76, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                circular_pixmap = create_circular_pixmap(scaled_pixmap, 76)
                self.avatar_label.setPixmap(circular_pixmap)
                Log.debug("本地头像加载成功")
            else:
                Log.error("本地头像文件无效")
                self.avatar_label.setText("头像")
        except Exception as e:
            Log.error(f"加载本地头像时出错: {e}")
            import traceback
            traceback.print_exc()
            self.avatar_label.setText("头像")
    
    def load_avatar(self, avatar_url):
        """加载用户头像
        
        Args:
            avatar_url: 头像URL
        """
        try:
            Log.debug(f"开始加载头像: {avatar_url}")

            # 创建网络管理器
            if not hasattr(self, 'network_manager'):
                self.network_manager = QNetworkAccessManager()
                self.network_manager.finished.connect(self.on_avatar_loaded)
                Log.debug("网络管理器创建成功")

            # 发起网络请求
            request = QNetworkRequest(QUrl(avatar_url))
            # 设置用户代理，避免被服务器拒绝
            request.setRawHeader(b'User-Agent', b'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            self.network_manager.get(request)
            Log.debug("网络请求已发起")

        except Exception as e:
            Log.error(f"加载头像时出错: {e}")
            import traceback
            traceback.print_exc()
            self.avatar_label.setText("头像")

    def on_avatar_loaded(self, reply):
        """头像加载完成的回调
        
        Args:
            reply: 网络请求的回复
        """
        try:
            Log.debug(f"头像请求完成，错误码: {reply.error()}")
            if reply.error() == QNetworkReply.NetworkError.NoError:
                data = reply.readAll()
                Log.debug(f"接收到头像数据，大小: {len(data)} 字节")
                
                # 保存头像到本地
                meta_dir = resource_path('.meta')
                avatar_file = os.path.join(meta_dir, 'avatar.jpg')
                with open(avatar_file, 'wb') as f:
                    f.write(data)
                Log.debug(f"头像保存到本地成功: {avatar_file}")
                
                pixmap = QPixmap()
                if pixmap.loadFromData(data):
                    Log.debug("头像数据加载成功，开始处理")
                    scaled_pixmap = pixmap.scaled(76, 76, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    circular_pixmap = create_circular_pixmap(scaled_pixmap, 76)
                    self.avatar_label.setPixmap(circular_pixmap)
                    Log.debug("头像设置成功")
                else:
                    Log.warn("头像数据加载失败")
                    self.avatar_label.setText("头像")
            else:
                Log.error(f"网络请求失败: {reply.errorString()}")
                self.avatar_label.setText("头像")
        except Exception as e:
            Log.error(f"处理头像数据时出错: {e}")
            import traceback
            traceback.print_exc()
            self.avatar_label.setText("头像")
        finally:
            reply.deleteLater()

    def logout(self, force=False):
        """注销登录"""
        if not force:
            reply = QMessageBox.question(self, "确认注销", "确定要注销当前账号吗？",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
        else:
            reply = QMessageBox.StandardButton.Yes

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # 删除.meta文件夹下的所有文件
                meta_dir = resource_path('.meta')
                if os.path.exists(meta_dir):
                    for filename in os.listdir(meta_dir):
                        # 避免删除settings.json文件，保留程序配置
                        if filename == 'settings.json':
                            continue
                        file_path = os.path.join(meta_dir, filename)
                        try:
                            if os.path.isfile(file_path) or os.path.islink(file_path):
                                os.unlink(file_path)
                            elif os.path.isdir(file_path):
                                shutil.rmtree(file_path)
                        except Exception as e:
                            Log.error(f"删除 {file_path} 时出错: {e}")

                # 清空登录表单和数据
                self.username_input.clear()
                self.password_input.clear()
                self.book_list.clear()
                self.article_list.clear()

                # 显示登录表单
                self.show_login_form()

                tabs = self.findChild(QTabWidget)
                if tabs:
                    tabs.setCurrentIndex(0)

                if not force:
                    QMessageBox.information(self, "注销成功", "已成功注销账号")

            except Exception as e:
                QMessageBox.critical(self, "注销失败", f"注销过程中出错: {str(e)}")

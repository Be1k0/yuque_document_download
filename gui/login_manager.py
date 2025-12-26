import os
import json
import shutil
import time
import threading
from PyQt5.QtWidgets import QMessageBox, QTabWidget
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, QUrl, pyqtSignal
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
from src.libs.constants import YuqueAccount
from src.libs.log import Log
from src.core.yuque import YuqueApi
from src.libs.tools import get_local_cookies, save_cookies
from utils import AsyncWorker, resource_path, create_circular_pixmap

class LoginManagerMixin:
    # 定义信号
    web_login_finished = pyqtSignal()
    web_login_error = pyqtSignal(str)

    def check_login_status(self):
        """检查是否已经登录"""
        cookies = get_local_cookies()
        if cookies:
            self.show_user_info()
            tabs = self.findChild(QTabWidget)
            if tabs:
                tabs.setCurrentIndex(1)
            self.load_books()
        else:
            self.show_login_form()
            pass

    def login(self):
        """处理登录"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "输入错误", "用户名和密码不能为空")
            return

        # 禁用登录按钮并显示状态
        self.login_button.setEnabled(False)
        self.login_button.setText("登录中...")

        # 创建帐户对象
        account = YuqueAccount(username=username, password=password)

        # 在单独的线程中启动登录过程
        self.login_worker = AsyncWorker(YuqueApi.login, username, password)
        self.login_worker.taskFinished.connect(self.on_login_finished)
        self.login_worker.taskError.connect(self.on_login_error)
        self.login_worker.start()

    def web_login(self):
        """网页端登录"""
        # 禁用网页登录按钮并显示状态
        self.web_login_button.setEnabled(False)
        self.web_login_button.setText("正在打开浏览器...")

        # 连接信号
        self.web_login_finished.connect(self.on_web_login_finished)
        self.web_login_error.connect(self.on_web_login_error)

        # 在单独的线程中启动网页登录过程
        self.web_login_thread = threading.Thread(target=self._web_login_thread, daemon=True)
        self.web_login_thread.start()

    def _web_login_thread(self):
        """网页登录线程函数"""
        try:
            from playwright.sync_api import sync_playwright
            import playwright.sync_api as p
            import asyncio

            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"

            with sync_playwright() as p:
                browser_channels = ["msedge", "chrome", "360chrome", "qqbrowser", "brave", None]
                browser = None
                for channel in browser_channels:
                    try:
                        if channel:
                            Log.info(f"启动系统中的 {channel}...")
                            browser = p.chromium.launch(headless=False, channel=channel)
                        if browser:
                            break
                    except Exception:
                        continue

                if not browser:
                    self.web_login_error.emit("未检测到适配的浏览器，请先安装Edge或谷歌浏览器后再运行。")
                    return

                context = browser.new_context()
                page = context.new_page()
                page.goto("https://www.yuque.com/login")

                try:
                    page.wait_for_url(lambda url: "login" not in url and "yuque.com" in url, timeout=300000)
                    Log.info("检测到登录成功！正在提取数据...")
                    page.wait_for_load_state('networkidle')
                    cookies = context.cookies()
                except Exception as e:
                    Log.error("登录失败或超时。")
                    self.web_login_error.emit("登录失败或超时，请重试。")
                    browser.close()
                    return

                if not cookies:
                    self.web_login_error.emit("错误：未提取到任何 Cookie。")
                    browser.close()
                    return

                # 处理Cookie，仅拼接字符串
                cookie_list = []
                for cookie in cookies:
                    cookie_list.append(f"{cookie['name']}={cookie['value']}")

                # 强制设置过期时间为当前时间 + 一周（毫秒级）
                current_time_ms = int(time.time() * 1000)
                expire_time_ms = current_time_ms + (7 * 24 * 60 * 60 * 1000)
                Log.info(f"设置 Cookie 过期时间为一周后（{expire_time_ms}）")

                # 拼接Cookie字符串
                cookie_string = "; ".join(cookie_list)
                save_cookies(cookie_string, expire_time_ms)

                # 关闭浏览器
                time.sleep(1)
                browser.close()

                # 获取用户信息
                Log.info("正在获取用户信息...")
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    success = loop.run_until_complete(YuqueApi.get_user_info())
                    loop.close()

                    if not success:
                        self.web_login_error.emit("获取用户信息失败，请重试。")
                        return
                except Exception as e:
                    Log.error(f"获取用户信息时出错: {e}")
                    self.web_login_error.emit(f"获取用户信息时出错: {str(e)}")
                    return

                # 通知登录成功
                self.web_login_finished.emit()

        except ImportError:
            self.web_login_error.emit("未安装playwright库，请先运行: pip install playwright && playwright install")
        except Exception as e:
            Log.error(f"网页登录出错: {e}")
            self.web_login_error.emit(f"网页登录出错: {str(e)}")

    def on_web_login_finished(self):
        """网页登录完成后的回调"""
        self.web_login_button.setEnabled(True)
        self.web_login_button.setText("网页端登录")
        QMessageBox.information(self, "登录成功", "成功登录到语雀账号")

        # 显示用户信息，隐藏登录表单
        self.show_user_info()

        # 切换到知识库选择标签页
        tabs = self.findChild(QTabWidget)
        if tabs:
            tabs.setCurrentIndex(1)
        self.load_books()

    def on_web_login_error(self, error_msg):
        """网页登录出错的回调"""
        self.web_login_button.setEnabled(True)
        self.web_login_button.setText("网页端登录")
        QMessageBox.critical(self, "登录错误", f"网页登录出错: {error_msg}")

    def on_login_finished(self, result):
        """登录完成后的回调"""
        self.login_button.setEnabled(True)
        self.login_button.setText("登录")

        if result:
            # 登录成功
            QMessageBox.information(self, "登录成功", "成功登录到语雀账号")
            self.show_user_info()
            tabs = self.findChild(QTabWidget)
            if tabs:
                tabs.setCurrentIndex(1)
            self.load_books()
        else:
            QMessageBox.warning(self, "登录失败", "登录失败，请检查用户名和密码")

    def on_login_error(self, error_msg):
        """登录出错的回调"""
        self.login_button.setEnabled(True)
        self.login_button.setText("登录")
        QMessageBox.critical(self, "登录错误", f"登录过程出错: {error_msg}")

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
            # 确保.meta文件夹存在
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
                            # 如果本地存在头像文件，直接加载
                            self.load_avatar_from_local(avatar_file)
                        else:
                            # 否则从网络下载
                            self.load_avatar(avatar_url)
                    else:
                        # 设置默认头像
                        self.avatar_label.setText("头像")
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
                # 如果文件不存在，显示默认信息
                self.user_name_label.setText("用户名: --")
                self.user_id_label.setText("用户ID: --")
                self.avatar_label.setText("头像")

        except Exception as e:
            Log.error(f"更新用户信息显示时出错: {e}")
            import traceback
            traceback.print_exc()

    def load_avatar_from_local(self, avatar_path):
        """从本地文件加载头像"""
        try:
            Log.debug(f"从本地文件加载头像: {avatar_path}")
            pixmap = QPixmap(avatar_path)
            if not pixmap.isNull():
                # 缩放头像到合适大小
                scaled_pixmap = pixmap.scaled(76, 76, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                # 创建圆形头像
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
        """加载用户头像"""
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
            # 设置默认头像
            self.avatar_label.setText("头像")

    def on_avatar_loaded(self, reply):
        """头像加载完成的回调"""
        try:
            Log.debug(f"头像请求完成，错误码: {reply.error()}")
            if reply.error() == reply.NoError:
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
                    # 缩放头像到合适大小
                    scaled_pixmap = pixmap.scaled(76, 76, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    # 创建圆形头像
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

    def logout(self):
        """注销登录"""
        reply = QMessageBox.question(self, "确认注销", "确定要注销当前账号吗？",
                                     QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.No)

        if reply == QMessageBox.Yes:
            try:
                # 删除.meta文件夹下的所有文件
                meta_dir = resource_path('.meta')
                if os.path.exists(meta_dir):
                    # 删除文件夹内所有内容
                    for filename in os.listdir(meta_dir):
                        file_path = os.path.join(meta_dir, filename)
                        try:
                            if os.path.isfile(file_path) or os.path.islink(file_path):
                                os.unlink(file_path)
                            elif os.path.isdir(file_path):
                                shutil.rmtree(file_path)
                        except Exception as e:
                            Log.error(f"删除 {file_path} 时出错: {e}")

                # 清空输入框
                self.username_input.clear()
                self.password_input.clear()

                # 清空知识库列表
                self.book_list.clear()

                # 清空文章列表
                self.article_list.clear()

                # 显示登录表单
                self.show_login_form()

                # 切换到登录标签页
                tabs = self.findChild(QTabWidget)
                if tabs:
                    tabs.setCurrentIndex(0)

                QMessageBox.information(self, "注销成功", "已成功注销账号")

            except Exception as e:
                QMessageBox.critical(self, "注销失败", f"注销过程中出错: {str(e)}")

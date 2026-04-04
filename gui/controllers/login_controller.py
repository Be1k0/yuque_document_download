from PyQt6.QtCore import pyqtSignal
from src.core.yuque import YuqueClient
from src.core.web_login import SystemBrowserLoginBridge
from src.libs.log import Log
from src.libs.exceptions import CookiesExpiredError
from gui.controllers.base_controller import BaseController

class LoginController(BaseController):
    """登录控制器
    
    负责处理用户登录、登录状态检查和用户信息加载等相关任务。
    """
    
    # 信号定义
    login_success = pyqtSignal(object)  # 登录成功信号，携带用户信息
    login_failed = pyqtSignal(str)      # 登录失败信号，携带错误信息
    login_expired = pyqtSignal(str)     # 登录过期信号
    user_info_updated = pyqtSignal(dict) # 用户信息更新信号
    avatar_loaded = pyqtSignal(bytes)   # 头像加载完成信号
    captcha_required = pyqtSignal(str)  # 需要验证码信号
    
    def __init__(self, client: YuqueClient = None):
        super().__init__()
        self.client = client or YuqueClient()
        self.last_web_login_error = ""
        
    async def login(self, username: str, password: str) -> bool:
        """执行登录操作
        
        Args:
            username: 用户名
            password: 密码

        Returns:
            bool: 登录是否成功
        """
        if not username or not password:
            self.login_failed.emit("用户名或密码不能为空")
            return False
            
        try:
            self.log_info(f"正在尝试登录用户: {username}")
            
            # 执行登录
            success = await self.client.login(username, password)
            
            if success:
                # 获取用户信息
                user_info_success = await self.client.get_user_info()
                if user_info_success:
                    self.log_success("登录成功且获取用户信息成功")
                    from src.libs.tools import get_cache_user_info
                    user_info = get_cache_user_info()
                    if user_info:
                        # 兼容 dict 和 object
                        if isinstance(user_info, dict):
                            user_data = {
                                "name": user_info.get("name"),
                                "login": user_info.get("login"),
                                "avatar": user_info.get("avatar", "")
                            }
                        else:
                            user_data = {
                                "name": user_info.name,
                                "login": user_info.login,
                                "avatar": getattr(user_info, "avatar", "")
                            }
                        self.login_success.emit(user_data)
                        return True
            
            self.log_error("登录失败", Exception("用户名或密码错误"))
            self.login_failed.emit("登录失败，请检查用户名和密码")
            return False
            
        except Exception as e:
            self.log_error("登录过程中发生异常", e)
            self.login_failed.emit(f"登录异常: {str(e)}")
            return False

    async def check_login_status(self) -> bool:
        """检查登录状态
        
        Returns:
            bool: 登录状态是否有效
        """
        from src.libs.tools import get_local_cookies, get_cache_user_info
        
        cookies = get_local_cookies()
        if not cookies:
            from src.libs.constants import GLOBAL_CONFIG
            from src.libs.file import File
            f = File()
            if f.exists(GLOBAL_CONFIG.cookies_file):
                Log.info("Cookies 在本地已过期")
                self.login_expired.emit("您的登录凭证已过期，请重新登录")
            return False
            
        # 验证 cookies 是否有效
        try:
            is_valid = await self.client.get_user_info()
            if is_valid:
                user_info = get_cache_user_info()
                if user_info:
                    if isinstance(user_info, dict):
                        user_data = {
                            "name": user_info.get("name"),
                            "login": user_info.get("login"),
                            "avatar": user_info.get("avatar", "")
                        }
                    else:
                        user_data = {
                            "name": user_info.name,
                            "login": user_info.login,
                            "avatar": getattr(user_info, "avatar", "")
                        }
                    
                    self.login_success.emit(user_data)
                    return True
        except CookiesExpiredError:
            Log.info("Cookies 已过期")
            self.login_expired.emit("您的登录已过期，请重新登录")
            return False
        except Exception as e:
            err_msg = str(e)
            if "HTTP 401" in err_msg or "HTTP 403" in err_msg or "登录已过期" in err_msg:
                Log.info("服务端返回登录无效或已过期")
                self.login_expired.emit("您的登录已失效，请重新登录")
                return False
            Log.error(f"检查登录状态出错: {e}")
            return False
        
        return False

    async def load_user_avatar(self, avatar_url: str):
        """加载用户头像
        
        Args:
            avatar_url: 头像URL
        """
        if not avatar_url:
            return

        try:
            session = await self.client._get_session()
            async with session.get(avatar_url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    self.avatar_loaded.emit(data)
        except Exception as e:
            self.log_error(f"加载头像失败: {avatar_url}", e)

    async def web_login(self) -> bool:
        """执行网页登录
        
        Returns:
            bool: 登录是否成功
        """
        import time
        from src.libs.tools import save_cookies
        
        self.last_web_login_error = ""
        try:
            bridge = SystemBrowserLoginBridge()
            self.log_info("正在打开系统浏览器，请在浏览器中完成登录...")
            result = await bridge.login()

            if not result.cookie_string:
                self.last_web_login_error = "未提取到有效 Cookie，请重新完成网页登录。"
                return False

            current_time_ms = int(time.time() * 1000)
            expire_time_ms = current_time_ms + (7 * 24 * 60 * 60 * 1000)
            Log.debug(f"网页登录浏览器: {result.browser_name}")
            Log.debug(f"网页登录完成，最终页面: {result.final_url}")
            Log.debug(f"提取到的关键 Cookie: {', '.join(result.cookie_names) or '无'}")
            Log.debug(f"设置 Cookie 过期时间为一周后（{expire_time_ms}）")

            save_success = save_cookies(result.cookie_string, expire_time_ms)
            if not save_success:
                self.last_web_login_error = "保存网页登录 Cookie 失败，请检查 .meta 目录权限。"
                return False

            Log.debug("正在校验网页登录后的用户信息...")
            if not await self.client.get_user_info():
                self.last_web_login_error = "获取用户信息失败，请重试。"
                return False

            return await self.check_login_status()

        except ImportError:
            self.last_web_login_error = "未安装playwright库，请先运行: pip install playwright"
            return False
        except Exception as e:
            self.log_error("网页登录出错", e)
            self.last_web_login_error = str(e)
            return False

from PyQt6.QtCore import pyqtSignal
from src.core.yuque import YuqueClient
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
        import os
        import time
        from src.libs.tools import save_cookies
        
        try:
            from playwright.async_api import async_playwright
            
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
            
            # 尝试使用系统中安装的浏览器进行登录
            async with async_playwright() as p:
                browser_channels = ["msedge", "chrome", "360chrome", "qqbrowser", "brave", None]
                browser = None
                for channel in browser_channels:
                    try:
                        if channel:
                            self.log_info(f"启动系统中的 {channel}...")
                            browser = await p.chromium.launch(headless=False, channel=channel)
                        if browser:
                            break
                    except Exception:
                        continue
                
                if not browser:
                    try: 
                        browser = await p.chromium.launch(headless=False)
                    except:
                        pass
                
                if not browser:
                    self.login_failed.emit("未检测到适配的浏览器，请先安装Edge或谷歌浏览器后再运行。")
                    return False
                
                try:
                    context = await browser.new_context()
                    page = await context.new_page()
                    await page.goto("https://www.yuque.com/login")
                    
                    self.log_info("等待用户登录...")
                    
                    # 等待登录成功跳转
                    await page.wait_for_url(lambda url: "login" not in url and "yuque.com" in url, timeout=300000)
                    
                    self.log_info("检测到登录成功！正在提取数据...")
                    await page.wait_for_load_state('networkidle')
                    cookies = await context.cookies()
                    
                except Exception as e:
                    self.log_error("登录失败或超时", e)
                    self.login_failed.emit("登录失败或超时，请重试。")
                    if browser:
                        await browser.close()
                    return False
                
                if not cookies:
                    self.login_failed.emit("错误：未提取到任何 Cookie。")
                    if browser:
                        await browser.close()
                    return False
                
                # 处理Cookie
                cookie_list = []
                for cookie in cookies:
                    cookie_list.append(f"{cookie['name']}={cookie['value']}")
                
                # 强制设置过期时间为当前时间 + 一周
                current_time_ms = int(time.time() * 1000)
                expire_time_ms = current_time_ms + (7 * 24 * 60 * 60 * 1000)
                self.log_info(f"设置 Cookie 过期时间为一周后（{expire_time_ms}）")
                
                # 保存 Cookie
                cookie_string = "; ".join(cookie_list)
                save_cookies(cookie_string, expire_time_ms)
                
                await browser.close()
                
                self.log_info("正在获取用户信息...")
                success = await self.client.get_user_info()
                
                if not success:
                    self.login_failed.emit("获取用户信息失败，请重试。")
                    return False
                
                return await self.check_login_status()

        except ImportError:
            self.login_failed.emit("未安装playwright库，请先运行: pip install playwright")
            return False
        except Exception as e:
            self.log_error("网页登录出错", e)
            self.login_failed.emit(f"网页登录出错: {str(e)}")
            return False


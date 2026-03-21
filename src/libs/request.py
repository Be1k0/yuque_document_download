import asyncio
import json
import re
from typing import Dict, Any, Optional
from urllib.parse import urljoin
import contextlib
from .exceptions import CookiesExpiredError
import aiohttp
from .constants import GLOBAL_CONFIG
from .log import Log
from .tools import get_local_cookies

try:
    from .debug_logger import DebugLogger

    _has_debug_logger = True
except ImportError:
    _has_debug_logger = False


class Request:
    """HTTP请求类"""

    def __init__(self):
        self.host = self._get_match_host()

    @staticmethod
    def _get_match_host() -> str:
        """获取匹配的host"""
        return GLOBAL_CONFIG.yuque_host

    @staticmethod
    def _get_request_headers() -> Dict[str, str]:
        """获取请求头"""
        return {
            "Content-Type": "application/json",
            "referer": GLOBAL_CONFIG.yuque_referer,
            "origin": Request._get_match_host(),
            "User-Agent": GLOBAL_CONFIG.user_agent
        }

    @staticmethod
    @contextlib.asynccontextmanager
    async def _get_session(session: Optional[aiohttp.ClientSession]):
        """获取会话上下文管理器"""
        if session:
            yield session
        else:
            async with aiohttp.ClientSession() as new_session:
                yield new_session

    @staticmethod
    async def get(url: str, session: Optional[aiohttp.ClientSession] = None) -> Dict[str, Any]:
        """发送GET请求并返回JSON
        
        Args:
            url: 请求URL
            session: 可选的session对象
        """
        target_url = urljoin(Request._get_match_host(), url)

        cookies = get_local_cookies()
        if not cookies:
            Log.error("cookies已过期，请清除缓存后重新执行程序")
            raise CookiesExpiredError()

        headers = Request._get_request_headers()
        headers["cookie"] = cookies
        headers["x-requested-with"] = "XMLHttpRequest"

        if _has_debug_logger:
            DebugLogger.log_request(target_url, "GET", headers)

        ssl_context = False if GLOBAL_CONFIG.disable_ssl else None
        async with Request._get_session(session) as current_session:
            try:
                async with current_session.get(target_url, headers=headers, ssl=ssl_context) as response:
                    response_text = await response.text()

                    if _has_debug_logger:
                        DebugLogger.log_response(
                            response.status,
                            response.headers,
                            response_text
                        )

                    if response.status != 200:
                        Log.error(f"接口请求失败：{url}")
                        Log.error(f"状态码：{response.status}", detailed=True)
                        clean_text = response_text.replace('\n', '\\n').replace('\r', '')
                        Log.debug(f"响应内容：{clean_text}")
                        raise Exception(f"HTTP {response.status}: {response_text}")

                    return json.loads(response_text)
            except aiohttp.ClientError as e:
                Log.error(f"请求失败：{str(e)}")
                if _has_debug_logger:
                    DebugLogger.log_error(f"请求失败: {str(e)}")
                raise

    @staticmethod
    async def get_text(url: str, is_html: bool = False, session: Optional[aiohttp.ClientSession] = None) -> str:
        """发送GET请求并返回文本
        
        Args:
            url: 请求URL
            is_html: 是否为HTML请求
            session: 可选的session对象
        """
        target_url = urljoin(Request._get_match_host(), url)

        cookies = get_local_cookies()
        if not cookies:
            Log.error("cookies已过期，请清除缓存后重新执行程序")
            raise CookiesExpiredError()

        headers = Request._get_request_headers()
        headers["cookie"] = cookies

        if not is_html:
            headers["x-requested-with"] = "XMLHttpRequest"
        else:
            headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
            headers["Accept-Language"] = "zh-CN,zh;q=0.9,en;q=0.8"
            if "x-requested-with" in headers:
                del headers["x-requested-with"]

        if _has_debug_logger:
            DebugLogger.log_request(target_url, "GET", headers)

        ssl_context = False if GLOBAL_CONFIG.disable_ssl else None
        async with Request._get_session(session) as current_session:
            try:
                async with current_session.get(target_url, headers=headers, ssl=ssl_context) as response:
                    content = await response.text(errors='replace')

                    if _has_debug_logger:
                        content_summary = content[:2000] + "..." if len(content) > 2000 else content
                        DebugLogger.log_response(
                            response.status,
                            response.headers,
                            f"Content length: {len(content)}, Preview: {content_summary}"
                        )

                    if response.status != 200:
                        error_text = content
                        Log.error(f"接口请求失败：{url}")
                        Log.error(f"状态码：{response.status}", detailed=True)
                        clean_text = error_text.replace('\n', '\\n').replace('\r', '')
                        Log.info(f"请求失败详情: {target_url}")
                        Log.debug(f"响应内容：{clean_text}")
                        raise Exception(f"HTTP {response.status}: {error_text}")

                    if is_html and len(content) < 1000:
                        Log.warn(f"获取到的HTML内容可能不完整，长度仅为 {len(content)} 字符", detailed=True)

                    return content
            except aiohttp.ClientError as e:
                Log.error(f"请求失败：{str(e)}")
                if _has_debug_logger:
                    DebugLogger.log_error(f"请求失败: {str(e)}")
                raise

    @staticmethod
    async def get_text_with_cookies(url: str, cookies_str: str, is_html: bool = False, session: Optional[aiohttp.ClientSession] = None) -> str:
        """发送GET请求并返回文本(使用自定义Cookie)
        
        Args:
            url: 请求URL
            cookies_str: Cookie字符串,格式为 "name1=value1; name2=value2"
            is_html: 是否为HTML请求
            session: 可选的session对象
        """
        target_url = urljoin(Request._get_match_host(), url)

        headers = Request._get_request_headers()
        if cookies_str:
            headers["cookie"] = cookies_str

        if not is_html:
            headers["x-requested-with"] = "XMLHttpRequest"
        else:
            headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
            headers["Accept-Language"] = "zh-CN,zh;q=0.9,en;q=0.8"
            if "x-requested-with" in headers:
                del headers["x-requested-with"]

        if _has_debug_logger:
            DebugLogger.log_request(target_url, "GET", headers)

        ssl_context = False if GLOBAL_CONFIG.disable_ssl else None
        async with Request._get_session(session) as current_session:
            try:
                async with current_session.get(target_url, headers=headers, ssl=ssl_context) as response:
                    content = await response.text(errors='replace')

                    if _has_debug_logger:
                        content_summary = content[:2000] + "..." if len(content) > 2000 else content
                        DebugLogger.log_response(
                            response.status,
                            response.headers,
                            f"Content length: {len(content)}, Preview: {content_summary}"
                        )

                    if response.status != 200:
                        error_text = content
                        Log.error(f"接口请求失败:{url}")
                        Log.error(f"状态码:{response.status}", detailed=True)
                        clean_text = error_text.replace('\n', '\\n').replace('\r', '')
                        Log.info(f"请求失败详情: {target_url}")
                        Log.debug(f"响应内容：{clean_text}")
                        raise Exception(f"HTTP {response.status}: {error_text}")

                    if is_html and len(content) < 1000:
                        Log.warn(f"获取到的HTML内容可能不完整,长度仅为 {len(content)} 字符", detailed=True)

                    return content
            except aiohttp.ClientError as e:
                Log.error(f"请求失败:{str(e)}")
                if _has_debug_logger:
                    DebugLogger.log_error(f"请求失败: {str(e)}")
                raise


    @staticmethod
    async def post(url: str, data: Dict[str, Any], session: Optional[aiohttp.ClientSession] = None) -> Dict[str, Any]:
        """发送POST请求并返回JSON
        
        Args:
            url: 请求URL
            data: POST数据字典
            session: 可选的session对象
        """
        target_url = urljoin(Request._get_match_host(), url)

        headers = Request._get_request_headers()

        if _has_debug_logger:
            DebugLogger.log_request(target_url, "POST", headers, data)

        ssl_context = False if GLOBAL_CONFIG.disable_ssl else None
        async with Request._get_session(session) as current_session:
            try:
                async with current_session.post(target_url, headers=headers, json=data, ssl=ssl_context) as response:
                    response_text = await response.text()

                    try:
                        response_data = json.loads(response_text)
                    except json.JSONDecodeError:
                        response_data = {"text": response_text}

                    if _has_debug_logger:
                        DebugLogger.log_response(
                            response.status,
                            response.headers,
                            response_data
                        )

                    if response.cookies:
                        new_cookie_dict = {cookie.key: cookie.value for cookie in response.cookies.values()}
                        if new_cookie_dict:
                            from .tools import get_local_cookies, save_cookies
                            existing_cookie_str = get_local_cookies()
                            cookie_dict = {}
                            if existing_cookie_str:
                                for item in existing_cookie_str.split(";"):
                                    if "=" in item:
                                        k, v = item.split("=", 1)
                                        cookie_dict[k.strip()] = v.strip()
                            for k, v in new_cookie_dict.items():
                                cookie_dict[k.strip()] = v.strip()
                            merged_cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items() if k])
                            save_cookies(merged_cookie_str)

                    if response.status != 200:
                        Log.error(f"接口请求失败：{url}")
                        Log.error(f"状态码：{response.status}", detailed=True)
                        clean_text = response_text.replace('\n', '\\n').replace('\r', '')
                        Log.debug(f"响应内容：{clean_text}")
                        raise Exception(f"HTTP {response.status}: {response_text}")

                    return response_data
            except aiohttp.ClientError as e:
                Log.error(f"请求失败：{str(e)}")
                if _has_debug_logger:
                    DebugLogger.log_error(f"请求失败: {str(e)}")
                raise

    @staticmethod
    async def put(url: str, data: Dict[str, Any], session: Optional[aiohttp.ClientSession] = None, persist_cookies: bool = True, return_cookies: bool = False) -> Any:
        """发送PUT请求并返回JSON
        
        Args:
            url: 请求URL
            data: PUT数据字典
            session: 可选的session对象
        """
        target_url = urljoin(Request._get_match_host(), url)

        headers = Request._get_request_headers()

        if _has_debug_logger:
            DebugLogger.log_request(target_url, "PUT", headers, data)

        ssl_context = False if GLOBAL_CONFIG.disable_ssl else None
        async with Request._get_session(session) as current_session:
            try:
                async with current_session.put(target_url, headers=headers, json=data, ssl=ssl_context) as response:
                    response_text = await response.text()

                    try:
                        response_data = json.loads(response_text)
                    except json.JSONDecodeError:
                        response_data = {"text": response_text}

                    if _has_debug_logger:
                        DebugLogger.log_response(
                            response.status,
                            response.headers,
                            response_data
                        )

                    if response.cookies:
                        new_cookie_dict = {cookie.key: cookie.value for cookie in response.cookies.values()}
                        if new_cookie_dict:
                            from .tools import get_local_cookies, save_cookies
                            existing_cookie_str = get_local_cookies()
                            cookie_dict = {}
                            if existing_cookie_str:
                                for item in existing_cookie_str.split(";"):
                                    if "=" in item:
                                        k, v = item.split("=", 1)
                                        cookie_dict[k.strip()] = v.strip()
                            for k, v in new_cookie_dict.items():
                                cookie_dict[k.strip()] = v.strip()
                            merged_cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items() if k])
                            if persist_cookies:
                                save_cookies(merged_cookie_str)

                    if response.status != 200:
                        Log.error(f"接口请求失败：{url}")
                        Log.error(f"状态码：{response.status}", detailed=True)
                        clean_text = response_text.replace('\n', '\\n').replace('\r', '')
                        Log.debug(f"响应内容：{clean_text}")
                        raise Exception(f"HTTP {response.status}: {response_text}")

                    if return_cookies:
                        return response_data, new_cookie_dict if 'new_cookie_dict' in locals() else {}
                    return response_data
            except aiohttp.ClientError as e:
                Log.error(f"请求失败：{str(e)}")
                if _has_debug_logger:
                    DebugLogger.log_error(f"请求失败: {str(e)}")
                raise

    @staticmethod
    async def download_file(url: str, file_path: str, progress_callback=None, session: Optional[aiohttp.ClientSession] = None) -> bool:
        """下载文件
        
        Args:
            url: 文件URL
            file_path: 本地文件路径
            progress_callback: 可选的下载进度回调函数，接受一个参数表示下载进度百分比
            session: 可选的session对象"""
        try:
            headers = Request._get_request_headers()
            ssl_context = False if GLOBAL_CONFIG.disable_ssl else None
            
            async with Request._get_session(session) as current_session:
                async with current_session.get(url, headers=headers, ssl=ssl_context) as response:
                    if response.status != 200:
                        Log.error(f"文件下载失败：{url}")
                        return False

                    file_size = int(response.headers.get('content-length', 0))
                    downloaded = 0

                    import os
                    os.makedirs(os.path.dirname(file_path), exist_ok=True)

                    with open(file_path, 'wb') as file:
                        async for chunk in response.content.iter_chunked(8192):
                            file.write(chunk)
                            downloaded += len(chunk)

                            if progress_callback and file_size > 0:
                                progress = (downloaded / file_size) * 100
                                progress_callback(progress)

                    return True
        except Exception as e:
            Log.error(f"文件下载异常：{str(e)}")
            return False

    @staticmethod
    def extract_cookies_from_response(response_headers: Dict[str, str]) -> str:
        """从响应头中提取cookies
        
        Args:
            response_headers: 响应头
        """
        cookies = []
        set_cookie_headers = response_headers.get('set-cookie', [])

        if isinstance(set_cookie_headers, str):
            set_cookie_headers = [set_cookie_headers]

        for cookie_header in set_cookie_headers:
            cookie_match = re.match(r'([^=]+)=([^;]+)', cookie_header)
            if cookie_match:
                name, value = cookie_match.groups()
                cookies.append(f"{name}={value}")

        return "; ".join(cookies)

    @staticmethod
    async def get_with_retry(url: str, max_retries: int = 3, delay: float = 1.0, session: Optional[aiohttp.ClientSession] = None) -> Dict[str, Any]:
        """带重试的GET请求
        
        Args:
            url: 请求URL
            max_retries: 最大重试次数
            delay: 重试间隔初始值，单位秒，每次重试后会指数级增加
            session: 可选的session对象
        """
        for attempt in range(max_retries):
            try:
                return await Request.get(url, session=session)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                Log.warn(f"请求失败，{delay}秒后重试... (尝试 {attempt + 1}/{max_retries})")
                await asyncio.sleep(delay)
                delay *= 2

        raise Exception("重试次数已用完")

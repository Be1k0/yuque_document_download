import asyncio
import json
import re
from typing import Dict, Any
from urllib.parse import urljoin

import aiohttp

from .constants import GLOBAL_CONFIG
from .file import File
from .log import Log
from .tools import get_local_cookies  # get_user_config已移除

# 导入调试日志模块（如果启用调试模式）
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
        # 直接使用全局配置的host，因为已移除CLI配置支持
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
    async def get(url: str) -> Dict[str, Any]:
        """发送GET请求并返回JSON"""
        target_url = urljoin(Request._get_match_host(), url)

        cookies = get_local_cookies()
        if not cookies:
            Log.error("cookies已过期，请清除缓存后重新执行程序")
            raise Exception("cookies已过期")

        headers = Request._get_request_headers()
        headers["cookie"] = cookies
        headers["x-requested-with"] = "XMLHttpRequest"

        # 记录请求信息到调试日志
        if _has_debug_logger:
            DebugLogger.log_request(target_url, "GET", headers)

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(target_url, headers=headers) as response:
                    response_text = await response.text()

                    # 记录响应信息到调试日志
                    if _has_debug_logger:
                        DebugLogger.log_response(
                            response.status,
                            response.headers,
                            response_text
                        )

                    if response.status != 200:
                        Log.error(f"接口请求失败：{url}")
                        Log.error(f"状态码：{response.status}", detailed=True)
                        Log.error(f"响应内容：{response_text}", detailed=True)
                        raise Exception(f"HTTP {response.status}: {response_text}")

                    return json.loads(response_text)
            except aiohttp.ClientError as e:
                Log.error(f"请求失败：{str(e)}")
                if _has_debug_logger:
                    DebugLogger.log_error(f"请求失败: {str(e)}")
                raise

    @staticmethod
    async def get_text(url: str, is_html: bool = False) -> str:
        """发送GET请求并返回文本
        
        Args:
            url: 请求URL
            is_html: 是否请求HTML内容，默认为False
        """
        target_url = urljoin(Request._get_match_host(), url)

        cookies = get_local_cookies()
        if not cookies:
            Log.error("cookies已过期，请清除缓存后重新执行程序")
            raise Exception("cookies已过期")

        headers = Request._get_request_headers()
        headers["cookie"] = cookies

        # 如果请求的是HTML内容，不添加x-requested-with头，以便获取完整HTML
        if not is_html:
            headers["x-requested-with"] = "XMLHttpRequest"
        else:
            # 为HTML请求设置更适合的头部
            headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
            headers["Accept-Language"] = "zh-CN,zh;q=0.9,en;q=0.8"
            # 避免Ajax方式返回
            if "x-requested-with" in headers:
                del headers["x-requested-with"]

        # 记录请求信息到调试日志
        if _has_debug_logger:
            DebugLogger.log_request(target_url, "GET", headers)

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(target_url, headers=headers) as response:
                    content = await response.text(errors='replace')

                    # 记录响应信息到调试日志
                    if _has_debug_logger:
                        # HTML内容很大，记录摘要
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
                        Log.error(f"响应内容：{error_text}", detailed=True)
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
    async def post(url: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """发送POST请求并返回JSON"""
        target_url = urljoin(Request._get_match_host(), url)

        headers = Request._get_request_headers()

        # 记录请求信息到调试日志
        if _has_debug_logger:
            DebugLogger.log_request(target_url, "POST", headers, data)

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(target_url, headers=headers, json=data) as response:
                    response_text = await response.text()

                    # 尝试解析响应为JSON
                    try:
                        response_data = json.loads(response_text)
                    except json.JSONDecodeError:
                        response_data = {"text": response_text}

                    # 记录响应信息到调试日志
                    if _has_debug_logger:
                        DebugLogger.log_response(
                            response.status,
                            response.headers,
                            response_data
                        )

                    # 保存cookies
                    if response.cookies:
                        cookie_str = "; ".join([f"{cookie.key}={cookie.value}" for cookie in response.cookies.values()])
                        if cookie_str:
                            from .tools import save_cookies
                            save_cookies(cookie_str)

                    if response.status != 200:
                        Log.error(f"接口请求失败：{url}")
                        Log.error(f"状态码：{response.status}", detailed=True)
                        Log.error(f"响应内容：{response_data}", detailed=True)
                        raise Exception(f"HTTP {response.status}: {response_data}")

                    return response_data
            except aiohttp.ClientError as e:
                Log.error(f"请求失败：{str(e)}")
                if _has_debug_logger:
                    DebugLogger.log_error(f"请求失败: {str(e)}")
                raise

    @staticmethod
    async def download_file(url: str, file_path: str, progress_callback=None) -> bool:
        """下载文件"""
        try:
            headers = Request._get_request_headers()

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        Log.error(f"文件下载失败：{url}")
                        return False

                    file_size = int(response.headers.get('content-length', 0))
                    downloaded = 0

                    f = File()
                    # 确保目录存在
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
        """从响应头中提取cookies"""
        cookies = []
        set_cookie_headers = response_headers.get('set-cookie', [])

        if isinstance(set_cookie_headers, str):
            set_cookie_headers = [set_cookie_headers]

        for cookie_header in set_cookie_headers:
            # 提取cookie名称和值
            cookie_match = re.match(r'([^=]+)=([^;]+)', cookie_header)
            if cookie_match:
                name, value = cookie_match.groups()
                cookies.append(f"{name}={value}")

        return "; ".join(cookies)

    @staticmethod
    async def get_with_retry(url: str, max_retries: int = 3, delay: float = 1.0) -> Dict[str, Any]:
        """带重试的GET请求"""
        for attempt in range(max_retries):
            try:
                return await Request.get(url)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                Log.warn(f"请求失败，{delay}秒后重试... (尝试 {attempt + 1}/{max_retries})")
                await asyncio.sleep(delay)
                delay *= 2  # 指数退避

        raise Exception("重试次数已用完")

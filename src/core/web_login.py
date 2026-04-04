from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, urlparse

from ..libs.constants import GLOBAL_CONFIG
from ..libs.log import Log

try:
    from playwright.async_api import Browser, BrowserContext, Page, Request as PlaywrightRequest
    from playwright.async_api import Response as PlaywrightResponse
    from playwright.async_api import async_playwright
except ImportError:
    Browser = BrowserContext = Page = PlaywrightRequest = PlaywrightResponse = None
    async_playwright = None

try:
    import psutil
except ImportError:
    psutil = None

try:
    from ..libs.debug_logger import DebugLogger
    _has_debug_logger = True
except ImportError:
    _has_debug_logger = False


@dataclass
class BrowserLaunchTarget:
    """浏览器启动目标"""
    name: str
    path: str


@dataclass
class WebLoginResult:
    """网页登录结果"""
    browser_name: str
    cookie_string: str
    cookie_names: list[str]
    final_url: str


class SystemBrowserLoginBridge:
    """使用系统浏览器和 CDP 完成网页登录"""

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._browser_process: Optional[subprocess.Popen] = None
        self._profile_dir: Optional[str] = None
        self._observed_tasks: set[asyncio.Task] = set()
        self._browser_pid: Optional[int] = None

    async def login(self) -> WebLoginResult:
        """执行网页登录并提取 Cookie"""
        if async_playwright is None:
            raise ImportError("未安装playwright库，请先运行: pip install playwright")

        self._prepare_playwright_environment()
        launch_target = self._find_browser_target()
        if launch_target is None:
            raise RuntimeError(self.get_browser_error_message())

        port = self._find_free_port()
        self._profile_dir = self._create_profile_dir()

        self._log_runtime_debug(f"准备启动系统浏览器: {launch_target.name}")
        self._log_debug_data(
            "网页登录浏览器启动参数",
            {
                "browser_name": launch_target.name,
                "browser_path": launch_target.path,
                "debug_port": port,
                "profile_dir": self._profile_dir,
            },
        )

        try:
            self._browser_process = self._launch_browser_process(launch_target, port, self._profile_dir)
            self._browser_pid = self._browser_process.pid
            await self._wait_for_debug_port(port)

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")

            context = await self._wait_for_context()
            page = await self._prepare_login_page(context)
            self._attach_page_observers(page)

            Log.info("系统浏览器已连接，正在打开语雀登录页...")
            await page.goto(GLOBAL_CONFIG.yuque_referer, wait_until="domcontentloaded", timeout=GLOBAL_CONFIG.web_login_timeout_ms)
            return await self._wait_for_login_success(context, launch_target.name)
        finally:
            await self.close()

    async def close(self):
        """清理浏览器连接和临时目录"""
        tasks = list(self._observed_tasks)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            self._observed_tasks.clear()

        if self._browser is not None:
            with contextlib.suppress(Exception):
                for context in self._browser.contexts:
                    for page in context.pages:
                        with contextlib.suppress(Exception):
                            await page.close()
                    with contextlib.suppress(Exception):
                        await context.close()
                await self._browser.close()
            self._browser = None

        if self._playwright is not None:
            with contextlib.suppress(Exception):
                await self._playwright.stop()
            self._playwright = None

        self._terminate_browser_processes()

        if self._browser_process is not None:
            if self._browser_process.poll() is None:
                with contextlib.suppress(Exception):
                    self._browser_process.terminate()
                    self._browser_process.wait(timeout=5)
                if self._browser_process.poll() is None:
                    with contextlib.suppress(Exception):
                        self._browser_process.kill()
            self._browser_process = None
        self._browser_pid = None

        if self._profile_dir:
            shutil.rmtree(self._profile_dir, ignore_errors=True)
            self._profile_dir = None

    def _terminate_browser_processes(self):
        """按临时目录回收本次网页登录启动的浏览器进程"""
        if psutil is None or not self._profile_dir:
            return

        target_processes: dict[int, psutil.Process] = {}
        normalized_profile_dir = os.path.normcase(os.path.abspath(self._profile_dir))

        if self._browser_pid:
            with contextlib.suppress(psutil.Error):
                root_process = psutil.Process(self._browser_pid)
                target_processes[root_process.pid] = root_process
                for child in root_process.children(recursive=True):
                    target_processes[child.pid] = child

        for process in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmdline_list = process.info.get("cmdline") or []
                cmdline_text = os.path.normcase(" ".join(cmdline_list))
                if normalized_profile_dir in cmdline_text:
                    target_processes[process.pid] = process
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        if not target_processes:
            return

        self._log_runtime_debug(
            f"准备关闭网页登录浏览器进程: {', '.join(str(pid) for pid in sorted(target_processes))}"
        )

        processes = list(target_processes.values())
        for process in processes:
            with contextlib.suppress(psutil.Error):
                process.terminate()

        _, alive = psutil.wait_procs(processes, timeout=3)
        for process in alive:
            with contextlib.suppress(psutil.Error):
                process.kill()

        if alive:
            psutil.wait_procs(alive, timeout=2)

    def _find_browser_target(self) -> Optional[BrowserLaunchTarget]:
        """查找可用的系统浏览器"""
        browser_candidates = self._build_browser_candidates()
        for browser_name, candidate_paths in browser_candidates:
            for candidate_path in candidate_paths:
                if candidate_path and os.path.exists(candidate_path):
                    return BrowserLaunchTarget(name=browser_name, path=candidate_path)
        return None

    def _build_browser_candidates(self) -> list[tuple[str, list[str]]]:
        """构建浏览器候选路径"""
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("ProgramFiles", "")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
        home_dir = os.path.expanduser("~")

        if sys.platform.startswith("win"):
            return [
                (
                    "Microsoft Edge",
                    [
                        shutil.which("msedge.exe") or "",
                        os.path.join(program_files_x86, "Microsoft", "Edge", "Application", "msedge.exe"),
                        os.path.join(program_files, "Microsoft", "Edge", "Application", "msedge.exe"),
                    ],
                ),
                (
                    "Google Chrome",
                    [
                        shutil.which("chrome.exe") or "",
                        os.path.join(local_app_data, "Google", "Chrome", "Application", "chrome.exe"),
                        os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"),
                        os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"),
                    ],
                ),
                (
                    "Brave Browser",
                    [
                        shutil.which("brave.exe") or "",
                        os.path.join(local_app_data, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
                        os.path.join(program_files_x86, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
                        os.path.join(program_files, "BraveSoftware", "Brave-Browser", "Application", "brave.exe"),
                    ],
                ),
            ]

        if sys.platform == "darwin":
            return [
                (
                    "Microsoft Edge",
                    [
                        shutil.which("microsoft-edge") or "",
                        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                    ],
                ),
                (
                    "Google Chrome",
                    [
                        shutil.which("google-chrome") or "",
                        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                    ],
                ),
                (
                    "Chromium",
                    [
                        shutil.which("chromium") or "",
                        "/Applications/Chromium.app/Contents/MacOS/Chromium",
                    ],
                ),
                (
                    "Brave Browser",
                    [
                        shutil.which("brave-browser") or "",
                        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
                    ],
                ),
            ]

        return [
            (
                "Microsoft Edge",
                [
                    shutil.which("microsoft-edge") or "",
                    shutil.which("microsoft-edge-stable") or "",
                    "/usr/bin/microsoft-edge",
                    "/usr/bin/microsoft-edge-stable",
                ],
            ),
            (
                "Google Chrome",
                [
                    shutil.which("google-chrome") or "",
                    shutil.which("google-chrome-stable") or "",
                    "/usr/bin/google-chrome",
                    "/usr/bin/google-chrome-stable",
                ],
            ),
            (
                "Chromium",
                [
                    shutil.which("chromium") or "",
                    shutil.which("chromium-browser") or "",
                    "/usr/bin/chromium",
                    "/usr/bin/chromium-browser",
                ],
            ),
            (
                "Brave Browser",
                [
                    shutil.which("brave-browser") or "",
                    "/usr/bin/brave-browser",
                ],
            ),
            (
                "Vivaldi",
                [
                    shutil.which("vivaldi") or "",
                    "/usr/bin/vivaldi",
                ],
            ),
        ]

    def get_browser_error_message(self) -> str:
        """生成浏览器不可用时的提示信息"""
        firefox_installed = bool(shutil.which("firefox"))
        if firefox_installed:
            return "未检测到适配的 Chromium 内核浏览器。当前网页登录桥接仅支持 Edge、Chrome、Chromium、Brave、Vivaldi，暂不支持 Firefox。"
        return "未检测到适配的 Chromium 内核浏览器，请先安装 Edge、Chrome、Chromium、Brave 或 Vivaldi 后再运行。"

    def _launch_browser_process(self, launch_target: BrowserLaunchTarget, port: int, profile_dir: str) -> subprocess.Popen:
        """启动系统浏览器进程"""
        command = [
            launch_target.path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--new-window",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ]
        creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )

    def _create_profile_dir(self) -> str:
        """创建临时浏览器数据目录"""
        candidate_dirs = [
            GLOBAL_CONFIG.web_login_profile_dir,
            os.path.join(tempfile.gettempdir(), "yuque_document_download", "browser_profiles"),
        ]

        last_error: Optional[Exception] = None
        for candidate_dir in candidate_dirs:
            try:
                Path(candidate_dir).mkdir(parents=True, exist_ok=True)
                profile_dir = tempfile.mkdtemp(prefix="web_login_", dir=candidate_dir)
                self._log_runtime_debug(f"网页登录临时目录已创建: {profile_dir}")
                return profile_dir
            except Exception as error:
                last_error = error
                self._log_runtime_debug(f"网页登录临时目录创建失败: {candidate_dir}, error={error}")

        raise RuntimeError(f"创建网页登录浏览器临时目录失败: {last_error}")

    def _find_free_port(self) -> int:
        """获取本地可用端口"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    async def _wait_for_debug_port(self, port: int):
        """等待调试端口就绪"""
        deadline = asyncio.get_running_loop().time() + 15
        process_exit_code: Optional[int] = None
        while asyncio.get_running_loop().time() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.3)
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    return

            if self._browser_process is not None and self._browser_process.poll() is not None:
                if process_exit_code is None:
                    process_exit_code = self._browser_process.returncode
                    self._log_runtime_debug(
                        f"浏览器启动器进程已退出，等待调试端口接管: exit_code={process_exit_code}"
                    )
            await asyncio.sleep(0.2)

        if process_exit_code is not None:
            raise RuntimeError(
                f"浏览器进程意外退出，无法建立调试连接。退出码: {process_exit_code}"
            )
        raise TimeoutError("等待浏览器调试端口超时。")

    async def _wait_for_context(self) -> BrowserContext:
        """等待 CDP 默认上下文创建完成"""
        deadline = asyncio.get_running_loop().time() + 10
        while asyncio.get_running_loop().time() < deadline:
            if self._browser is not None and self._browser.contexts:
                return self._browser.contexts[0]
            await asyncio.sleep(0.2)
        raise TimeoutError("等待浏览器上下文初始化超时。")

    async def _prepare_login_page(self, context: BrowserContext) -> Page:
        """获取登录页实例"""
        page = None
        for existing_page in context.pages:
            if not existing_page.is_closed():
                page = existing_page
                break

        if page is None:
            page = await context.new_page()

        return page

    async def _wait_for_login_success(self, context: BrowserContext, browser_name: str) -> WebLoginResult:
        """等待登录成功并提取 Cookie"""
        timeout_seconds = GLOBAL_CONFIG.web_login_timeout_ms / 1000
        poll_seconds = GLOBAL_CONFIG.web_login_poll_interval_ms / 1000
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        last_url = ""
        last_cookie_names: set[str] = set()

        while asyncio.get_running_loop().time() < deadline:
            page = self._get_active_page(context)
            if page is None:
                if self._browser is not None and not self._browser.is_connected():
                    raise RuntimeError("浏览器连接已断开，网页登录已中断。")
                await asyncio.sleep(poll_seconds)
                continue

            current_url = page.url
            if current_url != last_url:
                self._log_runtime_debug(f"网页登录页面跳转到: {current_url}")
                last_url = current_url

            cookies = await self._get_yuque_cookies(context, current_url)
            cookie_names = {cookie["name"] for cookie in cookies}
            if cookie_names != last_cookie_names:
                self._log_runtime_debug(f"网页登录当前 Cookie: {', '.join(sorted(cookie_names)) or '无'}")
                self._log_debug_data("网页登录 Cookie 名称", sorted(cookie_names))
                last_cookie_names = cookie_names

            if self._is_login_completed(current_url, cookie_names):
                cookie_string = "; ".join(
                    f"{cookie['name']}={cookie['value']}"
                    for cookie in cookies
                    if cookie.get("name") and cookie.get("value") is not None
                )
                Log.success("检测到网页登录成功，正在提取 Cookie。")
                return WebLoginResult(
                    browser_name=browser_name,
                    cookie_string=cookie_string,
                    cookie_names=sorted(cookie_names),
                    final_url=current_url,
                )

            await asyncio.sleep(poll_seconds)

        raise TimeoutError("等待网页登录成功超时，请重试。")

    async def _get_yuque_cookies(self, context: BrowserContext, current_url: str) -> list[dict]:
        """获取可用于语雀请求的 Cookie 列表"""
        cookie_urls = [GLOBAL_CONFIG.yuque_referer, GLOBAL_CONFIG.yuque_host]
        if current_url and current_url.startswith(GLOBAL_CONFIG.yuque_host):
            cookie_urls.append(current_url)

        cookies = await context.cookies(cookie_urls)
        return self._deduplicate_cookies(cookies)

    def _deduplicate_cookies(self, cookies: list[dict]) -> list[dict]:
        """按名称去重并保留语雀请求相关 Cookie"""
        allowed_names = set(GLOBAL_CONFIG.yuque_request_cookie_names)
        cookie_map: dict[str, dict] = {}

        for cookie in cookies:
            name = str(cookie.get("name") or "").strip()
            if not name or name not in allowed_names:
                continue
            cookie_map[name] = cookie

        return [
            cookie_map[name]
            for name in GLOBAL_CONFIG.yuque_request_cookie_names
            if name in cookie_map
        ]

    def _is_login_completed(self, current_url: str, cookie_names: set[str]) -> bool:
        """判断网页登录是否完成"""
        if not current_url:
            return False

        parsed = urlparse(current_url)
        current_host = parsed.netloc
        if "yuque.com" not in current_host:
            return False

        normalized_path = parsed.path.rstrip("/") or "/"
        in_login_page = normalized_path in {"/login", "/login/"} or "login" in normalized_path
        required_cookies = set(GLOBAL_CONFIG.web_login_success_cookie_names)
        return not in_login_page and required_cookies.issubset(cookie_names)

    def _get_active_page(self, context: BrowserContext) -> Optional[Page]:
        """获取当前活动页面"""
        pages = [page for page in context.pages if not page.is_closed()]
        if not pages:
            return None
        return pages[-1]

    def _attach_page_observers(self, page: Page):
        """挂载登录相关观察日志"""
        page.on("request", lambda request: self._schedule_observer(self._log_relevant_request(request)))
        page.on("response", lambda response: self._schedule_observer(self._log_relevant_response(response)))

    def _schedule_observer(self, coroutine):
        """调度异步观察任务"""
        task = asyncio.create_task(coroutine)
        self._observed_tasks.add(task)
        task.add_done_callback(self._observed_tasks.discard)

    async def _log_relevant_request(self, request: PlaywrightRequest):
        """记录关键请求摘要"""
        if not self._is_relevant_url(request.url):
            return

        parsed = urlparse(request.url)
        payload = {
            "method": request.method,
            "host": parsed.netloc,
            "path": parsed.path,
        }

        if request.method.upper() == "POST" and request.post_data:
            form_data = parse_qs(request.post_data)
            payload["action"] = self._first_form_value(form_data, "Action")
            payload["scene_id"] = self._first_form_value(form_data, "SceneId")
            payload["certify_id"] = self._first_form_value(form_data, "CertifyId")
            payload["event_id"] = self._first_form_value(form_data, "eventid")
            payload["payload_size"] = len(request.post_data)

        self._log_runtime_debug(f"捕获关键请求: {parsed.netloc}{parsed.path}")
        self._log_debug_data("网页登录关键请求", payload)

    async def _log_relevant_response(self, response: PlaywrightResponse):
        """记录关键响应摘要"""
        if not self._is_relevant_url(response.url):
            return

        parsed = urlparse(response.url)
        payload: dict[str, object] = {
            "status": response.status,
            "host": parsed.netloc,
            "path": parsed.path,
        }

        try:
            body_text = await response.text()
            content_type = (response.headers.get("content-type") or "").lower()
            if "application/json" in content_type or body_text.strip().startswith("{"):
                response_body = json.loads(body_text)
            else:
                response_body = {"text": body_text[:500]}
        except Exception as error:
            response_body = {"error": str(error)}

        if parsed.netloc.endswith("captcha-open.aliyuncs.com") and isinstance(response_body, dict):
            result = response_body.get("Result") or {}
            payload["code"] = response_body.get("Code")
            payload["message"] = response_body.get("Message")
            payload["verify_code"] = result.get("VerifyCode")
            payload["verify_result"] = result.get("VerifyResult")
            payload["certify_id"] = result.get("certifyId") or response_body.get("CertifyId")

            if payload.get("verify_result") is False:
                Log.warn(
                    f"验证码校验失败: verify_code={payload.get('verify_code')}, certify_id={payload.get('certify_id')}"
                )
            else:
                self._log_runtime_debug(f"验证码接口响应: {payload.get('code') or payload.get('verify_code')}")
        elif parsed.netloc.endswith("collect.alipay.com") and isinstance(response_body, dict):
            payload["code"] = response_body.get("code")
            payload["code_v2"] = response_body.get("code_v2")
            self._log_runtime_debug(
                f"验证码埋点接口响应: code={payload.get('code')}, code_v2={payload.get('code_v2')}"
            )
        else:
            self._log_runtime_debug(f"关键响应返回状态: {response.status} {parsed.netloc}{parsed.path}")

        self._log_debug_data("网页登录关键响应", payload)

    def _is_relevant_url(self, url: str) -> bool:
        """判断是否为需要观察的 URL"""
        parsed = urlparse(url)
        return parsed.netloc in {"1buwf8.captcha-open.aliyuncs.com", "collect.alipay.com"}

    def _first_form_value(self, form_data: dict[str, list[str]], key: str) -> str:
        """获取表单首个字段值"""
        values = form_data.get(key) or [""]
        return values[0]

    def _log_debug_data(self, label: str, payload: dict):
        """输出结构化调试日志"""
        if _has_debug_logger:
            DebugLogger.log_data(label, payload)

    def _log_runtime_debug(self, message: str):
        """输出仅调试模式可见的运行日志"""
        Log.debug(message)

    def _prepare_playwright_environment(self):
        """初始化 Playwright 运行环境"""
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
        os.environ.setdefault("NODE_NO_WARNINGS", "1")

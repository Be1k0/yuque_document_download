import asyncio
import locale
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import aiohttp

from src.libs.constants import GLOBAL_CONFIG
from src.libs.log import Log


@dataclass
class ReleaseAsset:
    """发布资源信息"""

    name: str
    label: str
    download_url: str
    size: int


@dataclass
class ReleaseInfo:
    """版本发布信息"""

    tag_name: str
    body: str
    html_url: str
    published_at: str
    asset: ReleaseAsset


class UpdateCancelledError(Exception):
    """更新下载已取消"""


class UpdateManager:
    """更新管理器"""

    def __init__(self):
        self._api_url = GLOBAL_CONFIG.github_latest_release_api
        self._repo_url = GLOBAL_CONFIG.github_repo_url
        self._update_dir = Path(GLOBAL_CONFIG.update_temp_dir)

    @staticmethod
    def is_packaged_app() -> bool:
        """判断当前是否为可执行程序模式"""
        if getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS") or "__compiled__" in globals():
            return True

        executable_name = Path(sys.executable).name.lower()
        if UpdateManager.get_current_platform() == "windows":
            return executable_name not in {"python.exe", "pythonw.exe"}

        return not executable_name.startswith("python")

    @staticmethod
    def get_current_executable_path() -> Optional[Path]:
        """获取当前可执行文件路径"""
        if not UpdateManager.is_packaged_app():
            return None
        return Path(sys.executable).resolve()

    @staticmethod
    def get_current_platform() -> str:
        """获取当前平台标识"""
        if sys.platform.startswith("win"):
            return "windows"
        if sys.platform.startswith("linux"):
            return "linux"
        return platform.system().lower()

    @staticmethod
    def normalize_version(version: str) -> tuple[int, int, int, int, int]:
        """解析版本号，正式版高于 RC 版本"""
        match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(?:-RC(\d+))?$", version.strip(), re.IGNORECASE)
        if not match:
            raise ValueError(f"无法解析版本号: {version}")

        major, minor, patch, rc = match.groups()
        is_final = 1 if rc is None else 0
        rc_value = 0 if rc is None else int(rc)
        return int(major), int(minor), int(patch), is_final, rc_value

    @classmethod
    def is_newer_version(cls, current_version: str, latest_version: str) -> bool:
        """判断远端版本是否更新"""
        current = cls.normalize_version(current_version)
        latest = cls.normalize_version(latest_version)
        return latest > current

    async def fetch_latest_release(self) -> ReleaseInfo:
        """获取最新版本信息"""
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "yuque-document-download-updater",
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(self._api_url, ssl=False if GLOBAL_CONFIG.disable_ssl else None) as response:
                response_text = await response.text()
                if response.status != 200:
                    raise RuntimeError(f"获取最新版本失败，状态码: {response.status}")

                data = await response.json()

        asset = self._select_release_asset(data.get("assets") or [])
        if asset is None:
            raise RuntimeError(f"最新版本未找到可用的 {self.get_current_platform()} 可执行文件资源")

        release_info = ReleaseInfo(
            tag_name=data.get("tag_name", "").strip(),
            body=data.get("body", "").strip(),
            html_url=data.get("html_url") or self._repo_url,
            published_at=data.get("published_at", ""),
            asset=asset,
        )

        Log.info(f"软件最新版本为 {release_info.tag_name}")
        return release_info

    def _select_release_asset(self, assets: list[dict]) -> Optional[ReleaseAsset]:
        """根据当前平台选择可执行文件资源"""
        if not assets:
            return None

        platform_name = self.get_current_platform()
        candidate_assets = []
        for asset in assets:
            asset_name = str(asset.get("name") or "").lower()
            asset_label = str(asset.get("label") or "").lower()
            if platform_name == "windows" and (
                asset_name.endswith(".exe") or asset_label.endswith(".exe")
            ):
                candidate_assets.append(asset)
            elif platform_name == "linux" and (
                asset_name.endswith(".bin") or asset_label.endswith(".bin")
            ):
                candidate_assets.append(asset)

        if not candidate_assets:
            return None

        def sort_key(asset: dict) -> tuple[int, int]:
            name = f"{asset.get('name') or ''} {asset.get('label') or ''}".lower()
            score = 0
            if platform_name == "windows" and ("win" in name or "windows" in name):
                score += 2
            if platform_name == "linux" and ("linux" in name or "gnu/linux" in name):
                score += 2
            if "x64" in name or "amd64" in name or "x86_64" in name:
                score += 1
            return score, int(asset.get("size") or 0)

        selected = max(candidate_assets, key=sort_key)
        default_name = "update.exe" if platform_name == "windows" else "update.bin"
        return ReleaseAsset(
            name=selected.get("name") or default_name,
            label=selected.get("label") or selected.get("name") or default_name,
            download_url=selected.get("browser_download_url") or "",
            size=int(selected.get("size") or 0),
        )

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """清理文件名中的非法字符"""
        platform_name = UpdateManager.get_current_platform()
        if platform_name == "windows":
            sanitized = re.sub(r'[<>:"/\\\\|?*]', "_", filename.strip())
            return sanitized.rstrip(". ") or "update.exe"

        sanitized = filename.replace("/", "_").replace("\x00", "").strip()
        return sanitized or "update.bin"

    @classmethod
    def get_asset_target_name(cls, asset: ReleaseAsset) -> str:
        """获取更新资源应使用的程序文件名"""
        return cls.sanitize_filename(asset.label or asset.name)

    async def download_release_asset(
        self,
        release_info: ReleaseInfo,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> Path:
        """下载更新文件"""
        self._update_dir.mkdir(parents=True, exist_ok=True)
        target_name = self.get_asset_target_name(release_info.asset)
        target_path = self._update_dir / target_name
        temp_path = target_path.with_suffix(target_path.suffix + ".download")

        headers = {"User-Agent": "yuque-document-download-updater"}
        ssl_context = False if GLOBAL_CONFIG.disable_ssl else None
        download_url = self.build_download_url(release_info.asset.download_url)

        Log.info(f"开始下载更新文件: {target_name}")
        Log.info(f"更新原始下载地址: {release_info.asset.download_url}")
        Log.info(f"更新实际下载地址: {download_url}")

        last_report_time = 0.0

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(download_url, ssl=ssl_context) as response:
                    if response.status != 200:
                        raise RuntimeError(f"下载更新文件失败，状态码: {response.status}")

                    total_size = int(response.headers.get("Content-Length", release_info.asset.size or 0))
                    downloaded_size = 0

                    with open(temp_path, "wb") as file:
                        async for chunk in response.content.iter_chunked(1024 * 512):
                            if cancel_callback and cancel_callback():
                                raise UpdateCancelledError("已取消更新下载")

                            file.write(chunk)
                            downloaded_size += len(chunk)

                            now = time.monotonic()
                            if progress_callback and (
                                downloaded_size >= total_size > 0 or
                                now - last_report_time >= 0.15
                            ):
                                progress_callback(downloaded_size, total_size, target_name)
                                last_report_time = now
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

        temp_path.replace(target_path)
        Log.info(f"更新文件下载完成: {target_path}")
        return target_path

    @staticmethod
    def normalize_proxy_base_url(proxy_base_url: str) -> str:
        """规范化加速地址"""
        normalized = proxy_base_url.strip()
        if normalized and not normalized.endswith("/"):
            normalized += "/"
        return normalized

    @classmethod
    def build_download_url(cls, download_url: str) -> str:
        """根据设置构建最终下载地址"""
        if not GLOBAL_CONFIG.enable_update_proxy:
            Log.info("程序更新下载加速已关闭，使用 GitHub 直连下载")
            return download_url

        normalized_proxy = cls.normalize_proxy_base_url(GLOBAL_CONFIG.update_proxy_base_url)
        if not normalized_proxy:
            Log.info("程序更新加速地址为空，使用 GitHub 直连下载")
            return download_url

        final_url = f"{normalized_proxy}{download_url}"
        Log.info(f"程序更新下载加速已启用: {normalized_proxy}")
        return final_url

    def prepare_update_script(self, downloaded_file: Path) -> tuple[Path, Path]:
        """生成更新脚本和日志文件"""
        current_executable = self.get_current_executable_path()
        if current_executable is None:
            raise RuntimeError("当前为源码运行模式，无法自动替换程序文件")

        self._update_dir.mkdir(parents=True, exist_ok=True)

        target_executable = current_executable.parent / downloaded_file.name
        log_path = self._update_dir / "update.log"
        platform_name = self.get_current_platform()
        if platform_name == "windows":
            script_path = self._update_dir / "apply_update.bat"
            cleanup_script_path = self._update_dir / "cleanup_update.bat"
            self._prepare_windows_update_scripts(
                downloaded_file,
                current_executable,
                target_executable,
                script_path,
                cleanup_script_path,
                log_path,
            )
        elif platform_name == "linux":
            script_path = self._update_dir / "apply_update.sh"
            cleanup_script_path = self._update_dir / "cleanup_update.sh"
            self._prepare_linux_update_scripts(
                downloaded_file,
                current_executable,
                target_executable,
                script_path,
                cleanup_script_path,
                log_path,
            )
        else:
            raise RuntimeError(f"当前平台暂不支持自动更新: {platform_name}")

        Log.info(f"更新目标路径: {target_executable}")
        Log.info(f"更新脚本已生成: {script_path}")
        Log.info(f"清理脚本已生成: {cleanup_script_path}")
        return script_path, log_path

    def _prepare_windows_update_scripts(
        self,
        downloaded_file: Path,
        current_executable: Path,
        target_executable: Path,
        script_path: Path,
        cleanup_script_path: Path,
        log_path: Path,
    ) -> None:
        """生成 Windows 更新脚本"""
        backup_path = target_executable.with_suffix(target_executable.suffix + ".bak")
        current_backup_path = current_executable.with_suffix(current_executable.suffix + ".old.bak")

        script_lines = [
            "@echo off",
            "setlocal EnableExtensions",
            f'set "SRC={downloaded_file}"',
            f'set "CUR={current_executable}"',
            f'set "DST={target_executable}"',
            f'set "BAK={backup_path}"',
            f'set "CURBAK={current_backup_path}"',
            f'set "LOG={log_path}"',
            f'set "CLEANUP={cleanup_script_path}"',
            'echo [%date% %time%] [更新脚本] 开始执行更新>"%LOG%"',
            "timeout /t 2 /nobreak >nul",
            'if /I not "%CUR%"=="%DST%" echo [%date% %time%] [更新脚本] 检测到新版本文件名变化: "%CUR%" 到 "%DST%">>"%LOG%"',
            "for /l %%i in (1,1,15) do (",
            '  if exist "%DST%" copy /y "%DST%" "%BAK%" >nul 2>>"%LOG%"',
            '  if /I not "%CUR%"=="%DST%" if exist "%CUR%" copy /y "%CUR%" "%CURBAK%" >nul 2>>"%LOG%"',
            '  copy /y "%SRC%" "%DST%" >nul 2>>"%LOG%"',
            "  if not errorlevel 1 goto launch",
            '  echo [%date% %time%] [更新脚本] 第 %%i 次替换失败，继续重试>>"%LOG%"',
            "  timeout /t 1 /nobreak >nul",
            ")",
            'echo [%date% %time%] [更新脚本] 更新失败，已达到最大重试次数>>"%LOG%"',
            "goto end",
            ":launch",
            'echo [%date% %time%] [更新脚本] 更新成功，准备启动新版本>>"%LOG%"',
        ]

        cleanup_lines = [
            "@echo off",
            "setlocal EnableExtensions",
            f'set "LOG={log_path}"',
            f'set "SRC={downloaded_file}"',
            f'set "CUR={current_executable}"',
            f'set "CURBAK={current_backup_path}"',
            f'set "DSTBAK={backup_path}"',
            f'set "APPLY={script_path}"',
            'echo [%date% %time%] [清理脚本] 开始执行更新后清理>>"%LOG%"',
            "ping 127.0.0.1 -n 5 >nul",
        ]

        if current_executable != target_executable:
            cleanup_lines.extend([
                "for /l %%j in (1,1,10) do (",
                '  if not exist "%CUR%" goto cleanup_old_done',
                '  del /f /q "%CUR%" >nul 2>>"%LOG%"',
                '  if not exist "%CUR%" goto cleanup_old_done',
                '  echo [%date% %time%] [清理脚本] 第 %%j 次删除旧版本文件失败，继续重试>>"%LOG%"',
                "  ping 127.0.0.1 -n 2 >nul",
                ")",
                'if exist "%CUR%" echo [%date% %time%] [清理脚本] 旧版本文件仍未删除>>"%LOG%"',
                ":cleanup_old_done",
            ])

        cleanup_lines.extend([
            'if exist "%SRC%" del /f /q "%SRC%" >nul 2>>"%LOG%"',
            'if exist "%SRC%" echo [%date% %time%] [清理脚本] 更新临时文件删除失败>>"%LOG%"',
            'if exist "%CURBAK%" del /f /q "%CURBAK%" >nul 2>>"%LOG%"',
            'if exist "%CURBAK%" echo [%date% %time%] [清理脚本] 旧版本备份文件删除失败>>"%LOG%"',
            'if exist "%DSTBAK%" del /f /q "%DSTBAK%" >nul 2>>"%LOG%"',
            'if exist "%DSTBAK%" echo [%date% %time%] [清理脚本] 新版本备份文件删除失败>>"%LOG%"',
            'echo [%date% %time%] [清理脚本] 更新后清理结束>>"%LOG%"',
            'echo [%date% %time%] [清理脚本] 已安排更新脚本和清理脚本自删除>>"%LOG%"',
            'start "" /b cmd /c "ping 127.0.0.1 -n 3 >nul & del /f /q ""%APPLY%"" ""%~f0"""',
        ])

        script_lines.extend([
            'start "" "%DST%"',
            'echo [%date% %time%] [更新脚本] 新版本已启动，开始执行清理脚本>>"%LOG%"',
            'call "%CLEANUP%"',
            ":end",
        ])

        script_encoding = "mbcs" if os.name == "nt" else (locale.getpreferredencoding(False) or "utf-8")
        script_path.write_text("\n".join(script_lines) + "\n", encoding=script_encoding)
        cleanup_script_path.write_text("\n".join(cleanup_lines) + "\n", encoding=script_encoding)
        Log.info(f"更新脚本写入编码: {script_encoding}")

    def _prepare_linux_update_scripts(
        self,
        downloaded_file: Path,
        current_executable: Path,
        target_executable: Path,
        script_path: Path,
        cleanup_script_path: Path,
        log_path: Path,
    ) -> None:
        """生成 Linux 更新脚本"""
        backup_path = target_executable.with_suffix(target_executable.suffix + ".bak")
        current_backup_path = current_executable.with_suffix(current_executable.suffix + ".old.bak")

        def linux_log(prefix: str, message: str) -> str:
            escaped_message = message.replace('"', '\\"')
            return f'echo "[$(date \'+%Y-%m-%d %H:%M:%S\')] [{prefix}] {escaped_message}" >> "$LOG"'

        script_lines = [
            "#!/bin/sh",
            'SRC="{0}"'.format(downloaded_file),
            'CUR="{0}"'.format(current_executable),
            'DST="{0}"'.format(target_executable),
            'BAK="{0}"'.format(backup_path),
            'CURBAK="{0}"'.format(current_backup_path),
            'LOG="{0}"'.format(log_path),
            'CLEANUP="{0}"'.format(cleanup_script_path),
            linux_log("更新脚本", "开始执行更新"),
            "sleep 2",
            '[ "$CUR" != "$DST" ] && ' + linux_log("更新脚本", '检测到新版本文件名变化: "$CUR" 到 "$DST"'),
            "i=1",
            "while [ $i -le 15 ]; do",
            '  [ -f "$DST" ] && cp -f "$DST" "$BAK" 2>>"$LOG"',
            '  [ "$CUR" != "$DST" ] && [ -f "$CUR" ] && cp -f "$CUR" "$CURBAK" 2>>"$LOG"',
            '  cp -f "$SRC" "$DST" 2>>"$LOG" && chmod +x "$DST" 2>>"$LOG" && break',
            '  {0}'.format(linux_log("更新脚本", '第 $i 次替换失败，继续重试')),
            "  i=$((i + 1))",
            "  sleep 1",
            "done",
            'if [ $i -gt 15 ]; then',
            '  {0}'.format(linux_log("更新脚本", "更新失败，已达到最大重试次数")),
            "  exit 1",
            "fi",
            linux_log("更新脚本", "更新成功，准备启动新版本"),
            'nohup "$DST" >/dev/null 2>&1 &',
            linux_log("更新脚本", "新版本已启动，开始执行清理脚本"),
            'nohup sh "$CLEANUP" >/dev/null 2>&1 &',
        ]

        cleanup_lines = [
            "#!/bin/sh",
            'SRC="{0}"'.format(downloaded_file),
            'CUR="{0}"'.format(current_executable),
            'CURBAK="{0}"'.format(current_backup_path),
            'DSTBAK="{0}"'.format(backup_path),
            'APPLY="{0}"'.format(script_path),
            'LOG="{0}"'.format(log_path),
            linux_log("清理脚本", "开始执行更新后清理"),
            "sleep 5",
        ]

        if current_executable != target_executable:
            cleanup_lines.extend([
                "j=1",
                "while [ $j -le 10 ]; do",
                '  [ ! -e "$CUR" ] && break',
                '  rm -f "$CUR" 2>>"$LOG"',
                '  [ ! -e "$CUR" ] && break',
                '  {0}'.format(linux_log("清理脚本", '第 $j 次删除旧版本文件失败，继续重试')),
                "  j=$((j + 1))",
                "  sleep 1",
                "done",
                '  [ -e "$CUR" ] && {0}'.format(linux_log("清理脚本", "旧版本文件仍未删除")),
            ])

        cleanup_lines.extend([
            'rm -f "$SRC" 2>>"$LOG"',
            'rm -f "$CURBAK" 2>>"$LOG"',
            'rm -f "$DSTBAK" 2>>"$LOG"',
            '[ -e "$SRC" ] && {0}'.format(linux_log("清理脚本", "更新临时文件删除失败")),
            '[ -e "$CURBAK" ] && {0}'.format(linux_log("清理脚本", "旧版本备份文件删除失败")),
            '[ -e "$DSTBAK" ] && {0}'.format(linux_log("清理脚本", "新版本备份文件删除失败")),
            linux_log("清理脚本", "更新后清理结束"),
            linux_log("清理脚本", "已安排更新脚本和清理脚本自删除"),
            '(sleep 3; rm -f "$APPLY" "$0") >/dev/null 2>&1 &',
        ])

        script_encoding = "utf-8"
        script_path.write_text("\n".join(script_lines) + "\n", encoding=script_encoding)
        cleanup_script_path.write_text("\n".join(cleanup_lines) + "\n", encoding=script_encoding)
        os.chmod(script_path, 0o755)
        os.chmod(cleanup_script_path, 0o755)
        Log.info(f"更新脚本写入编码: {script_encoding}")

    @staticmethod
    def launch_update_script(script_path: Path) -> None:
        """启动更新脚本"""
        if UpdateManager.get_current_platform() == "windows":
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(
                ["cmd", "/c", str(script_path)],
                creationflags=creation_flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return

        subprocess.Popen(
            ["sh", str(script_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    async def install_release(
        self,
        release_info: ReleaseInfo,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancel_callback: Optional[Callable[[], bool]] = None,
    ) -> Path:
        """下载并准备安装更新"""
        downloaded_file = await self.download_release_asset(
            release_info,
            progress_callback=progress_callback,
            cancel_callback=cancel_callback,
        )
        script_path, _ = self.prepare_update_script(downloaded_file)
        return script_path

    @staticmethod
    async def quit_application(delay: float = 0.3) -> None:
        """给脚本启动留出短暂时间"""
        await asyncio.sleep(delay)

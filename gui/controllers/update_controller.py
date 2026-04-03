from PyQt6.QtCore import pyqtSignal

from gui.controllers.base_controller import BaseController
from src.libs.update_manager import ReleaseInfo, UpdateCancelledError, UpdateManager


class UpdateController(BaseController):
    """更新控制器"""

    update_available = pyqtSignal(object)
    update_not_available = pyqtSignal(str)
    update_error = pyqtSignal(str)
    update_cancelled = pyqtSignal(str)
    download_progress = pyqtSignal(int, int, str)
    update_ready = pyqtSignal(str)

    def __init__(self, manager: UpdateManager = None):
        super().__init__()
        self.manager = manager or UpdateManager()
        self.latest_release_info: ReleaseInfo | None = None
        self._cancel_requested = False
        self.last_check_failed = False
        self.last_check_error_message = ""

    async def check_for_updates(self, current_version: str) -> ReleaseInfo | None:
        """检查是否有新版本"""
        self.last_check_failed = False
        self.last_check_error_message = ""
        try:
            release_info = await self.manager.fetch_latest_release()
            self.latest_release_info = release_info

            if self.manager.is_newer_version(current_version, release_info.tag_name):
                self.update_available.emit(release_info)
                return release_info

            message = f"当前已是最新版本: {current_version}"
            self.log_info(message)
            self.update_not_available.emit(message)
            return None
        except Exception as exc:
            message = f"检查更新失败: {exc}"
            self.last_check_failed = True
            self.last_check_error_message = message
            self.log_error("检查更新失败", exc)
            self.update_error.emit(message)
            return None

    async def download_and_prepare_update(self, current_version: str) -> str | None:
        """下载并准备更新"""
        if not self.manager.is_packaged_app():
            message = "当前为源码运行模式，无法自动替换程序文件"
            self.log_warn(message)
            self.update_error.emit(message)
            return None

        release_info = self.latest_release_info
        if release_info is None:
            release_info = await self.check_for_updates(current_version)

        if release_info is None:
            return None

        self._cancel_requested = False

        try:
            script_path = await self.manager.install_release(
                release_info,
                progress_callback=self._on_download_progress,
                cancel_callback=self.is_cancel_requested,
            )
            self.log_info(f"更新准备完成: {script_path}")
            self.update_ready.emit(str(script_path))
            return str(script_path)
        except UpdateCancelledError as exc:
            message = str(exc)
            self.log_warn(message)
            self.update_cancelled.emit(message)
            return None
        except Exception as exc:
            message = f"下载更新失败: {exc}"
            self.log_error("下载更新失败", exc)
            self.update_error.emit(message)
            return None

    def launch_update(self, script_path: str) -> None:
        """启动更新脚本"""
        try:
            self.manager.launch_update_script(script_path)
            self.log_info(f"更新脚本已启动: {script_path}")
        except Exception as exc:
            message = f"启动更新脚本失败: {exc}"
            self.log_error("启动更新脚本失败", exc)
            self.update_error.emit(message)

    def _on_download_progress(self, current: int, total: int, asset_name: str) -> None:
        """转发下载进度"""
        self.download_progress.emit(current, total, asset_name)

    def request_cancel(self) -> None:
        """请求取消下载"""
        self._cancel_requested = True

    def is_cancel_requested(self) -> bool:
        """判断是否已请求取消"""
        return self._cancel_requested

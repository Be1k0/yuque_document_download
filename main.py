__version__ = "v2.1.1"

import sys
import os
import ctypes
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt
from src.libs.log import Log
from gui.main_window import YuqueGUI

def excepthook(exc_type, exc_value, exc_traceback):
    """全局异常处理程序，用于记录未处理的异常"""
    import traceback
    from pathlib import Path
    import datetime

    exception_text = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    sys.stderr.write(f"Unhandled exception: {exception_text}\n")

    try:
        log_dir = os.path.join(os.getcwd(), "debug_logs")
        Path(log_dir).mkdir(exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_filename = f"crash_{timestamp}.log"
        crash_log_file = os.path.join(log_dir, log_filename)

        with open(crash_log_file, "a", encoding="utf-8") as f:
            f.write(f"\n[{timestamp}] Unhandled exception:\n{exception_text}\n")
    except Exception as log_error:
        sys.stderr.write(f"Failed to write crash log: {log_error}\n") 

    try:
        if QApplication.instance():
            QMessageBox.critical(None, "程序错误",
                                 f"程序发生错误,请联系开发者并提供以下信息:\n\n{str(exc_value)}\n\n"
                                 f"详细错误日志已保存到: {crash_log_file if 'crash_log_file' in locals() else 'unknown'}")
    except Exception as ui_error:
        sys.stderr.write(f"Failed to show error dialog: {ui_error}\n")

# 设置Qt插件路径
def setup_qt_plugins():
    """修复 Qt 平台插件在venv环境中的路径问题"""
    if 'QT_QPA_PLATFORM_PLUGIN_PATH' in os.environ:
        return

    plugin_path = None
    
    # 检查当前虚拟环境路径
    executable_dir = os.path.dirname(sys.executable)
    potential_paths = [
        os.path.join(executable_dir, 'Lib', 'site-packages', 'PyQt6', 'Qt6', 'plugins'),
        os.path.join(executable_dir, '..', 'Lib', 'site-packages', 'PyQt6', 'Qt6', 'plugins'),
        os.path.join(executable_dir, 'site-packages', 'PyQt6', 'Qt6', 'plugins'),
    ]

    # 查找存在的路径
    for path in potential_paths:
        if os.path.exists(path) and os.path.isdir(path):
            plugin_path = path
            break
    
    if plugin_path:
        os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = plugin_path
        os.environ['QT_PLUGIN_PATH'] = plugin_path

def setup_windows_appid():
    if sys.platform == 'win32':
        try:
            myappid = f"be1k0.yuque.downloader.{__version__}"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

def main():
    setup_qt_plugins()
    setup_windows_appid()
    
    # 安装全局异常处理程序
    sys.excepthook = excepthook

    # 允许在高DPI屏幕上正确缩放
    if hasattr(Qt.ApplicationAttribute, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt.ApplicationAttribute, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    # 解决 Windows 下高分屏缩放过大的问题
    if hasattr(Qt, 'HighDpiScaleFactorRoundingPolicy'):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    try:
        import qasync
        import asyncio

        # 创建应用程序实例
        app = QApplication(sys.argv)
        
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__ if not "__compiled__" in globals() else sys.argv[0])), "favicon.ico")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
        
        # 使用 qasync 创建与 Qt 集成的事件循环
        loop = qasync.QEventLoop(app)
        asyncio.set_event_loop(loop)

        window = YuqueGUI()
        window.show()

        with loop:
            loop.run_forever()

    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        
        try:
            Log.error(f"启动失败: {str(e)}\n{error_traceback}")
        except:
            pass

if __name__ == "__main__":
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))
    
    if sys.platform == 'win32':
        pass
        
    main()


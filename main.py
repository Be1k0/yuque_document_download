import sys
import os
import nest_asyncio
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt
from src.libs.log import Log
from gui.main_window import YuqueGUI

def excepthook(exc_type, exc_value, exc_traceback):
    """全局异常处理程序，用于记录未处理的异常"""
    import traceback
    from pathlib import Path
    import datetime

    exception_text = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    sys.stderr.write(f"Unhandled exception: {exception_text}\n")

    # 写入崩溃日志文件
    try:
        log_dir = os.path.join(os.getcwd(), "debug_logs")
        Path(log_dir).mkdir(exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_filename = f"crash_{timestamp}.log"
        crash_log_file = os.path.join(log_dir, log_filename)

        with open(crash_log_file, "a", encoding="utf-8") as f:
            f.write(f"\n[{timestamp}] Unhandled exception:\n{exception_text}\n")
    except:
        pass 

    try:
        if QApplication.instance():
            QMessageBox.critical(None, "程序错误",
                                 f"程序发生错误，请联系开发者并提供以下信息：\n\n{str(exc_value)}\n\n"
                                 f"详细错误日志已保存到: {crash_log_file if 'crash_log_file' in locals() else 'unknown'}")
    except:
        pass

# 设置Qt插件路径（在导入PyQt5之前）
def setup_qt_plugins():
    """修复 Qt 平台插件路径问题"""
    # 如果已经设置了环境变量，则跳过
    if 'QT_QPA_PLATFORM_PLUGIN_PATH' in os.environ:
        return

    plugin_path = None
    
    # 1. 检查当前虚拟环境路径
    executable_dir = os.path.dirname(sys.executable)
    potential_paths = [
        os.path.join(executable_dir, 'Lib', 'site-packages', 'PyQt5', 'Qt5', 'plugins'),
        os.path.join(executable_dir, '..', 'Lib', 'site-packages', 'PyQt5', 'Qt5', 'plugins'),
        os.path.join(executable_dir, 'site-packages', 'PyQt5', 'Qt5', 'plugins'),
    ]
    
    # 2. 检查 sys.path 中的 site-packages
    for path in sys.path:
        if 'site-packages' in path:
            potential_paths.append(os.path.join(path, 'PyQt5', 'Qt5', 'plugins'))

    # 3. 查找存在的路径
    for path in potential_paths:
        if os.path.exists(path) and os.path.isdir(path):
            plugin_path = path
            break
    
    if plugin_path:
        os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = plugin_path
        os.environ['QT_PLUGIN_PATH'] = plugin_path

def main():
    nest_asyncio.apply()
    setup_qt_plugins()
    
    # 安装全局异常处理程序
    sys.excepthook = excepthook

    # 允许在高DPI屏幕上正确缩放
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    # 解决 Windows 下高分屏缩放过大的问题
    # PassThrough 策略允许使用非整数缩放因子，避免强制向上取整导致的界面过大
    if hasattr(Qt, 'HighDpiScaleFactorRoundingPolicy'):
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    try:
        # 创建应用程序实例
        app = QApplication(sys.argv)
        window = YuqueGUI()
        window.show()
        sys.exit(app.exec_())

    except Exception as e:
        import traceback
        Log.error(f"启动失败: {str(e)}\n{traceback.format_exc()}")

        try:
            if QApplication.instance():
                QMessageBox.critical(None, "启动失败", f"程序启动失败: {str(e)}")
        except:
            pass


if __name__ == "__main__":
    if getattr(sys, 'frozen', False):
        os.chdir(os.path.dirname(sys.executable))
    main()

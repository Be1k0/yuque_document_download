import os
import json
from PyQt6.QtWidgets import QApplication
from src.libs.path_utils import get_bundled_resource_path
from src.libs.log import Log
try:
    import winreg
except ImportError:
    winreg = None

class ThemeManager:
    """主题管理器类
    
    提供主题切换和获取主题配置的功能
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ThemeManager, cls).__new__(cls)
            cls._instance.init()
        return cls._instance
    
    def init(self):
        """初始化主题管理器"""
        self.current_theme = "default"
        self.theme_config = {}
        self.load_config()
        
    def load_config(self):
        """加载主题配置"""
        config_path = get_bundled_resource_path(os.path.join("src", "ui", "themes", "theme_config.json"))
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    self.theme_config = json.load(f)
            else:
                Log.error(f"主题配置文件不存在: {config_path}")
                # 提供默认配置
                self.theme_config = {
                    "default": {
                        "primary_color": "#0d6efd",
                        "secondary_color": "#6c757d",
                        "background_color": "#f8f9fa",
                        "text_color": "#333333",
                        "border_color": "#dee2e6",
                        "success_color": "#198754",
                        "warning_color": "#ffc107",
                        "danger_color": "#dc3545",
                        "panel_background": "#ffffff"
                    },
                    "dark": {
                        "primary_color": "#0d6efd",
                        "secondary_color": "#adb5bd",
                        "background_color": "#212529",
                        "text_color": "#f8f9fa",
                        "border_color": "#495057",
                        "success_color": "#198754",
                        "warning_color": "#ffc107",
                        "danger_color": "#dc3545",
                        "panel_background": "#343a40"
                    }
                }
        except Exception as e:
            Log.error(f"加载主题配置失败: {e}")

    def apply_theme(self, app_or_widget, theme_name=None):
        """应用主题到应用程序或窗口部件
        
        Args:
            app_or_widget: QApplication实例或QWidget实例
            theme_name: 要应用的主题名称
        """
        if theme_name:
            self.current_theme = theme_name
            
        # 决定实际要应用的主题
        actual_theme = self.current_theme
        if self.current_theme == "system":
            actual_theme = self.get_system_theme()
            
        theme_vars = self.theme_config.get(actual_theme, self.theme_config.get("default", {}))
        
        # 加载 QSS 文件
        qss_filename = f"{actual_theme}.qss"
        qss_path = get_bundled_resource_path(os.path.join("src", "ui", "themes", qss_filename))
        
        # 如果特定主题文件不存在，回退到默认主题
        if not os.path.exists(qss_path) and actual_theme != "default":
             qss_path = get_bundled_resource_path(os.path.join("src", "ui", "themes", "default.qss"))
             
        try:
            if os.path.exists(qss_path):
                with open(qss_path, 'r', encoding='utf-8') as f:
                    qss_content = f.read()
                    
                # 替换变量 - 按键长度降序排序
                sorted_keys = sorted(theme_vars.keys(), key=len, reverse=True)
                for key in sorted_keys:
                    value = theme_vars[key]
                    if isinstance(value, str) and "src/ui/themes" in value:
                        normalized_path = value.replace("/", os.sep)
                        abs_path = get_bundled_resource_path(normalized_path)
                        value = abs_path.replace("\\", "/")
                        
                    qss_content = qss_content.replace(f"@{key}", value)
                    
                # 应用样式表
                if isinstance(app_or_widget, QApplication):
                    app_or_widget.setStyleSheet(qss_content)
                else:
                    app_or_widget.setStyleSheet(qss_content)
                    
            else:
                Log.error(f"找不到主题文件: {qss_path}")
        except Exception as e:
            Log.error(f"应用主题失败: {e}")

    def get_color(self, key_name, default_color="#000000"):
        """获取当前主题的颜色变量
        
        Args:
            key_name: 颜色变量名称
            default_color: 默认颜色值
        """
        actual_theme = self.current_theme
        if self.current_theme == "system":
            actual_theme = self.get_system_theme()
        theme_vars = self.theme_config.get(actual_theme, self.theme_config.get("default", {}))
        return theme_vars.get(key_name, default_color)

    def get_theme_names(self):
        """获取所有可用主题名称"""
        return list(self.theme_config.keys())

    def get_system_theme(self):
        """检测系统主题（仅支持Windows）"""
        if not winreg:
            return "default"
            
        try:
            registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            key = winreg.OpenKey(registry, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "default" if value == 1 else "dark"
        except Exception:
            return "default"

# 全局实例
THEME_MANAGER = ThemeManager()

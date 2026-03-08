from PyQt6.QtCore import QObject
from src.libs.log import Log

class BaseController(QObject):
    """控制器基类
    
    所有控制器类应继承自该类。
    """
    
    def __init__(self):
        super().__init__()
    
    def log_error(self, message: str, exception: Exception = None):
        """记录错误日志"""
        if exception:
            Log.error(f"{message}: {str(exception)}")
        else:
            Log.error(message)
            
    def log_info(self, message: str):
        """记录信息日志"""
        Log.info(message)
        
    def log_success(self, message: str):
        """记录成功日志"""
        Log.success(message)
        
    def log_warn(self, message: str):
        """记录警告日志"""
        Log.warn(message)

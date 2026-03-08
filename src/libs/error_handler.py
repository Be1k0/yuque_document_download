import traceback
import functools
from typing import Callable, Any
from .log import Log

class ErrorHandler:
    """统一错误处理工具类"""
    
    @staticmethod
    def format_exception(e: Exception, include_traceback: bool = True) -> str:
        """格式化异常信息
        
        Args:
            e: 异常对象
            include_traceback: 是否包含完整堆栈跟踪
        """
        error_msg = f"{type(e).__name__}: {str(e)}"
        
        if include_traceback:
            tb = traceback.format_exc()
            error_msg = f"{error_msg}\n\n堆栈跟踪:\n{tb}"
        
        return error_msg
    
    @staticmethod
    def log_exception(e: Exception, context: str = "", detailed: bool = True):
        """记录异常到日志
        
        Args:
            e: 异常对象
            context: 业务上下文描述
            detailed: 是否记录详细信息(包含堆栈跟踪)
        """
        error_msg = ErrorHandler.format_exception(e, include_traceback=detailed)
        
        if context:
            Log.error(f"[{context}] {error_msg}", detailed=detailed)
        else:
            Log.error(error_msg, detailed=detailed)
    
    @staticmethod
    def async_error_handler(context: str = "", reraise: bool = True, default_return: Any = None):
        """异步函数错误处理装饰器
        
        Args:
            context: 业务上下文描述,如"下载知识库"
            reraise: 是否重新抛出异常
            default_return: 如果不重新抛出,返回的默认值
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def wrapper(*args, **kwargs) -> Any:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if type(e).__name__ == "CookiesExpiredError":
                        ErrorHandler.log_exception(e, context or func.__name__, detailed=False)
                        raise
                    ErrorHandler.log_exception(e, context or func.__name__)
                    if reraise:
                        raise
                    return default_return
            return wrapper
        return decorator
    
    @staticmethod
    def sync_error_handler(context: str = "", reraise: bool = True, default_return: Any = None):
        """同步函数错误处理装饰器
        
        Args:
            context: 业务上下文描述
            reraise: 是否重新抛出异常
            default_return: 如果不重新抛出,返回的默认值
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if type(e).__name__ == "CookiesExpiredError":
                        ErrorHandler.log_exception(e, context or func.__name__, detailed=False)
                        raise
                    ErrorHandler.log_exception(e, context or func.__name__)
                    if reraise:
                        raise
                    return default_return
            return wrapper
        return decorator
    
    @staticmethod
    def safe_execute(func: Callable, *args, context: str = "", default_return: Any = None, **kwargs) -> Any:
        """安全执行函数,捕获所有异常
        
        Args:
            func: 要执行的函数
            *args: 函数参数
            context: 业务上下文
            default_return: 发生异常时的返回值
            **kwargs: 函数关键字参数
        """
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if type(e).__name__ == "CookiesExpiredError":
                ErrorHandler.log_exception(e, context or func.__name__, detailed=False)
                raise
            ErrorHandler.log_exception(e, context or func.__name__)
            return default_return

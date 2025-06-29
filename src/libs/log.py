from enum import Enum

from colorama import Fore, Style, init

# 初始化colorama
init(autoreset=True)


class Action(Enum):
    SUCCESS = "SUCCESS"
    INFO = "INFO"
    ERROR = "ERROR"
    WARN = "WARN"
    DEBUG = "DEBUG"


def dump_log(action: Action, message: str):
    """输出日志信息"""
    if action == Action.SUCCESS:
        print(f"{Fore.GREEN}{message}{Style.RESET_ALL}")
    elif action == Action.INFO:
        print(f"{Fore.CYAN}{message}{Style.RESET_ALL}")
    elif action == Action.ERROR:
        print(f"{Fore.RED}{message}{Style.RESET_ALL}")
    elif action == Action.WARN:
        print(f"{Fore.YELLOW}{message}{Style.RESET_ALL}")
    elif action == Action.DEBUG:
        print(f"{Fore.MAGENTA}[DEBUG] {message}{Style.RESET_ALL}")


class Log:
    """日志工具类"""

    NAME = "ytool->"
    # 默认不启用调试模式
    _debug_mode = False

    @classmethod
    def set_debug_mode(cls, enabled: bool):
        """设置调试模式"""
        cls._debug_mode = enabled

    @classmethod
    def is_debug_mode(cls) -> bool:
        """获取当前调试模式状态"""
        return cls._debug_mode

    @staticmethod
    def success(message: str):
        """成功消息"""
        print(f"{Fore.GREEN}{message}{Style.RESET_ALL}")

    @staticmethod
    def info(message: str):
        """普通消息"""
        print(f"{Fore.CYAN}{message}{Style.RESET_ALL}")

    @classmethod
    def error(cls, message: str, detailed: bool = False):
        """错误消息
        
        Args:
            message: 错误消息
            detailed: 是否为详细错误，详细错误只在调试模式下显示
        """
        if detailed and not cls._debug_mode:
            return
        print(f"{Fore.RED}{message}{Style.RESET_ALL}")

    @classmethod
    def warn(cls, message: str, detailed: bool = False):
        """警告消息
        
        Args:
            message: 警告消息
            detailed: 是否为详细警告，详细警告只在调试模式下显示
        """
        if detailed and not cls._debug_mode:
            return
        print(f"{Fore.YELLOW}{message}{Style.RESET_ALL}")

    @classmethod
    def debug(cls, message: str):
        """调试消息，只在调试模式下显示"""
        if not cls._debug_mode:
            return
        print(f"{Fore.MAGENTA}[DEBUG] {message}{Style.RESET_ALL}")

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path


class DebugLogger:
    """调试日志记录器"""

    # 类变量，标记是否已初始化
    _initialized = False
    _logger = None
    _log_file = None

    @classmethod
    def initialize(cls):
        """初始化调试日志记录器"""
        if cls._initialized:
            return

        # 创建日志目录
        log_dir = os.path.join(os.getcwd(), "debug_logs")
        Path(log_dir).mkdir(exist_ok=True)

        # 基于当前时间创建日志文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"debug_{timestamp}.log"
        cls._log_file = os.path.join(log_dir, log_filename)

        # 配置日志记录器
        logger = logging.getLogger("yuque_debug")
        logger.setLevel(logging.DEBUG)

        # 文件处理器
        file_handler = logging.FileHandler(cls._log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)

        # 格式化器
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)

        # 添加处理器
        logger.addHandler(file_handler)

        # 保存记录器对象
        cls._logger = logger
        cls._initialized = True

        # 记录初始信息
        cls.log_info(f"调试日志已初始化，日志文件: {cls._log_file}")
        cls.log_info(f"系统信息: {sys.platform}, Python: {sys.version}")

    @classmethod
    def log_info(cls, message):
        """记录普通信息"""
        if not cls._initialized:
            return
        cls._logger.info(message)

    @classmethod
    def log_error(cls, message):
        """记录错误信息"""
        if not cls._initialized:
            return
        cls._logger.error(message)

    @classmethod
    def log_warning(cls, message):
        """记录警告信息"""
        if not cls._initialized:
            return
        cls._logger.warning(message)

    @classmethod
    def log_debug(cls, message):
        """记录调试信息"""
        if not cls._initialized:
            return
        cls._logger.debug(message)

    @classmethod
    def log_request(cls, url, method, headers, data=None):
        """记录HTTP请求信息"""
        if not cls._initialized:
            return

        request_info = {
            "url": url,
            "method": method,
            "headers": headers,
            "data": data
        }

        cls._logger.debug(f"HTTP请求: {json.dumps(request_info, ensure_ascii=False, indent=2)}")

    @classmethod
    def log_response(cls, status_code, headers, body):
        """记录HTTP响应信息"""
        if not cls._initialized:
            return

        # 尝试格式化响应体为JSON（如果适用）
        response_body = body
        try:
            if isinstance(body, str):
                json_body = json.loads(body)
                response_body = json_body
        except:
            pass

        response_info = {
            "status_code": status_code,
            "headers": dict(headers),
            "body": response_body
        }

        cls._logger.debug(f"HTTP响应: {json.dumps(response_info, ensure_ascii=False, indent=2, default=str)}")

    @classmethod
    def log_data(cls, label, data):
        """记录结构化数据"""
        if not cls._initialized:
            return

        try:
            if isinstance(data, (dict, list)):
                data_str = json.dumps(data, ensure_ascii=False, indent=2, default=str)
            else:
                data_str = str(data)

            cls._logger.debug(f"{label}: {data_str}")
        except Exception as e:
            cls._logger.error(f"无法记录数据 '{label}': {str(e)}")

import json
import logging
import os
from datetime import datetime
from pathlib import Path

class DebugLogger:
    """调试日志记录器
    
    该类负责在程序运行过程中记录详细的调试信息，包括系统环境、HTTP请求与响应、以及其他关键事件。
    """

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

        # 收集完整的系统环境信息
        sys_info = cls._get_system_info()
            
        cls.log_data("系统环境信息", sys_info)

    @staticmethod
    def _get_system_info():
        """收集系统环境信息，包括操作系统、Python版本、硬件信息、网络配置等"""
        import uuid
        import os
        import sys
        import time
        import platform
        import socket
        from datetime import datetime
        import requests
        
        try:
            from main import __version__ as app_version
        except ImportError:
            app_version = "Unknown"

        info = {
            "app_version": app_version,
            "os": {
                "system": platform.system(),
                "release": platform.release(),
                "version": platform.version(),
                "machine": platform.machine(),
                "platform": platform.platform()
            },
            "python": {
                "version": sys.version,
                "executable": sys.executable,
                "is_frozen": getattr(sys, 'frozen', False)
            },
            "hardware": {
                "cpu_processor": platform.processor(),
                "cpu_name": "Unknown",
                "cpu_count": os.cpu_count(),
                "memory": "Unknown"
            },
            "network": {
                "hostname": socket.gethostname(),
                "mac_address": ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff) for elements in range(0,2*6,2)][::-1]),
                "local_ips": [],
                "public_ip": "Unknown",
                "dns_resolution": "Unknown",
                "yuque_connectivity": "Unknown",
                "system_proxy_effective": "Unknown"
            },
            "environment": {
                "cwd": os.getcwd(),
                "http_proxy": os.environ.get("HTTP_PROXY"),
                "https_proxy": os.environ.get("HTTPS_PROXY"),
                "all_proxy": os.environ.get("ALL_PROXY")
            },
            "system_proxy": {
                "enabled": False,
                "server": None
            },
            "process": {},
            "disk": {},
            "gpu": "Unknown",
            "running_processes": [],
            "time": {
                "timezone": time.tzname,
                "is_dst": time.localtime().tm_isdst,
                "local_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            "permissions": {
                "is_admin": False,
                "cwd_writable": os.access(os.getcwd(), os.W_OK)
            },
            "startup": {
                "argv": sys.argv
            }
        }
        
        # 网络基础检测
        try:
            hostname, aliases, ips = socket.gethostbyname_ex(socket.gethostname())
            info["network"]["local_ips"] = ips
        except Exception as e:
            info["network"]["local_ips"] = [f"Error: {str(e)}"]

        # 系统级进程与资源检测
        try:
            import psutil
            pid = os.getpid()
            p = psutil.Process(pid)
            info["process"] = {
                "pid": pid,
                "ppid": p.ppid(),
                "start_time": datetime.fromtimestamp(p.create_time()).strftime("%Y-%m-%d %H:%M:%S"),
                "threads_count": p.num_threads(),
                "memory_usage_mb": round(p.memory_info().rss / (1024 * 1024), 2),
                "cpu_percent": p.cpu_percent(interval=None)
            }
            
            # 磁盘信息获取当前执行目录所在磁盘
            disk_usage = psutil.disk_usage(os.path.abspath(os.sep))
            info["disk"] = {
                "target_path": os.getcwd(),
                "total_gb": round(disk_usage.total / (1024**3), 2),
                "free_gb": round(disk_usage.free / (1024**3), 2),
                "percent_used": disk_usage.percent
            }
        except ImportError:
            info["process"] = "psutil module missing"
            info["disk"] = "psutil module missing"
        except Exception as e:
            info["process"] = f"Error: {str(e)}"
            info["disk"] = f"Error: {str(e)}"

        # 网络深入检测 (公网IP、DNS与连通性)
        try:
            info["network"]["dns_resolution"] = socket.gethostbyname("www.yuque.com")
            with socket.create_connection(("www.yuque.com", 443), timeout=3):
                info["network"]["yuque_connectivity"] = "OK"
        except Exception as e:
            info["network"]["yuque_connectivity"] = f"Failed: {str(e)}"

        # 在子线程或者设置较短超时检测公网IP防卡死
        try:
            resp = requests.get("https://api.ipify.org", timeout=2)
            if resp.status_code == 200:
                info["network"]["public_ip"] = resp.text.strip()
        except:
            pass
            
        # 系统硬件(RAM)、代理与独有组件 (仅 Windows)
        if platform.system() == "Windows":
            # 完整物理内存提取 (兼容防 psutil 缺失)
            try:
                import ctypes
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                    ]
                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
                info["hardware"]["memory"] = {
                    "total_mb": stat.ullTotalPhys // (1024 * 1024),
                    "avail_mb": stat.ullAvailPhys // (1024 * 1024),
                    "load_percent": stat.dwMemoryLoad
                }
            except Exception as e:
                info["hardware"]["memory"] = f"Error: {str(e)}"
                
            # 提取系统局域网代理设定
            try:
                import winreg
                internet_settings = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Internet Settings')
                proxy_enable, _ = winreg.QueryValueEx(internet_settings, 'ProxyEnable')
                if proxy_enable:
                    proxy_server, _ = winreg.QueryValueEx(internet_settings, 'ProxyServer')
                    info["system_proxy"]["enabled"] = True
                    info["system_proxy"]["server"] = proxy_server
                winreg.CloseKey(internet_settings)
            except Exception as e:
                info["system_proxy"]["error"] = str(e)
                
            # 管理员权限检查
            try:
                import ctypes
                info["permissions"]["is_admin"] = ctypes.windll.shell32.IsUserAnAdmin() != 0
            except:
                pass
                
            # 获取显卡、CPU真实型号与安全软件状态 (WMI)
            try:
                import wmi
                w = wmi.WMI()
                info["gpu"] = [gpu.Name for gpu in w.Win32_VideoController()]
                # 通过 WMI 获取 CPU 品牌全称
                cpus = [cpu.Name.strip() for cpu in w.Win32_Processor()]
                if cpus:
                    info["hardware"]["cpu_name"] = cpus[0] if len(cpus) == 1 else cpus
                # 列出当前系统所有运行中的进程
                try:
                    import psutil
                    proc_names = sorted({p.info['name'] for p in psutil.process_iter(['name']) if p.info['name']})
                    info["running_processes"] = proc_names
                except Exception:
                    pass
            except ImportError:
                info["gpu"] = "wmi module missing"
            except Exception as e:
                info["gpu"] = f"WMI query failed: {str(e)}"

        # 配置与启动参数摘要
        try:
            from src.libs.constants import load_config
            cfg = load_config()
            info["startup"]["config_summary"] = {
                "yuque_host": getattr(cfg, "yuque_host", ""),
                "target_output_dir": getattr(cfg, "target_output_dir", ""),
                "disable_ssl": getattr(cfg, "disable_ssl", False)
            }
        except Exception as e:
            info["startup"]["config_error"] = str(e)

        return info

    @classmethod
    def log_info(cls, message):
        """记录普通信息
        
        Args:
            message: 要记录的信息
        """
        if not cls._initialized:
            return
        cls._logger.info(message)

    @classmethod
    def log_error(cls, message):
        """记录错误信息
        
        Args:
            message: 要记录的错误信息
        """
        if not cls._initialized:
            return
        cls._logger.error(message)

    @classmethod
    def log_warning(cls, message):
        """记录警告信息
        
        Args:
            message: 要记录的警告信息
        """
        if not cls._initialized:
            return
        cls._logger.warning(message)

    @classmethod
    def log_debug(cls, message):
        """记录调试信息
        
        Args:
            message: 要记录的调试信息
        """
        if not cls._initialized:
            return
        cls._logger.debug(message)

    @classmethod
    def log_request(cls, url, method, headers, data=None):
        """记录HTTP请求信息
        
        Args:
            url: 请求的URL
            method: 请求的方法
            headers: 请求头
            data: 请求体
        """
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
        """记录HTTP响应信息
        
        Args:
            status_code: 响应的状态码
            headers: 响应头
            body: 响应体
        """
        if not cls._initialized:
            return

        # 尝试格式化响应体为JSON
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
        """记录结构化数据
        
        Args:
            label: 数据标签
            data: 要记录的数据
        """
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

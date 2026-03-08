class YuqueExportError(Exception):
    """语雀导出工具基础异常
    
    所有自定义异常的基类
    """
    def __init__(self, message: str, details: dict = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)
    
    def __str__(self):
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message

class AuthenticationError(YuqueExportError):
    """认证错误基类"""
    pass

class CookiesExpiredError(AuthenticationError):
    """Cookies 过期异常
    
    当用户登录状态过期时抛出
    """
    def __init__(self, message: str = "登录已过期,请重新登录"):
        super().__init__(message)

class LoginFailedError(AuthenticationError):
    """登录失败异常
    
    当用户名或密码错误时抛出
    """
    def __init__(self, message: str = "登录失败,请检查用户名和密码"):
        super().__init__(message)

class NetworkError(YuqueExportError):
    """网络错误基类"""
    pass

class RequestTimeoutError(NetworkError):
    """请求超时异常"""
    def __init__(self, url: str, timeout: int):
        super().__init__(
            f"请求超时: {url}",
            {"url": url, "timeout": timeout}
        )

class ConnectionError(NetworkError):
    """连接错误异常"""
    def __init__(self, url: str, reason: str = ""):
        super().__init__(
            f"连接失败: {url}",
            {"url": url, "reason": reason}
        )

class ResourceError(YuqueExportError):
    """资源错误基类"""
    pass

class BookNotFoundError(ResourceError):
    """知识库未找到异常"""
    def __init__(self, book_name: str):
        super().__init__(
            f"知识库不存在: {book_name}",
            {"book": book_name}
        )

class DocNotFoundError(ResourceError):
    """文档未找到异常"""
    def __init__(self, doc_id: str, book_name: str = ""):
        details = {"doc_id": doc_id}
        if book_name:
            details["book"] = book_name
        super().__init__(
            f"文档不存在: {doc_id}",
            details
        )

class ImageDownloadError(ResourceError):
    """图片下载错误异常"""
    def __init__(self, url: str, reason: str = ""):
        super().__init__(
            f"图片下载失败: {url}",
            {"url": url, "reason": reason}
        )

class DataError(YuqueExportError):
    """数据错误基类"""
    pass


class ParseError(DataError):
    """解析错误异常"""
    def __init__(self, data_type: str, reason: str = ""):
        super().__init__(
            f"{data_type} 解析失败",
            {"type": data_type, "reason": reason}
        )


class ValidationError(DataError):
    """数据验证错误异常"""
    def __init__(self, field: str, value: any, reason: str = ""):
        super().__init__(
            f"验证失败: {field}",
            {"field": field, "value": value, "reason": reason}
        )

class DownloadError(YuqueExportError):
    """下载错误基类"""
    pass

class DownloadInterruptedError(DownloadError):
    """下载中断异常"""
    def __init__(self, message: str = "下载被中断"):
        super().__init__(message)

class StorageError(YuqueExportError):
    """存储错误基类"""
    pass

class DiskFullError(StorageError):
    """磁盘空间不足异常"""
    def __init__(self, path: str):
        super().__init__(
            f"磁盘空间不足: {path}",
            {"path": path}
        )

class FileWriteError(StorageError):
    """文件写入错误异常"""
    def __init__(self, file_path: str, reason: str = ""):
        super().__init__(
            f"文件写入失败: {file_path}",
            {"file": file_path, "reason": reason}
        )

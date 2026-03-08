from typing import List, Dict, Any
from gui.controllers.base_controller import BaseController
from src.core.yuque import YuqueClient
from src.libs.exceptions import CookiesExpiredError, NetworkError

class ArticleController(BaseController):
    """文章控制器
    
    负责处理文章列表的获取和缓存等相关任务。
    """
    
    def __init__(self, client: YuqueClient = None):
        super().__init__()
        self.client = client or YuqueClient()
        
    async def get_articles(self, namespace: str) -> List[Dict[str, Any]]:
        """获取指定知识库的文章列表
        
        Args:
            namespace: 知识库命名空间
            
        Returns:
            List[Dict[str, Any]]: 文章列表，如果获取失败返回空列表或包含错误信息的字典
        """
        import asyncio
        from src.libs.tools import get_docs_cache, save_docs_cache
        
        if not namespace:
            self.log_error("尝试获取文章列表时 namespace 为空")
            return []
            
        # 尝试从缓存获取
        cached_docs = get_docs_cache(namespace)
        if cached_docs:
            self.log_info(f"从缓存加载知识库 {namespace} 的文章列表")
            return cached_docs
            
        self.log_info(f"正在获取知识库文章: {namespace}")
        
        # 如果没有缓存则从API获取
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                docs = await self.client.get_book_docs(namespace)
                
                if docs:
                    self.log_success(f"成功获取 {len(docs)} 篇文章: {namespace}")
                    save_docs_cache(namespace, docs)
                    return docs
                
                # API返回成功但没有数据，可能是网络问题或API异常，进行重试
                if docs is None:
                    self.log_warn(f"未获取到文档，将在 {retry_delay} 秒后重试 (尝试 {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 1.5
                    continue
                else:
                    return []
                    
            except CookiesExpiredError:
                self.log_warn("Cookies 已过期")
                return {"error": "cookies_expired", "message": "登录已过期，请重新登录"}
                
            except NetworkError as e:
                self.log_warn(f"网络连接问题: {e}，将在 {retry_delay} 秒后重试 (尝试 {attempt + 1}/{max_retries})")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
                continue
                
            except Exception as e:
                error_msg = str(e)
                self.log_error(f"获取文档列表失败: {error_msg}")
                
                # 其他错误
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 1.5
                    continue
                else:
                    return {"error": "fetch_failed", "message": f"获取文档列表失败: {error_msg}"}
                    
        return {"error": "all_retries_failed", "message": "多次尝试获取文档列表均失败"}

from typing import List, Optional
from gui.controllers.base_controller import BaseController
from src.core.yuque import YuqueClient
from src.libs.constants import BookItem
from src.libs.tools import get_cache_books_info
from src.libs.exceptions import CookiesExpiredError, NetworkError

class BookController(BaseController):
    """知识库控制器
    
    负责处理知识库列表的获取和缓存等相关任务。
    """
    
    def __init__(self, client: YuqueClient = None):
        super().__init__()
        self.client = client or YuqueClient()
        
    async def get_books(self) -> Optional[List[BookItem]]:
        """获取知识库列表
        
        Returns:
            Optional[List[BookItem]]: 知识库列表，如果获取失败返回 None 或空列表
        """
        # 尝试从缓存获取
        books_info = get_cache_books_info()
        if books_info:
            self.log_info("从缓存加载知识库列表成功")
            return books_info
        
        # 缓存不存在或已过期，从远程获取
        try:
            self.log_info(f"开始远程获取知识库列表: {self.client.config.yuque_book_stacks}")
            
            # 异步获取知识库数据
            result = await self.client.get_user_bookstacks()
            
            if result and "books_info" in result:
                raw_books = result["books_info"]
                books = []
                for item in raw_books:
                    try:
                        if "docs" not in item:
                            item["docs"] = []
                        books.append(BookItem(**item))
                    except Exception as e:
                        self.log_error(f"转换知识库数据失败: {item.get('name', 'unknown')}", e)
                        
                self.log_success(f"成功获取 {len(books)} 个知识库")
                return books
            else:
                self.log_error("获取知识库列表失败: 返回数据为空或格式错误")
                return []
                
        except CookiesExpiredError:
            self.log_error("Cookies 已过期，请重新登录")
            return []
        except NetworkError as e:
            self.log_error(f"网络请求失败: {e}")
            return []
        except Exception as e:
            self.log_error("获取知识库列表时发生异常", e)
            return []


import json
import re
import urllib.parse
from typing import Dict, Any, Optional
from ..libs.log import Log

class YuqueParser:
    """语雀数据解析器类
    
    提供从页面内容中解析知识库目录信息和从URL中提取slug的静态方法
    """

    @staticmethod
    def parse_book_toc(text_content: str) -> Optional[Dict[str, Any]]:
        """从页面内容中解析知识库目录信息
        
        Args:
            text_content: 页面内容文本
        """
        patterns = [
            r'decodeURIComponent\("([^"]+)"\)'
        ]

        data = None
        for i, pattern in enumerate(patterns, 1):
            try:
                matches = re.search(pattern, text_content, re.DOTALL)
                if matches:
                    if "decodeURIComponent" in pattern:
                        # 需要URL解码
                        encoded_data = matches.group(1)
                        decoded_data = urllib.parse.unquote(encoded_data)
                        data = json.loads(decoded_data)
                    else:
                        # 直接是JSON字符串
                        json_str = matches.group(1)
                        data = json.loads(json_str)

                    if data:
                        break
            except Exception as e:
                Log.warn(f"模式{i}解析失败: {str(e)}", detailed=True)
                continue

        # 解析后的数据结构可能不同，尝试适配常见的结构
        if data:
            if "book" in data and "toc" in data["book"]:
                return data
            elif "toc" in data:
                return {"book": {"toc": data["toc"]}}
            elif "data" in data and "book" in data["data"]:
                if "toc" in data["data"]["book"]:
                    toc_data = data["data"]["book"]["toc"]
                    return {"book": {"toc": toc_data}}
        
        return None

    @staticmethod
    def extract_slug_from_url(url_path: str) -> Optional[str]:
        """从URL中提取slug
        
        Args:
            url_path: URL路径字符串
        """
        if not url_path:
            return None
        slug_match = re.search(r'/([^/]+)$', url_path)
        if slug_match:
            return slug_match.group(1)
        return None

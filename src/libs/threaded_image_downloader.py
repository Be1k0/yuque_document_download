import os
import re
from urllib.parse import urlparse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from .log import Log

class ThreadedImageDownloader:
    """多线程图片下载器"""

    def __init__(self, max_workers=5, progress_callback=None):
        self.max_workers = max_workers
        self.progress_callback = progress_callback
        self.downloaded_count = 0
        self.total_count = 0
        self.lock = threading.Lock()

    def download_image(self, image_url, image_dir, image_name_mode, idx, suffix, image_file_prefix):
        """下载单个图片
        
        Args:
            image_url: 图片URL
            image_dir: 图片存储目录
            image_name_mode: 图片命名模式
            idx: 图片索引
            suffix: 图片后缀
            image_file_prefix: 图片文件前缀
        """
        try:
            r = requests.get(image_url, stream=True, timeout=30)
            image_name = image_url.split('/')[-1]
            if image_name_mode == 'asc':
                image_name = image_file_prefix + str(idx) + suffix

            if r.status_code == 200:
                file_path = os.path.join(image_dir, image_name)
                with open(file_path, 'wb') as f:
                    f.write(r.content)

                with self.lock:
                    self.downloaded_count += 1
                    if self.progress_callback:
                        self.progress_callback(self.downloaded_count, self.total_count)

                Log.info(f'图片下载成功: {image_name}')
                return True
            else:
                Log.warn(f'图片下载失败: {image_url}, 状态码: {r.status_code}')
                return False
        except Exception as e:
            Log.error(f'图片下载异常: {image_url}, 错误: {str(e)}')
            return False
        finally:
            if 'r' in locals():
                del r

    def deal_yuque(self, origin_md_path, output_md_path, image_dir, image_url_prefix,
                   image_rename_mode, image_file_prefix, yuque_cdn_domain):
        """处理单个Markdown文件，提取图片URL并下载
        
        Args:
            origin_md_path: 原Markdown文件路径
            output_md_path: 输出Markdown文件路径
            image_dir: 图片存储目录
            image_url_prefix: 图片URL前缀
            image_rename_mode: 图片重命名模式
            image_file_prefix: 图片文件前缀
            yuque_cdn_domain: 语雀CDN域名
        """
        output_content = []
        image_tasks = []
        idx = 0

        # 解析文件，收集图片URL
        with open(origin_md_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f.readlines():
                line = re.sub(r'png#(.*)+', 'png)', line)
                image_urls = re.findall(r'https?://[^\s<>"\)\]]+\.(?:png|jpeg|jpg)', line, re.IGNORECASE)

                if image_urls:
                    for image_url in image_urls:
                        image_url = image_url.rstrip('.,;:!?')
                        parsed_path = urlparse(image_url).path
                        suffix = os.path.splitext(parsed_path)[1].lower()
                        if suffix not in {".png", ".jpeg", ".jpg"}:
                            suffix = ".png"

                        # 添加到下载任务列表
                        image_tasks.append((image_url, image_dir, image_rename_mode, idx, suffix, image_file_prefix))

                        # 更新文件内容中的图片URL
                        to_replace = '/'.join(image_url.split('/')[:-1])
                        new_image_url = image_url.replace(to_replace, 'placeholder')
                        if image_rename_mode == 'asc':
                            new_image_url = image_url_prefix + image_file_prefix + str(idx) + suffix
                        else:
                            new_image_url = new_image_url.replace('placeholder/', image_url_prefix)

                        line = line.replace(image_url, new_image_url)
                        idx += 1

                output_content.append(line)

        # 设置总数
        self.total_count = len(image_tasks)
        self.downloaded_count = 0

        if self.total_count > 0:
            Log.info(f'开始下载 {self.total_count} 张图片，使用 {self.max_workers} 个线程')

            # 多线程下载图片
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = []
                for task in image_tasks:
                    future = executor.submit(self.download_image, *task)
                    futures.append(future)

                # 等待所有下载完成
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        Log.error(f'下载任务异常: {str(e)}')

        # 写入处理后的Markdown文件
        with open(output_md_path, 'w', encoding='utf-8', errors='ignore') as f:
            for _output_content in output_content:
                f.write(str(_output_content))

        # 只有当原文件和输出文件不同时才删除原文件
        if origin_md_path != output_md_path:
            os.remove(origin_md_path)
            Log.info(f'删除原文件: {origin_md_path}')
        else:
            Log.info(f'原文件已更新: {origin_md_path}')

        return self.total_count

    def mkdir(self, image_dir):
        """创建目录
        
        Args:
            image_dir: 目录路径
        """
        image_dir = image_dir.strip().rstrip("\\")
        if os.path.exists(image_dir):
            Log.info(f'图片存储目录 {image_dir} 已存在')
        else:
            os.makedirs(image_dir)
            Log.info(f'图片存储目录 {image_dir} 创建成功')

    def process_single_file(self, md_file_path, image_url_prefix='', image_rename_mode='asc',
                            image_file_prefix='image-', yuque_cdn_domain='cdn.nlark.com'):
        """处理单个Markdown文件，下载图片到本地
        
        Args:
            md_file_path: Markdown文件路径
            image_url_prefix: 文档图片前缀，默认为空
            image_rename_mode: 图片重命名模式，默认为'asc'
            image_file_prefix: 图片文件前缀，默认为'image-'
            yuque_cdn_domain: 语雀CDN域名，默认为'cdn.nlark.com'
        """
        if not md_file_path.endswith('.md'):
            Log.info(f'文件 {md_file_path} 不是Markdown文件，跳过处理')
            return 0

        filename = os.path.basename(md_file_path)
        parent_dir = os.path.dirname(md_file_path)

        # 先解析文件，检查是否有图片URL
        has_images = False
        try:
            with open(md_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f.readlines():
                    line = re.sub(r'png#(.*)+', 'png)', line)
                    image_urls = re.findall(r'https?://[^\s<>"\)\]]+\.(?:png|jpeg|jpg)', line, re.IGNORECASE)
                    if image_urls:
                        has_images = True
                        break
        except Exception as e:
            Log.error(f'读取文件失败: {md_file_path}, 错误: {str(e)}')
            return 0

        if not has_images:
            Log.info(f'文档 {filename} 不包含图片，跳过处理')
            return 0

        # 检查文件是否已经在同名目录中
        folder_name = os.path.splitext(filename)[0]
        parent_folder_name = os.path.basename(parent_dir)

        # 如果文件已经在同名目录中，直接使用当前目录作为图片存储目录
        if parent_folder_name == folder_name:
            image_dir = parent_dir
            output_md_path = md_file_path  # 直接覆盖原文件
            Log.info(f'文件已在同名目录中，直接在当前目录处理: {parent_dir}')
        else:
            # 否则创建新的图片存储文件夹
            image_dir = os.path.join(parent_dir, folder_name)
            self.mkdir(image_dir)
            output_md_path = os.path.join(image_dir, filename)
            Log.info(f'创建新的图片存储目录: {image_dir}')

        cnt = self.deal_yuque(origin_md_path=md_file_path,
                              output_md_path=output_md_path,
                              image_dir=image_dir,
                              image_url_prefix=image_url_prefix,
                              image_rename_mode=image_rename_mode,
                              image_file_prefix=image_file_prefix,
                              yuque_cdn_domain=yuque_cdn_domain)

        Log.info(f'{filename} 处理完成，共 {cnt} 张图片')
        return cnt

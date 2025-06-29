import os
import re

import requests

from .log import Log

# 默认配置，可以通过参数覆盖
DEFAULT_YUQUE_CDN_DOMAIN = 'cdn.nlark.com'
DEFAULT_IMAGE_FILE_PREFIX = 'image-'


# 处理单个Markdown文件
def deal_yuque(origin_md_path, output_md_path, image_dir, image_url_prefix, image_rename_mode,
               image_file_prefix=DEFAULT_IMAGE_FILE_PREFIX):
    output_content = []
    idx = 0
    with open(origin_md_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f.readlines():
            line = re.sub(r'png#(.*)+', 'png)', line)
            image_url = str(
                re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*$$,]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', line))
            if ('https://' in image_url) and ('.png' in image_url or '.jpeg' in image_url):
                image_url = image_url.replace('(', '').replace(')', '').replace('[', '').replace(']', '').replace("'",
                                                                                                                  '')
                if '.png' in image_url:
                    suffix = '.png'
                elif '.jpeg' in image_url:
                    suffix = '.jpeg'
                download_image(image_url, image_dir, image_rename_mode, idx, suffix, image_file_prefix)
                to_replace = '/'.join(image_url.split('/')[:-1])
                new_image_url = image_url.replace(to_replace, 'placeholder')
                if image_rename_mode == 'asc':
                    new_image_url = image_url_prefix + image_file_prefix + str(idx) + suffix
                else:
                    new_image_url = new_image_url.replace('placeholder/', image_url_prefix)
                idx += 1
                line = line.replace(image_url, new_image_url)
            output_content.append(line)
    with open(output_md_path, 'w', encoding='utf-8', errors='ignore') as f:
        for _output_content in output_content:
            f.write(str(_output_content))
    os.remove(origin_md_path)
    return idx


# 下载图片
def download_image(image_url, image_dir, image_name_mode, idx, suffix, image_file_prefix=DEFAULT_IMAGE_FILE_PREFIX):
    r = requests.get(image_url, stream=True)
    image_name = image_url.split('/')[-1]
    if image_name_mode == 'asc':
        image_name = image_file_prefix + str(idx) + suffix
    if r.status_code == 200:
        open(os.path.join(image_dir, image_name), 'wb').write(r.content)
    del r


# 创建目录
def mkdir(image_dir):
    image_dir = image_dir.strip().rstrip("\\")
    if os.path.exists(image_dir):
        Log.info(f'图片存储目录 {image_dir} 已存在')
    else:
        os.makedirs(image_dir)
        Log.info(f'图片存储目录 {image_dir} 创建成功')


# 处理单个Markdown文件
def process_single_file(md_file_path, image_url_prefix='', image_rename_mode='asc',
                        image_file_prefix=DEFAULT_IMAGE_FILE_PREFIX, yuque_cdn_domain=DEFAULT_YUQUE_CDN_DOMAIN):
    """处理单个Markdown文件，下载图片到本地
    
    Args:
        md_file_path: Markdown文件路径
        image_url_prefix: 文档图片前缀，默认为空
        image_rename_mode: 图片重命名模式，默认为'asc'
        image_file_prefix: 图片文件前缀，默认为'image-'
        yuque_cdn_domain: 语雀CDN域名，默认为'cdn.nlark.com'
    
    Returns:
        int: 下载的图片数量
    """
    if not md_file_path.endswith('.md'):
        Log.info(f'文件 {md_file_path} 不是Markdown文件，跳过处理')
        return 0

    filename = os.path.basename(md_file_path)
    parent_dir = os.path.dirname(md_file_path)

    # 根据文件名创建对应的图片存储文件夹
    folder_name = os.path.splitext(filename)[0]
    image_dir = os.path.join(parent_dir, folder_name)
    mkdir(image_dir)

    # 将输出的Markdown文件放在对应的图片文件夹中
    output_md_path = os.path.join(image_dir, filename)

    cnt = deal_yuque(md_file_path, output_md_path, image_dir, image_url_prefix, image_rename_mode, image_file_prefix)
    Log.info(f'{filename} 处理完成，共 {cnt} 张图片')
    return cnt

'''
Author: Be1k0
URL: https://github.com/Be1k0/YuQue-BdT
'''

import html
import json
import mimetypes
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import unquote, urlparse

import requests

from .constants import GLOBAL_CONFIG
from .file import File
from .log import Log

BASE_URL = "https://www.yuque.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.0.0 Safari/537.36"
)

MARKDOWN_LINK_RE = re.compile(r"(!?)\[([^\]]*)\]\((https?://[^)\s]+)\)")
WINDOWS_BAD_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
SUPPORTED_CARD_TYPES = {"video", "audio"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}


@dataclass
class DocInfo:
    doc_id: int
    slug: str
    book_id: int
    namespace: str

    @property
    def page_url(self) -> str:
        if self.namespace and self.slug:
            return f"{BASE_URL}/{self.namespace}/{self.slug}"
        return BASE_URL


@dataclass
class CardInfo:
    name: str
    attrs: Dict[str, str]
    payload: Dict[str, Any]

    @property
    def card_id(self) -> str:
        return str(self.payload.get("id") or self.attrs.get("id") or "")


@dataclass
class LocalizeStats:
    source_md_path: str
    output_md_path: str
    direct_count: int = 0
    card_count: int = 0
    unsupported_count: int = 0
    failed_count: int = 0
    login_required_count: int = 0
    total_candidates: int = 0
    processed_candidates: int = 0

    @property
    def localized_count(self) -> int:
        return self.direct_count + self.card_count


class CardHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.cards: list[dict[str, str]] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "card":
            self.cards.append({key: value or "" for key, value in attrs})


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        Log.warn(f"读取 JSON 失败: {path} -> {exc}")
        return {}


def sanitize_filename(name: str, fallback: str = "file") -> str:
    name = unquote(name or "").split("?", 1)[0].split("#", 1)[0]
    name = Path(name).name
    name = WINDOWS_BAD_CHARS_RE.sub("_", name)
    name = re.sub(r"\s+", "_", name).strip(" ._")
    if not name:
        name = fallback

    reserved = {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
    stem = Path(name).stem.upper()
    if stem in reserved:
        name = f"{name}_"
    return name


def infer_filename_from_url(url: str, fallback: str = "file.bin") -> str:
    parsed = urlparse(url)
    name = Path(unquote(parsed.path)).name
    return sanitize_filename(name or fallback, fallback=fallback)


def ensure_extension(filename: str, url: str, content_type: str = "") -> str:
    if Path(filename).suffix:
        return filename

    url_suffix = Path(unquote(urlparse(url).path)).suffix
    if url_suffix:
        return f"{filename}{url_suffix}"

    guessed = ""
    if content_type:
        mime = content_type.split(";", 1)[0].strip()
        guessed = mimetypes.guess_extension(mime) or ""
    return f"{filename}{guessed or '.bin'}"


def normalize_url(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return url


def guess_mime_type(path: Path, fallback: str = "application/octet-stream") -> str:
    return mimetypes.guess_type(path.name)[0] or fallback


def render_video_html(local_link: str, display_name: str, local_path: Path) -> str:
    escaped_src = html.escape(local_link, quote=True)
    escaped_name = html.escape(display_name)
    escaped_type = html.escape(guess_mime_type(local_path, fallback="video/mp4"), quote=True)
    return (
        f'<video controls preload="metadata" style="max-width: 100%; height: auto;">\n'
        f'  <source src="{escaped_src}" type="{escaped_type}">\n'
        f'  <a href="{escaped_src}">{escaped_name}</a>\n'
        f'</video>'
    )


def parse_card_payload(value: str) -> Dict[str, Any]:
    if not value:
        return {}

    raw = html.unescape(value.strip())
    if raw.startswith("data:"):
        raw = raw[5:]

    # 语雀卡片的 value 可能同时混入 HTML 转义和 URL 编码。
    candidates = [raw, unquote(raw)]
    for candidate in candidates:
        candidate = candidate.strip()
        if candidate.startswith("data:"):
            candidate = candidate[5:]
        try:
            data = json.loads(candidate)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            continue
    return {}


def extract_cards(content: str) -> Dict[str, CardInfo]:
    parser = CardHTMLParser()
    parser.feed(content or "")

    cards: Dict[str, CardInfo] = {}
    for attrs in parser.cards:
        payload = parse_card_payload(attrs.get("value", ""))
        card = CardInfo(name=attrs.get("name", ""), attrs=attrs, payload=payload)
        if card.card_id:
            cards[card.card_id] = card
    return cards


class MarkdownAssetLocalizer:
    def __init__(
        self,
        cookie_string: str = "",
        max_workers: int = 5,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        image_rename_mode: str = "asc",
        image_file_prefix: str = "image-",
        yuque_cdn_domain: str = "cdn.nlark.com",
    ):
        self.cookie_string = cookie_string.strip()
        self.max_workers = max(1, int(max_workers))
        self.progress_callback = progress_callback
        self.image_rename_mode = image_rename_mode
        self.image_file_prefix = image_file_prefix or "image-"
        self.yuque_cdn_domain = (yuque_cdn_domain or "cdn.nlark.com").strip().lower()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.doc_cache: Dict[int, Dict[str, CardInfo]] = {}
        self.url_to_local_path: Dict[str, Path] = {}
        self.reserved_paths: set[Path] = set()
        self.current_doc_info: Optional[DocInfo] = None
        self.output_md_path: Optional[Path] = None
        self.asset_dir: Optional[Path] = None
        self.stats: Optional[LocalizeStats] = None
        self.has_login_cookie = False
        self.image_index = 0

    def process_single_file(
        self,
        md_file_path: str,
        current_doc_meta: Optional[Dict[str, Any]] = None,
        has_login_cookie: bool = False,
    ) -> LocalizeStats:
        source_path = Path(md_file_path)
        self.stats = LocalizeStats(
            source_md_path=str(source_path),
            output_md_path=str(source_path),
        )
        self.has_login_cookie = has_login_cookie
        self.current_doc_info = self._build_doc_info(current_doc_meta)
        self.url_to_local_path = {}
        self.reserved_paths = set()
        self.image_index = 0

        if source_path.suffix.lower() != ".md":
            Log.info(f"文件 {source_path.name} 不是 Markdown，跳过资源离线化")
            return self.stats

        if not source_path.exists():
            Log.warn(f"找不到 Markdown 文件: {source_path}")
            return self.stats

        markdown = source_path.read_text(encoding="utf-8", errors="ignore")
        candidate_count = self._count_candidates(markdown)
        self.stats.total_candidates = candidate_count
        if candidate_count == 0:
            Log.info(f"文档 {source_path.name} 不包含可离线的文件链接")
            return self.stats

        self.output_md_path, self.asset_dir = self._resolve_output_paths(source_path)
        self.stats.output_md_path = str(self.output_md_path)
        Log.info(
            f"开始离线化文档资源: {source_path.name}，候选链接 {candidate_count} 个，"
            f"输出目录 {self.asset_dir}"
        )

        replaced = MARKDOWN_LINK_RE.sub(self.replace_one_link, markdown)
        File().write(str(self.output_md_path), replaced)

        if self.output_md_path != source_path and source_path.exists():
            source_path.unlink()

        Log.info(
            "文档资源离线化完成: "
            f"{self.output_md_path.name}，"
            f"直接资源 {self.stats.direct_count} 个，"
            f"卡片媒体 {self.stats.card_count} 个，"
            f"需登录 {self.stats.login_required_count} 个，"
            f"暂不支持 {self.stats.unsupported_count} 个，"
            f"失败 {self.stats.failed_count} 个"
        )
        return self.stats

    def _build_doc_info(self, doc_meta: Optional[Dict[str, Any]]) -> Optional[DocInfo]:
        if not doc_meta:
            return None

        doc_id = self._safe_int(doc_meta.get("doc_id") or doc_meta.get("id"))
        book_id = self._safe_int(doc_meta.get("book_id"))
        slug = str(
            doc_meta.get("doc_url")
            or doc_meta.get("url")
            or doc_meta.get("slug")
            or ""
        ).strip()
        namespace = str(doc_meta.get("namespace") or "").strip()

        if not doc_id or not book_id or not slug or not namespace:
            return None

        return DocInfo(
            doc_id=doc_id,
            slug=slug,
            book_id=book_id,
            namespace=namespace,
        )

    def _safe_int(self, value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _count_candidates(self, markdown: str) -> int:
        count = 0
        for match in MARKDOWN_LINK_RE.finditer(markdown):
            _, _, url = match.groups()
            if self.is_direct_asset_url(url) or get_card_doc_id(url) is not None:
                count += 1
        return count

    def _resolve_output_paths(self, source_path: Path) -> Tuple[Path, Path]:
        parent_dir = source_path.parent
        folder_name = source_path.stem
        # 已经是“同名目录 + Markdown”结构时，直接复用现有目录。
        if parent_dir.name == folder_name:
            return source_path, parent_dir

        asset_dir = parent_dir / folder_name
        asset_dir.mkdir(parents=True, exist_ok=True)
        return asset_dir / source_path.name, asset_dir

    def api_headers(self, referer: str) -> Dict[str, str]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": referer,
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": USER_AGENT,
        }
        if self.cookie_string:
            headers["Cookie"] = self.cookie_string
        return headers

    def download_headers(self, url: str, referer: str) -> Dict[str, str]:
        headers = {
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": referer,
            "User-Agent": USER_AGENT,
        }
        if self.cookie_string and urlparse(url).netloc.lower().endswith("yuque.com"):
            headers["Cookie"] = self.cookie_string
        return headers

    def is_direct_asset_url(self, url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        path = parsed.path.lower()
        return (
            (host.endswith("yuque.com") and "/attachments/" in path)
            or (host == "cdn.nlark.com" and path.startswith("/yuque/"))
            or (self.yuque_cdn_domain and host == self.yuque_cdn_domain and path.startswith("/yuque/"))
        )

    def is_image_asset(self, url: str, label: str, bang: str) -> bool:
        if bang == "!":
            return True

        suffix = Path(unquote(urlparse(url).path)).suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            return True

        label_suffix = Path(label or "").suffix.lower()
        return label_suffix in IMAGE_EXTENSIONS

    def build_filename_hint(self, url: str, label: str, bang: str) -> str:
        if self.is_image_asset(url, label, bang) and self.image_rename_mode == "asc":
            self.image_index += 1
            return f"{self.image_file_prefix}{self.image_index}"

        return label or infer_filename_from_url(url)

    def resolve_doc_info(self, doc_id: int) -> DocInfo:
        if self.current_doc_info and self.current_doc_info.doc_id == doc_id:
            return self.current_doc_info

        books_by_namespace = self.load_books_by_namespace()
        cache_dir = Path(GLOBAL_CONFIG.meta_dir) / "Article_list_caching"
        for cache_file in cache_dir.glob("*.json"):
            docs_data = load_json(cache_file)
            namespace = self.infer_namespace(cache_file, books_by_namespace)
            book_id = books_by_namespace.get(namespace, 0)
            for doc in docs_data.get("docs", []):
                current_id = self._safe_int(doc.get("id"))
                if current_id != doc_id:
                    continue

                resolved_book_id = self._safe_int(doc.get("book_id")) or book_id
                slug = str(doc.get("url") or doc.get("slug") or "").strip()
                if resolved_book_id and slug and namespace:
                    return DocInfo(
                        doc_id=doc_id,
                        slug=slug,
                        book_id=resolved_book_id,
                        namespace=namespace,
                    )

        raise RuntimeError(f"无法定位 docs/{doc_id} 对应的文档信息")

    def load_books_by_namespace(self) -> Dict[str, int]:
        books_data = load_json(Path(GLOBAL_CONFIG.books_info_file))
        result: Dict[str, int] = {}
        for book in books_data.get("books_info", []):
            namespace = str(book.get("namespace") or "").strip()
            book_id = self._safe_int(book.get("id"))
            if namespace and book_id:
                result[namespace] = book_id
        return result

    def infer_namespace(self, cache_file: Path, books_by_namespace: Dict[str, int]) -> str:
        key = cache_file.stem
        if key.startswith("docs_"):
            key = key[5:]

        for namespace in books_by_namespace:
            if key == namespace.replace("/", "_"):
                return namespace

        if "_" in key:
            user, repo = key.split("_", 1)
            return f"{user}/{repo}"
        return ""

    def get_doc_cards(self, doc_id: int) -> Dict[str, CardInfo]:
        if doc_id in self.doc_cache:
            return self.doc_cache[doc_id]

        doc_info = self.resolve_doc_info(doc_id)
        url = f"{BASE_URL}/api/docs/{doc_info.slug}"
        params = {
            "merge_dynamic_data": "false",
            "book_id": str(doc_info.book_id),
        }
        Log.info(
            f"请求文档卡片信息: {url}?merge_dynamic_data=false&book_id={doc_info.book_id}"
        )
        response = self.session.get(
            url,
            params=params,
            headers=self.api_headers(doc_info.page_url),
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        content = data.get("data", {}).get("content", "")
        cards = extract_cards(content)
        self.doc_cache[doc_id] = cards
        Log.info(f"文档 docs/{doc_id} 解析到卡片 {len(cards)} 个")
        return cards

    def download_url(self, url: str, filename_hint: str, referer: str) -> Path:
        url = normalize_url(url)
        if url in self.url_to_local_path:
            return self.url_to_local_path[url]

        if not self.asset_dir:
            raise RuntimeError("附件输出目录未初始化")

        filename = sanitize_filename(filename_hint or infer_filename_from_url(url), fallback="asset")
        with self.session.get(
            url,
            headers=self.download_headers(url, referer),
            stream=True,
            timeout=60,
        ) as response:
            response.raise_for_status()
            filename = ensure_extension(filename, url, response.headers.get("Content-Type", ""))
            target = self.pick_target_path(filename)
            with target.open("wb") as file:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        file.write(chunk)

        self.url_to_local_path[url] = target
        Log.info(f"资源下载完成: {target.name}")
        return target

    def pick_target_path(self, filename: str) -> Path:
        if not self.asset_dir:
            raise RuntimeError("附件输出目录未初始化")

        candidate = self.asset_dir / sanitize_filename(filename)
        # 用内存占位，避免同一轮处理中出现重名覆盖。
        if candidate not in self.reserved_paths:
            self.reserved_paths.add(candidate)
            return candidate

        stem = candidate.stem
        suffix = candidate.suffix
        index = 1
        while True:
            next_candidate = self.asset_dir / f"{stem}_{index}{suffix}"
            if next_candidate not in self.reserved_paths:
                self.reserved_paths.add(next_candidate)
                return next_candidate
            index += 1

    def resolve_media_download_url(self, card: CardInfo, doc_info: DocInfo) -> Tuple[str, str]:
        media_id = card.payload.get("videoId") or card.payload.get("audioId")
        if not media_id:
            raise RuntimeError(f"{card.name} card 中没有 videoId/audioId")

        response = self.session.get(
            f"{BASE_URL}/api/video",
            params={"video_id": media_id},
            headers=self.api_headers(doc_info.page_url),
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        info = data.get("data", {}).get("info", {})
        download_url = (
            info.get("origin")
            or info.get("video")
            or info.get("url")
            or info.get("download_url")
        )
        if not download_url:
            raise RuntimeError(f"api/video 未返回可下载链接: {media_id}")

        filename = (
            card.payload.get("name")
            or card.payload.get("fileName")
            or infer_filename_from_url(media_id)
        )
        filename = ensure_extension(filename, media_id)
        return normalize_url(download_url), filename

    def to_markdown_path(self, path: Path) -> str:
        if not self.output_md_path:
            return path.name
        return path.relative_to(self.output_md_path.parent).as_posix()

    def replace_one_link(self, match: re.Match[str]) -> str:
        if not self.stats:
            return match.group(0)

        bang, label, url = match.groups()
        original = match.group(0)

        if not self.is_direct_asset_url(url) and get_card_doc_id(url) is None:
            return original

        try:
            if self.is_direct_asset_url(url):
                # 公开知识库里的非图片附件通常需要登录 Cookie 才能下载。
                if not self.has_login_cookie and self._is_login_required_direct_asset(url, label, bang):
                    self.stats.login_required_count += 1
                    return f"{original} <!-- 需要登录后才能离线保存该文件 -->"

                filename_hint = self.build_filename_hint(url, label, bang)
                referer = self.current_doc_info.page_url if self.current_doc_info else BASE_URL
                target = self.download_url(url, filename_hint, referer=referer)
                local_link = self.to_markdown_path(target)
                self.stats.direct_count += 1
                return f"{bang}[{label}]({local_link})"

            doc_id = get_card_doc_id(url)
            if doc_id is None:
                return original

            anchor = extract_card_anchor(url)
            doc_info = self.resolve_doc_info(doc_id)
            card = self.get_doc_cards(doc_id).get(anchor)
            if not card:
                self.stats.failed_count += 1
                return f"{original} <!-- 未找到对应语雀卡片: #{anchor} -->"

            if card.name not in SUPPORTED_CARD_TYPES:
                self.stats.unsupported_count += 1
                return f"{original} <!-- 暂时不支持下载该类型的文件: {card.name} #{anchor} -->"

            if not self.has_login_cookie:
                self.stats.login_required_count += 1
                return f"{original} <!-- 需要登录后才能离线保存该文件: {card.name} #{anchor} -->"

            download_url, filename = self.resolve_media_download_url(card, doc_info)
            target = self.download_url(download_url, filename, referer=doc_info.page_url)
            local_link = self.to_markdown_path(target)
            display_name = card.payload.get("name") or card.payload.get("fileName") or target.name
            self.stats.card_count += 1
            if card.name == "video":
                return render_video_html(local_link, str(display_name), target)
            return f"[{display_name}]({local_link})"
        except Exception as exc:
            self.stats.failed_count += 1
            return f"{original} <!-- 下载失败: {exc} -->"
        finally:
            self._mark_processed()

    def _is_login_required_direct_asset(self, url: str, label: str, bang: str) -> bool:
        host = urlparse(url).netloc.lower()
        return host.endswith("yuque.com") and not self.is_image_asset(url, label, bang)

    def _mark_processed(self) -> None:
        if not self.stats:
            return

        # 不论成功还是失败都推进进度，避免界面卡在半途。
        self.stats.processed_candidates += 1
        if self.progress_callback:
            self.progress_callback(
                self.stats.processed_candidates,
                self.stats.total_candidates,
            )


def get_card_doc_id(url: str) -> Optional[int]:
    parsed = urlparse(url)
    if not parsed.fragment:
        return None

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) == 2 and path_parts[0] == "docs" and path_parts[1].isdigit():
        return int(path_parts[1])
    return None


def extract_card_anchor(url: str) -> str:
    return unquote(urlparse(url).fragment or "")

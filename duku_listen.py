import json
import os
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import html2text
import requests

from duku_http_client import http_client


READING_PAGE_URL = "https://service.duku.cn/api/v1/duku/reading/page/get"
BOOK_PAGE_URL = "https://service.duku.cn/api/v1/duku/reading/bookPageBySecondCategoryInfo"
VOD_PLAY_INFO_URL = "https://playvideo.qcloud.com/getplayinfo/v2/1329148710/{file_id}"
PAGE_SIZE = 20


class _MediaSourceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = {"audio": [], "video": []}
        self.media_tag = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self.sources:
            self.media_tag = tag
            if attrs.get("src"):
                self.sources[tag].append(attrs["src"])
        elif tag == "source" and self.media_tag and attrs.get("src"):
            self.sources[self.media_tag].append(attrs["src"])

    def handle_endtag(self, tag):
        if tag == self.media_tag:
            self.media_tag = None


def _response_data(response):
    if not isinstance(response, str):
        raise RuntimeError(f"读库接口请求失败，HTTP 状态码：{response}")

    payload = json.loads(response)
    if payload.get("resultCode") != "A00000":
        raise RuntimeError(
            f"读库接口返回失败：{payload.get('resultCode')} {payload.get('resultMsg', '')}".strip()
        )
    return payload["data"]


def get_listen_page(client=http_client):
    response = client.get(READING_PAGE_URL, {"pageCode": "LISTEN"})
    return _response_data(response)


def get_listen_items(second_category_id, client=http_client):
    items = []
    current_page = 1

    while True:
        response = client.get(
            BOOK_PAGE_URL,
            {
                "secondCategoryId": second_category_id,
                "currentPage": current_page,
                "pageSize": PAGE_SIZE,
            },
        )
        data = _response_data(response)
        page_items = data.get("list") or []
        items.extend(page_items)

        total_page = data.get("totalPage")
        if total_page is not None:
            if current_page >= total_page:
                break
        elif not page_items or len(items) >= data.get("total", len(items)):
            break

        current_page += 1

    return items


def get_video_play_info(file_id, request_get=requests.get):
    response = request_get(VOD_PLAY_INFO_URL.format(file_id=file_id), timeout=30)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(
            f"腾讯云视频地址解析失败：{payload.get('code')} {payload.get('message', '')}".strip()
        )
    return payload["videoInfo"]


def choose_video_variant(video_info):
    transcodes = [
        item
        for item in video_info.get("transcodeList") or []
        if item.get("url") and (item.get("width") or 0) > 0 and (item.get("height") or 0) > 0
    ]
    if transcodes:
        return max(
            transcodes,
            key=lambda item: (
                (item.get("width") or 0) * (item.get("height") or 0),
                item.get("bitrate") or 0,
                item.get("size") or 0,
            ),
        )

    source = video_info.get("sourceVideo") or {}
    if source.get("url"):
        return source
    raise RuntimeError("腾讯云播放信息中没有可下载的视频地址")


def resolve_video_url(file_id, request_get=requests.get):
    return choose_video_variant(get_video_play_info(file_id, request_get=request_get))["url"]


def extract_html_media(article_detail, media_type):
    if not article_detail:
        return None
    parser = _MediaSourceParser()
    parser.feed(article_detail)
    sources = parser.sources.get(media_type) or []
    return sources[0] if sources else None


def get_item_media_url(item, request_get=requests.get):
    content_type = item.get("contentType")
    file_link = str(item.get("fileLink") or "").strip()

    if content_type == 2:
        if file_link.startswith(("http://", "https://")):
            return "video", file_link
        if file_link:
            return "video", resolve_video_url(file_link, request_get=request_get)
        return "video", extract_html_media(item.get("articleDetail"), "video")

    if content_type == 3:
        if file_link.startswith(("http://", "https://")):
            return "audio", file_link
        return "audio", extract_html_media(item.get("articleDetail"), "audio")

    return None, None


def _safe_name(value, max_length=120):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", str(value)).strip(" .")
    return (name or "untitled")[:max_length]


def _media_suffix(url, media_type):
    suffix = Path(urlparse(url).path).suffix.lower()
    allowed = {"audio": {".mp3", ".m4a", ".aac", ".wav"}, "video": {".mp4", ".m3u8", ".mov"}}
    if suffix in allowed[media_type]:
        return suffix
    return ".mp3" if media_type == "audio" else ".mp4"


def _save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _content_type_name(content_type):
    return {
        1: "电子书",
        2: "视频",
        3: "音频",
        4: "文章",
    }.get(content_type, f"未知类型（{content_type}）")


def _duration_text(duration):
    if duration in (None, ""):
        return None
    seconds = int(duration)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _item_book_id(item):
    return str(item.get("bookIdStr") or item.get("bookId") or "unknown")


def _item_directory_name(index, item):
    return f"{index:03d}-{_safe_name(item.get('title'))}-{_item_book_id(item)}"


def build_item_introduction(category, item):
    title = item.get("title") or "未命名项目"
    authors = "、".join(
        author.get("userName", "")
        for author in item.get("authorInfo") or []
        if author.get("userName")
    )
    lines = [f"# {title}", ""]
    fields = [
        ("栏目", category.get("secondCategoryName")),
        ("栏目 ID", category.get("secondCategoryId")),
        ("项目 ID", _item_book_id(item)),
        ("类型", _content_type_name(item.get("contentType"))),
        ("作者", authors or None),
        ("时长", _duration_text(item.get("contentDuration"))),
        ("发布时间", item.get("firstPublishTime")),
        ("摘要", item.get("summary")),
    ]
    for label, value in fields:
        if value not in (None, ""):
            lines.append(f"- **{label}**：{value}")

    cover_image = item.get("coverImage") or item.get("shareImage")
    if cover_image:
        lines.extend(["", f"![{title}]({cover_image})"])

    article_detail = item.get("articleDetail")
    if article_detail:
        introduction = html2text.html2text(article_detail).strip()
        if introduction:
            lines.extend(["", "## 介绍", "", introduction])
    elif item.get("summary"):
        lines.extend(["", "## 介绍", "", str(item["summary"])])

    return "\n".join(lines)


def build_category_introduction(category, items, item_directories):
    name = category.get("secondCategoryName") or "未命名栏目"
    lines = [f"# {name}", ""]
    fields = [
        ("栏目 ID", category.get("secondCategoryId")),
        ("项目数", len(items)),
        ("介绍", category.get("description")),
    ]
    for label, value in fields:
        if value not in (None, ""):
            lines.append(f"- **{label}**：{value}")

    if category.get("coverImage"):
        lines.extend(["", f"![{name}]({category['coverImage']})"])

    lines.extend(["", "## 项目", ""])
    for item, item_directory in zip(items, item_directories):
        title = item.get("title") or "未命名项目"
        media_type = _content_type_name(item.get("contentType"))
        lines.append(f"- [{title}]({item_directory.name}/介绍.md)（{media_type}）")
    return "\n".join(lines)


def build_category_index(category_entries):
    lines = ["# 听栏目", ""]
    for category, category_directory, item_count in category_entries:
        name = category.get("secondCategoryName") or "未命名栏目"
        lines.append(f"- [{name}]({category_directory.name}/栏目介绍.md)：{item_count} 个项目")
    return "\n".join(lines)


def _reuse_media_file(source_path, target_path):
    source_path = Path(source_path)
    target_path = Path(target_path)
    if target_path.exists() and target_path.stat().st_size > 0:
        return False

    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source_path, target_path)
    except OSError:
        shutil.copy2(source_path, target_path)
    return True


def select_listen_categories(categories, selectors=None):
    if not selectors:
        return categories

    selected = []
    selected_ids = set()
    for selector in selectors:
        value = str(selector).strip()
        match = None

        if value.isdigit():
            number = int(value)
            if 1 <= number <= len(categories):
                match = categories[number - 1]
            else:
                match = next(
                    (item for item in categories if str(item.get("secondCategoryId")) == value),
                    None,
                )
        else:
            exact_matches = [
                item for item in categories if str(item.get("secondCategoryName", "")).casefold() == value.casefold()
            ]
            if len(exact_matches) == 1:
                match = exact_matches[0]
            else:
                partial_matches = [
                    item for item in categories if value.casefold() in str(item.get("secondCategoryName", "")).casefold()
                ]
                if len(partial_matches) == 1:
                    match = partial_matches[0]

        if match is None:
            choices = "，".join(
                f"{index}:{item['secondCategoryName']}({item['secondCategoryId']})"
                for index, item in enumerate(categories, start=1)
            )
            raise ValueError(f"没有找到听栏目：{value}。可选栏目：{choices}")

        category_id = match["secondCategoryId"]
        if category_id not in selected_ids:
            selected.append(match)
            selected_ids.add(category_id)

    return selected


def download_media_file(url, output_path, request_get=requests.get):
    output_path = Path(output_path)
    if output_path.exists() and output_path.stat().st_size > 0:
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".part")
    try:
        with request_get(url, stream=True, timeout=(10, 120)) as response:
            response.raise_for_status()
            total_size = int(response.headers.get("Content-Length") or 0)
            downloaded_size = 0
            next_report = 64 * 1024 * 1024
            with temp_path.open("wb") as output:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        output.write(chunk)
                        downloaded_size += len(chunk)
                        if downloaded_size >= next_report:
                            if total_size:
                                percent = downloaded_size * 100 / total_size
                                print(f"  已下载 {downloaded_size / 1024 / 1024:.0f} MB ({percent:.1f}%)")
                            else:
                                print(f"  已下载 {downloaded_size / 1024 / 1024:.0f} MB")
                            next_report += 64 * 1024 * 1024
        os.replace(temp_path, output_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return True


def download_listen(
    output_dir="听",
    download_audio=True,
    download_video=True,
    client=http_client,
    request_get=requests.get,
    media_downloader=download_media_file,
    category_selectors=None,
):
    output_dir = Path(output_dir)
    metadata_dir = output_dir / "metadata"
    details_dir = metadata_dir / "details"

    listen_page = get_listen_page(client)
    _save_json(metadata_dir / "list.json", listen_page)

    all_categories = listen_page.get("showBookCategorySecondList") or []
    categories = select_listen_categories(all_categories, category_selectors)
    unique_item_ids = set()
    total_items = 0
    media_index = []
    category_entries = []
    media_sources = {}
    resolved_media = {}
    downloaded = 0
    reused = 0
    skipped = 0
    failed = 0

    for category_index, category in enumerate(categories, start=1):
        category_id = category["secondCategoryId"]
        category_name = category["secondCategoryName"]
        category_directory = output_dir / _safe_name(category_name)
        print(f"拉取听栏目 {category_index}/{len(categories)}：{category_name}")
        items = get_listen_items(category_id, client)
        total_items += len(items)
        detail = {
            "secondCategoryId": category_id,
            "secondCategoryName": category_name,
            "total": len(items),
            "list": items,
        }
        detail_name = f"{category_id}-{_safe_name(category_name)}.json"
        _save_json(details_dir / detail_name, detail)

        item_directories = []
        for item_index, item in enumerate(items, start=1):
            book_id = _item_book_id(item)
            unique_item_ids.add(book_id)
            item_directory = category_directory / _item_directory_name(item_index, item)
            item_directories.append(item_directory)
            introduction_path = item_directory / "介绍.md"
            _save_text(introduction_path, build_item_introduction(category, item))

            content_type = item.get("contentType")
            if content_type not in (2, 3):
                continue

            media_type = "video" if content_type == 2 else "audio"
            enabled = download_video if media_type == "video" else download_audio
            record = {
                "bookId": book_id,
                "title": item.get("title"),
                "contentType": content_type,
                "categoryId": category_id,
                "categoryName": category_name,
                "introductionPath": str(introduction_path),
                "status": "disabled" if not enabled else "pending",
            }

            if not enabled:
                media_index.append(record)
                continue

            print(f"处理媒体 {category_name} {item_index}/{len(items)}：{item.get('title')}")
            try:
                cache_key = (book_id, content_type)
                if cache_key not in resolved_media:
                    resolved_media[cache_key] = get_item_media_url(item, request_get=request_get)
                resolved_type, media_url = resolved_media[cache_key]
                if not media_url:
                    record["status"] = "missing"
                    failed += 1
                    media_index.append(record)
                    continue

                suffix = _media_suffix(media_url, resolved_type)
                if suffix == ".m3u8":
                    suffix = ".mp4"
                filename = f"{_safe_name(item.get('title'))}{suffix}"
                output_path = item_directory / filename
                record.update({"url": media_url, "path": str(output_path), "status": "downloading"})

                source_path = media_sources.get(cache_key)
                if source_path and Path(source_path).exists():
                    was_reused = _reuse_media_file(source_path, output_path)
                    record["status"] = "reused" if was_reused else "exists"
                    reused += int(was_reused)
                    skipped += int(not was_reused)
                elif output_path.exists() and output_path.stat().st_size > 0:
                    record["status"] = "exists"
                    media_sources[cache_key] = output_path
                    skipped += 1
                else:
                    if media_url.lower().split("?", 1)[0].endswith(".m3u8"):
                        client.download_m3u8_video(media_url, str(output_path))
                        was_downloaded = True
                    else:
                        was_downloaded = media_downloader(media_url, output_path, request_get=request_get)
                    record["status"] = "downloaded" if was_downloaded else "exists"
                    downloaded += int(was_downloaded)
                    skipped += int(not was_downloaded)
                    if output_path.exists():
                        media_sources[cache_key] = output_path
            except Exception as exc:
                record["status"] = "failed"
                record["error"] = str(exc)
                failed += 1
                print(f"媒体下载失败：{item.get('title')}：{exc}")
            media_index.append(record)
            _save_json(metadata_dir / "media.json", media_index)

        _save_text(
            category_directory / "栏目介绍.md",
            build_category_introduction(category, items, item_directories),
        )
        category_entries.append((category, category_directory, len(items)))

    _save_text(output_dir / "栏目列表.md", build_category_index(category_entries))
    _save_json(metadata_dir / "media.json", media_index)
    return {
        "categories": len(categories),
        "items": total_items,
        "unique_items": len(unique_item_ids),
        "media": len(media_index),
        "downloaded": downloaded,
        "reused": reused,
        "exists": skipped,
        "failed": failed,
    }

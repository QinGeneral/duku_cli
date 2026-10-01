import json
import os
import re
import urllib

import html2text
from downloader_basement import utils

from duku_http_client import http_client


READING_PAGE_URL = "https://service.duku.cn/api/v1/duku/reading/page/get"
BOOK_PAGE_URL = "https://service.duku.cn/api/v1/duku/reading/bookPageBySecondCategoryInfo"
PAGE_SIZE = 20


def _response_data(response):
    if not isinstance(response, str):
        raise RuntimeError(f"读库接口请求失败，HTTP 状态码：{response}")

    payload = json.loads(response)
    if payload.get("resultCode") != "A00000":
        raise RuntimeError(
            f"读库接口返回失败：{payload.get('resultCode')} {payload.get('resultMsg', '')}".strip()
        )
    return payload["data"]


def get_reading_categories(client=http_client):
    response = client.get(READING_PAGE_URL, {"pageCode": "READ_MOOK_TOTAL"})
    total_years = _response_data(response).get("pageSecondCategoryFilterTabList") or []
    response = client.get(READING_PAGE_URL, {"pageCode": "READ_MOOK_LATEST"})
    latest = _response_data(response).get("categorySecondTabList") or []

    years = {}
    seen_ids = set()

    def add_category(year_name, category):
        # IDs may be encoded as either JSON numbers or strings.
        category_id = str(category["secondCategoryId"])
        if category_id not in seen_ids:
            years[year_name]["categorySecondTabList"].append(category)
            seen_ids.add(category_id)

    # Preserve the total catalogue's year grouping, metadata and order.
    for year in total_years:
        year_name = year["subTabName"]
        years.setdefault(year_name, {**year, "categorySecondTabList": []})
        for category in year.get("categorySecondTabList") or []:
            add_category(year_name, category)

    for category in latest:
        if str(category["secondCategoryId"]) in seen_ids:
            continue
        issue = category["secondCategoryName"].strip()
        if not re.fullmatch(r"[0-9]{4}", issue):
            raise RuntimeError(f"无法从最新期刊名称推断年份：{issue}")
        # MOOK issue names use YYNN, e.g. 2603 belongs in 2026/2603.
        year_name = str(2000 + int(issue[:2]))
        years.setdefault(year_name, {"subTabName": year_name, "categorySecondTabList": []})
        add_category(year_name, category)

    return list(years.values())


def get_books_by_second_category(second_category_id, client=http_client):
    books = []
    current_page = 1

    while True:
        response = client.get(
            BOOK_PAGE_URL,
            {
                "secondCategoryId": second_category_id,
                "currentPage": current_page,
                "pageSize": PAGE_SIZE,
                "categoryOrder": 1,
            },
        )
        data = _response_data(response)
        page_books = data.get("list") or []
        books.extend(page_books)

        total_page = data.get("totalPage")
        if total_page is not None:
            if current_page >= total_page:
                break
        elif not page_books or len(books) >= data.get("total", len(books)):
            break

        current_page += 1

    return books


# 下载“读”-“TabBar”
def download_read_tab(output_dir: str = "读库v2"):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    years = get_reading_categories()
    for year_info in years:
        if year_info["categorySecondTabList"] is not None:
            year_dir = os.path.join(output_dir, year_info["subTabName"])
            if not os.path.exists(year_dir):
                os.makedirs(year_dir)
            for book in year_info["categorySecondTabList"]:
                print("开始下载" + year_info["subTabName"] + "的" + book["secondCategoryName"])
                book_dir = os.path.join(year_dir, book["secondCategoryName"]).replace(" ", "")
                if not os.path.exists(book_dir):
                    os.makedirs(book_dir)
                chapter_list = get_books_by_second_category(book["secondCategoryId"])
                for item in chapter_list:
                    print("开始下载" + book["secondCategoryName"] + "的" + item["title"])
                    epub_file = os.path.join(book_dir, item["title"] + ".epub")
                    cover = os.path.join(book_dir, item["title"] + "cover.jpg")
                    if os.path.exists(epub_file):
                        print("已存在" + book["secondCategoryName"] + "的" + item["title"] + "，跳过")
                    else:
                        http_client.download_file(item["fileLink"], epub_file)
                    if item["coverImage"] is not None and item["coverImage"] != "":
                        if not os.path.exists(cover):
                            http_client.download_image(item["coverImage"], cover)

                    if item["audioBookId"] is not None and item["audioBookId"] != "":
                        print("开始下载" + book["secondCategoryName"] + "的" + item["title"] + "的音频")
                        audio_url = (
                            "http://service.duku.cn/api/v1/duku/reading/bookInfo?bookId="
                            + str(item["audioBookId"])
                            + "&needAdditionalBookInfo=true&needFavoriteStatus=true"
                        )
                        audio_info = json.loads(http_client.get(audio_url, {}))["data"]
                        title = audio_info["title"]
                        audio_file_url = audio_info["fileLink"]
                        audio_file = os.path.join(book_dir, title + ".mp3")
                        if os.path.exists(audio_file):
                            print("已存在" + book["secondCategoryName"] + "的" + item["title"] + "的音频，跳过")
                            continue

                        audio_cover_url = audio_info["coverImage"]
                        audio_cover = os.path.join(book_dir, title + "audio_cover.jpg")

                        audio_intro = audio_info["articleDetail"]
                        http_client.download_audio(audio_file_url, audio_file)
                        http_client.download_image(audio_cover_url, audio_cover)
                        utils.save_to_file(os.path.join(book_dir, title + ".html"), audio_intro)
                        utils.save_to_file(
                            os.path.join(book_dir, title + ".md"), html2text.html2text(audio_intro)
                        )
                    print("下载" + book["secondCategoryName"] + "的" + item["title"] + "完成")


def get_one_article(book_dir, doc_id):
    book_content = json.loads(get_article_content(book_dir, doc_id))
    article = book_content["events"][0]["article"]

    if not os.path.exists(book_dir):
        os.makedirs(book_dir)

    content_detail = json.loads(article["contentHtml"])

    print("文章：" + book_dir + article["title"] + ".md" + " 开始下载 " + doc_id)

    markdown_content = ""
    markdown_content += "# " + article["title"] + "\n\n"
    if "writers" in article and len(article["writers"]) > 0:
        author = article["writers"][0]
        markdown_content += "![](" + author["avatar"] + ")\n"
        markdown_content += author["name"] + "\n"
        if "desc" in author:
            markdown_content += author["desc"] + "\n"
        if "intro" in author:
            markdown_content += author["intro"] + "\n"
        markdown_content += "\n"
    markdown_content += "> " + article["snippet"] + "\n\n"
    for line in content_detail:
        if line["type"] == 0:
            if "linetype" in line["text"] and line["text"]["linetype"] == "h1":
                markdown_content += "## "

            if "markups" in line["text"] and "source" in line["text"]["markups"][0]:
                markdown_content += (
                    "[" + line["text"]["text"] + "]" + "(" + line["text"]["markups"][0]["source"] + ")" + "\n"
                )
            elif (
                "markups" in line["text"]
                and "tag" in line["text"]["markups"][0]
                and line["text"]["markups"][0]["tag"] == "strong"
            ):
                start = line["text"]["markups"][0]["start"]
                end = line["text"]["markups"][0]["end"]
                markdown_content += "**" + line["text"]["text"][start:end] + "** " + line["text"]["text"][end:] + "\n"
            else:
                markdown_content += line["text"]["text"] + "\n"

        elif line["type"] == 1:
            markdown_content += "![](" + line["image"]["source"] + ")\n"

        markdown_content += "\n"

    cur_article_file = book_dir + article["title"] + ".md"
    cur_article_file = cur_article_file.replace(" ", "")
    cur_article_file = cur_article_file.replace("\n", "")

    if "musics" in article:
        musics = article["musics"]
        for music in musics:
            music_url = music["url"]
            music_name = music["name"]
            if music_name is None or music_name == "":
                music_name = article["title"]
            music_file = book_dir + music_name + ".mp3"
            if os.path.exists(music_file):
                print(f"音频：{music_file} 已存在")
                continue
            print(f"音频：{music_file} 下载中")
            http_client.download_audio(music_url, music_file)
            print(f"音频：{music_file} 已下载")

    if "videos" in article:
        videos = article["videos"]
        for video in videos:
            video_url = video["url"]

            parsed_url = urllib.parse.urlparse(video_url)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            actual_url = urllib.parse.unquote_plus(query_params.get("url", [""])[0])
            if actual_url != "":
                video_url = actual_url

            video_name = article["title"]
            video_file = book_dir + video_name + ".mp4"
            if os.path.exists(video_file):
                print(f"视频：{video_file} 已存在")
                continue
            print(f"视频：{video_file} 下载中")
            http_client.download_mp4(video_url, video_file)
            print(f"视频：{video_file} 已下载")

    utils.save_to_file(cur_article_file, markdown_content)
    print(f"文章：{cur_article_file} 已下载")
    return cur_article_file


if __name__ == "__main__":
    http_client.is_download_audio = True
    http_client.is_download_video = False
    download_read_tab()

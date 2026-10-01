import os
import json
import urllib
import urllib.parse
from downloader_basement import utils
from duku_http_client import http_client


def _require_legacy_token():
    token = os.environ.get("DUKU_LEGACY_TOKEN", "").strip()
    if not token:
        raise RuntimeError("历史接口需要设置 DUKU_LEGACY_TOKEN；推荐使用 `duku download`。")
    return urllib.parse.quote(token, safe="")


def get_book_article_list(page_id):
    url = (
        "https://api.qingmang.mobi/v2/page.events?hl=zh-Hans-US&page_id="
        + page_id
        + f"&platform=duku_ios&publication=35413&publication=35413&token={_require_legacy_token()}&v=1.4.1&vc=216"
    )

    response = http_client.get(url, {})
    return response.text


def get_article_content(book_dir, doc_id):
    url = (
        "https://api.qingmang.mobi/v2/pool.article.fetchEvent?doc_id="
        + doc_id
        + f"&hl=zh-Hans-US&list_id=m0&platform=duku_ios&publication=35413&template=raml&token={_require_legacy_token()}&v=1.4.1&vc=216&with_full_content=1"
    )

    cache_file = book_dir + doc_id + ".json"
    response = http_client.get_with_cache(cache_file, url, {})
    return response


def download_book(book_info):
    book = json.loads(get_book_article_list(book_info["book_id"]))
    book_dir = book_info["book_name"] + "/"
    if not os.path.exists(book_dir):
        os.makedirs(book_dir)
    else:
        print(f"{book_dir} 已存在")
        return

    utils.save_to_file(book_dir + "目录.json", json.dumps(book, indent=4))
    for item in book["events"]:
        if item["type"] == "article":
            article = item["article"]
            print(
                article["docId"],
                article["title"],
                # article["snippet"],
                # article["summary"],
                article["publishDate"],
                article["textLength"],
                # article["writers"],
            )
            article_detail = json.loads(get_article_content(book_dir, article["docIdString"]))
            article_detail = article_detail["events"][0]["article"]
            utils.save_to_file(
                book_dir + article_detail["title"] + ".json",
                json.dumps(article_detail, indent=4),
            )

        elif item["type"] == "image":
            print(item["image"]["cover"]["url"])


# 下载“读”-“TabBar”
def download_read_tab():
    dir = "读/"
    if not os.path.exists(dir):
        os.makedirs(dir)
    url = f"https://api.qingmang.mobi/v2/page.events?hl=zh-Hans-US&page_id=36692&platform=duku_ios&publication=35413&publication=35413&token={_require_legacy_token()}&v=1.4.1&vc=216"
    response = http_client.get(url, {})
    tabs = json.loads(response)["events"][1]["listsInfo"]
    for tab in tabs:
        if tab["name"] is not None:
            book_dir = tab["name"] + "/"
            book_dir = book_dir.replace(" ", "")
            tab_list_url = (
                "https://api.qingmang.mobi/v2/pool.article.filterEvents?hl=zh-Hans-US&list="
                + tab["listId"]
                + f"&platform=duku_ios&publication=35413&publication_id=35413&token={_require_legacy_token()}&v=1.4.1&vc=216&max=300"
            )
            tab_list = json.loads(http_client.get(tab_list_url, {}))[
                "events"
            ]
            for item in tab_list:
                if item["type"] == "article":
                    article = item["article"]
                    # cur_article_file = dir + book_dir + article["title"] + ".md"
                    # if os.path.exists(cur_article_file):
                    #     print("文章：" + cur_article_file + " 已存在")
                    # else:
                    get_one_article(dir + book_dir, article["docIdString"])
                else:
                    print(
                        item["type"],
                        item["article"]["title"],
                        item["article"]["docIdString"],
                    )


book_list = [
    {
        "book_id": "36822",
        "book_name": "读库 2302",
    },
    {
        "book_id": "36839",
        "book_name": "读库 2303",
    },
]


def download_all_book():
    dir = "2023《读库》总目/"
    if not os.path.exists(dir):
        os.makedirs(dir)
    for book_info in book_list:
        book = json.loads(get_book_article_list(book_info["book_id"]))
        book_dir = "《" + book_info["book_name"] + "》/"
        book_dir = book_dir.replace(" ", "")
        if not os.path.exists(book_dir):
            os.makedirs(book_dir)

        for item in book["events"]:
            if item["type"] == "article":
                article = item["article"]
                get_one_article(dir + book_dir, article["docIdString"])


def get_all_books():
    url = f"https://api.qingmang.mobi/v2/pool.article.events?hl=zh-Hans-US&is_unread=0&list_id=m641259&platform=duku_ios&publication=35413&publication_id=35413&token={_require_legacy_token()}&v=1.4.1&vc=216&max=20"
    response = http_client.get(url, {})

    all_books = json.loads(response.text)["events"]
    for item in all_books:
        book = item["article"]
        print(
            book["title"],
            # book["docIdString"],
            # book["cover"],
            # book["publishDate"],
            # book["summary"],
        )

        book_dir = book["title"] + "/"
        book_content = json.loads(get_article_content(book_dir, book["docIdString"]))
        # 判断 book_dir 是否存在，不存在则创建
        if not os.path.exists(book_dir):
            os.makedirs(book_dir)

        content_detail = json.loads(
            book_content["events"][0]["article"]["contentHtml"])

        markdown_content = ""
        cur_book_name = ""
        for line in content_detail:
            if line["type"] == 0:
                if "linetype" in line["text"] and line["text"]["linetype"] == "h1":
                    markdown_content += "# "
                    cur_book_name = line["text"]["text"] + "/"
                elif "linetype" in line["text"] and line["text"]["linetype"] == "h2":
                    markdown_content += "## "
                if "markups" in line["text"] and "source" in line["text"]["markups"][0]:
                    doc_source = line["text"]["markups"][0]["source"]
                    doc_id = doc_source.split("/")[-2].split(".")[0]
                    cur_article_link = get_one_article(
                        book_dir + cur_book_name, doc_id)
                    markdown_content += (
                        "## ["
                        + line["text"]["text"]
                        + "]"
                        + "("
                        + "/".join(cur_article_link.split("/")[1:])
                        + ")"
                        + "\n"
                    )
                elif (
                    "markups" in line["text"]
                    and "tag" in line["text"]["markups"][0]
                    and line["text"]["markups"][0]["tag"] == "strong"
                ):
                    start = line["text"]["markups"][0]["start"]
                    end = line["text"]["markups"][0]["end"]
                    markdown_content += (
                        "**"
                        + line["text"]["text"][start:end]
                        + "** "
                        + line["text"]["text"][end:]
                        + "\n"
                    )
                else:
                    markdown_content += line["text"]["text"] + "\n"

            elif line["type"] == 1:
                image_url = line["image"]["source"]
                file_name = book_dir + cur_book_name
                if not os.path.exists(file_name):
                    os.makedirs(file_name)

                file_name += "cover." + image_url.split(".")[-1]
                http_client.download_image(image_url, file_name)
                markdown_content += "![](" + line["image"]["source"] + ")\n"

            markdown_content += "\n"
        utils.save_to_file(book_dir + book["title"] + ".md", markdown_content)


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
    # markdown_content += "> 摘要：" + article["summary"] + "\n\n"
    for line in content_detail:
        if line["type"] == 0:
            if "linetype" in line["text"] and line["text"]["linetype"] == "h1":
                markdown_content += "## "

            if "markups" in line["text"] and "source" in line["text"]["markups"][0]:
                markdown_content += (
                    "["
                    + line["text"]["text"]
                    + "]"
                    + "("
                    + line["text"]["markups"][0]["source"]
                    + ")"
                    + "\n"
                )
            elif (
                "markups" in line["text"]
                and "tag" in line["text"]["markups"][0]
                and line["text"]["markups"][0]["tag"] == "strong"
            ):
                start = line["text"]["markups"][0]["start"]
                end = line["text"]["markups"][0]["end"]
                markdown_content += (
                    "**"
                    + line["text"]["text"][start:end]
                    + "** "
                    + line["text"]["text"][end:]
                    + "\n"
                )
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
            # 从查询参数中获取实际的 URL 并进行解码
            actual_url = urllib.parse.unquote_plus(query_params.get('url', [''])[0])
            if actual_url != '':
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


# get_all_books()
# download_all_book()
if __name__ == "__main__":
    http_client.is_download_audio = False
    http_client.is_download_video = False
    download_read_tab()

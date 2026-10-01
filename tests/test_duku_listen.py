import json
import tempfile
import unittest
from pathlib import Path

from duku_listen import (
    BOOK_PAGE_URL,
    PAGE_SIZE,
    READING_PAGE_URL,
    choose_video_variant,
    build_item_introduction,
    download_listen,
    extract_html_media,
    get_item_media_url,
    get_listen_items,
    get_listen_page,
    select_listen_categories,
)


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        return json.dumps(next(self.responses))


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class DukuListenTests(unittest.TestCase):
    def test_item_introduction_contains_metadata_and_html_description(self):
        category = {"secondCategoryId": 641390, "secondCategoryName": "杨照谈诗"}
        item = {
            "bookIdStr": "39396",
            "title": "黄国彬：重构艾略特（下）",
            "contentType": 3,
            "authorInfo": [{"userName": "杨照"}],
            "contentDuration": 1590,
            "firstPublishTime": "2023-04-24 11:33:36",
            "summary": "节目摘要",
            "articleDetail": "<p>节目正文介绍。</p>",
        }

        introduction = build_item_introduction(category, item)

        self.assertIn("**栏目**：杨照谈诗", introduction)
        self.assertIn("**作者**：杨照", introduction)
        self.assertIn("**时长**：00:26:30", introduction)
        self.assertIn("**摘要**：节目摘要", introduction)
        self.assertIn("节目正文介绍。", introduction)

    def test_category_selector_accepts_index_id_and_name(self):
        categories = [
            {"secondCategoryId": 641440, "secondCategoryName": "六重奏"},
            {"secondCategoryId": 641390, "secondCategoryName": "杨照谈诗"},
        ]

        self.assertEqual(select_listen_categories(categories, ["2"]), [categories[1]])
        self.assertEqual(select_listen_categories(categories, ["641390"]), [categories[1]])
        self.assertEqual(select_listen_categories(categories, ["杨照谈诗"]), [categories[1]])
        self.assertEqual(select_listen_categories(categories, ["杨照"]), [categories[1]])

    def test_category_selector_rejects_unknown_category(self):
        categories = [{"secondCategoryId": 641390, "secondCategoryName": "杨照谈诗"}]

        with self.assertRaisesRegex(ValueError, "没有找到听栏目"):
            select_listen_categories(categories, ["不存在"])

    def test_listen_page_request_matches_capture(self):
        data = {"showBookCategorySecondList": [{"secondCategoryId": 641390}]}
        client = FakeClient([{"resultCode": "A00000", "data": data}])

        self.assertEqual(get_listen_page(client), data)
        self.assertEqual(client.calls, [(READING_PAGE_URL, {"pageCode": "LISTEN"})])

    def test_listen_details_request_has_no_category_order_and_paginates(self):
        client = FakeClient(
            [
                {"resultCode": "A00000", "data": {"list": [{"bookId": 1}], "totalPage": 2}},
                {"resultCode": "A00000", "data": {"list": [{"bookId": 2}], "totalPage": 2}},
            ]
        )

        self.assertEqual(get_listen_items(641390, client), [{"bookId": 1}, {"bookId": 2}])
        for page, (url, params) in enumerate(client.calls, start=1):
            self.assertEqual(url, BOOK_PAGE_URL)
            self.assertEqual(
                params,
                {"secondCategoryId": 641390, "currentPage": page, "pageSize": PAGE_SIZE},
            )
            self.assertNotIn("categoryOrder", params)

    def test_video_resolver_prefers_highest_transcode_over_source(self):
        video_info = {
            "sourceVideo": {"url": "source.mp4", "width": 3840, "height": 2160, "size": 10_000},
            "transcodeList": [
                {"url": "720.mp4", "width": 1280, "height": 720, "size": 100},
                {"url": "1080.mp4", "width": 1920, "height": 1080, "size": 200},
            ],
        }

        self.assertEqual(choose_video_variant(video_info)["url"], "1080.mp4")

    def test_audio_url_falls_back_to_article_html(self):
        item = {
            "contentType": 3,
            "fileLink": "",
            "articleDetail": '<audio controls><source src="https://example.com/audio.mp3"></audio>',
        }

        self.assertEqual(
            get_item_media_url(item),
            ("audio", "https://example.com/audio.mp3"),
        )
        self.assertEqual(
            extract_html_media('<video src="https://example.com/video.mp4"></video>', "video"),
            "https://example.com/video.mp4",
        )

    def test_video_file_id_uses_tencent_play_info(self):
        calls = []

        def request_get(url, timeout):
            calls.append((url, timeout))
            return FakeResponse(
                {
                    "code": 0,
                    "videoInfo": {"sourceVideo": {"url": "https://example.com/video.mp4"}},
                }
            )

        self.assertEqual(
            get_item_media_url(
                {"contentType": 2, "fileLink": "5001834806946615413"},
                request_get=request_get,
            ),
            ("video", "https://example.com/video.mp4"),
        )
        self.assertIn("5001834806946615413", calls[0][0])

    def test_metadata_only_flow_saves_list_and_all_category_details(self):
        category = {"secondCategoryId": 641390, "secondCategoryName": "杨照谈诗"}
        item = {
            "bookId": 39396,
            "bookIdStr": "39396",
            "contentType": 3,
            "fileLink": "https://example.com/audio.mp3",
            "title": "示例音频",
        }
        client = FakeClient(
            [
                {
                    "resultCode": "A00000",
                    "data": {"showBookCategorySecondList": [category]},
                },
                {
                    "resultCode": "A00000",
                    "data": {"list": [item], "totalPage": 1},
                },
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            summary = download_listen(
                output_dir=temp_dir,
                download_audio=False,
                download_video=False,
                client=client,
            )
            metadata_dir = Path(temp_dir) / "metadata"

            self.assertTrue((metadata_dir / "list.json").exists())
            self.assertTrue((metadata_dir / "details" / "641390-杨照谈诗.json").exists())
            self.assertTrue((Path(temp_dir) / "栏目列表.md").exists())
            self.assertTrue((Path(temp_dir) / "杨照谈诗" / "栏目介绍.md").exists())
            item_introductions = list((Path(temp_dir) / "杨照谈诗").glob("*/介绍.md"))
            self.assertEqual(len(item_introductions), 1)
            media = json.loads((metadata_dir / "media.json").read_text(encoding="utf-8"))
            self.assertEqual(media[0]["status"], "disabled")
            self.assertEqual(summary["items"], 1)
            self.assertEqual(summary["unique_items"], 1)
            self.assertEqual(summary["downloaded"], 0)

    def test_metadata_flow_only_requests_selected_category(self):
        categories = [
            {"secondCategoryId": 641440, "secondCategoryName": "六重奏"},
            {"secondCategoryId": 641390, "secondCategoryName": "杨照谈诗"},
        ]
        item = {
            "bookId": 39396,
            "bookIdStr": "39396",
            "contentType": 3,
            "fileLink": "https://example.com/audio.mp3",
            "title": "示例音频",
        }
        client = FakeClient(
            [
                {
                    "resultCode": "A00000",
                    "data": {"showBookCategorySecondList": categories},
                },
                {
                    "resultCode": "A00000",
                    "data": {"list": [item], "totalPage": 1},
                },
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            summary = download_listen(
                output_dir=temp_dir,
                download_audio=False,
                download_video=False,
                client=client,
                category_selectors=["2"],
            )

            self.assertEqual(summary["categories"], 1)
            self.assertEqual(client.calls[1][1]["secondCategoryId"], 641390)
            details = list((Path(temp_dir) / "metadata" / "details").glob("*.json"))
            self.assertEqual([path.name for path in details], ["641390-杨照谈诗.json"])

    def test_duplicate_media_is_saved_under_each_category_and_reused(self):
        categories = [
            {"secondCategoryId": 1, "secondCategoryName": "栏目甲"},
            {"secondCategoryId": 2, "secondCategoryName": "栏目乙"},
        ]
        item = {
            "bookId": 39396,
            "bookIdStr": "39396",
            "contentType": 3,
            "fileLink": "https://example.com/audio.mp3",
            "title": "同一个节目",
            "summary": "介绍",
        }
        client = FakeClient(
            [
                {"resultCode": "A00000", "data": {"showBookCategorySecondList": categories}},
                {"resultCode": "A00000", "data": {"list": [item], "totalPage": 1}},
                {"resultCode": "A00000", "data": {"list": [item], "totalPage": 1}},
            ]
        )
        download_calls = []

        def media_downloader(url, output_path, request_get=None):
            download_calls.append(url)
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_bytes(b"audio")
            return True

        with tempfile.TemporaryDirectory() as temp_dir:
            summary = download_listen(
                output_dir=temp_dir,
                download_audio=True,
                download_video=False,
                client=client,
                media_downloader=media_downloader,
            )

            audio_files = list(Path(temp_dir).glob("栏目*/**/*.mp3"))
            self.assertEqual(len(audio_files), 2)
            self.assertEqual(len(download_calls), 1)
            self.assertEqual(summary["downloaded"], 1)
            self.assertEqual(summary["reused"], 1)


if __name__ == "__main__":
    unittest.main()

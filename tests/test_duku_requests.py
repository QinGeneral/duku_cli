import json
import unittest

from duku_download_v2 import (
    BOOK_PAGE_URL,
    PAGE_SIZE,
    READING_PAGE_URL,
    get_books_by_second_category,
    get_reading_categories,
)
from duku_http_client import DUKU_USER_AGENT, build_header


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        return json.dumps(next(self.responses))


class DukuRequestTests(unittest.TestCase):
    def test_headers_match_captured_android_request(self):
        headers = build_header("test-token")

        self.assertEqual(headers["Host"], "service.duku.cn")
        self.assertEqual(headers["satoken"], "test-token")
        self.assertEqual(headers["User-Agent"], DUKU_USER_AGENT)
        self.assertNotIn("Cookie", headers)

    def test_reading_categories_request_matches_capture(self):
        categories = [{"subTabName": "2026", "categorySecondTabList": []}]
        client = FakeClient(
            [
                {
                    "resultCode": "A00000",
                    "data": {"pageSecondCategoryFilterTabList": categories},
                },
                {"resultCode": "A00000", "data": {"categorySecondTabList": []}},
            ]
        )

        self.assertEqual(get_reading_categories(client), categories)
        self.assertEqual(
            client.calls,
            [
                (READING_PAGE_URL, {"pageCode": "READ_MOOK_TOTAL"}),
                (READING_PAGE_URL, {"pageCode": "READ_MOOK_LATEST"}),
            ],
        )

    def category_client(self, years, latest):
        return FakeClient([
            {"resultCode": "A00000", "data": {"pageSecondCategoryFilterTabList": years}},
            {"resultCode": "A00000", "data": {"categorySecondTabList": latest}},
        ])

    def test_latest_missing_issue_is_merged_once_into_existing_year(self):
        old = {"secondCategoryId": 641576, "secondCategoryName": "2602"}
        new = {"secondCategoryId": 641578, "secondCategoryName": "2603"}
        years = [{"subTabName": "2026", "categorySecondTabList": [old, old]}]
        client = self.category_client(years, [new, {**old, "secondCategoryId": "641576"}, new])

        self.assertEqual(get_reading_categories(client), [
            {"subTabName": "2026", "categorySecondTabList": [old, new]},
        ])

    def test_latest_creates_missing_year_without_changing_existing_grouping(self):
        old = {"secondCategoryId": 1, "secondCategoryName": "2602"}
        new = {"secondCategoryId": 2, "secondCategoryName": "2701"}
        years = [{"subTabName": "2026", "categorySecondTabList": [old]}]

        self.assertEqual(get_reading_categories(self.category_client(years, [new, old])), [
            years[0],
            {"subTabName": "2027", "categorySecondTabList": [new]},
        ])

    def test_empty_catalogues_and_latest_only_catalogue(self):
        new = {"secondCategoryId": 641578, "secondCategoryName": "2603"}
        self.assertEqual(get_reading_categories(self.category_client(None, None)), [])
        self.assertEqual(get_reading_categories(self.category_client(None, [new])), [
            {"subTabName": "2026", "categorySecondTabList": [new]},
        ])

    def test_unrecognized_new_issue_name_fails_instead_of_using_wrong_year(self):
        new = {"secondCategoryId": 1, "secondCategoryName": "特别刊"}
        with self.assertRaisesRegex(RuntimeError, "无法从最新期刊名称推断年份"):
            get_reading_categories(self.category_client([], [new]))

    def test_latest_api_failure_is_not_silently_ignored(self):
        client = FakeClient([
            {"resultCode": "A00000", "data": {"pageSecondCategoryFilterTabList": []}},
            {"resultCode": "A00005", "resultMsg": "用户未登录或登录过期"},
        ])
        with self.assertRaisesRegex(RuntimeError, "A00005"):
            get_reading_categories(client)

    def test_book_request_uses_singular_category_id_and_paginates(self):
        client = FakeClient(
            [
                {
                    "resultCode": "A00000",
                    "data": {"list": [{"bookId": 1}], "totalPage": 2},
                },
                {
                    "resultCode": "A00000",
                    "data": {"list": [{"bookId": 2}], "totalPage": 2},
                },
            ]
        )

        self.assertEqual(
            get_books_by_second_category(641576, client),
            [{"bookId": 1}, {"bookId": 2}],
        )
        self.assertEqual(len(client.calls), 2)
        for page, (url, params) in enumerate(client.calls, start=1):
            self.assertEqual(url, BOOK_PAGE_URL)
            self.assertEqual(
                params,
                {
                    "secondCategoryId": 641576,
                    "currentPage": page,
                    "pageSize": PAGE_SIZE,
                    "categoryOrder": 1,
                },
            )
            self.assertNotIn("secondCategoryIds", params)


if __name__ == "__main__":
    unittest.main()

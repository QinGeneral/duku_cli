from downloader_basement.base_http_client import BaseHttpClient

from duku_config import require_satoken


DUKU_USER_AGENT = (
    "cn.duku/2.1.7(Android {SDK_INT=30, ABIS=arm64-v8a, "
    "MODEL=Android SDK built for arm64, RELEASE=11, MANUFACTURER=unknown, "
    "BRAND=Android}) eink:false"
)


def build_header(satoken):
    return {
        "Host": "service.duku.cn",
        "satoken": satoken,
        "User-Agent": DUKU_USER_AGENT,
    }


class DukuHttpClient(BaseHttpClient):
    cache_dir = './cache'
    article_detail_url = "https://time.geekbang.org/serv/v1/article"

    def __init__(self, satoken=None):
        self.header = build_header(require_satoken(satoken))
        super().__init__()

    def login(self, driver):
        print("暂不支持自动登录")
        return

    def is_header_still_valid_by_request(self):
        return True


_http_client = None


def get_http_client(satoken=None):
    global _http_client

    if satoken is None and _http_client is not None:
        return _http_client

    resolved_satoken = require_satoken(satoken)
    if _http_client is None or _http_client.header.get("satoken") != resolved_satoken:
        _http_client = DukuHttpClient(resolved_satoken)
    return _http_client


class _HttpClientProxy:
    def __getattr__(self, name):
        return getattr(get_http_client(), name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        setattr(get_http_client(), name, value)


http_client = _HttpClientProxy()

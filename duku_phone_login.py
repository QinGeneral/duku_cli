import json
import shutil
import socket
import subprocess
import time
from base64 import b64decode, b64encode
from dataclasses import dataclass
from pathlib import Path
from tempfile import gettempdir
from urllib.error import URLError
from urllib.request import urlopen

import requests

from duku_config import get_config_dir, save_satoken
from duku_http_client import DUKU_USER_AGENT


CAPTCHA_URL = "http://fe-m.duku.cn/#/captcha"
SERVICE_HOST = "service.duku.cn"
SEND_VERIFY_CODE_URL = f"https://{SERVICE_HOST}/api/v1/duku/user/sendVerifyCode"
LOGIN_URL = f"https://{SERVICE_HOST}/api/v1/duku/user/login"
BIZ_NAME = "duku_user"
ALIYUN_VERIFY_HOST = "captcha-open.aliyuncs.com"
CAPTCHA_SCENE_ID = "132fltrt"


@dataclass(frozen=True)
class CaptchaResult:
    security_token: str
    certify_id: str
    scene_id: str = CAPTCHA_SCENE_ID


def build_service_headers():
    return {
        "Host": SERVICE_HOST,
        "satoken": "",
        "User-Agent": DUKU_USER_AGENT,
        "Content-Type": "application/json; charset=UTF-8",
    }


def build_captcha_verify_param(security_token, certify_id, scene_id=CAPTCHA_SCENE_ID):
    security_token = (security_token or "").strip()
    certify_id = (certify_id or "").strip()
    scene_id = (scene_id or "").strip()
    if not security_token:
        raise ValueError("securityToken 不能为空")
    if not certify_id:
        raise ValueError("certifyId 不能为空")
    if not scene_id:
        raise ValueError("sceneId 不能为空")

    return {
        "captchaVerifyParam": encode_captcha_verify_param(
            security_token=security_token,
            certify_id=certify_id,
            scene_id=scene_id,
        ),
        "sceneId": scene_id,
    }


def encode_captcha_verify_param(security_token, certify_id, scene_id=CAPTCHA_SCENE_ID):
    payload = {
        "certifyId": certify_id,
        "sceneId": scene_id,
        "isSign": True,
        "securityToken": security_token,
    }
    return b64encode(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")


def build_send_verify_code_payload(phone, security_token, certify_id, scene_id=CAPTCHA_SCENE_ID):
    return {
        "bizName": BIZ_NAME,
        "phone": _normalize_phone(phone),
        "captchaVerifyParam": build_captcha_verify_param(security_token, certify_id, scene_id),
    }


def build_login_payload(phone, verify_code):
    verify_code = (verify_code or "").strip()
    if not verify_code:
        raise ValueError("短信验证码不能为空")

    return {
        "bizName": BIZ_NAME,
        "phone": _normalize_phone(phone),
        "verifyCode": verify_code,
    }


def send_verify_code(
    phone,
    security_token,
    certify_id,
    scene_id=CAPTCHA_SCENE_ID,
    request_post=requests.post,
):
    payload = build_send_verify_code_payload(phone, security_token, certify_id, scene_id)
    data = _post_json(
        SEND_VERIFY_CODE_URL,
        payload,
        action_name="发送短信验证码",
        request_post=request_post,
    )
    return data


def login_with_phone_code(phone, verify_code, request_post=requests.post):
    payload = build_login_payload(phone, verify_code)
    data = _post_json(
        LOGIN_URL,
        payload,
        action_name="手机号验证码登录",
        request_post=request_post,
    )
    token = (data.get("token") or "").strip()
    if not token:
        raise RuntimeError("手机号验证码登录成功响应中没有 token")
    return token


def phone_code_login(
    phone,
    verify_code,
    security_token,
    certify_id,
    scene_id=CAPTCHA_SCENE_ID,
    request_post=requests.post,
):
    send_verify_code(
        phone,
        security_token,
        certify_id,
        scene_id,
        request_post=request_post,
    )
    token = login_with_phone_code(phone, verify_code, request_post=request_post)
    return save_satoken(token)


def capture_captcha_result(
    captcha_url=CAPTCHA_URL,
    timeout_seconds=300,
    poll_interval=0.5,
    driver_factory=None,
    decode_response=None,
):
    if driver_factory is None:
        driver = ChromeCdpBrowser()
    else:
        driver = driver_factory()
        if decode_response is None:
            decode_response = lambda body, _encoding: body

    cdp_state = {
        "candidate_ids": set(),
        "request_text_by_id": {},
        "processed_ids": set(),
        "reported_failures": set(),
    }

    try:
        print(f"正在打开验证码页面：{captcha_url}")
        print("请在打开的浏览器里完成安全验证，完成后不要立即关闭窗口。")
        driver.get(captcha_url)
        deadline = time.time() + timeout_seconds
        seen_request_ids = set()
        while time.time() < deadline:
            cdp_result = _extract_captcha_result_from_cdp_logs(driver, cdp_state)
            if cdp_result:
                return cdp_result

            for request in getattr(driver, "requests", []):
                request_key = id(request)
                if request_key in seen_request_ids:
                    continue
                if not _is_aliyun_verify_request(request):
                    continue
                seen_request_ids.add(request_key)
                result = _extract_captcha_result_from_request(request, decode_response)
                if result:
                    return result
            time.sleep(poll_interval)
    finally:
        driver.quit()

    raise TimeoutError(f"等待验证码完成超时：{timeout_seconds} 秒")


class ChromeCdpBrowser:
    def __init__(self, chrome_path=None, port=None, profile_dir=None):
        self.chrome_path = chrome_path or _find_chrome_executable()
        self.port = port or _find_free_port()
        self.profile_dir = profile_dir or _captcha_chrome_profile_dir()
        self.event_buffer = []
        self.next_message_id = 0
        self.ws = None
        self.process = subprocess.Popen(
            _build_chrome_cdp_command(self.chrome_path, self.port, self.profile_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            self.ws = self._connect_to_page()
            self.execute_cdp_cmd("Network.enable", {})
            self.execute_cdp_cmd("Page.enable", {})
        except Exception:
            self.quit()
            raise

    def get(self, url):
        self.execute_cdp_cmd("Page.navigate", {"url": url})

    def get_log(self, name):
        if name != "performance":
            return []

        entries = []
        if self.event_buffer:
            entries.extend(self.event_buffer)
            self.event_buffer = []

        deadline = time.time() + 0.2
        while time.time() < deadline:
            message = self._recv_message(timeout=0.05)
            if message is None:
                break
            if "method" in message:
                entries.append({"message": json.dumps({"message": message})})
        return entries

    def execute_cdp_cmd(self, method, params):
        self.next_message_id += 1
        message_id = self.next_message_id
        self.ws.send(json.dumps({"id": message_id, "method": method, "params": params}))

        while True:
            message = self._recv_message(timeout=3)
            if message is None:
                raise TimeoutError(f"等待 Chrome CDP 响应超时：{method}")
            if message.get("id") == message_id:
                if "error" in message:
                    raise RuntimeError(f"Chrome CDP 调用失败：{method} {message['error']}")
                return message.get("result") or {}
            if "method" in message:
                self.event_buffer.append({"message": json.dumps({"message": message})})

    def quit(self):
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
        if getattr(self, "process", None) is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def _connect_to_page(self):
        try:
            import websocket
        except ImportError as exc:
            raise RuntimeError("缺少 websocket-client 依赖，请先安装 websocket-client。") from exc

        deadline = time.time() + 10
        while time.time() < deadline:
            target = _first_cdp_page_target(self.port)
            if target:
                return websocket.create_connection(
                    target["webSocketDebuggerUrl"],
                    timeout=3,
                    origin="http://127.0.0.1",
                )
            time.sleep(0.1)
        raise TimeoutError("等待 Chrome 远程调试页面超时")

    def _recv_message(self, timeout):
        try:
            import websocket

            self.ws.settimeout(timeout)
            return json.loads(self.ws.recv())
        except websocket.WebSocketTimeoutException:
            return None


def _build_chrome_cdp_command(chrome_path, port, profile_dir):
    return [
        str(chrome_path),
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-quic",
        "--window-size=1100,900",
        "about:blank",
    ]


def _find_chrome_executable():
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    raise RuntimeError("未找到 Chrome/Chromium 浏览器")


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _first_cdp_page_target(port):
    try:
        with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as response:
            targets = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError):
        return None
    for target in targets:
        if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
            return target
    return None


def _captcha_chrome_profile_dir():
    profile_dir = get_config_dir() / "captcha-chrome-profile"
    try:
        profile_dir.mkdir(parents=True, exist_ok=True)
        return profile_dir
    except OSError:
        fallback_dir = Path(gettempdir()) / "duku-captcha-chrome-profile"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        return fallback_dir


def _extract_captcha_result_from_cdp_logs(driver, state):
    if not hasattr(driver, "get_log"):
        return None

    try:
        log_entries = driver.get_log("performance")
    except Exception:
        return None

    for entry in log_entries:
        try:
            message = json.loads(entry["message"])["message"]
        except (KeyError, TypeError, json.JSONDecodeError):
            continue

        method = message.get("method")
        params = message.get("params") or {}
        request_id = params.get("requestId")
        if not request_id:
            continue

        if method == "Network.requestWillBeSent":
            request = params.get("request") or {}
            url = request.get("url") or ""
            if ALIYUN_VERIFY_HOST in url:
                state["candidate_ids"].add(request_id)
                state["request_text_by_id"][request_id] = request.get("postData") or ""
            continue

        if method == "Network.responseReceived":
            response = params.get("response") or {}
            url = response.get("url") or ""
            if ALIYUN_VERIFY_HOST in url:
                state["candidate_ids"].add(request_id)
            continue

        if method != "Network.loadingFinished":
            continue
        if request_id not in state["candidate_ids"]:
            continue
        if request_id in state["processed_ids"]:
            continue

        try:
            body_info = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
        except Exception:
            continue

        state["processed_ids"].add(request_id)
        body = _decode_cdp_response_body(body_info)
        request_text = state["request_text_by_id"].get(request_id, "")
        result = _extract_captcha_result_from_text(body, request_text)
        if result:
            return result
        _report_captcha_failure_once(body, request_id, state)

    return None


def _decode_cdp_response_body(body_info):
    body = body_info.get("body") or ""
    if body_info.get("base64Encoded"):
        return b64decode(body).decode("utf-8", errors="replace")
    return body


def _is_aliyun_verify_request(request):
    return (
        request.response is not None
        and ALIYUN_VERIFY_HOST in request.url
        and "VerifyCaptchaV3" in _request_text(request)
    )


def _extract_captcha_result_from_request(request, decode):
    response = request.response
    if response is None:
        return None

    body = response.body or b""
    if not body:
        return None

    encoding = response.headers.get("Content-Encoding", "identity")
    try:
        body = decode(body, encoding)
    except Exception:
        pass

    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")

    return _extract_captcha_result_from_text(
        body,
        request_text=_request_text(request),
    )


def _extract_captcha_result_from_text(body, request_text=""):
    payload = json.loads(body)
    result = payload.get("Result") or {}
    if result.get("VerifyResult") is not True:
        return None

    security_token = result.get("securityToken")
    certify_id = result.get("certifyId") or _extract_certify_id_from_text(request_text)
    scene_id = result.get("sceneId") or _extract_scene_id_from_text(request_text)
    if not security_token or not certify_id or not scene_id:
        return None

    return CaptchaResult(
        security_token=security_token,
        certify_id=certify_id,
        scene_id=scene_id,
    )


def _report_captcha_failure_once(body, request_id, state):
    message = _captcha_failure_message(body)
    if not message:
        return
    marker = (request_id, message)
    if marker in state["reported_failures"]:
        return
    state["reported_failures"].add(marker)
    print(message)


def _captcha_failure_message(body):
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return None
    result = payload.get("Result") or {}
    if result.get("VerifyResult") is not False:
        return None
    verify_code = result.get("VerifyCode") or "未知"
    certify_id = result.get("certifyId") or "未知"
    return (
        "检测到一次阿里云安全验证失败："
        f"VerifyCode={verify_code}, certifyId={certify_id}。"
        "请在浏览器里刷新验证码页后重新完成验证。"
    )


def _extract_certify_id_from_request_payload(request):
    return _extract_certify_id_from_text(_request_text(request))


def _extract_certify_id_from_text(text):
    if not text:
        return None

    form = _parse_form_text(text)
    certify_id = _first_form_value(form, "CertifyId", "certifyId")
    if certify_id:
        return certify_id

    captcha_payload = _extract_captcha_verify_request_payload(form)
    return captcha_payload.get("certifyId")


def _extract_scene_id_from_text(text):
    if not text:
        return None

    form = _parse_form_text(text)
    scene_id = _first_form_value(form, "SceneId", "sceneId")
    if scene_id:
        return scene_id

    captcha_payload = _extract_captcha_verify_request_payload(form)
    return captcha_payload.get("sceneId")


def _parse_form_text(text):
    from urllib.parse import parse_qs

    return parse_qs(text, keep_blank_values=True)


def _first_form_value(form, *keys):
    for key in keys:
        values = form.get(key)
        if values and values[0]:
            return values[0]
    return None


def _extract_captcha_verify_request_payload(form):
    params = form.get("CaptchaVerifyParam")
    if not params:
        return {}
    try:
        payload = json.loads(params[0])
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _request_text(request):
    body = getattr(request, "body", None)
    if not body:
        return ""
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    return str(body)


def _normalize_phone(phone):
    phone = (phone or "").strip()
    if not phone:
        raise ValueError("手机号不能为空")
    return phone


def _post_json(url, payload, action_name, request_post=requests.post):
    response = request_post(
        url,
        json=payload,
        headers=build_service_headers(),
        timeout=30,
    )
    response.raise_for_status()

    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError(f"{action_name}响应不是 JSON：{response.text}") from exc

    if result.get("resultCode") != "A00000":
        message = result.get("resultMsg") or result.get("message") or result
        raise RuntimeError(f"{action_name}失败：{message}")

    return result.get("data") or {}

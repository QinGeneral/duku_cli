import json
import os
import tempfile
import unittest
from base64 import b64decode
from pathlib import Path

from duku_phone_login import (
    LOGIN_URL,
    SEND_VERIFY_CODE_URL,
    CaptchaResult,
    _captcha_failure_message,
    _build_chrome_cdp_command,
    _extract_captcha_result_from_request,
    _extract_captcha_result_from_text,
    build_send_verify_code_payload,
    capture_captcha_result,
    login_with_phone_code,
    phone_code_login,
    send_verify_code,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakePost:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def __call__(self, url, json, headers, timeout):
        self.calls.append(
            {
                "url": url,
                "json": json,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return FakeResponse(next(self.responses))


class FakeSeleniumResponse:
    def __init__(self, payload):
        self.body = json.dumps(payload).encode("utf-8")
        self.headers = {}


class FakeSeleniumRequest:
    def __init__(self, body, payload, url="https://dqdr8o-verify.captcha-open.aliyuncs.com/"):
        self.url = url
        self.body = body.encode("utf-8")
        self.response = FakeSeleniumResponse(payload)


class FakeDriver:
    def __init__(self, requests):
        self.requests = requests
        self.opened_urls = []
        self.quit_called = False

    def get(self, url):
        self.opened_urls.append(url)

    def quit(self):
        self.quit_called = True


class FakeCdpDriver:
    def __init__(self, log_entries, response_body):
        self.log_entries = log_entries
        self.response_body = response_body
        self.opened_urls = []
        self.quit_called = False
        self.requests = []

    def get(self, url):
        self.opened_urls.append(url)

    def get_log(self, name):
        self.assert_log_name = name
        entries = self.log_entries
        self.log_entries = []
        return entries

    def execute_cdp_cmd(self, command, params):
        self.executed_command = (command, params)
        return {"body": self.response_body, "base64Encoded": False}

    def quit(self):
        self.quit_called = True


def performance_entry(method, params):
    return {"message": json.dumps({"message": {"method": method, "params": params}})}


class PhoneLoginTests(unittest.TestCase):
    def test_send_verify_code_payload_maps_security_token_and_certify_id(self):
        payload = build_send_verify_code_payload(
            " 13800138000 ",
            "security-token",
            "certify-id",
            "132fltrt",
        )

        captcha_param = payload["captchaVerifyParam"]
        decoded = json.loads(b64decode(captcha_param["captchaVerifyParam"]).decode("utf-8"))

        self.assertEqual(payload["bizName"], "duku_user")
        self.assertEqual(payload["phone"], "13800138000")
        self.assertEqual(captcha_param["sceneId"], "132fltrt")
        self.assertEqual(
            decoded,
            {
                "certifyId": "certify-id",
                "sceneId": "132fltrt",
                "isSign": True,
                "securityToken": "security-token",
            },
        )

    def test_send_verify_code_uses_captured_android_endpoint(self):
        fake_post = FakePost([{"resultCode": "A00000", "data": {}}])

        send_verify_code(
            "13800138000",
            "security-token",
            "certify-id",
            "132fltrt",
            request_post=fake_post,
        )

        self.assertEqual(fake_post.calls[0]["url"], SEND_VERIFY_CODE_URL)
        self.assertEqual(fake_post.calls[0]["headers"]["Host"], "service.duku.cn")
        self.assertEqual(fake_post.calls[0]["headers"]["satoken"], "")
        self.assertEqual(
            fake_post.calls[0]["json"]["captchaVerifyParam"]["sceneId"],
            "132fltrt",
        )
        self.assertEqual(
            json.loads(
                b64decode(
                    fake_post.calls[0]["json"]["captchaVerifyParam"]["captchaVerifyParam"]
                ).decode("utf-8")
            ),
            {
                "certifyId": "certify-id",
                "sceneId": "132fltrt",
                "isSign": True,
                "securityToken": "security-token",
            },
        )

    def test_login_returns_token_from_captured_login_response_shape(self):
        fake_post = FakePost(
            [
                {
                    "resultCode": "A00000",
                    "data": {"token": "new-token"},
                }
            ]
        )

        token = login_with_phone_code(
            "13800138000",
            "839201",
            request_post=fake_post,
        )

        self.assertEqual(token, "new-token")
        self.assertEqual(fake_post.calls[0]["url"], LOGIN_URL)
        self.assertEqual(
            fake_post.calls[0]["json"],
            {
                "bizName": "duku_user",
                "phone": "13800138000",
                "verifyCode": "839201",
            },
        )

    def test_phone_code_login_saves_returned_token_as_satoken(self):
        fake_post = FakePost(
            [
                {"resultCode": "A00000", "data": {}},
                {"resultCode": "A00000", "data": {"token": "saved-token"}},
            ]
        )

        old_config_dir = os.environ.get("DUKU_CONFIG_DIR")
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["DUKU_CONFIG_DIR"] = temp_dir
            try:
                config_path = phone_code_login(
                    "13800138000",
                    "839201",
                    "security-token",
                    "certify-id",
                    "132fltrt",
                    request_post=fake_post,
                )
            finally:
                if old_config_dir is None:
                    os.environ.pop("DUKU_CONFIG_DIR", None)
                else:
                    os.environ["DUKU_CONFIG_DIR"] = old_config_dir

            config = json.loads(Path(config_path).read_text(encoding="utf-8"))

        self.assertEqual(config["satoken"], "saved-token")
        self.assertEqual([call["url"] for call in fake_post.calls], [SEND_VERIFY_CODE_URL, LOGIN_URL])

    def test_extracts_security_token_and_certify_id_from_aliyun_verify_response(self):
        request = FakeSeleniumRequest(
            "Action=VerifyCaptchaV3&SceneId=132fltrt&CertifyId=request-certify-id",
            {
                "Result": {
                    "securityToken": "security-token",
                    "VerifyResult": True,
                    "certifyId": "response-certify-id",
                }
            },
        )

        result = _extract_captcha_result_from_request(
            request,
            decode=lambda body, _encoding: body,
        )

        self.assertEqual(
            result,
            CaptchaResult(
                security_token="security-token",
                certify_id="response-certify-id",
                scene_id="132fltrt",
            ),
        )

    def test_capture_captcha_result_opens_url_reads_verify_response_and_quits_driver(self):
        request = FakeSeleniumRequest(
            "Action=VerifyCaptchaV3&SceneId=132fltrt&CertifyId=response-certify-id",
            {
                "Result": {
                    "securityToken": "security-token",
                    "VerifyResult": True,
                    "certifyId": "response-certify-id",
                }
            },
        )
        driver = FakeDriver([request])

        result = capture_captcha_result(
            captcha_url="http://fe-m.duku.cn/#/captcha",
            timeout_seconds=1,
            poll_interval=0,
            driver_factory=lambda: driver,
            decode_response=lambda body, _encoding: body,
        )

        self.assertEqual(
            result,
            CaptchaResult(
                security_token="security-token",
                certify_id="response-certify-id",
                scene_id="132fltrt",
            ),
        )
        self.assertEqual(driver.opened_urls, ["http://fe-m.duku.cn/#/captcha"])
        self.assertTrue(driver.quit_called)

    def test_capture_captcha_result_reads_chrome_cdp_network_body(self):
        verify_url = "https://dqdr8o-verify.captcha-open.aliyuncs.com/"
        log_entries = [
            performance_entry(
                "Network.requestWillBeSent",
                {
                    "requestId": "captcha-1",
                    "request": {
                        "url": verify_url,
                        "postData": "Action=VerifyCaptchaV3&SceneId=132fltrt&CertifyId=request-certify-id",
                    },
                },
            ),
            performance_entry(
                "Network.responseReceived",
                {
                    "requestId": "captcha-1",
                    "response": {"url": verify_url},
                },
            ),
            performance_entry(
                "Network.loadingFinished",
                {"requestId": "captcha-1"},
            ),
        ]
        driver = FakeCdpDriver(
            log_entries,
            json.dumps(
                {
                    "Result": {
                        "securityToken": "security-token",
                        "VerifyResult": True,
                        "certifyId": "response-certify-id",
                    }
                }
            ),
        )

        result = capture_captcha_result(
            captcha_url="http://fe-m.duku.cn/#/captcha",
            timeout_seconds=1,
            poll_interval=0,
            driver_factory=lambda: driver,
        )

        self.assertEqual(
            result,
            CaptchaResult(
                security_token="security-token",
                certify_id="response-certify-id",
                scene_id="132fltrt",
            ),
        )
        self.assertEqual(
            driver.executed_command,
            ("Network.getResponseBody", {"requestId": "captcha-1"}),
        )
        self.assertEqual(driver.opened_urls, ["http://fe-m.duku.cn/#/captcha"])
        self.assertTrue(driver.quit_called)

    def test_failed_aliyun_verify_result_is_not_accepted_as_captcha_result(self):
        body = json.dumps(
            {
                "Result": {
                    "VerifyCode": "F001",
                    "VerifyResult": False,
                    "certifyId": "failed-certify-id",
                }
            }
        )

        self.assertIsNone(_extract_captcha_result_from_text(body))
        self.assertIn("VerifyCode=F001", _captcha_failure_message(body))

    def test_chrome_cdp_command_uses_plain_chrome_without_webdriver_flags(self):
        command = _build_chrome_cdp_command(
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            9222,
            Path("/tmp/duku-profile"),
        )

        self.assertEqual(command[0], "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        self.assertIn("--remote-debugging-port=9222", command)
        self.assertIn("--remote-allow-origins=*", command)
        self.assertIn("--user-data-dir=/tmp/duku-profile", command)
        self.assertIn("about:blank", command)
        self.assertFalse(any("enable-automation" in item for item in command))
        self.assertFalse(any("user-agent" in item for item in command))


if __name__ == "__main__":
    unittest.main()

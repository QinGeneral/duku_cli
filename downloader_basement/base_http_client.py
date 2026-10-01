import json
import os
import shutil
from pathlib import Path
from io import BytesIO
import requests
from downloader_basement.utils import save_to_file, read_from_file

class BaseHttpClient(object):
    # 是否下载音频
    is_download_audio = True
    # 是否下载视频
    is_download_video = True
    key_header_cookie = 'Cookie'
    header_file = 'header.json'
    chrome_app_path = '/Applications/Google Chrome.app'

    header = {}
    cache_dir = ''
    home_page_url = ''
    get_validate_header_url = ''

    def __init__(self):
        self.prepare_cache()
        # self.validate_header_if_need()

    def prepare_cache(self):
        if not os.path.exists(self.cache_dir):
            os.mkdir(self.cache_dir)

    def get_cookies_header(self):
        """
        获取浏览器cookies和请求头信息

        Returns:
            tuple: 包含cookies和请求头的元组
                - cookies (list): 包含浏览器cookies的列表
                - header (dict): 包含请求头的字典
        """
        if Path(self.chrome_app_path).exists():
            from selenium.webdriver.chrome.service import Service
            from seleniumwire import webdriver
            from webdriver_manager.chrome import ChromeDriverManager

            options = webdriver.ChromeOptions()
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        else:
            print('未找到浏览器驱动，请在安装')
            exit(0)

        driver.execute_cdp_cmd("Network.enable", {})
        driver.maximize_window()
        driver.get(self.home_page_url)

        self.login(driver)

        cookies = driver.get_cookies()
        header = {}
        for request in driver.requests:
            if request.response and request.url == self.get_validate_header_url:
                header = request.headers
                break

        driver.quit()

        return cookies, header

    def login(self, driver):
        pass

    def validate_header_if_need(self):
        header_cache_file = os.path.join(self.cache_dir, self.header_file)
        if self.is_header_still_valid(header_cache_file):
            print("header still work")
            return

        print("header expired")
        # header 过期
        cookies, validate_header = self.get_cookies_header()
        for key in validate_header.keys():
            if key == self.key_header_cookie:
                self.header[key] = validate_header[key]
        save_to_file(header_cache_file, json.dumps(self.header))

    def is_header_still_valid(self, header_file):
        """
        判断缓存的头部信息是否仍然有效。
        Args:
            header_file (str): 缓存头部信息的文件路径。
        Returns:
            bool: 如果缓存的头部信息仍然有效，则返回True；否则返回False。
        """
        header_from_file = {}
        # 检查 header 缓存
        if os.path.exists(header_file):
            header_from_file = json.loads(read_from_file(header_file))
        else:
            return False
        self.header = header_from_file
        return self.is_header_still_valid_by_request()

    def is_header_still_valid_by_request(self):
        pass

    def get(self, url, params = None):
        try:
            response = requests.get(url, headers=self.header, params=params)
        except requests.exceptions.SSLError:
            response = requests.get(url, headers=self.header, params=params, verify=False)

        if response.status_code == 200:
            return response.text
        else:
            print("请求失败", response)
            print("错误码:", response.status_code)
            return response.status_code

    def get_cache_file_name(self, source_file_name):
        directory, filename = os.path.split(source_file_name)
        directory = os.path.join(directory, "cache/")
        dest_file_name = os.path.join(directory, filename)
        if not os.path.exists(directory):
            os.makedirs(directory)
        # todo 移除异常处理逻辑
        if os.path.exists(source_file_name):
            shutil.move(source_file_name, dest_file_name)
        return dest_file_name

    def get_with_cache(self, json_file_name, url, params, force_remote=False):
        return self.request_with_cache(json_file_name, url, params, False, force_remote)

    def post_with_cache(self, json_file_name, url, data, force_remote=False):
        return self.request_with_cache(json_file_name, url, data, True, force_remote)

    def request_with_cache(self, json_file_name, url, data, is_post, force_remote):
        json_file_name = self.get_cache_file_name(json_file_name)

        response_json = "{}"
        is_find_cache_file = False
        if os.path.exists(json_file_name) and not force_remote:
            response_json = read_from_file(json_file_name)
            is_find_cache_file = True
        else:
            if is_post:
                response_json = self.post(url, data)
            else:
                response_json = self.get(url, data)
            if type(response_json) == str:
                save_to_file(json_file_name, response_json)
            is_find_cache_file = False
        return response_json

    def post(self, url, data):
        try:
            response = requests.post(url, json=data, headers=self.header)
        except requests.exceptions.SSLError:
            response = requests.post(url, json=data, headers=self.header, verify=False)
            print("Post SSLError, set verify=False")
        except requests.exceptions.ProxyError:
            response = requests.post(url, json=data, headers=self.header, verify=False)
            print("Post ProxyError, set verify=False")
            return

        # 处理响应
        if response.ok:
            return response.text
        else:
            print("请求失败", response)
            print("错误码:", response.status_code)
            return response.status_code

    def download_file(self, url, path):
        try:
            with requests.get(url, stream=True) as r:
                r.raise_for_status()
                with open(path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
        except Exception as e:
            print(f"download file exception {e}", url)

    def download_m3u8_video(self, m3u8_url, output_path):
        if not self.is_download_video:
            print("is_download_video m3u8 is false")
            return
        from downloader_basement.m3u8_downloader import download_m3u8_video

        download_m3u8_video(url=m3u8_url, output_path=output_path)

    def download_mp4(self, url, output_path):
        if not self.is_download_video:
            print("is_download_video is false")
            return
        self.download_file(url, output_path)

    def download_audio(self, url, output_path):
        if not self.is_download_audio:
            print("is_download_audio is false")
            return
        self.download_file(url, output_path)

    def download_image(self, image_url, file_name):
        if os.path.exists(file_name):
            print(f"图片已存在：{file_name}")
            return
        print(f"下载图片：{file_name}", image_url)
        try:
            response = requests.get(image_url)
        except requests.exceptions.SSLError:
            response = requests.get(image_url, verify=False)
            print("download image exception, retry", image_url)
        from PIL import Image

        img = Image.open(BytesIO(response.content))
        if '.' not in file_name:  # 确保文件名有扩展名
            file_name += '.jpg'
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.save(file_name)

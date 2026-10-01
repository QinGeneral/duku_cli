from Crypto.Cipher import AES
import m3u8
import requests
import os

from downloader_basement import downloader_configs


# 下载m3u8文件
def download_m3u8(url, path):
    r = requests.get(url)
    with open(path, "wb") as f:
        f.write(r.content)


# 解析m3u8文件
def parse_m3u8(path):
    with open(path, "r") as f:
        lines = f.readlines()
        video_urls = []
        for line in lines:
            if line.startswith("#"):
                continue
            video_urls.append(line.strip())
        return video_urls


def get_key(key_url):
    try:
        r = requests.get(key_url)
    except requests.exceptions.SSLError:
        r = requests.get(key_url, verify=False)
        print("get_key SSLError, set verify=False")
    return r.content


store_key = None


# 下载ts文件
def download_ts(url, path, key):
    global store_key
    cryptor = None
    if key != None:
        key_content = get_key(key.uri)
        if len(key_content) != 0:
            store_key = key_content
        elif store_key != None:
            key_content = store_key
        cryptor = AES.new(key_content, AES.MODE_CBC)
    try:
        r = requests.get(url)
    except requests.exceptions.ChunkedEncodingError:
        print("Download ts exception ChunkedEncodingError, retry", url)
        download_ts(url, path, key)
        return
    except requests.exceptions.SSLError:
        print("Download ts exception SSLError, retry", url)
        download_ts(url, path, key)
        return
    except requests.exceptions.ConnectionError:
        print("Download ts exception ConnectionError, retry", url)
        download_ts(url, path, key)
        return
    with open(path, "wb") as f:
        if cryptor != None:
            f.write(cryptor.decrypt(r.content))
        else:
            f.write(r.content)


# 清理ts文件
def clean_ts(filenames):
    for filename in filenames:
        os.remove(filename)


# 下载m3u8视频
def download_m3u8_video(url, output_path):
    if not downloader_configs.is_download_video:
        print("is_download_video is False, skip downloading video.")
        return
    dir_path, file_name = os.path.split(output_path)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

    m3u8_file_path = os.path.join(dir_path, "temp.m3u8")
    ts_dir_path = os.path.join(dir_path, "ts")
    if not os.path.exists(ts_dir_path):
        os.makedirs(ts_dir_path)

    # 下载m3u8文件
    download_m3u8(url, m3u8_file_path)

    # 解析m3u8文件
    video_urls = parse_m3u8(m3u8_file_path)
    video = m3u8.load(url)
    keys = video.keys

    # 下载ts文件
    ts_filenames = []
    video_ts_url_root = url.rsplit("/", 1)[0] + "/"
    for i, video_url in enumerate(video_urls):
        ts_filename = os.path.join(ts_dir_path, "{}.ts".format(i))
        print(f"TS ：{output_path} 进度: {i}/{len(video_urls)}")
        download_ts(
            video_url if "http" in video_url else video_ts_url_root + video_url,
            ts_filename,
            keys[i] if i < len(keys) else keys[0],
        )
        ts_filenames.append(ts_filename)

    concat_cmd = '"concat:'
    for ts_file in ts_filenames:
        concat_cmd += ts_file + "|"
    concat_cmd = concat_cmd[:-1] + '"'

    # 删除临时文件
    os.remove(m3u8_file_path)

    output_path = output_path.replace(" ", "\ ")
    output_path = output_path.replace("&", "\&")
    output_path = output_path.replace("(", "\(")
    output_path = output_path.replace(")", "\)")
    output_path = output_path.replace("|", "\|")
    output_path = output_path.replace("<", "\<")
    output_path = output_path.replace(">", "\>")
    output_path = output_path.replace("，", "\，")
    output_path = output_path.replace("《", "\《")
    output_path = output_path.replace("》", "\》")
    output_path = output_path.replace("'", "\\'")
    output_path = output_path.replace("\"", "\\\"")
    print("output_path: ", output_path)
    # 转换成mp4格式
    os.system(f"ffmpeg -y -i {concat_cmd} -c copy {output_path}")

    # 清理ts文件
    clean_ts(ts_filenames)
    os.removedirs(ts_dir_path)


# def example():
#     url = "https://m.igetget.com/ddmedia/public/v1/m3u8/3502177924415528/52/m.m3u8"
#     download_m3u8_video(url, "./听书/《安卓传奇》| 杨蕾解读/《安卓传奇》| 杨蕾解读.aac")

# example()

# concat_cmd="concat:得到/听书/《安卓传奇》| 杨蕾解读/ts/0.ts|得到/听书/《安卓传奇》| 杨蕾解读/ts/1.ts"
# concat_cmd = concat_cmd.replace("|", "\|")
# concat_cmd = concat_cmd.replace(" ", "\ ")
# output_path="得到/听书/《安卓传奇》| 杨蕾解读/《安卓传奇》| 杨蕾解读.aac"

# output_path = output_path.replace(" ", "\ ")
# output_path = output_path.replace("&", "\&")
# output_path = output_path.replace("(", "\(")
# output_path = output_path.replace(")", "\)")
# output_path = output_path.replace("|", "\|")
# output_path = output_path.replace("<", "\<")
# output_path = output_path.replace(">", "\>")
# output_path = output_path.replace("，", "\，")
# output_path = output_path.replace("'", "\\'")
# output_path = output_path.replace("\"", "\\\"")
# os.system(f"ffmpeg -y -i {concat_cmd} -c copy {output_path}")
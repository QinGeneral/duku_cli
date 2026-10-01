# duku_cli · 读库下载助手

本项目用于辅助下载读库文章/电子书及“听”栏目，并将 Markdown 转成 EPUB。保留原有脚本与 `duku` 命令入口，Python 3.10 及以上可用。

使用前提：

1. 你已购买读库会员；
2. 你可以自行获取有效的 `satoken`；
3. 下载内容仅用于个人阅读，不做传播或售卖。

## 安装

安装发布版（Python 3.10 及以上）：

```bash
uv tool install duku-cli
duku --help
```

升级：

```bash
uv tool upgrade duku-cli
```

需要在 Python 项目中使用时可执行 `uv add duku-cli`，或在虚拟环境中执行 `python -m pip install duku-cli`。

从源码开发：

```bash
git clone https://github.com/QinGeneral/duku_cli.git
cd duku_cli
```

在项目目录下创建虚拟环境并安装：

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell：.venv\Scripts\Activate.ps1
python -m pip install -e .
```

安装完成后即可直接使用 `duku` 命令：

```bash
duku -h
```

如果你只是想装依赖，也可以继续使用：

```bash
pip install -r requirements.txt
```

如需把 Markdown 转 EPUB，还需要本机安装 [pandoc](https://pandoc.org/installing.html)。短信登录需要 Chrome / Chromium，并由你在浏览器中完成安全验证；旧版 m3u8 下载辅助函数需要 `ffmpeg`。

`downloader_basement` 已作为普通 Python 包包含在项目中，无需初始化子模块或配置 GitHub SSH 密钥。

## 配置 satoken

推荐方式一：保存到本地配置

```bash
duku login --satoken "<你的 satoken>"
```

默认会保存到 `~/.duku/config.json`。可用 `DUKU_CONFIG_DIR` 更改配置目录。凭据优先级为命令行参数、`DUKU_SATOKEN` 环境变量、本地配置。环境变量不会自动从 `.env` 文件加载。

配置、浏览器登录资料和下载内容均属于本地私人数据，请勿提交或附到 issue 中。

如果需要通过手机号短信验证码登录，可以使用：

```bash
duku phoneCodeLogin --phone "<你的手机号>"
```

命令会打开 `http://fe-m.duku.cn/#/captcha`，请在浏览器中完成安全验证；随后工具会发送短信验证码，输入短信验证码后会自动登录并把返回的 `token` 保存为后续请求使用的 `satoken`。

推荐方式二：使用环境变量

```bash
export DUKU_SATOKEN="<你的 satoken>"
```

也可以只在单次命令里临时传入：

```bash
duku download --satoken "<你的 satoken>"
```

## CLI 用法

### 1）下载读库内容

```bash
duku download --output-dir 读库v2
duku download --output-dir 读库v2 --download-audio
duku download --output-dir 读库v2 --download-audio --download-video
```

下载时会合并“总目”和“最新”目录，按分类 ID 去重，避免漏掉尚未收录到总目的新一期；内容仍按年份和期号保存。

常用参数：

- `--output-dir`：下载输出目录，默认 `读库v2`
- `--download-audio`：下载音频（默认不下载）
- `--download-video`：下载视频（默认不下载）
- `--satoken`：本次运行临时使用的 token

### 2）下载“听”栏目

默认拉取全部栏目和详情，并下载其中的音频与视频：

```bash
duku listen --output-dir 听
```

只下载指定栏目，可使用栏目序号、栏目 ID 或名称：

```bash
duku listen --category 13
duku listen --category 641390
duku listen --category 杨照谈诗
```

需要一次下载多个栏目时，可重复传入 `--category`。

只更新列表和详情 JSON：

```bash
duku listen --output-dir 听 --metadata-only
```

也可以按媒体类型跳过：

```bash
duku listen --skip-video
duku listen --skip-audio
```

内容会按栏目名组织：

```text
听/
  栏目列表.md
  杨照谈诗/
    栏目介绍.md
    001-项目标题-bookId/
      介绍.md
      项目标题.mp3
```

栏目介绍包含封面和项目清单；每个项目的介绍包含作者、摘要、时长、发布时间、封面和正文介绍。原始接口数据仍保存在 `听/metadata`。视频 FileId 会通过腾讯云点播接口解析，优先下载可用的最高分辨率转码；没有转码时回退原视频，文件可能较大。

### 3）批量转换 EPUB

```bash
duku convert all --base-dir ./读库v2
```

### 4）转换单本 EPUB

```bash
duku convert one --md-dir ./某本书目录 --epub-name ./某本书.epub
```

## 兼容说明

- 安装后推荐使用 `duku` 命令。
- `duku_cli.py` 仍可直接执行，适合本地开发调试。
- `duku_download.py` 为历史脚本，默认流程仍基于 `duku_download_v2.py`。


## 开发与验证

```bash
python -m pip install -e '.[dev]'
python -m unittest discover -s tests -v
python scripts/check_public_tree.py
python -m build
```

现有测试使用模拟 HTTP 响应和临时目录，不会调用真实登录、发送短信或下载会员内容。GitHub Actions 在 Python 3.10 / 3.12 上运行隐私检查、现有测试、构建和安装包 CLI 检查。

历史 `duku_download.py` 保留在项目中；其旧接口 token 改为从 `DUKU_LEGACY_TOKEN` 环境变量读取，与新版 `DUKU_SATOKEN` 分开。旧接口的可用性需自行验证，默认 CLI 仍走 v2 接口。

## 隐私与开源范围

本仓库只包含源码、现有测试、默认封面和工程文档。不包含旧 Git 历史、抓包、APK、账号配置、缓存或已下载的文章、电子书及音视频。默认输出目录和常见私人文件已加入 `.gitignore`；使用自定义输出目录时，请自行将其加入忽略规则。

隐私检查只显示文件位置和风险类型，不打印敏感值。它检查 Git 跟踪文件和未忽略文件中的常见凭据及私人文件，不能覆盖所有敏感数据格式；发布前仍需检查实际 diff 和安装包。

## 许可证与贡献

保留原仓库的 [GPLv3 许可证](LICENSE)，打包元数据与之保持一致。源码来源和基础库说明见 [NOTICE.md](NOTICE.md)。软件许可证不授予读库内容、商标或服务的权利；项目为非官方工具。问题和贡献流程见 [CONTRIBUTING.md](CONTRIBUTING.md)，敏感信息处理见 [SECURITY.md](SECURITY.md)。


实际功能验证结果和覆盖范围见 [VERIFICATION.md](VERIFICATION.md)。


发布维护流程见 [RELEASING.md](RELEASING.md)。

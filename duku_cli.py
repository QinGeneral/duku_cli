import argparse
import importlib.util
from pathlib import Path


def _import_phone_login():
    try:
        import duku_phone_login

        return duku_phone_login
    except ModuleNotFoundError as exc:
        if exc.name != 'duku_phone_login':
            raise

    module_path = Path(__file__).with_name('duku_phone_login.py')
    spec = importlib.util.spec_from_file_location('duku_phone_login', module_path)
    if spec is None or spec.loader is None:
        raise ModuleNotFoundError(
            f'无法从 {module_path} 加载 duku_phone_login'
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_parser():
    parser = argparse.ArgumentParser(
        prog='duku',
        description='读库下载与转换工具（CLI）',
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    login_parser = subparsers.add_parser('login', help='保存 satoken 到本地配置')
    login_parser.add_argument(
        '--satoken',
        required=True,
        help='读库请求头中的 satoken，支持直接粘贴 satoken 值或 satoken=xxx',
    )

    phone_login_parser = subparsers.add_parser(
        'phoneCodeLogin',
        help='通过手机短信验证码登录并保存 satoken',
    )
    phone_login_parser.add_argument(
        '--phone',
        help='登录手机号；未传时会交互式输入',
    )
    phone_login_parser.add_argument(
        '--captcha-url',
        default='http://fe-m.duku.cn/#/captcha',
        help='安全验证页面 URL（默认：http://fe-m.duku.cn/#/captcha）',
    )
    phone_login_parser.add_argument(
        '--captcha-timeout',
        type=int,
        default=300,
        help='等待用户完成安全验证的超时时间，单位秒（默认：300）',
    )
    phone_login_parser.add_argument(
        '--verify-code',
        help='短信验证码；未传时会交互式输入',
    )

    download_parser = subparsers.add_parser('download', help='下载读库内容')
    download_parser.add_argument(
        '--output-dir',
        default='读库v2',
        help='下载输出目录（默认：读库v2）',
    )
    download_parser.add_argument(
        '--download-audio',
        action='store_true',
        help='下载音频（默认关闭）',
    )
    download_parser.add_argument(
        '--download-video',
        action='store_true',
        help='下载视频（默认关闭）',
    )
    download_parser.add_argument(
        '--satoken',
        help='本次运行临时使用的 satoken；未传时会读取本地配置或 DUKU_SATOKEN 环境变量',
    )

    listen_parser = subparsers.add_parser('listen', help='拉取“听”栏目并下载音频和视频')
    listen_parser.add_argument(
        '--output-dir',
        default='听',
        help='下载输出目录（默认：听）',
    )
    listen_parser.add_argument(
        '--category',
        action='append',
        help='只下载指定栏目；可传序号、栏目 ID 或名称，可重复使用',
    )
    listen_parser.add_argument(
        '--metadata-only',
        action='store_true',
        help='只拉取列表和详情 JSON，不下载媒体',
    )
    listen_parser.add_argument(
        '--skip-audio',
        action='store_true',
        help='不下载音频',
    )
    listen_parser.add_argument(
        '--skip-video',
        action='store_true',
        help='不下载视频',
    )
    listen_parser.add_argument(
        '--satoken',
        help='本次运行临时使用的 satoken；未传时会读取本地配置或 DUKU_SATOKEN 环境变量',
    )

    convert_parser = subparsers.add_parser('convert', help='将 Markdown 转换为 EPUB')
    convert_subparsers = convert_parser.add_subparsers(dest='convert_command', required=True)

    convert_all_parser = convert_subparsers.add_parser('all', help='批量转换目录内所有书籍')
    convert_all_parser.add_argument(
        '--base-dir',
        default='./',
        help='要扫描的根目录（默认：当前目录）',
    )

    convert_one_parser = convert_subparsers.add_parser('one', help='转换单本书')
    convert_one_parser.add_argument('--md-dir', required=True, help='Markdown 文件所在目录')
    convert_one_parser.add_argument('--epub-name', required=True, help='输出 epub 路径')

    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()

    try:
        if args.command == 'login':
            from duku_config import save_satoken

            config_path = save_satoken(args.satoken)
            print(f'satoken 已保存到 {config_path}')
            return

        if args.command == 'phoneCodeLogin':
            phone_login = _import_phone_login()
            from duku_config import save_satoken

            phone = args.phone or input('请输入手机号: ').strip()
            captcha = phone_login.capture_captcha_result(
                captcha_url=args.captcha_url,
                timeout_seconds=args.captcha_timeout,
            )
            print('安全验证通过，正在发送短信验证码...')
            phone_login.send_verify_code(
                phone,
                captcha.security_token,
                captcha.certify_id,
                captcha.scene_id,
            )
            print('短信验证码已发送。')
            verify_code = args.verify_code or input('请输入短信验证码: ').strip()
            token = phone_login.login_with_phone_code(phone, verify_code)
            config_path = save_satoken(token)
            print(f'登录成功，satoken 已保存到 {config_path}')
            return

        if args.command == 'download':
            from duku_download_v2 import download_read_tab
            from duku_http_client import get_http_client

            http_client = get_http_client(args.satoken)
            http_client.is_download_audio = args.download_audio
            http_client.is_download_video = args.download_video
            download_read_tab(output_dir=args.output_dir)
            return

        if args.command == 'listen':
            from duku_http_client import get_http_client
            from duku_listen import download_listen

            http_client = get_http_client(args.satoken)
            metadata_only = args.metadata_only
            summary = download_listen(
                output_dir=args.output_dir,
                download_audio=not metadata_only and not args.skip_audio,
                download_video=not metadata_only and not args.skip_video,
                client=http_client,
                category_selectors=args.category,
            )
            print(
                '听栏目处理完成：'
                f"{summary['categories']} 个栏目，{summary['items']} 条详情，"
                f"去重后 {summary['unique_items']} 条内容，"
                f"下载 {summary['downloaded']}，复用 {summary['reused']}，"
                f"已存在 {summary['exists']}，失败 {summary['failed']}"
            )
            return

        if args.command == 'convert':
            from md_to_epub import convert_all, convert_one

            if args.convert_command == 'all':
                convert_all(base_dir=args.base_dir)
                return
            if args.convert_command == 'one':
                convert_one(args.md_dir, args.epub_name)
                return
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        parser.exit(2, f'错误: {exc}\n')

    parser.error('未知命令')


if __name__ == '__main__':
    main()

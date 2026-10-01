import os
import subprocess
from datetime import date
from pathlib import Path

from PIL import Image


def get_all_md_file(dir_path):
    files = os.listdir(dir_path)
    files = [item for item in files if item.endswith('.md')]
    files = [os.path.join(dir_path, item) for item in files]
    return sorted(files)


def cut_image(path, target):
    img = Image.open(path)
    area = (510, 130, 970, 804)
    cropped_img = img.crop(area)
    cropped_img.save(target)


def convert_one(dir_path, epub_name):
    if os.path.exists(epub_name):
        print(epub_name, ' already exists')
        return

    files = get_all_md_file(dir_path)
    if not files:
        print('no md file in ', dir_path)
        return

    cmd = [
        'pandoc',
        *files,
        '-o',
        epub_name,
        '--metadata',
        f"title={os.path.basename(epub_name).split('.')[0]}",
        '--metadata',
        'author=作者：读库',
        '--metadata',
        'publisher=出版发行：新星出版社',
        '--metadata',
        'rights=版权所有：@读库',
        '--metadata',
        f'date=电子书生成日期：{date.today().isoformat()}',
    ]

    cover = os.path.join(dir_path, 'cover.png')
    target = os.path.join(dir_path, 'cover_cut.png')
    if os.path.exists(cover):
        cut_image(cover, target)
        cmd.extend(['--epub-cover-image', target])
    else:
        default_cover = Path(__file__).resolve().with_name('cover_default.png')
        if not default_cover.exists():
            default_cover = Path(__file__).resolve().parent / 'duku_assets' / 'cover_default.png'
        if default_cover.exists():
            cmd.extend(['--epub-cover-image', str(default_cover)])

    subprocess.run(cmd, check=True)


def convert_all(base_dir='./'):
    year_dirs = os.listdir(base_dir)
    year_dirs = [
        item for item in year_dirs if os.path.isdir(os.path.join(base_dir, item)) and item != '.git'
    ]
    for year_dir in year_dirs:
        year_dir_path = os.path.join(base_dir, year_dir)
        one_year_dirs = os.listdir(year_dir_path)
        one_year_dirs = [
            item for item in one_year_dirs if os.path.isdir(os.path.join(year_dir_path, item))
        ]
        for one_year_dir in one_year_dirs:
            book_name = one_year_dir
            if book_name.startswith('《') and book_name.endswith('》'):
                book_name = book_name[1:-1]
            epub_name = os.path.join(year_dir_path, book_name + '.epub')
            print(epub_name, ' convert begin')
            convert_one(os.path.join(year_dir_path, one_year_dir), epub_name)
            print(epub_name, ' convert finish')


if __name__ == '__main__':
    convert_all()

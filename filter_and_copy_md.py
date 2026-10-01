import os
import shutil
import glob


def filter_and_copy_md_files():
    """
    递归查找当前目录及所有子目录的Markdown文件，平铺复制到Downloads/duku文件夹
    过滤掉包含"即将发货"、"全文音频版"的文件以及README文件
    同名文件进行覆盖
    特殊处理：识别文章作者，将相同作者的文章合并到对应的Markdown文件中
    """
    # 获取当前目录及所有子目录的.md文件（递归查找）
    current_dir = os.getcwd()
    md_files = glob.glob("**/*.md", recursive=True)
    
    if not md_files:
        print("当前目录及子目录没有找到Markdown文件")
        return
    
    # 创建目标目录
    home_dir = os.path.expanduser("~")
    target_dir = os.path.join(home_dir, "Downloads", "duku")
    
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)
        print(f"创建目录: {target_dir}")
    
    # 过滤条件
    filter_keywords = ["即将发货", "全文音频版"]
    
    copied_count = 0
    filtered_count = 0
    overwritten_count = 0
    author_articles = {}  # 存储按作者分类的文章 {作者名: [文章列表]}
    
    for md_file in md_files:
        # 检查文件名是否包含过滤关键词或是README文件
        file_name = os.path.basename(md_file)
        file_name_lower = file_name.lower()
        
        # 过滤条件：包含关键词或是README文件
        should_filter = (
            any(keyword in file_name for keyword in filter_keywords) or
            file_name_lower.startswith('readme')
        )
        
        if should_filter:
            if file_name_lower.startswith('readme'):
                print(f"过滤文件: {md_file} (README文件)")
            else:
                print(f"过滤文件: {md_file} (包含: {', '.join([kw for kw in filter_keywords if kw in file_name])})")
            filtered_count += 1
        else:
            # 检查文章作者
            source_path = os.path.join(current_dir, md_file)
            author = get_article_author(source_path)
            
            if author:
                # 读取文件内容
                try:
                    with open(source_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # 提取文件名作为标题（去掉.md扩展名）
                    title = os.path.splitext(file_name)[0]
                    
                    # 按作者分类存储文章
                    if author not in author_articles:
                        author_articles[author] = []
                    
                    author_articles[author].append({
                        'title': title,
                        'content': content,
                        'source': md_file
                    })
                    print(f"识别作者文章: {file_name} - 作者: {author} (来源: {md_file})")
                except Exception as e:
                    print(f"读取作者文章失败: {md_file} - {str(e)}")
            else:
                # 没有识别到作者的文章，单独复制
                target_path = os.path.join(target_dir, file_name)
                
                # 检查是否会覆盖同名文件
                will_overwrite = os.path.exists(target_path)
                
                try:
                    shutil.copy2(source_path, target_path)
                    if will_overwrite:
                        print(f"覆盖文件: {file_name} (来源: {md_file})")
                        overwritten_count += 1
                    else:
                        print(f"拷贝成功: {file_name} (来源: {md_file})")
                    copied_count += 1
                except Exception as e:
                    print(f"拷贝失败: {md_file} - {str(e)}")
    
    # 处理作者文章合并
    total_author_articles = 0
    for author, articles in author_articles.items():
        merge_author_articles(author, articles, target_dir)
        total_author_articles += len(articles)
    
    print(f"\n操作完成！")
    print(f"总共找到: {len(md_files)} 个Markdown文件")
    print(f"已拷贝: {copied_count} 个文件")
    print(f"其中覆盖: {overwritten_count} 个文件")
    print(f"已过滤: {filtered_count} 个文件")
    print(f"作者文章: {total_author_articles} 个，按 {len(author_articles)} 个作者合并")
    print(f"目标目录: {target_dir}")


def get_article_author(file_path):
    """
    获取文章作者
    通过读取文件第四行来获取作者信息
    兼容逻辑：如果第四行是图片链接，则读取第五行
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
            # 检查第四行
            if len(lines) >= 4:
                fourth_line = lines[3].strip()  # 第四行（索引为3）
                
                # 判断第四行是否是图片链接
                if is_image_link(fourth_line):
                    # 如果第四行是图片链接，尝试读取第五行
                    if len(lines) >= 5:
                        fifth_line = lines[4].strip()  # 第五行（索引为4）
                        if is_valid_author_name(fifth_line):
                            return fifth_line
                else:
                    # 第四行不是图片链接，检查是否是有效的作者名
                    if is_valid_author_name(fourth_line):
                        return fourth_line
                        
    except Exception as e:
        print(f"读取文件失败 {file_path}: {str(e)}")
    return None


def is_image_link(line):
    """
    判断一行是否是图片链接
    支持 Markdown 格式: ![alt](url) 和 HTML 格式: <img src="url">
    """
    line = line.strip()
    if not line:
        return False
    
    # Markdown 图片格式: ![alt](url)
    if line.startswith('![') and '](' in line and line.endswith(')'):
        return True
    
    # HTML img 标签
    if line.startswith('<img') and 'src=' in line and line.endswith('>'):
        return True
    
    # 纯图片URL（常见图片扩展名）
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg']
    if any(ext in line.lower() for ext in image_extensions):
        return True
    
    return False


def is_valid_author_name(line):
    """
    判断一行是否是有效的作者名
    """
    line = line.strip()
    # 如果第四行不为空且不是纯标点符号，认为是作者名
    if line and line not in ['', '-', '--', '---', '====', '***', '***', '___']:
        # 排除明显不是作者名的内容
        invalid_patterns = ['http://', 'https://', 'www.', '.com', '.cn', '.org']
        if not any(pattern in line.lower() for pattern in invalid_patterns):
            return True
    return False


def is_zhang_lixian_article(file_path):
    """
    判断是否是张立宪的文章
    通过读取文件第四行来判断
    """
    author = get_article_author(file_path)
    if author:
        zhang_keywords = ["张立宪", "老六"]
        return any(keyword in author for keyword in zhang_keywords)
    return False


def merge_author_articles(author, articles, target_dir):
    """
    将同一作者的文章合并到一个Markdown文件中
    """
    if not articles:
        return
    
    # 清理作者名，用于文件名
    safe_author = author.replace('/', '_').replace('\\', '_').replace(':', '_')
    
    merged_content = f"# {author}文章合集\n\n"
    merged_content += f"本文件包含 {len(articles)} 篇{author}的文章\n\n"
    merged_content += "---\n\n"
    
    for article in articles:
        # 添加文章标题
        merged_content += f"## {article['title']}\n\n"
        
        # 添加来源信息
        merged_content += f"*来源文件: {article['source']}*\n\n"
        
        # 添加文章内容
        merged_content += article['content']
        
        # 添加分隔符
        merged_content += "\n\n---\n\n"
    
    # 保存合并后的文件
    merged_file_path = os.path.join(target_dir, f"{safe_author}文章合集.md")
    try:
        with open(merged_file_path, 'w', encoding='utf-8') as f:
            f.write(merged_content)
        print(f"{author}文章合并完成: {merged_file_path}")
    except Exception as e:
        print(f"合并{author}文章失败: {str(e)}")


if __name__ == "__main__":
    filter_and_copy_md_files() 
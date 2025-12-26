import requests
from bs4 import BeautifulSoup
import time
import os
import re
import json
import random
from ebooklib import epub
from abc import ABC, abstractmethod

class VerificationError(Exception):
    """当检测到验证码或风控时抛出"""
    pass

# --- 策略模式：格式化器 ---

class BookFormatter(ABC):
    @abstractmethod
    def detect_existing_progress(self, book_data, save_dir, split_files):
        """
        检测已下载的进度。
        返回: 已下载的最后一个章节的索引 (int), 如果没有则返回 -1
        """
        pass

    @abstractmethod
    def initialize(self, book_data, save_dir, split_files, append_mode=False, downloader=None):
        """
        初始化保存环境。
        返回: context (上下文对象，用于后续步骤)
        """
        pass

    @abstractmethod
    def write_chapter(self, context, chapter_data, content, index):
        """
        写入单个章节。
        """
        pass

    @abstractmethod
    def finalize(self, context):
        """
        完成保存。
        返回: 最终文件或目录的路径
        """
        pass
    
    def get_final_path(self, save_dir, book_data, split_files):
        """获取最终文件路径，用于跳过下载时返回"""
        if split_files:
            return os.path.join(save_dir, book_data['title'])
        else:
            # 默认实现，子类可覆盖
            return os.path.join(save_dir, f"{book_data['title']}.txt")

class TxtFormatter(BookFormatter):
    def detect_existing_progress(self, book_data, save_dir, split_files):
        last_index = -1
        
        if split_files:
            book_folder = os.path.join(save_dir, book_data['title'])
            if os.path.exists(book_folder):
                pattern = re.compile(r'^(\d{3})_')
                for fname in os.listdir(book_folder):
                    match = pattern.match(fname)
                    if match:
                        idx = int(match.group(1)) - 1
                        if idx > last_index:
                            last_index = idx
        else:
            filepath = os.path.join(save_dir, f"{book_data['title']}.txt")
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        f.seek(0, 2)
                        fsize = f.tell()
                        seek_size = min(fsize, 20480) # 20KB
                        f.seek(fsize - seek_size)
                        content = f.read()
                        
                        matches = re.findall(r'=== (.+?) ===', content)
                        if matches:
                            last_title = matches[-1]
                            # 倒序查找
                            for i in range(len(book_data['chapters']) - 1, -1, -1):
                                if book_data['chapters'][i]['title'] == last_title:
                                    last_index = i
                                    break
                except:
                    pass
        return last_index

    def initialize(self, book_data, save_dir, split_files, append_mode=False, downloader=None):
        context = {
            'downloader': downloader,
            'book_data': book_data,
            'save_dir': save_dir,
            'split_files': split_files,
            'files_created': []
        }
        
        if split_files:
            # 创建目录
            book_folder = os.path.join(save_dir, book_data['title'])
            if not os.path.exists(book_folder):
                os.makedirs(book_folder)
            context['target_dir'] = book_folder
            
            # 如果不是追加模式，或者简介不存在，则写入简介
            intro_path = os.path.join(book_folder, "000_简介.txt")
            if not append_mode or not os.path.exists(intro_path):
                with open(intro_path, 'w', encoding='utf-8') as f:
                    if book_data.get('cover_url'):
                        f.write(f"[封面: {book_data['cover_url']}]\n\n")
                    f.write(f"Title: {book_data['title']}\n")
                    f.write(f"Author: {book_data['author']}\n")
                    f.write("="*20 + "\n\n")
                    f.write(f"{book_data.get('introduction', '')}\n")
        else:
            # 单文件
            filename = f"{book_data['title']}.txt"
            filepath = os.path.join(save_dir, filename)
            mode = 'a' if append_mode else 'w'
            f = open(filepath, mode, encoding='utf-8')
            
            if not append_mode:
                if book_data.get('cover_url'):
                    f.write(f"[封面: {book_data['cover_url']}]\n\n")
                f.write(f"Title: {book_data['title']}\n")
                f.write(f"Author: {book_data['author']}\n")
                f.write("="*20 + "\n\n")
                f.write(f"简介:\n{book_data.get('introduction', '')}\n")
                f.write("="*20 + "\n\n")
            else:
                f.write("\n\n") # 追加模式下加个换行分隔
                
            context['file_handle'] = f
            context['filepath'] = filepath
            
        return context

    def write_chapter(self, context, chapter_data, content, index):
        # 转换内容列表为字符串
        text_content = ""
        if isinstance(content, str):
             text_content = content
        else:
             lines = []
             for item in content:
                 if item['type'] == 'text':
                     lines.append(item['data'])
                 elif item['type'] == 'image':
                     lines.append(f"[图片: {item['data']}]")
             text_content = "\n\n".join(lines)

        if context['split_files']:
            # 分文件
            safe_title = re.sub(r'[\\/*?:"<>|]', "", chapter_data['title'])
            filename = f"{index+1:03d}_{safe_title}.txt"
            filepath = os.path.join(context['target_dir'], filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(text_content)
            context['files_created'].append(filepath)
        else:
            # 单文件
            f = context['file_handle']
            f.write(f"\n\n=== {chapter_data['title']} ===\n\n")
            f.write(text_content)

    def finalize(self, context):
        if context['split_files']:
            return context['target_dir']
        else:
            context['file_handle'].close()
            return context['filepath']

class MdFormatter(BookFormatter):
    def detect_existing_progress(self, book_data, save_dir, split_files):
        last_index = -1
        if split_files:
            book_folder = os.path.join(save_dir, book_data['title'])
            if os.path.exists(book_folder):
                pattern = re.compile(r'^(\d{3})_')
                for fname in os.listdir(book_folder):
                    match = pattern.match(fname)
                    if match:
                        idx = int(match.group(1)) - 1
                        if idx > last_index:
                            last_index = idx
        else:
            filepath = os.path.join(save_dir, f"{book_data['title']}.md")
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        f.seek(0, 2)
                        fsize = f.tell()
                        seek_size = min(fsize, 20480)
                        f.seek(fsize - seek_size)
                        content = f.read()
                        
                        matches = re.findall(r'## (.+?)\n', content)
                        if matches:
                            last_title = matches[-1].strip()
                            for i in range(len(book_data['chapters']) - 1, -1, -1):
                                if book_data['chapters'][i]['title'] == last_title:
                                    last_index = i
                                    break
                except:
                    pass
        return last_index

    def initialize(self, book_data, save_dir, split_files, append_mode=False, downloader=None):
        context = {
            'downloader': downloader,
            'book_data': book_data,
            'save_dir': save_dir,
            'split_files': split_files,
            'files_created': []
        }
        
        if split_files:
            book_folder = os.path.join(save_dir, book_data['title'])
            if not os.path.exists(book_folder):
                os.makedirs(book_folder)
            context['target_dir'] = book_folder
            
            intro_path = os.path.join(book_folder, "000_简介.md")
            if not append_mode or not os.path.exists(intro_path):
                with open(intro_path, 'w', encoding='utf-8') as f:
                    if book_data.get('cover_url'):
                        f.write(f"![封面]({book_data['cover_url']})\n\n")
                    f.write(f"# {book_data['title']}\n")
                    f.write(f"**Author:** {book_data['author']}\n\n")
                    f.write("## 简介\n\n")
                    f.write(f"{book_data.get('introduction', '')}\n")
        else:
            filename = f"{book_data['title']}.md"
            filepath = os.path.join(save_dir, filename)
            mode = 'a' if append_mode else 'w'
            f = open(filepath, mode, encoding='utf-8')
            
            if not append_mode:
                if book_data.get('cover_url'):
                    f.write(f"![封面]({book_data['cover_url']})\n\n")
                f.write(f"# {book_data['title']}\n")
                f.write(f"**Author:** {book_data['author']}\n\n")
                f.write("## 简介\n\n")
                f.write(f"{book_data.get('introduction', '')}\n\n")
                f.write("---\n\n")
            else:
                f.write("\n\n---\n\n") # Append separator
                
            context['file_handle'] = f
            context['filepath'] = filepath
            
        return context

    def write_chapter(self, context, chapter_data, content, index):
        # 转换内容列表为字符串
        text_content = ""
        if isinstance(content, str):
             text_content = content
        else:
             lines = []
             for item in content:
                 if item['type'] == 'text':
                     lines.append(item['data'])
                 elif item['type'] == 'image':
                     lines.append(f"![image]({item['data']})")
             text_content = "\n\n".join(lines)

        if context['split_files']:
            safe_title = re.sub(r'[\\/*?:"<>|]', "", chapter_data['title'])
            filename = f"{index+1:03d}_{safe_title}.md"
            filepath = os.path.join(context['target_dir'], filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# {chapter_data['title']}\n\n")
                f.write(text_content)
            context['files_created'].append(filepath)
        else:
            f = context['file_handle']
            f.write(f"## {chapter_data['title']}\n\n")
            f.write(text_content)
            f.write("\n\n")

    def finalize(self, context):
        if context['split_files']:
            return context['target_dir']
        else:
            context['file_handle'].close()
            return context['filepath']

class EpubFormatter(BookFormatter):
    def detect_existing_progress(self, book_data, save_dir, split_files):
        return -1

    def initialize(self, book_data, save_dir, split_files, append_mode=False, downloader=None):
        # EPUB 忽略 split_files
        book = epub.EpubBook()

        # 设置封面
        if book_data.get('cover_url') and downloader:
            try:
                cover_data = downloader.get_image_content(book_data['cover_url'])
                if cover_data:
                    # 获取扩展名
                    ext = 'jpg'
                    if '.png' in book_data['cover_url']: ext = 'png'
                    elif '.gif' in book_data['cover_url']: ext = 'gif'
                    
                    book.set_cover(f"cover.{ext}", cover_data)
            except Exception as e:
                print(f"设置封面失败: {e}")

        book.set_identifier(f'fanqie-{int(time.time())}')
        book.set_title(book_data['title'])
        book.set_language('zh')
        book.add_author(book_data['author'])
        book.add_metadata('DC', 'description', book_data.get('introduction', ''))
        
        spine = []
        toc = []
        
        # 简介
        intro_content = book_data.get('introduction', '').replace('\n', '<br/>')
        c_intro = epub.EpubHtml(title='简介', file_name='intro.xhtml', lang='zh')
        c_intro.content = f'<h1>简介</h1><p>{intro_content}</p>'
        book.add_item(c_intro)
        spine.append(c_intro)
        toc.append(c_intro)
        
        return {
            'downloader': downloader,
            'book': book,
            'spine': spine,
            'toc': toc,
            'save_dir': save_dir,
            'title': book_data['title']
        }

    def write_chapter(self, context, chapter_data, content, index):
        html_parts = []
        
        if isinstance(content, str):
            html_parts = [f"<p>{line}</p>" for line in content.split('\n\n')]
        else:
            img_idx = 0
            for item in content:
                if item['type'] == 'text':
                    html_parts.append(f"<p>{item['data']}</p>")
                elif item['type'] == 'image':
                    img_url = item['data']
                    if context.get('downloader'):
                        img_data = context['downloader'].get_image_content(img_url)
                        if img_data:
                            # Determine extension
                            ext = 'jpg'
                            if '.png' in img_url: ext = 'png'
                            elif '.gif' in img_url: ext = 'gif'
                            elif '.webp' in img_url: ext = 'webp'
                            elif '.jpeg' in img_url: ext = 'jpg'
                            
                            img_filename = f"img_{index+1}_{img_idx}.{ext}"
                            
                            # Create EpubImage
                            epub_img = epub.EpubImage()
                            epub_img.file_name = img_filename
                            epub_img.media_type = f'image/{ext}'
                            epub_img.content = img_data
                            
                            # Add to book
                            context['book'].add_item(epub_img)
                            
                            html_parts.append(f'<img src="{img_filename}" alt="image" />')
                            img_idx += 1
                        else:
                            html_parts.append(f'<p>[图片下载失败: {img_url}]</p>')
                    else:
                        html_parts.append(f'<p>[图片: {img_url}]</p>')

        html_content = "".join(html_parts)
        c = epub.EpubHtml(title=chapter_data['title'], file_name=f'chap_{index+1}.xhtml', lang='zh')
        c.content = f'<h1>{chapter_data["title"]}</h1>{html_content}'
        
        context['book'].add_item(c)
        context['spine'].append(c)
        context['toc'].append(c)

    def finalize(self, context):
        book = context['book']
        book.toc = context['toc']
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = ['nav'] + context['spine']
        
        filename = f"{context['title']}.epub"
        filepath = os.path.join(context['save_dir'], filename)
        epub.write_epub(filepath, book)
        return filepath

# --- 主下载器类 ---

class FanqieDownloader:
    def __init__(self, cookies=None):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        self.cookies = cookies
        # 字符集来自研究（番茄小说混淆映射）
        # 注意：此映射可能会随时间变化。
        self.code_start = 58344
        self.code_end = 58715
        self.charset = [
            'D', '在', '主', '特', '家', '军', '然', '表', '场', '4', '要', '只', 'v', '和', '?', '6', '别', '还', 'g',
            '现', '儿', '岁', '?', '?', '此', '象', '月', '3', '出', '战', '工', '相', 'o', '男', '首', '失', '世', 'F',
            '都', '平', '文', '什', 'V', 'O', '将', '真', 'T', '那', '当', '?', '会', '立', '些', 'u', '是', '十', '张',
            '学', '气', '大', '爱', '两', '命', '全', '后', '东', '性', '通', '被', '1', '它', '乐', '接', '而', '感',
            '车', '山', '公', '了', '常', '以', '何', '可', '话', '先', 'p', 'i', '叫', '轻', 'M', '士', 'w', '着', '变',
            '尔', '快', 'l', '个', '说', '少', '色', '里', '安', '花', '远', '7', '难', '师', '放', 't', '报', '认',
            '面', '道', 'S', '?', '克', '地', '度', 'I', '好', '机', 'U', '民', '写', '把', '万', '同', '水', '新', '没',
            '书', '电', '吃', '像', '斯', '5', '为', 'y', '白', '几', '日', '教', '看', '但', '第', '加', '候', '作',
            '上', '拉', '住', '有', '法', 'r', '事', '应', '位', '利', '你', '声', '身', '国', '问', '马', '女', '他',
            'Y', '比', '父', 'x', 'A', 'H', 'N', 's', 'X', '边', '美', '对', '所', '金', '活', '回', '意', '到', 'z',
            '从', 'j', '知', '又', '内', '因', '点', 'Q', '三', '定', '8', 'R', 'b', '正', '或', '夫', '向', '德', '听',
            '更', '?', '得', '告', '并', '本', 'q', '过', '记', 'L', '让', '打', 'f', '人', '就', '者', '去', '原', '满',
            '体', '做', '经', 'K', '走', '如', '孩', 'c', 'G', '给', '使', '物', '?', '最', '笑', '部', '?', '员', '等',
            '受', 'k', '行', '一', '条', '果', '动', '光', '门', '头', '见', '往', '自', '解', '成', '处', '天', '能',
            '于', '名', '其', '发', '总', '母', '的', '死', '手', '入', '路', '进', '心', '来', 'h', '时', '力', '多',
            '开', '己', '许', 'd', '至', '由', '很', '界', 'n', '小', '与', 'Z', '想', '代', '么', '分', '生', '口',
            '再', '妈', '望', '次', '西', '风', '种', '带', 'J', '?', '实', '情', '才', '这', '?', 'E', '我', '神', '格',
            '长', '觉', '间', '年', '眼', '无', '不', '亲', '关', '结', '0', '友', '信', '下', '却', '重', '己', '老',
            '2', '音', '字', 'm', '呢', '明', '之', '前', '高', 'P', 'B', '目', '太', 'e', '9', '起', '稜', '她', '也',
            'W', '用', '方', '子', '英', '每', '理', '便', '西', '数', '期', '中', 'C', '外', '样', 'a', '海', '们', '任'
        ]

    def decode_char(self, char_code):
        if self.code_start <= char_code <= self.code_end:
            bias = char_code - self.code_start
            if 0 <= bias < len(self.charset):
                return self.charset[bias]
        return chr(char_code)

    def decode_text(self, text):
        decoded = []
        for char in text:
            decoded.append(self.decode_char(ord(char)))
        return "".join(decoded)

    def get_image_content(self, url):
        """
        下载图片内容
        """
        try:
            # 简单的防盗链处理
            headers = self.headers.copy()
            headers['Referer'] = 'https://fanqienovel.com/'
            
            response = requests.get(url, headers=headers, cookies=self.cookies, timeout=30)
            response.raise_for_status()
            return response.content
        except Exception as e:
            # 静默失败，返回None
            return None

    def get_book_info(self, url):
        """
        获取书籍信息和章节列表。
        """
        try:
            response = requests.get(url, headers=self.headers, cookies=self.cookies)
            response.encoding = 'utf-8'
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')
            
            # 尝试获取标题
            title_tag = soup.select_one('.info-name h1') or soup.select_one('h1')
            title = title_tag.get_text(strip=True) if title_tag else "Unknown_Book"
            title = self.decode_text(title)
            
            # 尝试获取作者
            author_tag = soup.select_one('.author-name-text')
            author = author_tag.get_text(strip=True) if author_tag else "Unknown_Author"
            author = self.decode_text(author)

            # 尝试获取简介
            intro_tag = soup.select_one('.page-abstract-content')
            introduction = intro_tag.get_text(strip=True) if intro_tag else "No introduction available."
            introduction = self.decode_text(introduction)

            # 获取章节
            chapters = []
            # 选择器可能会变化，尝试常见的选择器
            chapter_items = soup.select('.chapter-item a') or soup.select('.chapter-list a')
            
            for item in chapter_items:
                chapter_title = item.get_text(strip=True)
                chapter_href = item.get('href')
                if chapter_href:
                    if not chapter_href.startswith('http'):
                        chapter_href = 'https://fanqienovel.com' + chapter_href
                    chapters.append({
                        'title': chapter_title,
                        'url': chapter_href
                    })
            
            return {
                'title': title,
                'author': author,
                'introduction': introduction,
                'chapters': chapters,
                'cover_url': self._get_cover_url(soup)
            }
        except Exception as e:
            raise Exception(f"获取书籍信息失败: {str(e)}")

    def _get_cover_url(self, soup):
        """
        提取封面图片URL
        """
        try:
            # 1. 优先从 JSON-LD 数据中获取（通常包含高清、无水印且正确的封面）
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                if not script.string:
                    continue
                try:
                    data = json.loads(script.string)
                    # 统一处理为列表
                    items = data if isinstance(data, list) else [data]
                    
                    for item in items:
                        # 检查 image 字段
                        if 'image' in item:
                            img = item['image']
                            if isinstance(img, list) and img:
                                return img[0]
                            elif isinstance(img, str) and img:
                                return img
                        # 检查 images 字段 (部分 schema 使用此字段)
                        if 'images' in item:
                            img = item['images']
                            if isinstance(img, list) and img:
                                return img[0]
                            elif isinstance(img, str) and img:
                                return img
                except:
                    continue

            # 2. 尝试从 script 中正则匹配（作为 JSON-LD 的补充）
            # 匹配类似 "https://...novel-pic..." 的链接
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string and 'novel-pic' in script.string:
                    urls = re.findall(r'https?://[^"\'\s]+novel-pic[^"\'\s]+', script.string)
                    if urls:
                        # 过滤掉转义字符
                        clean_url = urls[0].replace('\\u002F', '/').replace('\\', '')
                        return clean_url

            # 3. 尝试 CSS 选择器，但要过滤掉默认占位图
            img = soup.select_one('.book-cover-img') or \
                  soup.select_one('.book-img img') or \
                  soup.select_one('.page-header-left img')
            
            if img:
                src = img.get('src')
                if src:
                    # 处理相对路径或无协议的URL
                    if src.startswith('//'):
                        full_src = 'https:' + src
                    elif src.startswith('/'):
                        full_src = 'https://fanqienovel.com' + src
                    else:
                        full_src = src
                    
                    # 过滤占位图 (novel-static 通常是静态资源或占位图)
                    if 'novel-static' not in full_src:
                        return full_src
        except Exception as e:
            print(f"提取封面出错: {e}")
        return None

    def get_chapter_content(self, url):
        """
        获取并解码单个章节的内容。
        返回: list of dict {'type': 'text'|'image', 'data': str}
        """
        try:
            response = requests.get(url, headers=self.headers, cookies=self.cookies)
            response.encoding = 'utf-8'
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')
            
            # 内容选择器
            content_div = soup.select_one('.muye-reader-content') or soup.select_one('.muye-reader-content-16')
            
            if not content_div:
                # 检查是否是验证码页面
                # 1. 检查 title
                page_title = soup.title.string if soup.title else ""
                # 2. 检查常见验证码关键字或脚本
                page_text = response.text
                if "WAF" in page_title or "验证" in page_title or "captcha" in page_text or "verify" in page_text:
                    raise VerificationError("检测到验证码或风控页面")
                
                # 如果只是 VIP 锁定，通常会有特定的提示，这里简单处理
                return [{"type": "text", "data": "未找到内容或内容被锁定（VIP章节）。"}]

            # 提取内容（文本和图片）
            return self._extract_content_recursively(content_div)
        except VerificationError:
            raise
        except Exception as e:
            return [{"type": "text", "data": f"获取章节出错: {str(e)}"}]

    def _extract_content_recursively(self, element):
        """
        递归提取元素内容，保持顺序
        """
        items = []
        # 处理 element 自身就是 img 的情况 (虽然在 children 循环中不会出现，但为了通用性)
        if element.name == 'img':
            src = element.get('src')
            if src:
                return [{'type': 'image', 'data': src}]
            return []

        # 遍历子节点
        for child in element.children:
            if not child.name:
                # 处理直接的文本节点 (NavigableString)
                raw_text = str(child)
                decoded_text = self.decode_text(raw_text)
                if decoded_text.strip():
                    items.append({'type': 'text', 'data': decoded_text})
                continue
                
            if child.name == 'p':
                # 检查 p 标签内是否有图片
                imgs = child.find_all('img')
                if imgs:
                    # 如果 p 标签内混杂了图片，为了保持顺序，我们需要递归处理 p 标签
                    items.extend(self._extract_content_recursively(child))
                else:
                    # 普通文本段落
                    raw_text = child.get_text()
                    decoded_text = self.decode_text(raw_text)
                    if decoded_text.strip():
                        items.append({'type': 'text', 'data': decoded_text})
            
            elif child.name == 'img':
                src = child.get('src')
                if src:
                    items.append({'type': 'image', 'data': src})
                    
            elif child.name == 'div':
                # 递归处理 div
                items.extend(self._extract_content_recursively(child))
                
            else:
                # 其他标签（如 span, strong 等），如果包含图片则递归，否则提取文本
                imgs = child.find_all('img')
                if imgs:
                    items.extend(self._extract_content_recursively(child))
                else:
                    raw_text = child.get_text()
                    decoded_text = self.decode_text(raw_text)
                    if decoded_text.strip():
                        items.append({'type': 'text', 'data': decoded_text})
                        
        return items

    def get_rank_categories(self):
        """
        从排行榜页面获取可用的分类。
        返回字典列表: {'name': str, 'url': str}
        """
        try:
            url = "https://fanqienovel.com/rank"
            response = requests.get(url, headers=self.headers, cookies=self.cookies)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')
            
            categories = []
            seen = set()
            
            # 查找所有以 /rank/ 开头的链接
            # 这是一种启发式方法，可能会包含一些导航链接，但通常这些是分类
            for link in soup.find_all('a'):
                href = link.get('href')
                text = link.get_text(strip=True)
                if href and href.startswith('/rank/') and text:
                    # 过滤掉一些常见的非分类链接（如果有）（例如 'More'）
                    if text not in seen and len(text) < 10: # 分类名称通常较短
                        full_url = 'https://fanqienovel.com' + href
                        categories.append({'name': text, 'url': full_url})
                        seen.add(text)
            
            return categories
        except Exception as e:
            raise Exception(f"获取排行榜分类失败: {str(e)}")

    def parse_rank_books(self, html_content, base_url="https://fanqienovel.com"):
        """
        解析排行榜 HTML 内容获取书籍列表。
        """
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            books = []
            seen_books = {} # url -> {'index': int, 'from_img': bool}

            for link in soup.find_all('a'):
                href = link.get('href')
                if href and '/page/' in href:
                    full_url = base_url + href if not href.startswith('http') else href
                    
                    title = ""
                    from_img = False

                    # 1. 优先尝试从图片 alt 获取标题 (通常最准确且无干扰)
                    img = link.find('img')
                    if img and img.get('alt'):
                        title = img.get('alt')
                        from_img = True
                    
                    # 尝试查找其他可能的标题来源
                    if not title:
                        # 尝试找内部的 h4 或其他标题标签
                        for tag in ['h1', 'h2', 'h3', 'h4', 'div', 'span']:
                            found_tag = link.find(tag, class_=lambda x: x and ('name' in x or 'title' in x))
                            if found_tag:
                                title = found_tag.get_text(strip=True)
                                break

                    # 2. 其次尝试直接获取文本
                    if not title:
                        title = link.get_text(strip=True)
                    
                    if not title:
                        title = "Unknown Title"

                    # 3. 尝试解码标题（处理混淆字符）
                    # 只有当 title 看起来被混淆（包含特定范围的字符）或者我们确定它是从文本中提取的才尝试解码
                    # 但 decode_text 是安全的，如果字符不在范围内会返回原字符
                    title = self.decode_text(title)

                    # 4. 简单的标题清理
                    # 如果标题包含中文且有空格，可能是格式问题，尝试去除空格
                    if title and any('\u4e00' <= char <= '\u9fff' for char in title):
                         title = "".join(title.split())

                    if full_url in seen_books:
                        # 如果已经存在，检查是否可以用更高质量的标题（来自图片）覆盖
                        entry = seen_books[full_url]
                        if not entry['from_img'] and from_img:
                             books[entry['index']]['title'] = title
                             entry['from_img'] = True
                    else:
                        books.append({'title': title, 'url': full_url})
                        seen_books[full_url] = {'index': len(books)-1, 'from_img': from_img}

                    # --- 提取额外元数据 (状态, 在读, 更新) ---
                    # 获取当前书籍对象的引用
                    if full_url in seen_books:
                        current_book = books[seen_books[full_url]['index']]
                    else:
                        # 理论上不应该走到这里，因为上面已经添加了
                        continue

                    # 如果元数据尚未提取 (避免重复提取)
                    if 'status' not in current_book:
                        status = "未知"
                        reading_count = "未知"
                        last_update = "未知"
                        update_time = "未知"

                        # 尝试查找包含元数据的父容器
                        # 通常这些信息在链接的父级或祖父级的文本中
                        # 我们向上查找直到找到包含 "连载中" 或 "已完结" 的容器，或者达到一定的深度
                        container = link.parent
                        found_meta = False
                        for _ in range(3): # 向上查找最多3层
                            if container and container.name != 'body':
                                text = container.get_text(" ", strip=True)
                                if '连载中' in text or '已完结' in text:
                                    found_meta = True
                                    break
                                container = container.parent
                            else:
                                break
                        
                        if found_meta and container:
                            text = container.get_text(" ", strip=True)
                            
                            # 状态
                            m_status = re.search(r'(连载中|已完结)', text)
                            if m_status:
                                status = m_status.group(1)
                            
                            # 在读
                            m_read = re.search(r'在读[:：]?\s*([\d\.万]+)', text)
                            if m_read:
                                reading_count = m_read.group(1)
                                
                            # 最近更新
                            if '最近更新' in text:
                                # 简单的分割提取
                                parts = text.split('最近更新')
                                if len(parts) > 1:
                                    update_part = parts[1].strip()
                                    # 尝试提取时间 (yyyy-mm-dd HH:MM or yyyy-mm-dd)
                                    m_date = re.search(r'(\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2})?)', update_part)
                                    if m_date:
                                        update_time = m_date.group(1)
                                        # 截取到时间之前的部分作为章节名
                                        last_update = update_part[:m_date.start()].strip(" :：|")
                                    else:
                                        # 如果没找到时间，就取前一段
                                        last_update = update_part.strip(" :：|")

                        current_book.update({
                            'status': status,
                            'reading_count': reading_count,
                            'last_update': last_update,
                            'update_time': update_time
                        })

            
            return books
        except Exception as e:
            raise Exception(f"解析书籍列表失败: {str(e)}")

    def get_rank_books(self, category_url):
        """
        从分类排行榜页面获取书籍。
        返回字典列表: {'title': str, 'url': str}
        注意：这里的标题可能会被混淆，所以使用 get_book_info 获取干净的标题。
        """
        try:
            response = requests.get(category_url, headers=self.headers, cookies=self.cookies)
            response.encoding = 'utf-8' # 强制使用 UTF-8，防止中文乱码
            response.raise_for_status()
            return self.parse_rank_books(response.text)
        except Exception as e:
            raise Exception(f"获取排行榜书籍失败: {str(e)}")

    def _sleep(self, delay):
        """通用休眠逻辑"""
        if delay < 0:
            time.sleep(random.triangular(0.5, 1.0, 0.5))
        else:
            time.sleep(delay)

    def save_book(self, book_data, save_dir, formatter, chapter_indices=None, split_files=False, control_callback=None, delay=-1, progress_callback=None, max_chapters=0, verification_callback=None):
        """
        通用的书籍保存方法，使用策略模式。
        max_chapters: 限制下载的章节数量（0表示不限制）。
                      如果是新下载，则下载前N章。
                      如果是增量更新，则下载接下来的N章。
        """
        # 0. 自动增量检测
        # 仅当 chapter_indices 为 None (全本下载) 时才启用增量检测
        # 如果用户手动选择了章节范围，则完全遵从用户选择
        append_mode = False
        if chapter_indices is None:
            last_index = formatter.detect_existing_progress(book_data, save_dir, split_files)
            if last_index >= 0:
                start_idx = last_index + 1
                if start_idx < len(book_data['chapters']):
                     # 有新章节，自动生成新的 indices
                     end_idx = len(book_data['chapters'])
                     
                     # 应用 max_chapters 限制
                     if max_chapters > 0:
                         limit_end = start_idx + max_chapters
                         if limit_end < end_idx:
                             end_idx = limit_end
                             
                     chapter_indices = list(range(start_idx, end_idx))
                     append_mode = True
                     
                     msg = f"检测到本地进度 (已下载至第 {last_index+1} 章)，将从第 {start_idx+1} 章开始续传"
                     if max_chapters > 0:
                         msg += f" (限制更新 {max_chapters} 章)"
                     msg += "..."
                     
                     if progress_callback:
                         progress_callback(0, 0, msg)
                else:
                    # 已经全部下载
                    if progress_callback:
                        progress_callback(0, 0, f"书籍已是最新 (共 {len(book_data['chapters'])} 章)，跳过下载。")
                    return formatter.get_final_path(save_dir, book_data, split_files)

        chapters_to_download = []
        
        # 确保 chapter_indices 有值
        if chapter_indices is None:
            end_idx = len(book_data['chapters'])
            # 如果是全新下载且有限制
            if max_chapters > 0:
                end_idx = min(max_chapters, end_idx)
            chapter_indices = list(range(end_idx))

        # 过滤有效索引
        valid_indices = [idx for idx in chapter_indices if 0 <= idx < len(book_data['chapters'])]
        
        total_chapters = len(valid_indices)
        
        # 1. 初始化
        context = formatter.initialize(book_data, save_dir, split_files, append_mode, downloader=self)
        
        try:
            # 2. 循环下载
            for i, real_idx in enumerate(valid_indices):
                chapter = book_data['chapters'][real_idx]
                
                if control_callback:
                    control_callback()

                if progress_callback:
                    progress_callback(i + 1, total_chapters, chapter['title'])
                
                content = None
                while True:
                    try:
                        content = self.get_chapter_content(chapter['url'])
                        break
                    except VerificationError:
                        if verification_callback:
                            # 调用验证回调，通常这会暂停程序直到用户解决验证码
                            verification_callback(chapter['url'])
                            # 回调返回后（用户点击继续），继续循环重试
                            continue
                        else:
                            raise

                # 3. 写入章节
                # 注意：传递真实的章节索引 real_idx，确保文件名序号正确 (e.g. 051_xxx.txt)
                formatter.write_chapter(context, chapter, content, real_idx)
                
                # 4. 休眠
                self._sleep(delay)
            
            # 5. 完成
            return formatter.finalize(context)
            
        except Exception as e:
            # 这里可以添加清理逻辑，例如关闭文件句柄
            if isinstance(context, dict) and 'file_handle' in context:
                try:
                    context['file_handle'].close()
                except:
                    pass
            raise e

    def save_to_txt(self, book_data, save_dir, progress_callback=None, chapter_indices=None, split_files=False, control_callback=None, delay=-1, max_chapters=0, verification_callback=None):
        return self.save_book(book_data, save_dir, TxtFormatter(), chapter_indices, split_files, control_callback, delay, progress_callback, max_chapters, verification_callback)

    def save_to_md(self, book_data, save_dir, progress_callback=None, chapter_indices=None, split_files=False, control_callback=None, delay=-1, max_chapters=0, verification_callback=None):
        return self.save_book(book_data, save_dir, MdFormatter(), chapter_indices, split_files, control_callback, delay, progress_callback, max_chapters, verification_callback)

    def save_to_epub(self, book_data, save_dir, progress_callback=None, chapter_indices=None, control_callback=None, delay=-1, max_chapters=0, verification_callback=None):
        return self.save_book(book_data, save_dir, EpubFormatter(), chapter_indices, False, control_callback, delay, progress_callback, max_chapters, verification_callback)

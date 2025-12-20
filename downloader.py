import requests
from bs4 import BeautifulSoup
import time
import os
import re
import random
from ebooklib import epub
from abc import ABC, abstractmethod

class VerificationError(Exception):
    """当检测到验证码或风控时抛出"""
    pass

# --- 策略模式：格式化器 ---

class BookFormatter(ABC):
    @abstractmethod
    def initialize(self, book_data, save_dir, split_files):
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

class TxtFormatter(BookFormatter):
    def initialize(self, book_data, save_dir, split_files):
        context = {
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
            
            # 写简介
            intro_path = os.path.join(book_folder, "000_简介.txt")
            with open(intro_path, 'w', encoding='utf-8') as f:
                f.write(f"Title: {book_data['title']}\n")
                f.write(f"Author: {book_data['author']}\n")
                f.write("="*20 + "\n\n")
                f.write(f"{book_data.get('introduction', '')}\n")
        else:
            # 单文件
            filename = f"{book_data['title']}.txt"
            filepath = os.path.join(save_dir, filename)
            f = open(filepath, 'w', encoding='utf-8')
            f.write(f"Title: {book_data['title']}\n")
            f.write(f"Author: {book_data['author']}\n")
            f.write("="*20 + "\n\n")
            f.write(f"简介:\n{book_data.get('introduction', '')}\n")
            f.write("="*20 + "\n\n")
            context['file_handle'] = f
            context['filepath'] = filepath
            
        return context

    def write_chapter(self, context, chapter_data, content, index):
        if context['split_files']:
            # 分文件
            safe_title = re.sub(r'[\\/*?:"<>|]', "", chapter_data['title'])
            filename = f"{index+1:03d}_{safe_title}.txt"
            filepath = os.path.join(context['target_dir'], filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            context['files_created'].append(filepath)
        else:
            # 单文件
            f = context['file_handle']
            f.write(f"\n\n=== {chapter_data['title']} ===\n\n")
            f.write(content)

    def finalize(self, context):
        if context['split_files']:
            return context['target_dir']
        else:
            context['file_handle'].close()
            return context['filepath']

class MdFormatter(BookFormatter):
    def initialize(self, book_data, save_dir, split_files):
        context = {
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
            with open(intro_path, 'w', encoding='utf-8') as f:
                f.write(f"# {book_data['title']}\n")
                f.write(f"**Author:** {book_data['author']}\n\n")
                f.write("## 简介\n\n")
                f.write(f"{book_data.get('introduction', '')}\n")
        else:
            filename = f"{book_data['title']}.md"
            filepath = os.path.join(save_dir, filename)
            f = open(filepath, 'w', encoding='utf-8')
            f.write(f"# {book_data['title']}\n")
            f.write(f"**Author:** {book_data['author']}\n\n")
            f.write("## 简介\n\n")
            f.write(f"{book_data.get('introduction', '')}\n\n")
            f.write("---\n\n")
            context['file_handle'] = f
            context['filepath'] = filepath
            
        return context

    def write_chapter(self, context, chapter_data, content, index):
        if context['split_files']:
            safe_title = re.sub(r'[\\/*?:"<>|]', "", chapter_data['title'])
            filename = f"{index+1:03d}_{safe_title}.md"
            filepath = os.path.join(context['target_dir'], filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# {chapter_data['title']}\n\n")
                f.write(content)
            context['files_created'].append(filepath)
        else:
            f = context['file_handle']
            f.write(f"## {chapter_data['title']}\n\n")
            f.write(content)
            f.write("\n\n")

    def finalize(self, context):
        if context['split_files']:
            return context['target_dir']
        else:
            context['file_handle'].close()
            return context['filepath']

class EpubFormatter(BookFormatter):
    def initialize(self, book_data, save_dir, split_files):
        # EPUB 忽略 split_files
        book = epub.EpubBook()
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
            'book': book,
            'spine': spine,
            'toc': toc,
            'save_dir': save_dir,
            'title': book_data['title']
        }

    def write_chapter(self, context, chapter_data, content, index):
        html_content = "".join([f"<p>{line}</p>" for line in content.split('\n\n')])
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
                'chapters': chapters
            }
        except Exception as e:
            raise Exception(f"获取书籍信息失败: {str(e)}")

    def get_chapter_content(self, url):
        """
        获取并解码单个章节的内容。
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
                return "未找到内容或内容被锁定（VIP章节）。"

            # 提取段落
            paragraphs = content_div.find_all('p')
            decoded_paragraphs = []
            
            for p in paragraphs:
                raw_text = p.get_text()
                decoded_text = self.decode_text(raw_text)
                decoded_paragraphs.append(decoded_text)
            
            return "\n\n".join(decoded_paragraphs)
        except VerificationError:
            raise
        except Exception as e:
            return f"获取章节出错: {str(e)}"

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

    def save_book(self, book_data, save_dir, formatter, chapter_indices=None, split_files=False, control_callback=None, delay=-1, progress_callback=None):
        """
        通用的书籍保存方法，使用策略模式。
        """
        chapters_to_download = []
        if chapter_indices:
             for idx in chapter_indices:
                 if 0 <= idx < len(book_data['chapters']):
                     chapters_to_download.append(book_data['chapters'][idx])
        else:
            chapters_to_download = book_data['chapters']

        total_chapters = len(chapters_to_download)
        
        # 1. 初始化
        context = formatter.initialize(book_data, save_dir, split_files)
        
        try:
            # 2. 循环下载
            for i, chapter in enumerate(chapters_to_download):
                if control_callback:
                    control_callback()

                if progress_callback:
                    progress_callback(i + 1, total_chapters, chapter['title'])
                
                content = self.get_chapter_content(chapter['url'])
                
                # 3. 写入章节
                formatter.write_chapter(context, chapter, content, i)
                
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

    def save_to_txt(self, book_data, save_dir, progress_callback=None, chapter_indices=None, split_files=False, control_callback=None, delay=-1):
        return self.save_book(book_data, save_dir, TxtFormatter(), chapter_indices, split_files, control_callback, delay, progress_callback)

    def save_to_md(self, book_data, save_dir, progress_callback=None, chapter_indices=None, split_files=False, control_callback=None, delay=-1):
        return self.save_book(book_data, save_dir, MdFormatter(), chapter_indices, split_files, control_callback, delay, progress_callback)

    def save_to_epub(self, book_data, save_dir, progress_callback=None, chapter_indices=None, control_callback=None, delay=-1):
        return self.save_book(book_data, save_dir, EpubFormatter(), chapter_indices, False, control_callback, delay, progress_callback)

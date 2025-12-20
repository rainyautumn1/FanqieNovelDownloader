import requests
from bs4 import BeautifulSoup
import time
import os
import re
import random
from ebooklib import epub

class VerificationError(Exception):
    """当检测到验证码或风控时抛出"""
    pass

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
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')
            
            # 尝试获取标题
            title_tag = soup.select_one('.info-name h1') or soup.select_one('h1')
            title = title_tag.get_text(strip=True) if title_tag else "Unknown_Book"
            
            # 尝试获取作者
            author_tag = soup.select_one('.author-name-text')
            author = author_tag.get_text(strip=True) if author_tag else "Unknown_Author"

            # 尝试获取简介
            intro_tag = soup.select_one('.page-abstract-content')
            introduction = intro_tag.get_text(strip=True) if intro_tag else "No introduction available."

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

    def get_rank_books(self, category_url):
        """
        从分类排行榜页面获取书籍。
        返回字典列表: {'title': str, 'url': str}
        注意：这里的标题可能会被混淆，所以使用 get_book_info 获取干净的标题。
        """
        try:
            response = requests.get(category_url, headers=self.headers, cookies=self.cookies)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')
            
            books = []
            # 书籍通常链接到 /page/
            # 寻找包含 /page/ 的链接
            
            # 使用集合避免重复（图片链接 + 标题链接）
            seen_urls = set()
            
            # 如果可能，更精确地查找书籍项目
            # 常见结构: .rank-book-list .book-item a
            
            # 让我们搜索所有 href 包含 '/page/' 的 'a' 标签
            for link in soup.find_all('a'):
                href = link.get('href')
                if href and '/page/' in href:
                    full_url = 'https://fanqienovel.com' + href if not href.startswith('http') else href
                    if full_url not in seen_urls:
                        # 如果可能，提取标题
                        title = link.get_text(strip=True)
                        if not title:
                            # 尝试在子元素或 alt 属性中查找标题
                            img = link.find('img')
                            if img and img.get('alt'):
                                title = img.get('alt')
                            else:
                                title = "Unknown Title"
                        
                        books.append({'title': title, 'url': full_url})
                        seen_urls.add(full_url)
            
            return books
        except Exception as e:
            raise Exception(f"获取排行榜书籍失败: {str(e)}")

    def save_to_txt(self, book_data, save_dir, progress_callback=None, chapter_indices=None, split_files=False, control_callback=None):
        """
        保存书籍为 TXT 格式。
        chapter_indices: 要下载的章节索引列表（从0开始）。如果为 None，则下载所有章节。
        split_files: 如果为 True，则将每一章保存为一个单独的文件。
        control_callback: 在下载每一章之前调用的函数，用于检查暂停/停止状态。
        """
        chapters_to_download = []
        if chapter_indices:
             for idx in chapter_indices:
                 if 0 <= idx < len(book_data['chapters']):
                     chapters_to_download.append(book_data['chapters'][idx])
        else:
            chapters_to_download = book_data['chapters']

        total_chapters = len(chapters_to_download)
        
        if split_files:
            # 为书籍创建一个文件夹
            book_folder = os.path.join(save_dir, book_data['title'])
            if not os.path.exists(book_folder):
                os.makedirs(book_folder)
            
            # 保存简介
            intro_filepath = os.path.join(book_folder, "000_简介.txt")
            with open(intro_filepath, 'w', encoding='utf-8') as f:
                f.write(f"Title: {book_data['title']}\n")
                f.write(f"Author: {book_data['author']}\n")
                f.write("="*20 + "\n\n")
                f.write(f"{book_data.get('introduction', '')}\n")

            saved_paths = []
            
            for i, chapter in enumerate(chapters_to_download):
                if control_callback:
                    control_callback()

                if progress_callback:
                    progress_callback(i + 1, total_chapters, chapter['title'])
                
                content = self.get_chapter_content(chapter['url'])
                
                # 清理文件名
                safe_title = re.sub(r'[\\/*?:"<>|]', "", chapter['title'])
                filename = f"{i+1:03d}_{safe_title}.txt"
                filepath = os.path.join(book_folder, filename)
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                saved_paths.append(filepath)
                time.sleep(random.triangular(0.5, 1.0, 0.5))
                
            return book_folder # 返回目录路径
            
        else:
            # 单个文件
            filename = f"{book_data['title']}.txt"
            filepath = os.path.join(save_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Title: {book_data['title']}\n")
                f.write(f"Author: {book_data['author']}\n")
                f.write("="*20 + "\n\n")
                f.write(f"简介:\n{book_data.get('introduction', '')}\n")
                f.write("="*20 + "\n\n")
                
                for i, chapter in enumerate(chapters_to_download):
                    if control_callback:
                        control_callback()

                    if progress_callback:
                        progress_callback(i + 1, total_chapters, chapter['title'])
                    
                    content = self.get_chapter_content(chapter['url'])
                    f.write(f"\n\n=== {chapter['title']} ===\n\n")
                    f.write(content)
                    time.sleep(random.triangular(0.5, 1.0, 0.5))

            return filepath

    def save_to_md(self, book_data, save_dir, progress_callback=None, chapter_indices=None, split_files=False, control_callback=None):
        """
        保存书籍为 MD (Markdown) 格式。
        """
        chapters_to_download = []
        if chapter_indices:
             for idx in chapter_indices:
                 if 0 <= idx < len(book_data['chapters']):
                     chapters_to_download.append(book_data['chapters'][idx])
        else:
            chapters_to_download = book_data['chapters']

        total_chapters = len(chapters_to_download)
        
        if split_files:
            # 为书籍创建一个文件夹
            book_folder = os.path.join(save_dir, book_data['title'])
            if not os.path.exists(book_folder):
                os.makedirs(book_folder)
            
            # 保存简介
            intro_filepath = os.path.join(book_folder, "000_简介.md")
            with open(intro_filepath, 'w', encoding='utf-8') as f:
                f.write(f"# {book_data['title']}\n")
                f.write(f"**Author:** {book_data['author']}\n\n")
                f.write("## 简介\n\n")
                f.write(f"{book_data.get('introduction', '')}\n")

            for i, chapter in enumerate(chapters_to_download):
                if control_callback:
                    control_callback()

                if progress_callback:
                    progress_callback(i + 1, total_chapters, chapter['title'])
                
                content = self.get_chapter_content(chapter['url'])
                
                # 清理文件名
                safe_title = re.sub(r'[\\/*?:"<>|]', "", chapter['title'])
                filename = f"{i+1:03d}_{safe_title}.md"
                filepath = os.path.join(book_folder, filename)
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(f"# {chapter['title']}\n\n")
                    f.write(content)
                
                time.sleep(random.triangular(0.5, 1.0, 0.5))
                
            return book_folder
            
        else:
            # 单个文件
            filename = f"{book_data['title']}.md"
            filepath = os.path.join(save_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# {book_data['title']}\n")
                f.write(f"**Author:** {book_data['author']}\n\n")
                f.write("## 简介\n\n")
                f.write(f"{book_data.get('introduction', '')}\n\n")
                f.write("---\n\n")
                
                for i, chapter in enumerate(chapters_to_download):
                    if control_callback:
                        control_callback()

                    if progress_callback:
                        progress_callback(i + 1, total_chapters, chapter['title'])
                    
                    content = self.get_chapter_content(chapter['url'])
                    f.write(f"## {chapter['title']}\n\n")
                    f.write(content)
                    f.write("\n\n")
                    time.sleep(random.triangular(0.5, 1.0, 0.5))

            return filepath

    def save_to_epub(self, book_data, save_dir, progress_callback=None, chapter_indices=None, control_callback=None):
        # EPUB 不支持以相同方式分割文件（它本身就是一个 zip），
        # 但我们可以支持部分下载。
        
        chapters_to_download = []
        if chapter_indices:
             for idx in chapter_indices:
                 if 0 <= idx < len(book_data['chapters']):
                     chapters_to_download.append(book_data['chapters'][idx])
        else:
            chapters_to_download = book_data['chapters']

        book = epub.EpubBook()
        book.set_identifier(f'fanqie-{int(time.time())}')
        book.set_title(book_data['title'])
        book.set_language('zh')
        book.add_author(book_data['author'])
        
        # 将简介添加到描述元数据中
        book.add_metadata('DC', 'description', book_data.get('introduction', ''))

        spine = []
        toc = []

        # 添加简介章节
        intro_content = book_data.get('introduction', '').replace('\n', '<br/>')
        c_intro = epub.EpubHtml(title='简介', file_name='intro.xhtml', lang='zh')
        c_intro.content = f'<h1>简介</h1><p>{intro_content}</p>'
        book.add_item(c_intro)
        spine.append(c_intro)
        toc.append(c_intro)

        total_chapters = len(chapters_to_download)
        for i, chapter in enumerate(chapters_to_download):
            if control_callback:
                control_callback()

            if progress_callback:
                progress_callback(i + 1, total_chapters, chapter['title'])

            content = self.get_chapter_content(chapter['url'])
            # 将换行符转换为 HTML 段落
            html_content = "".join([f"<p>{line}</p>" for line in content.split('\n\n')])
            
            c = epub.EpubHtml(title=chapter['title'], file_name=f'chap_{i+1}.xhtml', lang='zh')
            c.content = f'<h1>{chapter["title"]}</h1>{html_content}'
            book.add_item(c)
            spine.append(c)
            toc.append(c)
            time.sleep(random.triangular(0.5, 1.0, 0.5)) # 礼貌等待

        book.toc = toc
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = ['nav'] + spine

        filename = f"{book_data['title']}.epub"
        filepath = os.path.join(save_dir, filename)
        epub.write_epub(filepath, book)
        
        return filepath

import os
import time
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QComboBox, QCheckBox, QPushButton, QGroupBox, QRadioButton, QLineEdit
from downloader import VerificationError

# 批量下载工作线程
class BatchDownloadWorker(QThread):
    progress_signal = Signal(int, int, str) # 当前书籍索引, 总书籍数, 当前状态
    log_signal = Signal(str)
    finished_signal = Signal(str) # 摘要
    error_signal = Signal(str)

    def __init__(self, downloader, rank_url, save_dir, top_n=5, chapters_count=0, fmt='txt', split_files=False, delay=-1):
        super().__init__()
        self.downloader = downloader
        self.rank_url = rank_url
        self.save_dir = save_dir
        self.top_n = top_n
        self.chapters_count = chapters_count # 0 表示全部
        self.fmt = fmt
        self.split_files = split_files
        self.delay = delay
        self.is_paused = False
        self.is_stopped = False

    def pause(self):
        self.is_paused = True
        self.log_signal.emit("批量下载已暂停")

    def resume(self):
        self.is_paused = False
        self.log_signal.emit("批量下载继续")

    def stop(self):
        self.is_stopped = True
        self.is_paused = False
        self.log_signal.emit("正在停止批量下载...")

    def check_control_status(self):
        if self.is_stopped:
            raise Exception("用户停止下载")
        
        while self.is_paused:
            time.sleep(0.1)
            if self.is_stopped:
                raise Exception("用户停止下载")

    def run(self):
        try:
            self.log_signal.emit(f"正在分析榜单页面: {self.rank_url}")
            books = self.downloader.get_rank_books(self.rank_url)
            
            if not books:
                self.error_signal.emit("未在当前页面找到书籍链接，请确认这是榜单/书库页面。")
                return

            # 应用前 N 本限制
            target_books = books[:self.top_n]
            total_books = len(target_books)
            
            self.log_signal.emit(f"发现 {len(books)} 本书，将下载前 {total_books} 本")
            
            # 创建目录
            if not os.path.exists(self.save_dir):
                os.makedirs(self.save_dir)

            # 预先获取所有书籍信息以更新标题
            self.log_signal.emit("正在预获取书籍信息以更新标题...")
            for i, book in enumerate(target_books):
                self.check_control_status()
                try:
                    # 快速获取信息，不获取章节内容，仅为了标题
                    # 注意：get_book_info 会获取章节列表，速度可能稍慢，但为了准确标题是必要的
                    self.progress_signal.emit(i, total_books, f"正在获取书籍信息 [{i+1}/{total_books}]")
                    book_info = self.downloader.get_book_info(book['url'])
                    # 更新书籍列表中的标题
                    target_books[i]['title'] = book_info['title']
                    target_books[i]['author'] = book_info['author']
                    target_books[i]['book_info'] = book_info # 缓存起来后续使用
                    
                    # 立即发送更新信号给UI
                    self.progress_signal.emit(i, total_books, f"已获取: {book_info['title']}")
                    
                    # 防止请求过快
                    time.sleep(0.5)
                except Exception as e:
                    self.log_signal.emit(f"获取书籍信息失败: {book.get('url')} - {str(e)}")
                    # 失败不影响继续，只是标题可能不准

            success_count = 0

            for i, book in enumerate(target_books):
                # 在书籍之间检查状态
                self.check_control_status()

                try:
                    # 使用缓存的 info 或者重新获取（如果之前失败了）
                    if 'book_info' in book:
                        book_info = book['book_info']
                    else:
                        self.log_signal.emit(f"[{i+1}/{total_books}] 正在获取书籍信息: {book['url']}")
                        book_info = self.downloader.get_book_info(book['url'])
                    
                    real_title = book_info['title']
                    
                    self.log_signal.emit(f"[{i+1}/{total_books}] 开始下载: {real_title}")
                    self.progress_signal.emit(i, total_books, f"正在下载: {real_title}")
                    
                    # 确定章节
                    indices = None
                    if self.chapters_count > 0:
                        limit = min(self.chapters_count, len(book_info['chapters']))
                        indices = list(range(limit))
                        self.log_signal.emit(f"  - 仅下载前 {limit} 章")
                    
                    # 定义回调
                    def callback(curr, tot, title):
                        # 发送详细进度信息：[第几本/共几本] 书名 (第几章/共几章)
                        status_msg = f"正在下载 [{i+1}/{total_books}]: {real_title} ({curr}/{tot} 章)"
                        self.progress_signal.emit(i, total_books, status_msg)
                    
                    # 保存
                    if self.fmt == 'txt':
                        filepath = self.downloader.save_to_txt(
                            book_info, 
                            self.save_dir, 
                            callback,
                            chapter_indices=indices,
                            split_files=self.split_files,
                            control_callback=self.check_control_status,
                            delay=self.delay
                        )
                    elif self.fmt == 'md':
                        filepath = self.downloader.save_to_md(
                            book_info, 
                            self.save_dir, 
                            callback,
                            chapter_indices=indices,
                            split_files=self.split_files,
                            control_callback=self.check_control_status,
                            delay=self.delay
                        )
                    else: # epub格式
                        filepath = self.downloader.save_to_epub(
                            book_info, 
                            self.save_dir, 
                            callback,
                            chapter_indices=indices,
                            control_callback=self.check_control_status,
                            delay=self.delay
                        )
                    
                    self.log_signal.emit(f"[{i+1}/{total_books}] 完成: {real_title} -> {filepath}")
                    success_count += 1
                    
                except Exception as e:
                    if str(e) == "用户停止下载":
                        raise e
                    
                    if isinstance(e, VerificationError) or "验证码" in str(e):
                        self.error_signal.emit(f"检测到验证码，批量下载已停止。请手动验证后重试。")
                        return

                    self.log_signal.emit(f"[{i+1}/{total_books}] 失败: {book.get('title', 'Unknown')} - {str(e)}")
                    # 继续下一本书
                
                # 小延迟
                time.sleep(1)

            self.finished_signal.emit(f"批量下载完成! 成功: {success_count}/{total_books}\n保存位置: {self.save_dir}")

        except Exception as e:
            if str(e) == "用户停止下载":
                self.error_signal.emit("批量下载已停止")
            else:
                self.error_signal.emit(f"批量下载出错: {str(e)}")

# 获取榜单/分类书籍列表的工作线程
class RankParserWorker(QThread):
    finished_signal = Signal(list)
    error_signal = Signal(str)

    def __init__(self, downloader, rank_url, html_content=None):
        super().__init__()
        self.downloader = downloader
        self.rank_url = rank_url
        self.html_content = html_content

    def run(self):
        try:
            if self.html_content:
                books = self.downloader.parse_rank_books(self.html_content)
            else:
                books = self.downloader.get_rank_books(self.rank_url)
            self.finished_signal.emit(books)
        except Exception as e:
            self.error_signal.emit(str(e))

# 获取书籍信息的工作线程
class BookInfoWorker(QThread):
    finished_signal = Signal(dict)
    error_signal = Signal(str)
    
    def __init__(self, downloader, url):
        super().__init__()
        self.downloader = downloader
        self.url = url
        
    def run(self):
        try:
            info = self.downloader.get_book_info(self.url)
            self.finished_signal.emit(info)
        except Exception as e:
            self.error_signal.emit(str(e))

# 下载工作线程
class DownloadWorker(QThread):
    progress_signal = Signal(int, int, str) # 当前, 总数, 标题
    log_signal = Signal(str)
    finished_signal = Signal(str) # 文件路径
    error_signal = Signal(str)

    def __init__(self, downloader, book_url, save_dir, fmt, book_info=None, chapter_indices=None, split_files=False, delay=-1, chapter_limit=0):
        super().__init__()
        self.downloader = downloader
        self.book_url = book_url
        self.save_dir = save_dir
        self.fmt = fmt
        self.book_info = book_info
        self.chapter_indices = chapter_indices
        self.split_files = split_files
        self.delay = delay
        self.chapter_limit = chapter_limit
        self.is_paused = False
        self.is_stopped = False

    def pause(self):
        self.is_paused = True
        self.log_signal.emit("下载已暂停")

    def resume(self):
        self.is_paused = False
        self.log_signal.emit("下载继续")

    def stop(self):
        self.is_stopped = True
        self.is_paused = False # 确保我们不会卡在暂停循环中
        self.log_signal.emit("正在停止下载...")

    def check_control_status(self):
        if self.is_stopped:
            raise Exception("用户停止下载")
        
        while self.is_paused:
            time.sleep(0.1)
            if self.is_stopped:
                raise Exception("用户停止下载")

    def run(self):
        try:
            if not self.book_info:
                self.log_signal.emit(f"正在获取书籍信息: {self.book_url}")
                self.book_info = self.downloader.get_book_info(self.book_url)
            
            # 重新发送信息以防万一
            self.log_signal.emit(f"书名: {self.book_info['title']}")
            self.log_signal.emit(f"作者: {self.book_info['author']}")
            
            # 处理章节限制
            if self.chapter_limit > 0 and not self.chapter_indices:
                limit = min(self.chapter_limit, len(self.book_info['chapters']))
                self.chapter_indices = list(range(limit))
                self.log_signal.emit(f"根据设置，仅下载前 {limit} 章")

            chapters_to_download_count = len(self.chapter_indices) if self.chapter_indices else len(self.book_info['chapters'])
            self.log_signal.emit(f"计划下载章节数: {chapters_to_download_count}")

            if not self.book_info['chapters']:
                self.error_signal.emit("未找到章节，请检查页面是否为书籍目录页。")
                return

            def callback(current, total, title):
                self.progress_signal.emit(current, total, title)

            if self.fmt == 'txt':
                filepath = self.downloader.save_to_txt(
                    self.book_info, 
                    self.save_dir, 
                    callback,
                    chapter_indices=self.chapter_indices,
                    split_files=self.split_files,
                    control_callback=self.check_control_status,
                    delay=self.delay
                )
            elif self.fmt == 'md':
                filepath = self.downloader.save_to_md(
                    self.book_info, 
                    self.save_dir, 
                    callback,
                    chapter_indices=self.chapter_indices,
                    split_files=self.split_files,
                    control_callback=self.check_control_status,
                    delay=self.delay
                )
            else:
                filepath = self.downloader.save_to_epub(
                    self.book_info, 
                    self.save_dir, 
                    callback,
                    chapter_indices=self.chapter_indices,
                    control_callback=self.check_control_status,
                    delay=self.delay
                )
            
            self.finished_signal.emit(filepath)

        except Exception as e:
            self.error_signal.emit(str(e))

# 标题修正工作线程
class TitleCorrectionWorker(QThread):
    title_updated = Signal(str, str) # task_id, new_title

    def __init__(self, downloader, tasks):
        """
        tasks: list of (task_id, book_url)
        """
        super().__init__()
        self.downloader = downloader
        self.tasks = tasks

    def run(self):
        for task_id, book_url in self.tasks:
            try:
                # 仅获取 info，不下载
                book_info = self.downloader.get_book_info(book_url)
                if book_info and book_info.get('title'):
                    self.title_updated.emit(task_id, book_info['title'])
                time.sleep(0.5) # 避免请求过快
            except:
                pass # 失败忽略，保持原样

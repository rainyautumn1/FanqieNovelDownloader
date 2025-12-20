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

            success_count = 0

            for i, book in enumerate(target_books):
                # 在书籍之间检查状态
                self.check_control_status()

                try:
                    self.log_signal.emit(f"[{i+1}/{total_books}] 正在获取书籍信息: {book['url']}")
                    self.progress_signal.emit(i, total_books, f"正在获取信息: {book.get('title', 'Unknown')}")
                    
                    # 获取书籍信息 (获取真实标题)
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
                        # 我们定期更新日志或保持静默以避免刷屏
                        pass
                    
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

    def __init__(self, downloader, book_url, save_dir, fmt, book_info=None, chapter_indices=None, split_files=False, delay=-1):
        super().__init__()
        self.downloader = downloader
        self.book_url = book_url
        self.save_dir = save_dir
        self.fmt = fmt
        self.book_info = book_info
        self.chapter_indices = chapter_indices
        self.split_files = split_files
        self.delay = delay
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

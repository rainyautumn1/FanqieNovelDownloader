import sys
import os
import time
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLineEdit, QPushButton, QProgressBar, 
                             QTextEdit, QLabel, QMessageBox, QComboBox, QDialog,
                             QGroupBox, QRadioButton, QCheckBox, QSpinBox, QTabWidget)
from PySide6.QtCore import QUrl, QThread, Signal, Slot, Qt
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
import json

from downloader import FanqieDownloader

# Worker Thread for Batch Downloading
class BatchDownloadWorker(QThread):
    progress_signal = Signal(int, int, str) # current_book_idx, total_books, current_status
    log_signal = Signal(str)
    finished_signal = Signal(str) # summary
    error_signal = Signal(str)

    def __init__(self, downloader, rank_url, save_dir, top_n=5, chapters_count=0, fmt='txt', split_files=False):
        super().__init__()
        self.downloader = downloader
        self.rank_url = rank_url
        self.save_dir = save_dir
        self.top_n = top_n
        self.chapters_count = chapters_count # 0 means all
        self.fmt = fmt
        self.split_files = split_files

    def run(self):
        try:
            self.log_signal.emit(f"正在分析榜单页面: {self.rank_url}")
            books = self.downloader.get_rank_books(self.rank_url)
            
            if not books:
                self.error_signal.emit("未在当前页面找到书籍链接，请确认这是榜单/书库页面。")
                return

            # Apply Top N limit
            target_books = books[:self.top_n]
            total_books = len(target_books)
            
            self.log_signal.emit(f"发现 {len(books)} 本书，将下载前 {total_books} 本")
            
            # Create directory
            if not os.path.exists(self.save_dir):
                os.makedirs(self.save_dir)

            success_count = 0

            for i, book in enumerate(target_books):
                try:
                    self.log_signal.emit(f"[{i+1}/{total_books}] 正在获取书籍信息: {book['url']}")
                    self.progress_signal.emit(i, total_books, f"正在获取信息: {book.get('title', 'Unknown')}")
                    
                    # Get Book Info (this gets the real title)
                    book_info = self.downloader.get_book_info(book['url'])
                    real_title = book_info['title']
                    
                    self.log_signal.emit(f"[{i+1}/{total_books}] 开始下载: {real_title}")
                    self.progress_signal.emit(i, total_books, f"正在下载: {real_title}")
                    
                    # Determine chapters
                    indices = None
                    if self.chapters_count > 0:
                        limit = min(self.chapters_count, len(book_info['chapters']))
                        indices = list(range(limit))
                        self.log_signal.emit(f"  - 仅下载前 {limit} 章")
                    
                    # Define callback
                    def callback(curr, tot, title):
                        # We update log periodically or just keep silent to avoid spam
                        pass
                    
                    # Save
                    if self.fmt == 'txt':
                        filepath = self.downloader.save_to_txt(
                            book_info, 
                            self.save_dir, 
                            callback,
                            chapter_indices=indices,
                            split_files=self.split_files
                        )
                    elif self.fmt == 'md':
                        filepath = self.downloader.save_to_md(
                            book_info, 
                            self.save_dir, 
                            callback,
                            chapter_indices=indices,
                            split_files=self.split_files
                        )
                    else: # epub
                        filepath = self.downloader.save_to_epub(
                            book_info, 
                            self.save_dir, 
                            callback,
                            chapter_indices=indices
                        )
                    
                    self.log_signal.emit(f"[{i+1}/{total_books}] 完成: {real_title} -> {filepath}")
                    success_count += 1
                    
                except Exception as e:
                    self.log_signal.emit(f"[{i+1}/{total_books}] 失败: {book.get('title', 'Unknown')} - {str(e)}")
                    # Continue to next book
                
                # Small delay
                time.sleep(1)

            self.finished_signal.emit(f"批量下载完成! 成功: {success_count}/{total_books}\n保存位置: {self.save_dir}")

        except Exception as e:
            self.error_signal.emit(f"批量下载出错: {str(e)}")

class BatchOptionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量下载设置")
        self.resize(300, 250)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Top N
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("下载当前页前 N 本书:"))
        self.spin_top_n = QSpinBox()
        self.spin_top_n.setRange(1, 100)
        self.spin_top_n.setValue(5)
        h1.addWidget(self.spin_top_n)
        layout.addLayout(h1)
        
        # Chapter Limit
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("每本限制章节 (0为全部):"))
        self.spin_chapter_limit = QSpinBox()
        self.spin_chapter_limit.setRange(0, 5000)
        self.spin_chapter_limit.setValue(0)
        h2.addWidget(self.spin_chapter_limit)
        layout.addLayout(h2)

        # Format Selection
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("保存格式:"))
        self.combo_fmt = QComboBox()
        self.combo_fmt.addItems(["txt", "epub", "md"])
        h3.addWidget(self.combo_fmt)
        layout.addLayout(h3)

        # Split File Option
        h4 = QHBoxLayout()
        h4.addWidget(QLabel("分章保存:"))
        self.check_split = QCheckBox("每章一个文件 (仅TXT/MD有效)")
        h4.addWidget(self.check_split)
        layout.addLayout(h4)
        
        layout.addStretch()
        
        # Buttons
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("开始下载")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
    def get_data(self):
        return self.spin_top_n.value(), self.spin_chapter_limit.value(), self.combo_fmt.currentText(), self.check_split.isChecked()

# Worker Thread for Fetching Book Info
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

# Worker Thread for Downloading
class DownloadWorker(QThread):
    progress_signal = Signal(int, int, str) # current, total, title
    log_signal = Signal(str)
    finished_signal = Signal(str) # filepath
    error_signal = Signal(str)

    def __init__(self, downloader, book_url, save_dir, fmt, book_info=None, chapter_indices=None, split_files=False):
        super().__init__()
        self.downloader = downloader
        self.book_url = book_url
        self.save_dir = save_dir
        self.fmt = fmt
        self.book_info = book_info
        self.chapter_indices = chapter_indices
        self.split_files = split_files

    def run(self):
        try:
            if not self.book_info:
                self.log_signal.emit(f"正在获取书籍信息: {self.book_url}")
                self.book_info = self.downloader.get_book_info(self.book_url)
            
            # Re-emit info just in case
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
                    split_files=self.split_files
                )
            elif self.fmt == 'md':
                filepath = self.downloader.save_to_md(
                    self.book_info, 
                    self.save_dir, 
                    callback,
                    chapter_indices=self.chapter_indices,
                    split_files=self.split_files
                )
            else:
                filepath = self.downloader.save_to_epub(
                    self.book_info, 
                    self.save_dir, 
                    callback,
                    chapter_indices=self.chapter_indices
                )
            
            self.finished_signal.emit(filepath)

        except Exception as e:
            self.error_signal.emit(str(e))

class CustomWebEnginePage(QWebEnginePage):
    """Custom Page to handle opening links in the same view instead of new tabs"""
    def createWindow(self, _type):
        return self

class CustomWebEngineView(QWebEngineView):
    """Custom View to use our Custom Page"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPage(CustomWebEnginePage(self))

    def createWindow(self, _type):
        return self

class ChapterSelectionDialog(QDialog):
    def __init__(self, total_chapters, parent=None):
        super().__init__(parent)
        self.setWindowTitle("下载选项")
        self.resize(400, 300)
        self.total_chapters = total_chapters
        
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Chapter Selection Group
        grp_box = QGroupBox("章节选择")
        grp_layout = QVBoxLayout(grp_box)
        
        self.radio_all = QRadioButton(f"全部章节 (共 {self.total_chapters} 章)")
        self.radio_all.setChecked(True)
        grp_layout.addWidget(self.radio_all)
        
        # Range
        range_layout = QHBoxLayout()
        self.radio_range = QRadioButton("范围选择:")
        self.spin_start = QSpinBox()
        self.spin_start.setRange(1, self.total_chapters)
        self.spin_start.setValue(1)
        self.spin_end = QSpinBox()
        self.spin_end.setRange(1, self.total_chapters)
        self.spin_end.setValue(self.total_chapters)
        range_layout.addWidget(self.radio_range)
        range_layout.addWidget(QLabel("第"))
        range_layout.addWidget(self.spin_start)
        range_layout.addWidget(QLabel("章 到 第"))
        range_layout.addWidget(self.spin_end)
        range_layout.addWidget(QLabel("章"))
        grp_layout.addLayout(range_layout)
        
        # List
        list_layout = QHBoxLayout()
        self.radio_list = QRadioButton("自定义列表:")
        self.edit_list = QLineEdit()
        self.edit_list.setPlaceholderText("例如: 1,3,5 (逗号分隔)")
        list_layout.addWidget(self.radio_list)
        list_layout.addWidget(self.edit_list)
        grp_layout.addLayout(list_layout)
        
        layout.addWidget(grp_box)
        
        # File Options
        file_box = QGroupBox("文件保存选项")
        file_layout = QVBoxLayout(file_box)
        self.check_split = QCheckBox("分章保存 (每章一个文件)")
        self.check_split.setToolTip("仅TXT/MD格式有效")
        file_layout.addWidget(self.check_split)
        layout.addWidget(file_box)
        
        # Buttons
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("开始下载")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        # Connect signals to auto-select radio buttons
        self.spin_start.valueChanged.connect(lambda: self.radio_range.setChecked(True))
        self.spin_end.valueChanged.connect(lambda: self.radio_range.setChecked(True))
        self.edit_list.textChanged.connect(lambda: self.radio_list.setChecked(True))
        
    def get_data(self):
        # Return (indices, split_files)
        # indices is list of 0-based indices, or None for all
        split = self.check_split.isChecked()
        
        if self.radio_all.isChecked():
            return None, split
            
        indices = []
        if self.radio_range.isChecked():
            start = self.spin_start.value() - 1
            end = self.spin_end.value()
            if start < 0: start = 0
            if end > self.total_chapters: end = self.total_chapters
            indices = list(range(start, end))
            
        elif self.radio_list.isChecked():
            # Basic parsing for comma separated
            text = self.edit_list.text()
            parts = text.replace('，', ',').split(',')
            for p in parts:
                try:
                    idx = int(p.strip()) - 1
                    if 0 <= idx < self.total_chapters:
                        indices.append(idx)
                except:
                    pass
            indices = sorted(list(set(indices)))
            
        return indices, split

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("番茄小说内置浏览器下载器 (SVIP支持)")
        self.resize(1200, 800)

        self.downloader = FanqieDownloader()
        self.current_cookies = {}
        self.full_cookies_map = {} # Store full cookie info for persistence
        self.pending_book_info = None

        self.setup_ui()
        
        # Setup Cookie Store monitoring
        self.cookie_store = self.web_view.page().profile().cookieStore()
        self.cookie_store.cookieAdded.connect(self.on_cookie_added)
        
        # Load saved cookies
        self.load_cookies()
        
        # Initial Load
        self.web_view.setUrl(QUrl("https://fanqienovel.com/"))

    def load_cookies(self):
        cookie_file = os.path.join(os.getcwd(), "cookies.json")
        if os.path.exists(cookie_file):
            try:
                with open(cookie_file, 'r', encoding='utf-8') as f:
                    cookies_list = json.load(f)
                    
                count = 0
                for c_data in cookies_list:
                    try:
                        name = c_data.get('name')
                        value = c_data.get('value')
                        domain = c_data.get('domain', '')
                        path = c_data.get('path', '/')
                        secure = c_data.get('secure', False)
                        http_only = c_data.get('http_only', False)
                        expiration_date = c_data.get('expiration_date')
                        
                        if name and value:
                            # Update memory for downloader
                            self.current_cookies[name] = value
                            self.full_cookies_map[name] = c_data
                            
                            # Inject into browser
                            q_cookie = QNetworkCookie(name.encode('utf-8'), value.encode('utf-8'))
                            if domain:
                                q_cookie.setDomain(domain)
                            if path:
                                q_cookie.setPath(path)
                            if secure:
                                q_cookie.setSecure(True)
                            if http_only:
                                q_cookie.setHttpOnly(True)
                            
                            # Log for debugging (optional, can be removed later)
                            # print(f"Loading cookie: {name} for domain: {domain}")

                            self.cookie_store.setCookie(q_cookie)
                            count += 1
                    except Exception as inner_e:
                        print(f"Error loading single cookie: {inner_e}")
                
                print(f"Loaded {count} cookies from file.")
                self.log(f"已加载 {count} 个保存的 Cookies")
            except Exception as e:
                print(f"Error loading cookies: {e}")
                self.log(f"加载 Cookies 失败: {e}")

    def save_cookies(self):
        try:
            cookie_file = os.path.join(os.getcwd(), "cookies.json")
            cookies_list = list(self.full_cookies_map.values())
            with open(cookie_file, 'w', encoding='utf-8') as f:
                json.dump(cookies_list, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving cookies: {e}")


    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Nav Bar
        nav_layout = QHBoxLayout()
        
        self.back_btn = QPushButton("后退")
        self.back_btn.clicked.connect(lambda: self.web_view.back())
        nav_layout.addWidget(self.back_btn)

        self.forward_btn = QPushButton("前进")
        self.forward_btn.clicked.connect(lambda: self.web_view.forward())
        nav_layout.addWidget(self.forward_btn)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(lambda: self.web_view.reload())
        nav_layout.addWidget(self.refresh_btn)

        self.url_bar = QLineEdit()
        self.url_bar.returnPressed.connect(self.navigate_to_url)
        nav_layout.addWidget(self.url_bar)

        self.go_btn = QPushButton("前往")
        self.go_btn.clicked.connect(self.navigate_to_url)
        nav_layout.addWidget(self.go_btn)

        self.home_btn = QPushButton("回首页")
        self.home_btn.clicked.connect(lambda: self.web_view.setUrl(QUrl("https://fanqienovel.com/")))
        nav_layout.addWidget(self.home_btn)

        main_layout.addLayout(nav_layout)

        # Browser
        self.web_view = CustomWebEngineView()
        
        # Configure Persistent Profile for Native Storage
        storage_path = os.path.join(os.getcwd(), "browser_data")
        if not os.path.exists(storage_path):
            os.makedirs(storage_path)
            
        # Create a named profile which implies persistence if we set storage path
        profile = QWebEngineProfile("FanqieProfile", self.web_view)
        profile.setPersistentStoragePath(storage_path)
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        
        # Create page with this profile
        page = CustomWebEnginePage(profile, self.web_view)
        self.web_view.setPage(page)
        
        self.web_view.urlChanged.connect(self.update_url_bar)
        self.web_view.loadFinished.connect(self.check_download_availability)
        main_layout.addWidget(self.web_view, stretch=1)

        # Controls
        control_group = QWidget()
        control_layout = QHBoxLayout(control_group)
        
        self.status_label = QLabel("状态: 就绪")
        control_layout.addWidget(self.status_label)

        control_layout.addStretch()

        control_layout.addWidget(QLabel("格式:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["txt", "epub", "md"])
        control_layout.addWidget(self.format_combo)

        # Single Download Button
        self.download_btn = QPushButton("下载当前书籍")
        self.download_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 5px 15px;")
        self.download_btn.clicked.connect(self.start_download_flow)
        self.download_btn.setEnabled(False) 
        control_layout.addWidget(self.download_btn)

        # Batch Download Button
        self.batch_btn = QPushButton("批量下载当前页书籍")
        self.batch_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 5px 15px;")
        self.batch_btn.clicked.connect(self.on_batch_btn_clicked)
        self.batch_btn.setEnabled(False)
        control_layout.addWidget(self.batch_btn)

        main_layout.addWidget(control_group)

        # Shared Bottom
        self.progress_bar = QProgressBar()
        main_layout.addWidget(self.progress_bar)

        self.log_area = QTextEdit()
        self.log_area.setMaximumHeight(100)
        self.log_area.setReadOnly(True)
        main_layout.addWidget(self.log_area)

    def navigate_to_url(self):
        url = self.url_bar.text().strip()
        if not url.startswith("http"):
            url = "https://" + url
        self.web_view.setUrl(QUrl(url))

    def update_url_bar(self, qurl):
        self.url_bar.setText(qurl.toString())
        self.check_download_availability()

    def check_download_availability(self):
        url = self.web_view.url().toString()
        is_book = "/page/" in url and "fanqienovel.com" in url
        # Detect rank or library pages
        is_rank = ("fanqienovel.com" in url) and ("/rank" in url or "/library" in url or "sort=" in url)
        
        if is_book:
            self.download_btn.setEnabled(True)
            self.download_btn.setText("下载此书 (检测到目录)")
            self.status_label.setText("发现书籍，可以下载")
            self.batch_btn.setEnabled(False)
        elif is_rank:
            self.download_btn.setEnabled(False)
            self.download_btn.setText("请进入书籍目录页")
            self.batch_btn.setEnabled(True)
            self.status_label.setText("发现榜单/书库，可批量下载")
        else:
            self.download_btn.setEnabled(False)
            self.download_btn.setText("请进入书籍目录页")
            self.batch_btn.setEnabled(False)
            self.status_label.setText("请浏览至书籍目录页或榜单页")

    def log(self, msg):
        self.log_area.append(msg)
        sb = self.log_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def on_cookie_added(self, cookie):
        name = cookie.name().data().decode('utf-8')
        value = cookie.value().data().decode('utf-8')
        domain = cookie.domain()
        path = cookie.path()
        secure = cookie.isSecure()
        http_only = cookie.isHttpOnly()
        # expiration = cookie.expirationDate() # QDateTime
        
        self.current_cookies[name] = value
        
        self.full_cookies_map[name] = {
            'name': name,
            'value': value,
            'domain': domain,
            'path': path,
            'secure': secure,
            'http_only': http_only
        }
        
        # Auto-save
        self.save_cookies()

    # --- Single Download Methods ---

    def start_download_flow(self):
        self.download_btn.setEnabled(False)
        self.batch_btn.setEnabled(False)
        self.log("正在同步登录状态...")
        
        # Sync User-Agent to match browser
        ua = self.web_view.page().profile().httpUserAgent()
        self.downloader.headers['User-Agent'] = ua

        # Use the cookies captured from QWebEngineCookieStore
        self.downloader.cookies = self.current_cookies
        self.log(f"已同步 Cookies (数量: {len(self.current_cookies)}), 正在获取书籍信息...")
        
        # Start fetching book info
        url = self.web_view.url().toString()
        self.info_worker = BookInfoWorker(self.downloader, url)
        self.info_worker.finished_signal.connect(self.on_book_info_ready)
        self.info_worker.error_signal.connect(self.on_error_reset)
        self.info_worker.start()

    def on_book_info_ready(self, book_info):
        self.pending_book_info = book_info
        self.log(f"成功获取书籍信息: {book_info['title']}, 共 {len(book_info['chapters'])} 章")
        
        # Show selection dialog
        dialog = ChapterSelectionDialog(len(book_info['chapters']), self)
        if dialog.exec():
            indices, split_files = dialog.get_data()
            self.start_real_download(book_info, indices, split_files)
        else:
            self.log("用户取消下载")
            self.download_btn.setEnabled(True)
            self.check_download_availability() # Restore batch btn if needed

    def start_real_download(self, book_info, indices, split_files):
        self.log("开始下载任务...")
        
        save_dir = os.path.join(os.getcwd(), "downloads")
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
            
        fmt = self.format_combo.currentText()
        url = self.web_view.url().toString()
        
        self.worker = DownloadWorker(self.downloader, url, save_dir, fmt, 
                                   book_info=book_info, 
                                   chapter_indices=indices, 
                                   split_files=split_files)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.log_signal.connect(self.log)
        self.worker.finished_signal.connect(self.on_download_finished)
        self.worker.error_signal.connect(self.on_error_reset)
        
        self.worker.start()

    def update_progress(self, current, total, title):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(f"正在下载: {title} ({current}/{total})")

    def on_download_finished(self, filepath):
        self.log(f"下载完成! 保存路径: {filepath}")
        QMessageBox.information(self, "完成", f"书籍下载完成！\n保存至: {filepath}")
        self.reset_ui_state()

    def on_error_reset(self, err_msg):
        self.log(f"错误: {err_msg}")
        QMessageBox.warning(self, "出错", f"发生错误: {err_msg}")
        self.reset_ui_state()

    def reset_ui_state(self):
        self.progress_bar.setValue(0)
        self.check_download_availability()

    # --- Batch Download Methods ---

    def on_batch_btn_clicked(self):
        # 1. Ask for settings
        dialog = BatchOptionsDialog(self)
        if dialog.exec():
            top_n, chapter_limit, fmt, split_files = dialog.get_data()
            self.start_batch_download(top_n, chapter_limit, fmt, split_files)
        else:
            self.log("取消批量下载")

    def parse_category_path(self, title, url):
        # Default values
        level1 = "其他频"
        level2 = "其他榜"
        level3 = "其他分类"
        
        # Level 1: Gender
        if "男频" in title:
            level1 = "男频"
        elif "女频" in title:
            level1 = "女频"
        elif "/rank/general" in url:
            level1 = "男频"
        elif "/rank/girls" in url:
            level1 = "女频"
            
        # Level 2: Rank Type
        if "新书榜" in title:
            level2 = "新书榜"
        elif "阅读榜" in title or "热榜" in title:
            level2 = "阅读榜"
        elif "完结榜" in title:
            level2 = "完结榜"
        elif "好评榜" in title:
            level2 = "好评榜"
        elif "口碑榜" in title:
            level2 = "口碑榜"
        
        # Level 3: Category
        # Remove common suffixes and prefixes to isolate category
        clean_name = title
        # Remove site suffix
        for suffix in ["-番茄小说官网", "_官网", "番茄小说官网", "官网", "番茄小说", "免费阅读", "小说排行榜", "排行榜"]:
            clean_name = clean_name.replace(suffix, "")
        
        # Remove Level 1 and Level 2 keywords
        clean_name = clean_name.replace("男频", "").replace("女频", "")
        clean_name = clean_name.replace("新书榜", "").replace("阅读榜", "").replace("完结榜", "").replace("好评榜", "").replace("口碑榜", "").replace("热榜", "")
        
        # Remove "小说" if it remains at end or inside
        clean_name = clean_name.replace("小说", "")
        
        # Clean up punctuation
        clean_name = clean_name.replace("-", "").replace("_", "").replace("·", "").strip()
        
        if clean_name:
            level3 = clean_name
        else:
            if "全部" in title:
                level3 = "全部"
            else:
                level3 = "综合"
                
        return level1, level2, level3

    def start_batch_download(self, top_n, chapter_limit, fmt='txt', split_files=False):
        self.batch_btn.setEnabled(False)
        self.download_btn.setEnabled(False)
        
        url = self.web_view.url().toString()
        title = self.web_view.title()
        
        self.log(f"准备批量下载: {title} (Top {top_n}, 格式: {fmt}, 分章: {split_files})")
        
        # Sync UA and Cookies
        ua = self.web_view.page().profile().httpUserAgent()
        self.downloader.headers['User-Agent'] = ua
        self.downloader.cookies = self.current_cookies
        
        save_base_dir = os.path.join(os.getcwd(), "downloads")
        
        # Parse path components
        l1, l2, l3 = self.parse_category_path(title, url)
        
        # Construct final save path
        final_save_path = os.path.join(save_base_dir, l1, l2, l3)
        self.log(f"保存路径: {final_save_path}")

        self.batch_worker = BatchDownloadWorker(
            self.downloader, 
            url, 
            final_save_path, 
            top_n=top_n,
            chapters_count=chapter_limit,
            fmt=fmt,
            split_files=split_files
        )
        self.batch_worker.progress_signal.connect(self.on_batch_progress)
        self.batch_worker.log_signal.connect(self.log)
        self.batch_worker.finished_signal.connect(self.on_batch_finished)
        self.batch_worker.error_signal.connect(self.on_batch_error)
        self.batch_worker.start()

    def on_batch_progress(self, current_idx, total, status):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current_idx)
        self.status_label.setText(status)

    def on_batch_finished(self, summary):
        self.log(summary)
        QMessageBox.information(self, "批量下载完成", summary)
        self.reset_ui_state()
        
    def on_batch_error(self, err):
        self.log(f"批量下载出错: {err}")
        QMessageBox.warning(self, "出错", str(err))
        self.reset_ui_state()

if __name__ == "__main__":
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
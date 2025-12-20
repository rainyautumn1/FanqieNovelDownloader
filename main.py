import sys
import os
import time
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLineEdit, QPushButton, QProgressBar, 
                             QTextEdit, QLabel, QMessageBox, QComboBox, QDialog,
                             QGroupBox, QRadioButton, QCheckBox, QSpinBox, QTabWidget)
from PySide6.QtCore import QUrl, QThread, Signal, Slot, Qt, QTimer
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
import json

from downloader import FanqieDownloader, VerificationError

# 批量下载工作线程
class BatchDownloadWorker(QThread):
    progress_signal = Signal(int, int, str) # 当前书籍索引, 总书籍数, 当前状态
    log_signal = Signal(str)
    finished_signal = Signal(str) # 摘要
    error_signal = Signal(str)

    def __init__(self, downloader, rank_url, save_dir, top_n=5, chapters_count=0, fmt='txt', split_files=False):
        super().__init__()
        self.downloader = downloader
        self.rank_url = rank_url
        self.save_dir = save_dir
        self.top_n = top_n
        self.chapters_count = chapters_count # 0 表示全部
        self.fmt = fmt
        self.split_files = split_files
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
                            control_callback=self.check_control_status
                        )
                    elif self.fmt == 'md':
                        filepath = self.downloader.save_to_md(
                            book_info, 
                            self.save_dir, 
                            callback,
                            chapter_indices=indices,
                            split_files=self.split_files,
                            control_callback=self.check_control_status
                        )
                    else: # epub格式
                        filepath = self.downloader.save_to_epub(
                            book_info, 
                            self.save_dir, 
                            callback,
                            chapter_indices=indices,
                            control_callback=self.check_control_status
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

class BatchOptionsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量下载设置")
        self.resize(300, 250)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # 前 N 本
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("下载当前页前 N 本书:"))
        self.spin_top_n = QSpinBox()
        self.spin_top_n.setRange(1, 100)
        self.spin_top_n.setValue(5)
        h1.addWidget(self.spin_top_n)
        layout.addLayout(h1)
        
        # 章节限制
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("每本限制章节 (0为全部):"))
        self.spin_chapter_limit = QSpinBox()
        self.spin_chapter_limit.setRange(0, 5000)
        self.spin_chapter_limit.setValue(0)
        h2.addWidget(self.spin_chapter_limit)
        layout.addLayout(h2)

        # 格式选择
        h3 = QHBoxLayout()
        h3.addWidget(QLabel("保存格式:"))
        self.combo_fmt = QComboBox()
        self.combo_fmt.addItems(["txt", "epub", "md"])
        h3.addWidget(self.combo_fmt)
        layout.addLayout(h3)

        # 分章保存选项
        h4 = QHBoxLayout()
        h4.addWidget(QLabel("分章保存:"))
        self.check_split = QCheckBox("每章一个文件 (仅TXT/MD有效)")
        h4.addWidget(self.check_split)
        layout.addLayout(h4)
        
        layout.addStretch()
        
        # 按钮
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

    def __init__(self, downloader, book_url, save_dir, fmt, book_info=None, chapter_indices=None, split_files=False):
        super().__init__()
        self.downloader = downloader
        self.book_url = book_url
        self.save_dir = save_dir
        self.fmt = fmt
        self.book_info = book_info
        self.chapter_indices = chapter_indices
        self.split_files = split_files
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
                    control_callback=self.check_control_status
                )
            elif self.fmt == 'md':
                filepath = self.downloader.save_to_md(
                    self.book_info, 
                    self.save_dir, 
                    callback,
                    chapter_indices=self.chapter_indices,
                    split_files=self.split_files,
                    control_callback=self.check_control_status
                )
            else:
                filepath = self.downloader.save_to_epub(
                    self.book_info, 
                    self.save_dir, 
                    callback,
                    chapter_indices=self.chapter_indices,
                    control_callback=self.check_control_status
                )
            
            self.finished_signal.emit(filepath)

        except Exception as e:
            self.error_signal.emit(str(e))

class CustomWebEnginePage(QWebEnginePage):
    """自定义页面以在同一视图中打开链接而不是新标签页"""
    def createWindow(self, _type):
        return self

class CustomWebEngineView(QWebEngineView):
    """使用我们要自定义页面的自定义视图"""
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
        
        # 章节选择组
        grp_box = QGroupBox("章节选择")
        grp_layout = QVBoxLayout(grp_box)
        
        self.radio_all = QRadioButton(f"全部章节 (共 {self.total_chapters} 章)")
        self.radio_all.setChecked(True)
        grp_layout.addWidget(self.radio_all)
        
        # 范围
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
        
        # 列表
        list_layout = QHBoxLayout()
        self.radio_list = QRadioButton("自定义列表:")
        self.edit_list = QLineEdit()
        self.edit_list.setPlaceholderText("例如: 1,3,5 (逗号分隔)")
        list_layout.addWidget(self.radio_list)
        list_layout.addWidget(self.edit_list)
        grp_layout.addLayout(list_layout)
        
        layout.addWidget(grp_box)
        
        # 文件保存选项
        file_box = QGroupBox("文件保存选项")
        file_layout = QVBoxLayout(file_box)
        self.check_split = QCheckBox("分章保存 (每章一个文件)")
        self.check_split.setToolTip("仅TXT/MD格式有效")
        file_layout.addWidget(self.check_split)
        layout.addWidget(file_box)
        
        # 按钮
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("开始下载")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        # 连接信号以自动选择单选按钮
        self.spin_start.valueChanged.connect(lambda: self.radio_range.setChecked(True))
        self.spin_end.valueChanged.connect(lambda: self.radio_range.setChecked(True))
        self.edit_list.textChanged.connect(lambda: self.radio_list.setChecked(True))
        
    def get_data(self):
        # 返回 (indices, split_files)
        # indices 是基于0的索引列表，或 None 表示全部
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
            # 逗号分隔的基本解析
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
        self.full_cookies_map = {} # 存储完整的 Cookie 信息以进行持久化
        self.pending_book_info = None
        
        # 自定义导航历史记录
        self.custom_history = []
        self.history_index = -1
        self.is_navigating_history = False

        self.setup_ui()
        
        # 设置 Cookie 存储监控
        self.cookie_store = self.web_view.page().profile().cookieStore()
        self.cookie_store.cookieAdded.connect(self.on_cookie_added)
        
        # 加载保存的 Cookies
        self.load_cookies()
        
        # 初始加载
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
                            # 更新下载器的内存
                            self.current_cookies[name] = value
                            self.full_cookies_map[name] = c_data
                            
                            # 注入浏览器
                            q_cookie = QNetworkCookie(name.encode('utf-8'), value.encode('utf-8'))
                            if domain:
                                q_cookie.setDomain(domain)
                            if path:
                                q_cookie.setPath(path)
                            if secure:
                                q_cookie.setSecure(True)
                            if http_only:
                                q_cookie.setHttpOnly(True)
                            
                            # 调试日志 (可选，稍后可删除)
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

        # 导航栏
        nav_layout = QHBoxLayout()
        
        self.back_btn = QPushButton("后退")
        self.back_btn.setEnabled(False) # 初始禁用
        nav_layout.addWidget(self.back_btn)

        self.forward_btn = QPushButton("前进")
        self.forward_btn.setEnabled(False) # 初始禁用
        nav_layout.addWidget(self.forward_btn)

        self.refresh_btn = QPushButton("刷新")
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

        # 浏览器
        self.web_view = CustomWebEngineView()
        
        # 配置本地存储的持久配置文件
        storage_path = os.path.join(os.getcwd(), "browser_data")
        if not os.path.exists(storage_path):
            os.makedirs(storage_path)
            
        # 创建命名配置文件，如果设置了存储路径则意味着持久化
        profile = QWebEngineProfile("FanqieProfile", self.web_view)
        profile.setPersistentStoragePath(storage_path)
        profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        
        # 使用此配置文件创建页面
        page = CustomWebEnginePage(profile, self.web_view)
        self.web_view.setPage(page)
        
        # 连接导航信号
        self.back_btn.clicked.connect(self.on_back_custom)
        self.forward_btn.clicked.connect(self.on_forward_custom)
        self.refresh_btn.clicked.connect(self.web_view.reload)

        self.web_view.urlChanged.connect(self.update_url_bar)
        self.web_view.loadFinished.connect(self.check_download_availability)
        main_layout.addWidget(self.web_view, stretch=1)

        # 控制
        control_group = QWidget()
        control_layout = QHBoxLayout(control_group)
        
        self.status_label = QLabel("状态: 就绪")
        control_layout.addWidget(self.status_label)

        control_layout.addStretch()

        control_layout.addWidget(QLabel("格式:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["txt", "epub", "md"])
        control_layout.addWidget(self.format_combo)

        # 单本下载按钮
        self.download_btn = QPushButton("下载当前书籍")
        self.download_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 5px 15px;")
        self.download_btn.clicked.connect(self.start_download_flow)
        self.download_btn.setEnabled(False) 
        control_layout.addWidget(self.download_btn)

        # 批量下载按钮
        self.batch_btn = QPushButton("批量下载当前页书籍")
        self.batch_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 5px 15px;")
        self.batch_btn.clicked.connect(self.on_batch_btn_clicked)
        self.batch_btn.setEnabled(False)
        control_layout.addWidget(self.batch_btn)

        # 控制按钮
        self.pause_btn = QPushButton("暂停")
        self.pause_btn.clicked.connect(self.on_pause_clicked)
        self.pause_btn.setEnabled(False)
        control_layout.addWidget(self.pause_btn)

        self.resume_btn = QPushButton("继续")
        self.resume_btn.clicked.connect(self.on_resume_clicked)
        self.resume_btn.setEnabled(False)
        control_layout.addWidget(self.resume_btn)

        self.stop_btn = QPushButton("停止")
        self.stop_btn.setStyleSheet("background-color: #F44336; color: white; font-weight: bold;")
        self.stop_btn.clicked.connect(self.on_stop_clicked)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn)

        main_layout.addWidget(control_group)

        # 共享底部
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
        url_str = qurl.toString()
        
        # 自动移除手机端强制参数
        if "force_mobile=1" in url_str or "_mobile=1" in url_str:
            new_url = url_str.replace("force_mobile=1", "").replace("_mobile=1", "")
            # 清理可能产生的多余符号
            new_url = new_url.replace("?&", "?").replace("&&", "&")
            if new_url.endswith("?") or new_url.endswith("&"):
                new_url = new_url[:-1]
            
            if new_url != url_str:
                self.log("检测到手机端页面，正在自动切换回 PC 端...")
                self.web_view.setUrl(QUrl(new_url))
                return

        self.url_bar.setText(url_str)
        self.check_download_availability()
        
        # 自定义历史记录逻辑
        if self.is_navigating_history:
            # 如果是历史记录导航导致的，重置标志位
            self.is_navigating_history = False
        else:
            # 如果是新页面
            # 避免重复记录（比如页面内部重定向或者锚点变化，这里先简单判断字符串）
            if self.history_index == -1 or (self.history_index < len(self.custom_history) and self.custom_history[self.history_index] != url_str):
                # 如果当前不在列表末尾，截断后面的
                if self.history_index < len(self.custom_history) - 1:
                    self.custom_history = self.custom_history[:self.history_index + 1]
                
                self.custom_history.append(url_str)
                self.history_index += 1
        
        self.update_nav_buttons()

    def update_nav_buttons(self):
        # 使用自定义历史记录状态
        self.back_btn.setEnabled(self.history_index > 0)
        self.forward_btn.setEnabled(self.history_index < len(self.custom_history) - 1)

    def on_back_custom(self):
        if self.history_index > 0:
            self.is_navigating_history = True
            self.history_index -= 1
            url = self.custom_history[self.history_index]
            self.web_view.setUrl(QUrl(url))
            self.update_nav_buttons()

    def on_forward_custom(self):
        if self.history_index < len(self.custom_history) - 1:
            self.is_navigating_history = True
            self.history_index += 1
            url = self.custom_history[self.history_index]
            self.web_view.setUrl(QUrl(url))
            self.update_nav_buttons()

    def check_download_availability(self):
        url = self.web_view.url().toString()
        is_book = "/page/" in url and "fanqienovel.com" in url
        # 检测榜单或书库页面
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
            
        # 延迟更新导航按钮，确保 history 已更新
        # QTimer.singleShot(100, self.update_nav_buttons)
        # QTimer.singleShot(500, self.update_nav_buttons) # 双重保险

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
        # expiration = cookie.expirationDate() # QDateTime (未翻译，代码注释)
        
        self.current_cookies[name] = value
        
        self.full_cookies_map[name] = {
            'name': name,
            'value': value,
            'domain': domain,
            'path': path,
            'secure': secure,
            'http_only': http_only
        }
        
        # 自动保存
        self.save_cookies()

    # --- 单本下载方法 ---

    def on_pause_clicked(self):
        # 检查单本工作线程
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            self.worker.pause()
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(True)
        # 检查批量工作线程
        elif hasattr(self, 'batch_worker') and self.batch_worker and self.batch_worker.isRunning():
            self.batch_worker.pause()
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(True)

    def on_resume_clicked(self):
        # 检查单本工作线程
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            self.worker.resume()
            self.pause_btn.setEnabled(True)
            self.resume_btn.setEnabled(False)
        # 检查批量工作线程
        elif hasattr(self, 'batch_worker') and self.batch_worker and self.batch_worker.isRunning():
            self.batch_worker.resume()
            self.pause_btn.setEnabled(True)
            self.resume_btn.setEnabled(False)

    def on_stop_clicked(self):
        # 检查单本工作线程
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            self.worker.stop()
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
        # 检查批量工作线程
        elif hasattr(self, 'batch_worker') and self.batch_worker and self.batch_worker.isRunning():
            self.batch_worker.stop()
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)

    def start_download_flow(self):
        self.download_btn.setEnabled(False)
        self.batch_btn.setEnabled(False)
        self.log("正在同步登录状态...")
        
        # 同步 User-Agent 以匹配浏览器
        ua = self.web_view.page().profile().httpUserAgent()
        self.downloader.headers['User-Agent'] = ua

        # 使用从 QWebEngineCookieStore 捕获的 cookies
        self.downloader.cookies = self.current_cookies
        self.log(f"已同步 Cookies (数量: {len(self.current_cookies)}), 正在获取书籍信息...")
        
        # 开始获取书籍信息
        url = self.web_view.url().toString()
        self.info_worker = BookInfoWorker(self.downloader, url)
        self.info_worker.finished_signal.connect(self.on_book_info_ready)
        self.info_worker.error_signal.connect(self.on_error_reset)
        self.info_worker.start()

    def on_book_info_ready(self, book_info):
        self.pending_book_info = book_info
        self.log(f"成功获取书籍信息: {book_info['title']}, 共 {len(book_info['chapters'])} 章")
        
        # 显示选择对话框
        dialog = ChapterSelectionDialog(len(book_info['chapters']), self)
        if dialog.exec():
            indices, split_files = dialog.get_data()
            self.start_real_download(book_info, indices, split_files)
        else:
            self.log("用户取消下载")
            self.download_btn.setEnabled(True)
            self.check_download_availability() # 如果需要，恢复批量按钮

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

        # 启用控制按钮
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.resume_btn.setEnabled(False)

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
        if "用户停止下载" in err_msg:
            QMessageBox.information(self, "停止", "用户停止下载")
        elif "检测到验证码" in err_msg or "验证码" in err_msg:
            QMessageBox.warning(self, "需要验证", "检测到验证码或风控页面。\n请在右侧浏览器中完成验证码，然后重新尝试下载。")
        else:
            QMessageBox.warning(self, "出错", f"发生错误: {err_msg}")
        self.reset_ui_state()

    def reset_ui_state(self):
        self.progress_bar.setValue(0)
        self.check_download_availability()
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)

    # --- 批量下载方法 ---

    def on_batch_btn_clicked(self):
        # 1. 询问设置
        dialog = BatchOptionsDialog(self)
        if dialog.exec():
            top_n, chapter_limit, fmt, split_files = dialog.get_data()
            self.start_batch_download(top_n, chapter_limit, fmt, split_files)
        else:
            self.log("取消批量下载")

    def parse_category_path(self, title, url):
        # 默认值
        level1 = "其他频"
        level2 = "其他榜"
        level3 = "其他分类"
        
        # 第一层: 男频/女频
        if "男频" in title:
            level1 = "男频"
        elif "女频" in title:
            level1 = "女频"
        elif "/rank/general" in url:
            level1 = "男频"
        elif "/rank/girls" in url:
            level1 = "女频"
            
        # 第二层: 榜单类型
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
        
        # 第三层: 分类
        # 移除常见的后缀和前缀以分离分类
        clean_name = title
        # 移除站点后缀
        for suffix in ["-番茄小说官网", "_官网", "番茄小说官网", "官网", "番茄小说", "免费阅读", "小说排行榜", "排行榜"]:
            clean_name = clean_name.replace(suffix, "")
        
        # 移除第一层和第二层关键字
        clean_name = clean_name.replace("男频", "").replace("女频", "")
        clean_name = clean_name.replace("新书榜", "").replace("阅读榜", "").replace("完结榜", "").replace("好评榜", "").replace("口碑榜", "").replace("热榜", "")
        
        # 如果 "小说" 留在结尾或中间，则移除
        clean_name = clean_name.replace("小说", "")
        
        # 清理标点符号
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
        
        # 同步 UA 和 Cookies
        ua = self.web_view.page().profile().httpUserAgent()
        self.downloader.headers['User-Agent'] = ua
        self.downloader.cookies = self.current_cookies
        
        save_base_dir = os.path.join(os.getcwd(), "downloads")
        
        # 解析路径组件
        l1, l2, l3 = self.parse_category_path(title, url)
        
        # 构建最终保存路径
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

        # 启用控制按钮
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.resume_btn.setEnabled(False)

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
        
        if "验证码" in str(err):
            QMessageBox.warning(self, "需要验证", str(err))
        elif "批量下载已停止" in str(err) or "用户停止下载" in str(err):
            QMessageBox.information(self, "停止", "用户停止下载")
        else:
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
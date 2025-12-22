import sys
import os
import openpyxl
import traceback
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLineEdit, QPushButton, QProgressBar, 
                             QTextEdit, QLabel, QMessageBox, QComboBox)
from PySide6.QtCore import QUrl, Qt
from PySide6.QtNetwork import QNetworkCookie
from PySide6.QtWebEngineCore import QWebEngineProfile
import json

import logging
from logging_config import setup_logging
from downloader import FanqieDownloader
from workers import BatchDownloadWorker, BookInfoWorker, DownloadWorker, RankParserWorker, TitleCorrectionWorker
from ui_components import CustomWebEngineView, CustomWebEnginePage, ChapterSelectionDialog, BatchOptionsDialog, FAQDialog
from download_manager import DownloadManager
from download_ui import DownloadManagerWindow
from update_manager import check_update
from version import VERSION

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"番茄小说下载器内置浏览器版 v{VERSION}")
        self.resize(1200, 800)

        # 设置窗口图标
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app.ico')
        if os.path.exists(icon_path):
            from PySide6.QtGui import QIcon
            QApplication.instance().setWindowIcon(QIcon(icon_path))

        # 启动时检查更新
        # 使用 QTimer.singleShot 在主循环启动后执行，避免阻塞启动或 UI 未就绪
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1000, lambda: self.check_for_updates())

        self.downloader = FanqieDownloader()
        
        # 初始化下载管理器
        self.download_manager = DownloadManager(self.downloader)
        self.download_window = DownloadManagerWindow()
        self.setup_manager_connections()

        self.current_cookies = {}
        self.full_cookies_map = {} # 存储完整的 Cookie 信息以进行持久化
        self.pending_book_info = None
        
        # 自定义导航历史记录
        self.custom_history = []
        self.history_index = -1
        self.is_navigating_history = False

        self.setup_ui()
        
        # 显式显示开源声明弹窗 (只在第一次显示，或者每次启动都显示？用户要求显著标记，建议放在主界面上方或弹窗)
        # 这里选择在 UI 初始化后，在主界面顶部添加一个显著的 Banner
        
        # 初始化日志系统
        self.log_signal = setup_logging()
        self.log_signal.log_received.connect(self.append_log)

        # 设置 Cookie 存储监控
        self.cookie_store = self.web_view.page().profile().cookieStore()
        self.cookie_store.cookieAdded.connect(self.on_cookie_added)
        
        # 加载保存的 Cookies
        self.load_cookies()
        
        # 初始加载
        self.web_view.setUrl(QUrl("https://fanqienovel.com/"))

    def check_for_updates(self, force=False):
        """调用 update_manager 检查更新"""
        try:
            # check_update 返回 False 表示正在进行更新（需要关闭当前窗口），返回 True 表示无需更新或取消
            should_continue = check_update(self, force=force)
            if not should_continue:
                # 如果 check_update 内部触发了更新流程，理论上它会处理重启
                # 但这里我们确保主窗口关闭
                self.close()
        except Exception as e:
            self.log(f"自动更新检查出错: {e}")

    def setup_manager_connections(self):
        # UI -> Manager
        self.download_window.start_all_signal.connect(self.download_manager.start_all)
        self.download_window.pause_all_signal.connect(self.download_manager.pause_all)
        self.download_window.cancel_all_signal.connect(self.download_manager.cancel_all)
        self.download_window.clear_finished_signal.connect(self.download_window.clear_finished_items)
        self.download_window.max_concurrent_changed.connect(self.download_manager.set_max_concurrent_tasks)
        
        # Manager -> UI
        self.download_manager.task_added.connect(self.on_task_added)
        self.download_manager.task_updated.connect(self.on_task_updated)
        self.download_manager.task_status_changed.connect(self.download_window.update_downloading_item_status)
        self.download_manager.task_finished.connect(self.on_task_finished)
        self.download_manager.task_removed.connect(self.download_window.remove_downloading_item)
        self.download_manager.verification_needed.connect(self.on_verification_needed)

    def on_task_updated(self, task_id, current, total, msg):
        # 获取任务对象以检查是否有标题更新
        task = self.download_manager.get_task(task_id)
        title = task.title if task else None
        
        # 在UI更新时传递标题
        self.download_window.update_downloading_item(task_id, current, total, msg, title)

    def on_task_added(self, task_id, title):
        widget = self.download_window.add_downloading_item(task_id, title)
        # 连接单个任务的操作信号
        widget.action_triggered.connect(self.handle_task_action)
        
        # 如果下载窗口未显示，可以给个提示或者自动显示（根据需求，这里暂不自动显示，避免打扰）
        # self.download_window.show()

    def handle_task_action(self, task_id, action):
        if action == 'pause':
            self.download_manager.pause_task(task_id)
        elif action == 'resume':
            self.download_manager.start_task(task_id)
        elif action == 'cancel':
            self.download_manager.cancel_task(task_id)

    def on_task_finished(self, task_id, title, filepath):
        # 移除正在下载列表
        self.download_window.remove_downloading_item(task_id)
        # 添加到完成列表
        widget = self.download_window.add_finished_item(task_id, title, filepath)
        # 连接完成项的操作信号
        widget.open_folder_signal.connect(self.open_file_folder)
        widget.delete_signal.connect(self.delete_finished_record)
        
        # 弹窗提示
        # QMessageBox.information(self, "下载完成", f"《{title}》下载完成！")

    def on_verification_needed(self, task_id, url):
        """处理验证码请求"""
        # 1. 恢复窗口如果被最小化
        if self.isMinimized():
            self.showNormal()
        
        # 2. 激活窗口到前台
        self.activateWindow()
        self.raise_()
        
        # 3. 浏览器加载验证码页面
        self.web_view.setUrl(QUrl(url))
        
        # 4. 检查是否已经有验证弹窗，避免重复
        if hasattr(self, 'verification_dialog') and self.verification_dialog.isVisible():
            return

        # 5. 显示非模态对话框，允许用户操作浏览器
        self.verification_dialog = QMessageBox(self)
        self.verification_dialog.setWindowTitle("等待验证完成")
        self.verification_dialog.setText("检测到番茄小说安全验证，下载已暂停。\n\n1. 请在主界面浏览器中完成验证码操作。\n2. 验证完成后，点击下方按钮恢复下载。\n\n提示：您可以拖动此窗口以免遮挡验证码。")
        self.verification_dialog.setIcon(QMessageBox.Information)
        
        # 添加自定义按钮
        self.resume_btn = self.verification_dialog.addButton("验证已完成，前往下载管理", QMessageBox.AcceptRole)
        self.resume_btn.setEnabled(False) # 初始禁用，等待验证通过
        
        # 设置为非模态，允许用户操作主窗口
        self.verification_dialog.setWindowModality(Qt.NonModal)
        # 保持在顶层
        self.verification_dialog.setWindowFlags(self.verification_dialog.windowFlags() | Qt.WindowStaysOnTopHint)
        
        # 连接按钮点击事件
        self.resume_btn.clicked.connect(self.on_verification_completed)
        
        # 监听标题变化，自动检测验证是否完成
        self.web_view.titleChanged.connect(self.check_verification_status)
        self.web_view.loadFinished.connect(lambda _: self.check_verification_status(self.web_view.title()))
        
        self.verification_dialog.show()

    def check_verification_status(self, title):
        """检查页面标题，判断验证是否完成"""
        if not hasattr(self, 'verification_dialog') or not self.verification_dialog.isVisible():
            return

        # 简单的反向检查：如果标题不包含这些关键字，认为是正常页面
        # 注意：这里可能需要根据实际情况微调
        if "WAF" not in title and "验证" not in title and "Security" not in title:
             # 双重检查：确保不是空标题
             if title and len(title) > 0:
                 if hasattr(self, 'resume_btn'):
                    self.resume_btn.setEnabled(True)
                    self.resume_btn.setText("验证已通过，点击前往下载管理")
        else:
             if hasattr(self, 'resume_btn'):
                self.resume_btn.setEnabled(False)
                self.resume_btn.setText("等待验证完成...")

    def on_verification_completed(self):
        """用户点击验证完成按钮"""
        if hasattr(self, 'verification_dialog'):
            # 断开信号连接，避免资源泄露或后续误触
            try:
                self.web_view.titleChanged.disconnect(self.check_verification_status)
                # loadFinished 的 lambda 比较难断开，但由于 dialog 销毁，影响不大，或者我们可以把 lambda 换成具名函数
            except:
                pass
            self.verification_dialog.close()
        
        # 通知管理器验证已完成，恢复下载
        if hasattr(self, 'download_manager'):
            self.download_manager.resolve_verification()

        # 显示并激活下载管理窗口
        self.download_window.show()
        self.download_window.raise_()
        self.download_window.activateWindow()

    def open_file_folder(self, path):
        try:
            os.startfile(path)
        except Exception as e:
            self.log(f"无法打开文件夹: {e}")

    def delete_finished_record(self, task_id):
        self.download_window.remove_finished_item(task_id)

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
                            
                            # 调试日志 (可选)
                            # logging.debug(f"Loading cookie: {name} for domain: {domain}")

                            self.cookie_store.setCookie(q_cookie)
                            count += 1
                    except Exception as inner_e:
                        logging.warning(f"Error loading single cookie: {inner_e}")
                
                logging.info(f"Loaded {count} cookies from file.")
                self.log(f"已加载 {count} 个保存的 Cookies")
            except Exception as e:
                logging.error(f"Error loading cookies: {e}")
                self.log(f"加载 Cookies 失败: {e}")

    def save_cookies(self):
        try:
            cookie_file = os.path.join(os.getcwd(), "cookies.json")
            cookies_list = list(self.full_cookies_map.values())
            with open(cookie_file, 'w', encoding='utf-8') as f:
                json.dump(cookies_list, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"Error saving cookies: {e}")


    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # === 开源声明 Banner ===
        notice_frame = QWidget()
        # 使用更现代清新的渐变背景色 (浅蓝 -> 浅白) 和 柔和的阴影/圆角
        notice_frame.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #E3F2FD, stop:1 #F8F9FA);
                border: 1px solid #B0BEC5;
                border-radius: 6px;
            }
        """)
        notice_layout = QVBoxLayout(notice_frame)
        notice_layout.setContentsMargins(15, 10, 15, 10)
        
        notice_text = (
            "<p style='margin:0; font-weight:bold; color: #D32F2F; font-size: 15px;'>⚠️ 绝对免费！本项目是开源项目，如果您是付费购买的，请立即退款并举报商家。</p>"
            "<p style='margin:6px 0 0 0; color: #455A64; font-size: 13px;'>项目地址：<a href='https://github.com/rainyautumn1/FanqieNovelDownloader' style='color:#1976D2; text-decoration: none; font-weight: bold;'>https://github.com/rainyautumn1/FanqieNovelDownloader</a> 如果觉得本软件好用，请给作者一个star</p>"
            "<p style='margin:4px 0 0 0; color: #455A64; font-size: 13px;'>软件使用有疑问欢迎到B站私信作者，不过请优先点击【常见问题】按钮，里面应该有解答。</p>"
        )
        notice_label = QLabel(notice_text)
        notice_label.setTextFormat(Qt.RichText)
        notice_label.setOpenExternalLinks(True)
        notice_label.setWordWrap(True)
        # 标签背景透明，避免遮挡渐变
        notice_label.setStyleSheet("background: transparent; border: none;")
        
        notice_layout.addWidget(notice_label)
        main_layout.addWidget(notice_frame)
        # =======================

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

        # control_layout.addWidget(QLabel("格式:"))
        # self.format_combo = QComboBox()
        # self.format_combo.addItems(["txt", "epub", "md"])
        # control_layout.addWidget(self.format_combo)

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

        # 下载管理按钮
        self.manager_btn = QPushButton("下载管理")
        self.manager_btn.setStyleSheet("background-color: #607D8B; color: white; font-weight: bold;")
        self.manager_btn.clicked.connect(lambda: self.download_window.show())
        control_layout.addWidget(self.manager_btn)

        # Bilibili 链接按钮
        self.bili_btn = QPushButton("B站主页")
        self.bili_btn.setStyleSheet("background-color: #FB7299; color: white; font-weight: bold;")
        self.bili_btn.clicked.connect(lambda: self.open_bilibili_link())
        control_layout.addWidget(self.bili_btn)

        # 常见问题按钮
        self.faq_btn = QPushButton("常见问题")
        self.faq_btn.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold;")
        self.faq_btn.clicked.connect(self.show_faq)
        control_layout.addWidget(self.faq_btn)

        # 检查更新按钮
        self.update_btn = QPushButton("检查更新")
        self.update_btn.setStyleSheet("font-weight: bold;")
        self.update_btn.clicked.connect(lambda: self.check_for_updates(force=True))
        control_layout.addWidget(self.update_btn)

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

    def closeEvent(self, event):
        """处理窗口关闭事件"""
        # 保存 cookies
        self.save_cookies()
        
        # 停止所有下载任务
        if hasattr(self, 'download_manager'):
            self.download_manager.stop_all()
            
        event.accept()

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

    def append_log(self, msg, level):
        """响应日志信号，更新 UI"""
        # 可以根据 level 设置颜色
        if level >= logging.ERROR:
            msg = f'<span style="color:red;">{msg}</span>'
        elif level >= logging.WARNING:
            msg = f'<span style="color:orange;">{msg}</span>'
            
        self.log_area.append(msg)
        sb = self.log_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def log(self, msg):
        """兼容旧代码，将日志转发给 logging 系统"""
        logging.info(msg)

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
            indices, split_files, delay, fmt = dialog.get_data()
            self.start_real_download(book_info, indices, split_files, delay, fmt)
        else:
            self.log("用户取消下载")
            self.download_btn.setEnabled(True)
            self.check_download_availability() # 如果需要，恢复批量按钮

    def start_real_download(self, book_info, indices, split_files, delay=-1, fmt='txt'):
        self.log("开始下载任务...")
        
        save_dir = os.path.join(os.getcwd(), "downloads")
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
            
        # fmt = self.format_combo.currentText() # 已从对话框获取
        url = self.web_view.url().toString()
        
        # 添加到任务管理器
        self.download_manager.add_single_task(
            book_url=url, 
            save_dir=save_dir, 
            fmt=fmt, 
            book_info=book_info, 
            chapter_indices=indices, 
            split_files=split_files,
            delay=delay,
            title=book_info.get('title')
        )
        
        self.log("任务已添加至下载队列")
        QMessageBox.information(self, "已添加", "下载任务已添加到队列，请点击“下载管理”查看进度。")
        self.download_window.show()
        
        # 恢复按钮状态（因为现在是异步队列，不阻塞主界面）
        self.download_btn.setEnabled(True)
        self.check_download_availability()

    # 旧的单任务回调方法已废弃，保留空壳或移除
    def update_progress(self, current, total, title):
        pass

    def on_download_finished(self, filepath):
        pass

    def on_error_reset(self, err_msg):
        self.log(f"Worker Error: {err_msg}")

    def reset_ui_state(self):
        self.check_download_availability()
        # self.pause_btn.setEnabled(False)
        # self.resume_btn.setEnabled(False)
        # self.stop_btn.setEnabled(False)

    # --- 批量下载方法 ---

    def on_batch_btn_clicked(self):
        # 1. 询问设置
        dialog = BatchOptionsDialog(self)
        if dialog.exec():
            start, end, chapter_limit, fmt, split_files, delay = dialog.get_data()
            self.start_batch_download(start, end, chapter_limit, fmt, split_files, delay)
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

    def start_batch_download(self, start, end, chapter_limit, fmt='txt', split_files=False, delay=-1):
        self.log(f"准备批量下载 (第 {start} - {end} 本)...")
        self.batch_btn.setEnabled(False)

        # 同步 UA 和 Cookies
        ua = self.web_view.page().profile().httpUserAgent()
        self.downloader.headers['User-Agent'] = ua
        self.downloader.cookies = self.current_cookies
        
        # 保存配置供回调使用
        self.batch_config = {
            'start': start,
            'end': end,
            'chapter_limit': chapter_limit,
            'fmt': fmt,
            'split_files': split_files,
            'delay': delay
        }

        self.web_view.page().toHtml(self.on_batch_html_ready)

    def on_batch_html_ready(self, html):
        url = self.web_view.url().toString()
        self.rank_worker = RankParserWorker(self.downloader, url, html_content=html)
        self.rank_worker.finished_signal.connect(self.on_rank_parsed)
        self.rank_worker.error_signal.connect(self.on_batch_error_reset)
        self.rank_worker.start()
        
    def on_rank_parsed(self, books):
        self.batch_btn.setEnabled(True)
        
        if not books:
            self.log("未找到书籍，请确认页面类型")
            QMessageBox.warning(self, "错误", "未能在当前页面找到书籍列表。")
            return
            
        start = self.batch_config['start']
        end = self.batch_config['end']
        chapter_limit = self.batch_config['chapter_limit']
        fmt = self.batch_config['fmt']
        split_files = self.batch_config['split_files']
        delay = self.batch_config['delay']
        
        # 计算切片
        slice_start = max(0, start - 1)
        slice_end = end # 切片不包含 end，但用户输入的是包含的，所以不需要 -1 (0-based) ? 
        # 用户输入 1-5 (包含5)，0-based 是 0, 1, 2, 3, 4
        # slice [0:5] 是 0, 1, 2, 3, 4. 正确。
        
        target_books = books[slice_start:slice_end]
        self.log(f"解析成功，准备添加 {len(target_books)} 个下载任务 (从第 {start} 到 {end})")
        
        # 确定保存路径
        url = self.web_view.url().toString()
        title = self.web_view.title()
        save_base_dir = os.path.join(os.getcwd(), "downloads")
        l1, l2, l3 = self.parse_category_path(title, url)
        final_save_path = os.path.join(save_base_dir, l1, l2, l3)
        
        if not os.path.exists(final_save_path):
            os.makedirs(final_save_path)

        # --- 保存书籍元数据到 XLSX ---
        try:
            xlsx_filename = f"{l3}运营数据.xlsx"
            xlsx_path = os.path.join(final_save_path, xlsx_filename)
            
            # 检查文件是否存在
            file_exists = os.path.exists(xlsx_path)
            
            if file_exists:
                wb = openpyxl.load_workbook(xlsx_path)
                ws = wb.active
            else:
                wb = openpyxl.Workbook()
                ws = wb.active
                # 写入表头
                ws.append(['书名', 'URL', '状态', '在读人数', '最新章节', '更新时间'])
            
            for book in target_books:
                ws.append([
                    book.get('title', ''),
                    book.get('url', ''),
                    book.get('status', '未知'),
                    book.get('reading_count', '未知'),
                    book.get('last_update', '未知'),
                    book.get('update_time', '未知')
                ])
            
            wb.save(xlsx_path)
            self.log(f"已保存书籍运营数据到: {xlsx_path}")
        except Exception as e:
            self.log(f"保存元数据失败: {str(e)}")
            self.log(traceback.format_exc())
            
        added_tasks = [] # List of (task_id, book_url)
        
        for book in target_books:
            task_id = self.download_manager.add_single_task(
                book_url=book['url'],
                save_dir=final_save_path,
                fmt=fmt,
                book_info=None, # 让 Worker 自己去获取
                chapter_indices=None,
                split_files=split_files,
                delay=delay,
                chapter_limit=chapter_limit,
                title=book.get('title')
            )
            added_tasks.append((task_id, book['url']))
            
        # 启动标题修正 Worker
        if added_tasks:
            # 保持引用防止被垃圾回收
            self.title_correction_worker = TitleCorrectionWorker(self.downloader, added_tasks)
            self.title_correction_worker.title_updated.connect(self.download_manager.update_task_title)
            self.title_correction_worker.start()
            
        QMessageBox.information(self, "已添加", f"已将 {len(target_books)} 本书加入下载队列。")
        self.download_window.show()

    def on_batch_error_reset(self, err):
        self.batch_btn.setEnabled(True)
        self.log(f"解析榜单失败: {err}")
        QMessageBox.warning(self, "错误", f"解析榜单失败: {err}")

    def open_bilibili_link(self):
        import webbrowser
        webbrowser.open("https://space.bilibili.com/3493264627943530")

    def show_faq(self):
        dialog = FAQDialog(self)
        dialog.exec()

if __name__ == "__main__":
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    # 设置 AppUserModelID 以便任务栏图标正确显示
    try:
        from ctypes import windll
        myappid = f'rainyautumn.fanqienoveldownloader.gui.{VERSION}'
        windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except ImportError:
        pass

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
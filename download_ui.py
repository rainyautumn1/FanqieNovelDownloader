import os
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QListWidget, QListWidgetItem, 
                             QStackedWidget, QProgressBar, QDialog, QFrame,
                             QScrollArea, QSizePolicy, QSpinBox)
from PySide6.QtCore import Qt, Signal, QSize, QUrl
from PySide6.QtGui import QIcon, QFont, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

class DownloadingItemWidget(QWidget):
    # 信号：任务ID, 操作类型 ('pause', 'resume', 'cancel')
    action_triggered = Signal(str, str)
    
    def __init__(self, task_id, title, status="等待中", parent=None, cover_url=None):
        super().__init__(parent)
        self.task_id = task_id
        self.current_progress = 0
        self.cover_url = cover_url
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 图标
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(40, 53)
        self.icon_label.setScaledContents(True)
        self.icon_label.setStyleSheet("background-color: #E0E0E0; border-radius: 4px;")
        layout.addWidget(self.icon_label)

        if self.cover_url:
            self.load_cover()
    
    def load_cover(self):
        self.nam = QNetworkAccessManager(self)
        self.nam.finished.connect(self.on_cover_loaded)
        self.nam.get(QNetworkRequest(QUrl(self.cover_url)))

    def on_cover_loaded(self, reply):
        if reply.error() == QNetworkReply.NoError:
            data = reply.readAll()
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            if not pixmap.isNull():
                self.icon_label.setPixmap(pixmap)
        reply.deleteLater()
        
        # 信息区
        info_layout = QVBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        info_layout.addWidget(self.title_label)
        
        self.status_label = QLabel(status)
        self.status_label.setStyleSheet("color: #666; font-size: 12px;")
        info_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(5)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 100)
        info_layout.addWidget(self.progress_bar)
        
        layout.addLayout(info_layout, stretch=1)
        
        # 按钮区
        self.btn_pause = QPushButton("开始") # 默认为开始
        self.btn_pause.setFixedSize(60, 30)
        self.btn_pause.clicked.connect(self.on_pause_clicked)
        layout.addWidget(self.btn_pause)
        
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setFixedSize(60, 30)
        self.btn_cancel.setStyleSheet("color: red;")
        self.btn_cancel.clicked.connect(lambda: self.action_triggered.emit(self.task_id, 'cancel'))
        layout.addWidget(self.btn_cancel)

        # 根据初始状态设置按钮文本
        self.update_status(status) # status string might be "等待中" which maps to 'waiting' logic if passed as 'waiting'

    def update_progress(self, current, total, status_text):
        self.current_progress = current
        if total > 0:
            percent = int((current / total) * 100)
            self.progress_bar.setValue(percent)
        self.status_label.setText(status_text)
        
        # 更新按钮状态（针对已经在排队但有进度的特殊情况）
        if self.btn_pause.text() in ["开始", "继续"]:
             if self.current_progress > 0:
                 self.btn_pause.setText("继续")
             else:
                 self.btn_pause.setText("开始")
        
    def update_status(self, status):
        # status: 'running', 'paused', 'waiting', 'error'
        # 注意：这里传入的 status 是内部状态代码，不是显示的中文
        if status == 'running':
            self.btn_pause.setText("暂停")
            self.btn_pause.setEnabled(True)
        elif status == 'paused':
            self.btn_pause.setText("继续")
            self.btn_pause.setEnabled(True)
        elif status == 'waiting' or status == '等待中': # 兼容初始中文状态
            if self.current_progress > 0:
                self.btn_pause.setText("继续")
            else:
                self.btn_pause.setText("开始")
            self.btn_pause.setEnabled(True)
            if status == 'waiting':
                self.status_label.setText("等待下载...")
            
    def on_pause_clicked(self):
        text = self.btn_pause.text()
        if text == "暂停":
            self.action_triggered.emit(self.task_id, 'pause')
        else:
            self.action_triggered.emit(self.task_id, 'resume')

class FinishedItemWidget(QWidget):
    open_folder_signal = Signal(str) # path
    delete_signal = Signal(str) # task_id
    
    def __init__(self, task_id, title, filepath, parent=None, cover_url=None):
        super().__init__(parent)
        self.task_id = task_id
        self.filepath = filepath
        self.cover_url = cover_url
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 图标
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(40, 53)
        self.icon_label.setScaledContents(True)
        self.icon_label.setStyleSheet("background-color: #E0E0E0; border-radius: 4px;")
        layout.addWidget(self.icon_label)

        if self.cover_url:
            self.load_cover()
        
        # 信息
        info_layout = QVBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        info_layout.addWidget(self.title_label)
        
        self.path_label = QLabel(filepath)
        self.path_label.setStyleSheet("color: #888; font-size: 12px;")
        info_layout.addWidget(self.path_label)
        
        layout.addLayout(info_layout, stretch=1)
        
        # 按钮
        self.btn_open = QPushButton("打开文件夹")
        self.btn_open.clicked.connect(self.on_open_clicked)
        layout.addWidget(self.btn_open)
        
        self.btn_del = QPushButton("删除记录")
        self.btn_del.clicked.connect(lambda: self.delete_signal.emit(self.task_id))
        layout.addWidget(self.btn_del)

    def load_cover(self):
        self.nam = QNetworkAccessManager(self)
        self.nam.finished.connect(self.on_cover_loaded)
        self.nam.get(QNetworkRequest(QUrl(self.cover_url)))

    def on_cover_loaded(self, reply):
        if reply.error() == QNetworkReply.NoError:
            data = reply.readAll()
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            if not pixmap.isNull():
                self.icon_label.setPixmap(pixmap)
        reply.deleteLater()

    def on_open_clicked(self):
        if os.path.exists(self.filepath):
            folder = os.path.dirname(self.filepath)
            self.open_folder_signal.emit(folder)
        else:
            # 如果是目录本身
            if os.path.isdir(self.filepath):
                self.open_folder_signal.emit(self.filepath)

class DownloadManagerWindow(QWidget):
    # 信号定义
    start_all_signal = Signal()
    pause_all_signal = Signal()
    cancel_all_signal = Signal()
    clear_finished_signal = Signal()
    max_concurrent_changed = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("下载任务管理")
        self.resize(800, 600)
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # --- 左侧侧边栏 ---
        sidebar = QFrame()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet("background-color: #F5F6F7; border-right: 1px solid #DDD;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 20, 0, 0)
        sidebar_layout.setSpacing(10)
        
        # 侧边栏按钮样式
        self.btn_style_active = """
            QPushButton {
                text-align: left;
                padding-left: 20px;
                border: none;
                background-color: #E3F2FD;
                color: #2196F3;
                font-weight: bold;
                border-radius: 5px;
            }
        """
        self.btn_style_normal = """
            QPushButton {
                text-align: left;
                padding-left: 20px;
                border: none;
                background-color: transparent;
                color: #333;
            }
            QPushButton:hover {
                background-color: #E0E0E0;
            }
        """
        
        self.btn_downloading = QPushButton("正在下载")
        self.btn_downloading.setFixedSize(180, 40)
        self.btn_downloading.clicked.connect(lambda: self.switch_page(0))
        sidebar_layout.addWidget(self.btn_downloading, alignment=Qt.AlignHCenter)
        
        self.btn_finished = QPushButton("下载完成")
        self.btn_finished.setFixedSize(180, 40)
        self.btn_finished.clicked.connect(lambda: self.switch_page(1))
        sidebar_layout.addWidget(self.btn_finished, alignment=Qt.AlignHCenter)
        
        sidebar_layout.addStretch()
        main_layout.addWidget(sidebar)
        
        # --- 右侧内容区 ---
        content_area = QWidget()
        content_area.setStyleSheet("background-color: white;")
        content_layout = QVBoxLayout(content_area)
        
        self.stacked_widget = QStackedWidget()
        content_layout.addWidget(self.stacked_widget)
        
        # 页面 1: 正在下载
        self.page_downloading = QWidget()
        self.setup_downloading_page()
        self.stacked_widget.addWidget(self.page_downloading)
        
        # 页面 2: 下载完成
        self.page_finished = QWidget()
        self.setup_finished_page()
        self.stacked_widget.addWidget(self.page_finished)
        
        main_layout.addWidget(content_area)
        
        # 默认选中第一页
        self.switch_page(0)
        
    def setup_downloading_page(self):
        layout = QVBoxLayout(self.page_downloading)
        
        # 顶部控制栏
        top_bar = QHBoxLayout()
        self.lbl_downloading_count = QLabel("正在下载 0")
        self.lbl_downloading_count.setStyleSheet("font-size: 16px; font-weight: bold;")
        top_bar.addWidget(self.lbl_downloading_count)
        
        top_bar.addStretch()
        
        # 同时下载数量设置
        lbl_concurrent = QLabel("同时下载数:")
        top_bar.addWidget(lbl_concurrent)
        
        self.spin_concurrent = QSpinBox()
        self.spin_concurrent.setRange(1, 10)
        self.spin_concurrent.setValue(1)
        self.spin_concurrent.setToolTip("设置同时下载的任务数量")
        self.spin_concurrent.valueChanged.connect(self.on_concurrent_changed)
        top_bar.addWidget(self.spin_concurrent)
        
        top_bar.addSpacing(20)

        btn_start_all = QPushButton("全部开始")
        btn_start_all.clicked.connect(self.start_all_signal.emit)
        top_bar.addWidget(btn_start_all)
        
        btn_pause_all = QPushButton("全部暂停")
        btn_pause_all.clicked.connect(self.pause_all_signal.emit)
        top_bar.addWidget(btn_pause_all)
        
        btn_cancel_all = QPushButton("全部取消")
        btn_cancel_all.clicked.connect(self.cancel_all_signal.emit)
        top_bar.addWidget(btn_cancel_all)
        
        layout.addLayout(top_bar)
        
        # 警告提示
        self.warning_label = QLabel("温馨提示：同时下载数量越多，触发验证码的风险越高！当出现验证码时，所有下载将自动暂停，请配合完成验证。")
        self.warning_label.setStyleSheet("color: #E6A23C; background-color: #FDF6EC; padding: 8px; border-radius: 4px; border: 1px solid #FAECD8;")
        self.warning_label.setWordWrap(True)
        layout.addWidget(self.warning_label)
        
        # 列表区
        self.list_downloading = QListWidget()
        self.list_downloading.setFrameShape(QFrame.NoFrame)
        layout.addWidget(self.list_downloading)
        
        # 空状态占位 (默认隐藏)
        self.empty_downloading = QLabel("暂无正在下载的文件")
        self.empty_downloading.setAlignment(Qt.AlignCenter)
        self.empty_downloading.setStyleSheet("color: #999; font-size: 14px; margin-top: 50px;")
        # 这里为了简单，直接放在 layout 里，实际可以通过显隐控制
        # 更好的做法是用 StackedWidget 包裹 List 和 EmptyLabel，这里简化处理
        
    def on_concurrent_changed(self, value):
        self.max_concurrent_changed.emit(value)
        if value > 1:
            self.warning_label.setText(f"温馨提示：当前设置为 {value} 线程下载，请注意：并发数越高，触发验证码的几率越大！")
            self.warning_label.setStyleSheet("color: #F56C6C; background-color: #FEF0F0; padding: 8px; border-radius: 4px; border: 1px solid #FDE2E2;")
        else:
            self.warning_label.setText("温馨提示：单线程下载最安全，不易触发验证码。")
            self.warning_label.setStyleSheet("color: #E6A23C; background-color: #FDF6EC; padding: 8px; border-radius: 4px; border: 1px solid #FAECD8;")

    def setup_finished_page(self):
        layout = QVBoxLayout(self.page_finished)
        
        # 顶部控制栏
        top_bar = QHBoxLayout()
        self.lbl_finished_count = QLabel("共下载完成 0 个文件")
        self.lbl_finished_count.setStyleSheet("font-size: 16px; font-weight: bold;")
        top_bar.addWidget(self.lbl_finished_count)
        
        top_bar.addStretch()
        
        btn_clear = QPushButton("清除全部记录")
        btn_clear.setStyleSheet("background-color: #2196F3; color: white; border-radius: 4px; padding: 5px 10px;")
        btn_clear.clicked.connect(self.clear_finished_signal.emit)
        top_bar.addWidget(btn_clear)
        
        layout.addLayout(top_bar)
        
        # 列表区
        self.list_finished = QListWidget()
        self.list_finished.setFrameShape(QFrame.NoFrame)
        layout.addWidget(self.list_finished)
        
    def switch_page(self, index):
        self.stacked_widget.setCurrentIndex(index)
        if index == 0:
            self.btn_downloading.setStyleSheet(self.btn_style_active)
            self.btn_finished.setStyleSheet(self.btn_style_normal)
        else:
            self.btn_downloading.setStyleSheet(self.btn_style_normal)
            self.btn_finished.setStyleSheet(self.btn_style_active)

    def add_downloading_item(self, task_id, title, cover_url=None):
        item = QListWidgetItem(self.list_downloading)
        widget = DownloadingItemWidget(task_id, title, cover_url=cover_url)
        item.setSizeHint(widget.sizeHint())
        self.list_downloading.addItem(item)
        self.list_downloading.setItemWidget(item, widget)
        self.update_counts()
        return widget
        
    def remove_downloading_item(self, task_id):
        for i in range(self.list_downloading.count()):
            item = self.list_downloading.item(i)
            widget = self.list_downloading.itemWidget(item)
            if widget.task_id == task_id:
                self.list_downloading.takeItem(i)
                self.update_counts()
                return

    def update_downloading_item(self, task_id, current, total, status_text, title=None):
        for i in range(self.list_downloading.count()):
            item = self.list_downloading.item(i)
            widget = self.list_downloading.itemWidget(item)
            if widget.task_id == task_id:
                widget.update_progress(current, total, status_text)
                if title:
                    widget.title_label.setText(title)
                return

    def update_downloading_item_status(self, task_id, status):
        for i in range(self.list_downloading.count()):
            item = self.list_downloading.item(i)
            widget = self.list_downloading.itemWidget(item)
            if widget.task_id == task_id:
                widget.update_status(status)
                return
                
    def add_finished_item(self, task_id, title, filepath, cover_url=None):
        """添加一个新的下载完成项"""
        item = QListWidgetItem(self.list_finished)
        widget = FinishedItemWidget(task_id, title, filepath, cover_url=cover_url)
        item.setSizeHint(widget.sizeHint())
        self.list_finished.addItem(item)
        self.list_finished.setItemWidget(item, widget)
        self.update_counts()
        return widget
        
    def remove_finished_item(self, task_id):
        for i in range(self.list_finished.count()):
            item = self.list_finished.item(i)
            widget = self.list_finished.itemWidget(item)
            if widget.task_id == task_id:
                self.list_finished.takeItem(i)
                self.update_counts()
                return

    def clear_finished_items(self):
        self.list_finished.clear()
        self.update_counts()
        
    def update_counts(self):
        d_count = self.list_downloading.count()
        f_count = self.list_finished.count()
        self.lbl_downloading_count.setText(f"正在下载 {d_count}")
        self.lbl_finished_count.setText(f"共下载完成 {f_count} 个文件")
        
        # 处理空状态提示文本 (如果存在)
        if hasattr(self, 'btn_downloading'):
             self.btn_downloading.setText(f"正在下载  {d_count}")

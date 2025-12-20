from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox, QComboBox, QCheckBox, QPushButton, QGroupBox, QRadioButton, QLineEdit, QDoubleSpinBox, QMessageBox
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage

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

        # 延迟设置
        h_delay = QHBoxLayout()
        h_delay.addWidget(QLabel("下载间隔:"))
        self.combo_delay = QComboBox()
        self.combo_delay.addItems(["随机 (推荐)", "自定义"])
        self.spin_delay = QDoubleSpinBox()
        self.spin_delay.setRange(0.1, 60.0)
        self.spin_delay.setValue(1.0)
        self.spin_delay.setSingleStep(0.1)
        self.spin_delay.setEnabled(False) # 默认随机，禁用输入框
        
        self.combo_delay.currentIndexChanged.connect(self.on_delay_changed)
        
        h_delay.addWidget(self.combo_delay)
        h_delay.addWidget(self.spin_delay)
        h_delay.addWidget(QLabel("秒"))
        layout.addLayout(h_delay)
        
        self.lbl_delay_tip = QLabel("")
        self.lbl_delay_tip.setStyleSheet("color: red; font-size: 10px;")
        layout.addWidget(self.lbl_delay_tip)

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
        
    def on_delay_changed(self, index):
        if index == 0: # 随机
            self.spin_delay.setEnabled(False)
            self.lbl_delay_tip.setText("")
        else: # 自定义
            self.spin_delay.setEnabled(True)
            self.lbl_delay_tip.setText("⚠️ 警告: 间隔过短(<1s)极易触发验证码风控，请谨慎设置！")

    def get_data(self):
        delay = -1 if self.combo_delay.currentIndex() == 0 else self.spin_delay.value()
        return self.spin_top_n.value(), self.spin_chapter_limit.value(), self.combo_fmt.currentText(), self.check_split.isChecked(), delay

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
        
        # 延迟设置 (单本)
        h_delay = QHBoxLayout()
        h_delay.addWidget(QLabel("下载间隔:"))
        self.combo_delay = QComboBox()
        self.combo_delay.addItems(["随机 (推荐)", "自定义"])
        self.spin_delay = QDoubleSpinBox()
        self.spin_delay.setRange(0.1, 60.0)
        self.spin_delay.setValue(1.0)
        self.spin_delay.setSingleStep(0.1)
        self.spin_delay.setEnabled(False) # 默认随机
        
        self.combo_delay.currentIndexChanged.connect(self.on_delay_changed)
        
        h_delay.addWidget(self.combo_delay)
        h_delay.addWidget(self.spin_delay)
        h_delay.addWidget(QLabel("秒"))
        file_layout.addLayout(h_delay)
        
        self.lbl_delay_tip = QLabel("")
        self.lbl_delay_tip.setStyleSheet("color: red; font-size: 10px;")
        file_layout.addWidget(self.lbl_delay_tip)
        
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

    def on_delay_changed(self, index):
        if index == 0: # 随机
            self.spin_delay.setEnabled(False)
            self.lbl_delay_tip.setText("")
        else: # 自定义
            self.spin_delay.setEnabled(True)
            self.lbl_delay_tip.setText("⚠️ 警告: 间隔过短(<1s)极易触发验证码风控，请谨慎设置！")
        
    def get_data(self):
        # 返回 (indices, split_files, delay)
        # indices 是基于0的索引列表，或 None 表示全部
        split = self.check_split.isChecked()
        delay = -1 if self.combo_delay.currentIndex() == 0 else self.spin_delay.value()
        
        if self.radio_all.isChecked():
            return None, split, delay
            
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
            
        return indices, split, delay

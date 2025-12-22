
import os
import sys
import requests
import subprocess
import shutil
import zipfile
import json
import datetime
from packaging import version
from PySide6.QtWidgets import (QMessageBox, QApplication, QProgressDialog, QDialog, 
                               QVBoxLayout, QLabel, QPushButton, QHBoxLayout, 
                               QTextBrowser, QCheckBox, QProgressBar)
from PySide6.QtCore import Qt, QThread, Signal

# 导入本地版本
try:
    from version import VERSION as CURRENT_VERSION
except ImportError:
    CURRENT_VERSION = "0.0.0"

GITHUB_REPO = "rainyautumn1/FanqieNovelDownloader"
# 国内加速镜像列表 (按优先级排序)
MIRRORS = [
    "https://mirror.ghproxy.com/",
    "https://ghproxy.net/",
    "https://gh.ddlc.top/",
]

CONFIG_FILE = "update_config.json"

class UpdateConfig:
    @staticmethod
    def load():
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {}

    @staticmethod
    def save(data):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    @staticmethod
    def should_check_update():
        config = UpdateConfig.load()
        last_skip_date = config.get("last_skip_date")
        today = datetime.date.today().isoformat()
        return last_skip_date != today

    @staticmethod
    def set_skip_today():
        config = UpdateConfig.load()
        config["last_skip_date"] = datetime.date.today().isoformat()
        UpdateConfig.save(config)

class CheckWorker(QThread):
    finished = Signal(str, str, str) # remote_ver, changelog, error_msg

    def run(self):
        remote_ver = None
        changelog = None
        error_msg = None

        try:
            remote_ver = self.get_remote_version()
            if remote_ver:
                changelog = self.get_remote_changelog()
        except Exception as e:
            error_msg = str(e)

        self.finished.emit(remote_ver, changelog, error_msg)

    def get_remote_version(self):
        # 1. 尝试 jsDelivr CDN
        cdn_url = f"https://cdn.jsdelivr.net/gh/{GITHUB_REPO}@main/version.py"
        try:
            resp = requests.get(cdn_url, timeout=3)
            if resp.status_code == 200:
                for line in resp.text.splitlines():
                    if line.strip().startswith("VERSION"):
                        return line.split('"')[1]
        except:
            pass

        # 2. 尝试镜像
        raw_path = f"https://github.com/{GITHUB_REPO}/raw/main/version.py"
        for mirror in MIRRORS:
            try:
                url = f"{mirror}{raw_path}"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    for line in resp.text.splitlines():
                        if line.strip().startswith("VERSION"):
                            return line.split('"')[1]
            except:
                continue
        return None

    def get_remote_changelog(self):
        raw_path = f"https://github.com/{GITHUB_REPO}/raw/main/CHANGELOG.md"
        # 尝试通过镜像获取
        for mirror in MIRRORS:
            try:
                url = f"{mirror}{raw_path}"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    return resp.text
            except:
                continue
        return "无法获取更新日志。"

class UpdateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("检查更新")
        self.setFixedSize(550, 500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        self.layout = QVBoxLayout(self)

        # 声明与开源协议信息
        disclaimer_text = (
            "<p>本软件为 <b>免费开源软件</b> ，遵循 <b>GNU General Public License v3.0</b> 协议。</p>"
            "<p>严禁任何个人或组织将本软件（包含安装包、源代码及衍生版本）进行出售、转卖或用于任何商业盈利活动。</p>"
            "<p>如果您是付费购买的本软件，说明您已被骗，请立即申请退款并举报卖家。</p>"
            f"<p>GitHub仓库: <a href='https://github.com/{GITHUB_REPO}'>https://github.com/{GITHUB_REPO}</a></p>"
        )
        self.disclaimer_label = QLabel(disclaimer_text)
        self.disclaimer_label.setWordWrap(True)
        self.disclaimer_label.setOpenExternalLinks(True)
        self.disclaimer_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        # 给它加个背景色强调一下，类似用户截图中的区域
        self.disclaimer_label.setStyleSheet("QLabel { background-color: #f9f9f9; padding: 10px; border: 1px solid #e0e0e0; border-radius: 4px; }")
        self.layout.addWidget(self.disclaimer_label)

        # 增加 Bilibili 链接
        bilibili_link = (
            "<p>关注作者B站: <a href='https://space.bilibili.com/16111026?spm_id_from=333.1365.0.0'>落雨清秋真是太帅了</a></p>"
        )
        self.bili_label = QLabel(bilibili_link)
        self.bili_label.setOpenExternalLinks(True)
        self.bili_label.setStyleSheet("QLabel { color: #FB7299; font-weight: bold; margin-top: 5px; }")
        self.layout.addWidget(self.bili_label)
        
        # 状态标签
        self.status_label = QLabel("正在检查更新...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.status_label)
        
        # 进度条 (检查时显示)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0) # Indeterminate
        self.layout.addWidget(self.progress_bar)
        
        # 更新日志显示区
        self.changelog_browser = QTextBrowser()
        self.changelog_browser.hide()
        self.layout.addWidget(self.changelog_browser)
        
        # 底部按钮区
        self.button_layout = QHBoxLayout()
        self.layout.addLayout(self.button_layout)
        
        self.chk_skip_today = QCheckBox("今日不再提醒")
        self.chk_skip_today.hide()
        self.button_layout.addWidget(self.chk_skip_today)
        
        self.button_layout.addStretch()
        
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.on_cancel)
        self.btn_cancel.hide()
        self.button_layout.addWidget(self.btn_cancel)
        
        self.btn_ok = QPushButton("确定") # 用于无更新时关闭
        self.btn_ok.clicked.connect(self.accept)
        self.btn_ok.hide()
        self.button_layout.addWidget(self.btn_ok)

        self.btn_update = QPushButton("立即更新")
        self.btn_update.clicked.connect(self.start_update)
        self.btn_update.hide()
        self.button_layout.addWidget(self.btn_update)
        
        self.remote_ver = None
        
        # 启动检查线程
        self.worker = CheckWorker()
        self.worker.finished.connect(self.on_check_finished)
        self.worker.start()

    def on_check_finished(self, remote_ver, changelog, error_msg):
        self.progress_bar.hide()
        self.remote_ver = remote_ver
        
        if error_msg or not remote_ver:
            self.status_label.setText(f"检查失败: {error_msg or '无法连接服务器'}")
            self.btn_ok.show()
            return

        if version.parse(remote_ver) <= version.parse(CURRENT_VERSION):
            self.status_label.setText("当前已是最新版本。")
            self.btn_ok.show()
        else:
            self.status_label.setText(f"发现新版本: {remote_ver} (当前: {CURRENT_VERSION})")
            self.changelog_browser.setMarkdown(changelog if changelog else "无更新日志")
            self.changelog_browser.show()
            self.chk_skip_today.show()
            self.btn_cancel.setText("暂不更新")
            self.btn_cancel.show()
            self.btn_update.show()

    def on_cancel(self):
        if self.chk_skip_today.isChecked():
            UpdateConfig.set_skip_today()
            
        if self.remote_ver and version.parse(self.remote_ver) > version.parse(CURRENT_VERSION):
            QMessageBox.information(self, "手动更新", "如果您稍后想更新，请运行目录下的 'update_manager.py' 文件。")
            
        self.reject()

    def start_update(self):
        self.hide()
        # 调用原来的更新逻辑
        do_update(self.remote_ver, self.parent())
        # 更新完成后，do_update 会重启程序
        # 如果 do_update 返回，说明可能失败了，或者需要关闭当前程序
        self.accept() # 关闭对话框

def check_update(parent=None, force=False):
    """
    检查更新入口
    Args:
        parent: 父窗口
        force: 是否强制检查 (忽略今日跳过设置)
    Returns: 
        bool: True 表示主程序应继续运行，False 表示应停止（正在更新或已重启）
    """
    if not force and not UpdateConfig.should_check_update():
        print("今日已跳过检查更新")
        return True

    dialog = UpdateDialog(parent)
    result = dialog.exec()
    
    # 如果点击了“立即更新”，dialog.exec() 会在 start_update 中被 accept
    # 但实际上 start_update 里的 do_update 可能会重启进程
    
    # 如果用户点击“确定”(无更新) 或 “暂不更新”，result 分别为 Accepted 和 Rejected
    # 无论哪种情况，主程序都应该继续运行，除非正在执行更新
    
    # 在 do_update 中，如果更新成功会直接 restart_program() -> sys.exit()，所以不会运行到这里
    # 如果更新失败，会弹窗提示，然后返回到这里，此时应该让主程序继续
    
    return True

def do_update(remote_ver, parent=None):
    """执行更新逻辑 (复用之前的逻辑)"""
    
    # 创建进度条
    progress = QProgressDialog("正在更新...", "取消", 0, 100, parent)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setWindowTitle("自动更新")
    progress.show()
    progress.setValue(10)
    QApplication.processEvents()

    # 检查是否为打包后的 EXE 环境
    if getattr(sys, 'frozen', False):
        progress.setLabelText("正在下载最新安装包...")
        QApplication.processEvents()
        
        exe_url = f"https://github.com/{GITHUB_REPO}/releases/download/v{remote_ver}/FanqieDownloader_Setup.exe"
        exe_filename = f"FanqieDownloader_Setup_v{remote_ver}.exe"
        exe_path = os.path.join(os.path.dirname(sys.executable), exe_filename)
        
        download_success = False
        
        # 尝试下载 EXE
        for mirror in MIRRORS:
            try:
                # GitHub Release 的文件也需要通过镜像下载
                # 注意：很多镜像站对 release 的支持格式可能不同，这里尝试通用格式
                # 常见格式: https://mirror/https://github.com/...
                url = f"{mirror}{exe_url}"
                print(f"尝试下载安装包: {url}")
                
                resp = requests.get(url, stream=True, timeout=30)
                if resp.status_code == 200:
                    total_size = int(resp.headers.get('content-length', 0))
                    downloaded = 0
                    with open(exe_path, 'wb') as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                # 更新进度条 (20-90)
                                if total_size > 0:
                                    p = 20 + int((downloaded / total_size) * 70)
                                    progress.setValue(p)
                                    QApplication.processEvents()
                    download_success = True
                    break
            except Exception as e:
                print(f"下载失败: {e}")
        
        if not download_success:
            QMessageBox.warning(parent, "更新失败", f"无法下载安装包。\n请手动访问 GitHub 下载最新版 v{remote_ver}。")
            return

        progress.setValue(100)
        progress.setLabelText("下载完成，正在启动安装程序...")
        
        reply = QMessageBox.question(parent, "下载完成", 
                                     f"安装包已下载到:\n{exe_path}\n\n是否立即运行安装程序？\n(注意：安装时请先关闭本软件)",
                                     QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            try:
                # 启动安装程序
                os.startfile(exe_path)
                # 退出当前程序
                sys.exit(0)
            except Exception as e:
                QMessageBox.critical(parent, "错误", f"无法启动安装程序: {e}")
        return

    # 1. 优先尝试 Git Pull (开发环境)
    if os.path.exists(".git"):
        progress.setLabelText("正在通过 Git 拉取更新...")
        QApplication.processEvents()
        
        success = False
        for mirror in MIRRORS:
            try:
                # 构造镜像 Git URL
                git_url = f"{mirror}https://github.com/{GITHUB_REPO}.git"
                print(f"尝试从镜像拉取: {git_url}")
                
                # git pull
                result = subprocess.run(["git", "pull", git_url, "main"], capture_output=True, text=True, encoding='utf-8')
                if result.returncode == 0:
                    success = True
                    break
                else:
                    print(f"Git拉取失败: {result.stderr}")
            except Exception as e:
                print(f"Git操作异常: {e}")
                
        if success:
            progress.setValue(80)
            progress.setLabelText("正在安装新依赖...")
            QApplication.processEvents()
            install_dependencies()
            progress.setValue(100)
            QMessageBox.information(parent, "更新成功", f"已更新至版本 {remote_ver}，程序将自动重启。")
            restart_program()
            return

    # 2. 如果 Git 失败或没有 Git，尝试 Zip 下载
    progress.setLabelText("正在下载更新包 (Zip)...")
    progress.setValue(20)
    QApplication.processEvents()
    
    zip_url = f"https://github.com/{GITHUB_REPO}/archive/refs/heads/main.zip"
    download_success = False
    zip_path = "update_temp.zip"
    
    for mirror in MIRRORS:
        try:
            url = f"{mirror}{zip_url}"
            print(f"尝试下载: {url}")
            resp = requests.get(url, stream=True, timeout=15)
            if resp.status_code == 200:
                total_size = int(resp.headers.get('content-length', 0))
                downloaded = 0
                with open(zip_path, 'wb') as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            # 更新进度条 (20-70)
                            if total_size > 0:
                                p = 20 + int((downloaded / total_size) * 50)
                                progress.setValue(p)
                                QApplication.processEvents()
                download_success = True
                break
        except Exception as e:
            print(f"下载失败: {e}")
            
    if not download_success:
        QMessageBox.warning(parent, "更新失败", "无法下载更新文件，请检查网络或稍后重试。")
        return

    # 解压并覆盖
    try:
        progress.setLabelText("正在解压覆盖...")
        progress.setValue(75)
        QApplication.processEvents()
        
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            root_dir = zip_ref.namelist()[0].split('/')[0]
            zip_ref.extractall("temp_extract")
            
        src_dir = os.path.join("temp_extract", root_dir)
        for item in os.listdir(src_dir):
            s = os.path.join(src_dir, item)
            d = os.path.join(os.getcwd(), item)
            if os.path.isdir(s):
                copy_tree(s, d)
            else:
                shutil.copy2(s, d)
                
        # 清理
        try:
            os.remove(zip_path)
            shutil.rmtree("temp_extract")
        except:
            pass
        
        progress.setValue(90)
        progress.setLabelText("正在安装新依赖...")
        QApplication.processEvents()
        install_dependencies()
        
        progress.setValue(100)
        QMessageBox.information(parent, "更新成功", f"已更新至版本 {remote_ver}，程序将自动重启。")
        restart_program()
        
    except Exception as e:
        QMessageBox.critical(parent, "更新错误", f"文件覆盖失败: {e}\n建议手动下载最新版。")
        import traceback
        traceback.print_exc()

def copy_tree(src, dst):
    """递归复制目录，覆盖已存在的文件"""
    if not os.path.exists(dst):
        os.makedirs(dst)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            copy_tree(s, d)
        else:
            shutil.copy2(s, d)

def install_dependencies():
    """运行 pip install -r requirements.txt"""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    except:
        print("依赖安装失败，请手动运行 pip install -r requirements.txt")

def restart_program():
    """重启程序"""
    python = sys.executable
    os.execl(python, python, *sys.argv)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 强制不跳过
    if os.path.exists(CONFIG_FILE):
        os.remove(CONFIG_FILE)
    check_update()
    sys.exit(0)


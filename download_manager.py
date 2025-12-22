import uuid
import os
from PySide6.QtCore import QObject, Signal, QTimer
from workers import DownloadWorker, BatchDownloadWorker

class DownloadTask:
    def __init__(self, task_type, **kwargs):
        self.id = str(uuid.uuid4())
        self.type = task_type # 'single' or 'batch'
        self.kwargs = kwargs
        self.status = 'waiting' # waiting, running, paused, finished, error
        self.worker = None
        self.title = "未知任务"
        self.progress = (0, 0)
        self.status_msg = ""
        self.filepath = ""
        
        # 提取标题
        if task_type == 'single':
            if kwargs.get('title'):
                 self.title = kwargs.get('title')
            elif kwargs.get('book_info'):
                 self.title = kwargs.get('book_info').get('title', 'Unknown Book')
            else:
                 self.title = kwargs.get('book_url', 'Unknown URL')
        elif task_type == 'batch':
            # 对于批量任务，初始标题可能不准确，后续更新
            self.title = "批量下载任务"

class DownloadManager(QObject):
    task_added = Signal(str, str) # id, title
    task_updated = Signal(str, int, int, str) # id, current, total, msg
    task_status_changed = Signal(str, str) # id, status
    task_finished = Signal(str, str, str) # id, title, filepath
    task_removed = Signal(str) # id
    verification_needed = Signal(str, str) # id, url
    
    def __init__(self, downloader):
        super().__init__()
        self.downloader = downloader
        self.tasks = [] # List of DownloadTask
        self.max_concurrent_tasks = 1 # 默认单线程
        self.verification_active = False # 验证码状态标记
        self.queue_timer = QTimer()
        self.queue_timer.timeout.connect(self.process_queue)
        self.queue_timer.start(1000) # 每秒检查一次队列
        
    def set_max_concurrent_tasks(self, count):
        self.max_concurrent_tasks = count
        # 设置变更后立即检查队列
        self.process_queue()

    def add_single_task(self, book_url, save_dir, fmt, book_info=None, chapter_indices=None, split_files=False, delay=-1, chapter_limit=0, title=None):
        task = DownloadTask('single', 
                          book_url=book_url, 
                          save_dir=save_dir, 
                          fmt=fmt, 
                          book_info=book_info, 
                          chapter_indices=chapter_indices, 
                          split_files=split_files, 
                          delay=delay,
                          chapter_limit=chapter_limit,
                          title=title)
        
        # 初始化 Worker (但不启动)
        worker = DownloadWorker(self.downloader, book_url, save_dir, fmt, book_info, chapter_indices, split_files, delay, chapter_limit)
        self._setup_worker(task, worker)
        
        self.tasks.append(task)
        self.task_added.emit(task.id, task.title)
        return task.id
        
    def add_batch_task(self, rank_url, save_dir, top_n=5, chapters_count=0, fmt='txt', split_files=False, delay=-1):
        task = DownloadTask('batch',
                           rank_url=rank_url,
                           save_dir=save_dir,
                           top_n=top_n,
                           chapters_count=chapters_count,
                           fmt=fmt,
                           split_files=split_files,
                           delay=delay)
                           
        worker = BatchDownloadWorker(self.downloader, rank_url, save_dir, top_n, chapters_count, fmt, split_files, delay)
        self._setup_worker(task, worker)
        
        self.tasks.append(task)
        self.task_added.emit(task.id, task.title)
        return task.id

    def _setup_worker(self, task, worker):
        task.worker = worker
        
        # 连接信号
        # 使用 lambda 捕获 task.id 时要注意闭包问题，这里使用默认参数绑定
        worker.progress_signal.connect(lambda c, t, s, tid=task.id: self._on_worker_progress(tid, c, t, s))
        worker.finished_signal.connect(lambda path, tid=task.id: self._on_worker_finished(tid, path))
        worker.error_signal.connect(lambda err, tid=task.id: self._on_worker_error(tid, err))
        worker.verification_needed_signal.connect(lambda url, tid=task.id: self._on_verification_needed(tid, url))
        # log 信号暂时不需要在 UI 列表显示，或者显示在 status_msg 中
        
    def stop_all(self):
        """停止所有任务，用于程序退出"""
        self.queue_timer.stop()
        for task in self.tasks:
            if task.worker and task.worker.isRunning():
                task.worker.stop()
                if not task.worker.wait(2000): # 等待2秒
                    task.worker.terminate() # 强制终止

    def _on_verification_needed(self, task_id, url):
        # 标记验证状态
        self.verification_active = True
        
        # 暂停所有正在运行的任务（包括当前任务）
        self.pause_all()
        
        # 转发验证信号
        self.verification_needed.emit(task_id, url)
        
    def resolve_verification(self):
        """验证完成后调用，恢复调度"""
        self.verification_active = False
        # 尝试恢复所有被暂停的任务（变为waiting，由queue重新调度）
        self.start_all()

    def _on_worker_progress(self, task_id, current, total, msg):
        task = self.get_task(task_id)
        if task:
            task.progress = (current, total)
            task.status_msg = msg
            
            # 尝试从 msg 中提取标题（如果 worker 传递了 title 作为 msg，或者 msg 格式包含标题）
            # 但更好的方式是修改 signal 签名。不过为了兼容性，我们可以检查 msg 是否是 "书名: XXX" 格式
            # 或者，我们在 DownloadWorker 中已经有了 book_info，可以更新 task.title
            
            # 如果 worker 是 DownloadWorker，且有了 book_info，则更新 task.title
            if isinstance(task.worker, DownloadWorker) and task.worker.book_info:
                real_title = task.worker.book_info.get('title')
                if real_title and real_title != task.title:
                    task.title = real_title
                    # 我们需要一个新的信号来通知 UI 更新标题，或者复用 task_updated
                    # 这里我们复用 task_updated，但 UI 需要能处理 title 变化
                    # 也可以在 msg 中带上 title，但 msg 是给用户看的
            
            self.task_updated.emit(task_id, current, total, msg)
            
    def _on_worker_finished(self, task_id, filepath):
        task = self.get_task(task_id)
        if task:
            task.status = 'finished'
            task.filepath = filepath
            self.task_status_changed.emit(task_id, 'finished')
            self.task_finished.emit(task_id, task.title, filepath)
            # 自动从运行列表中移除逻辑由 UI 处理，Manager 保留记录直到显式清除
            
    def _on_worker_error(self, task_id, err_msg):
        task = self.get_task(task_id)
        if task:
            task.status = 'error'
            task.status_msg = err_msg
            self.task_updated.emit(task_id, 0, 0, f"错误: {err_msg}")
            self.task_status_changed.emit(task_id, 'error')

    def get_task(self, task_id):
        for t in self.tasks:
            if t.id == task_id:
                return t
        return None

    def process_queue(self):
        # 如果处于验证状态，暂停调度
        if self.verification_active:
            return

        # 1. 检查正在运行的任务数量
        running_tasks = [t for t in self.tasks if t.status == 'running']
        running_count = len(running_tasks)
        
        # 2. 如果运行数小于最大并发数，调度新任务
        if running_count < self.max_concurrent_tasks:
            # 计算还可以启动几个
            slots_available = self.max_concurrent_tasks - running_count
            
            # 查找 'waiting' 任务
            waiting_tasks = [t for t in self.tasks if t.status == 'waiting']
            
            # 启动可用名额的任务
            for i in range(min(slots_available, len(waiting_tasks))):
                next_task = waiting_tasks[i]
                self.start_task(next_task.id)

    def start_task(self, task_id):
        task = self.get_task(task_id)
        if not task: return
        
        # 移除强制单线程逻辑
        # for t in self.tasks:
        #    if t.id != task_id and t.status == 'running':
        #        self.pause_task(t.id)

        if task.status in ['waiting', 'paused', 'error']:
            task.status = 'running'
            self.task_status_changed.emit(task_id, 'running')
            if not task.worker.isRunning():
                if task.worker.is_paused:
                     task.worker.resume()
                else:
                    task.worker.start()
            else:
                task.worker.resume()

    def pause_task(self, task_id):
        task = self.get_task(task_id)
        if task and task.status == 'running':
            task.status = 'paused'
            task.worker.pause()
            self.task_status_changed.emit(task_id, 'paused')

    def cancel_task(self, task_id):
        task = self.get_task(task_id)
        if task:
            if task.status == 'running' or task.status == 'paused':
                task.worker.stop()
                task.worker.wait() # 等待线程结束
            
            task.status = 'cancelled'
            self.task_removed.emit(task_id)
            self.tasks.remove(task)

    # --- 批量操作 ---
    
    def start_all(self):
        for t in self.tasks:
            if t.status in ['paused', 'error']:
                # 将暂停的改为等待，以便队列处理器重新调度
                t.status = 'waiting'
                self.task_status_changed.emit(t.id, 'waiting')
        # 如果当前没有运行的，process_queue 会自动启动一个

    def pause_all(self):
        for t in self.tasks:
            if t.status == 'running':
                self.pause_task(t.id)
            elif t.status == 'waiting':
                t.status = 'paused'
                self.task_status_changed.emit(t.id, 'paused')

    def cancel_all(self):
        # 复制列表进行遍历，因为 cancel_task 会修改列表
        for t in list(self.tasks):
            if t.status not in ['finished']:
                self.cancel_task(t.id)

    def update_task_title(self, task_id, new_title):
        task = self.get_task(task_id)
        if task:
            task.title = new_title
            # 触发更新信号，利用已有的机制刷新UI
            self.task_updated.emit(task_id, task.progress[0], task.progress[1], task.status_msg)

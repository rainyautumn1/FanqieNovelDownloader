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
    
    def __init__(self, downloader):
        super().__init__()
        self.downloader = downloader
        self.tasks = [] # List of DownloadTask
        self.queue_timer = QTimer()
        self.queue_timer.timeout.connect(self.process_queue)
        self.queue_timer.start(1000) # 每秒检查一次队列
        
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
        # log 信号暂时不需要在 UI 列表显示，或者显示在 status_msg 中
        
    def _on_worker_progress(self, task_id, current, total, msg):
        task = self.get_task(task_id)
        if task:
            task.progress = (current, total)
            task.status_msg = msg
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
        # 简单的串行队列策略：
        # 1. 检查是否有 'running' 任务
        running_tasks = [t for t in self.tasks if t.status == 'running']
        if running_tasks:
            return # 有任务在跑，等待
            
        # 2. 如果没有，查找 'waiting' 任务
        waiting_tasks = [t for t in self.tasks if t.status == 'waiting']
        if waiting_tasks:
            next_task = waiting_tasks[0]
            self.start_task(next_task.id)

    def start_task(self, task_id):
        task = self.get_task(task_id)
        if not task: return
        
        # 强制暂停其他正在运行的任务（单线程限制）
        for t in self.tasks:
            if t.id != task_id and t.status == 'running':
                self.pause_task(t.id)

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

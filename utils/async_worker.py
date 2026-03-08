import asyncio
from PyQt6.QtCore import QThread, pyqtSignal

class AsyncWorker(QThread):
    """异步工作线程，用于在后台执行asyncio协程，避免阻塞GUI主线程"""
    taskFinished = pyqtSignal(object)
    taskError = pyqtSignal(object)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        """执行异步任务,确保事件循环正确关闭"""
        # 为当前线程创建一个新的事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # 检查func是否为协程函数
            if asyncio.iscoroutinefunction(self.func):
                result = loop.run_until_complete(self.func(*self.args, **self.kwargs))
            else:
                possible_coroutine = self.func(*self.args, **self.kwargs)

                # 检查返回值是否为协程对象
                if asyncio.iscoroutine(possible_coroutine):
                    result = loop.run_until_complete(possible_coroutine)
                else:
                    result = possible_coroutine
            
            self.taskFinished.emit(result)
            
        except Exception as e:
            self.taskError.emit(e)
            
        finally:
            # 确保事件循环总是被关闭,防止资源泄漏
            try:
                # 取消所有未完成的任务
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                
                # 等待所有任务取消完成
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception as cleanup_error:
                import sys
                sys.stderr.write(f"Error during event loop cleanup: {cleanup_error}\n")
            finally:
                loop.close()

import asyncio
from PyQt5.QtCore import QThread, pyqtSignal

# Worker thread for async operations
class AsyncWorker(QThread):
    taskFinished = pyqtSignal(object)
    taskError = pyqtSignal(str)
    taskProgress = pyqtSignal(str)

    def __init__(self, coro, *args, **kwargs):
        super().__init__()
        self.coro = coro
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.coro(*self.args, **self.kwargs))
            self.taskFinished.emit(result)
        except Exception as e:
            self.taskError.emit(str(e))
        finally:
            loop.close()

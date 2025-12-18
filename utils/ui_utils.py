import os
import sys
from io import StringIO
from PyQt5.QtCore import Qt, pyqtSignal, QMetaObject, Q_ARG, QObject, QSize, QRect, QPoint
from PyQt5.QtGui import QPixmap, QPainter, QPainterPath
from PyQt5.QtWidgets import QLayout, QLineEdit, QApplication

def resource_path(relative_path):
    """获取用户数据文件的绝对路径，兼容PyInstaller打包"""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller打包后，使用可执行文件所在目录
        base_path = os.path.dirname(sys.executable)
    else:
        # 开发环境，使用当前脚本所在目录

        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def static_resource_path(relative_path):
    """获取静态资源文件的绝对路径，兼容PyInstaller打包"""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller打包后，静态资源在临时目录中
        return os.path.join(sys._MEIPASS, relative_path)
    else:
        # 开发环境，使用当前脚本所在目录的父目录（因为现在在utils下）
        return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), relative_path)


def create_circular_pixmap(pixmap, size):
    """创建圆形头像"""
    # 创建一个正方形的透明图像
    circular_pixmap = QPixmap(size, size)
    circular_pixmap.fill(Qt.transparent)

    # 创建画家对象
    painter = QPainter(circular_pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)

    # 创建圆形路径
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)

    # 设置裁剪路径
    painter.setClipPath(path)

    # 绘制原始图像
    painter.drawPixmap(0, 0, size, size, pixmap)
    painter.end()

    return circular_pixmap


# 自定义FlowLayout布局，实现自适应排列
class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=-1):
        super(FlowLayout, self).__init__(parent)

        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)

        self.setSpacing(spacing)
        self.itemList = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.itemList.append(item)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self.doLayout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super(FlowLayout, self).setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()

        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())

        margin = self.contentsMargins()
        size += QSize(margin.left() + margin.right(), margin.top() + margin.bottom())
        return size

    def doLayout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0

        for item in self.itemList:
            wid = item.widget()
            spaceX = self.spacing() + wid.style().layoutSpacing(
                wid.sizePolicy().controlType(),
                wid.sizePolicy().controlType(),
                Qt.Horizontal)
            spaceY = self.spacing() + wid.style().layoutSpacing(
                wid.sizePolicy().controlType(),
                wid.sizePolicy().controlType(),
                Qt.Vertical)

            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y()


# 重定向stdout和stderr到GUI
class StdoutRedirector(StringIO):
    def __init__(self, text_widget, disable_terminal_output=True):
        super().__init__()
        self.text_widget = text_widget
        self.old_stdout = sys.stdout
        self.old_stderr = sys.stderr
        self.buffer = ""
        self.disable_terminal_output = disable_terminal_output

    def write(self, text):
        if not self.disable_terminal_output:
            self.old_stdout.write(text)  # 同时保留终端输出

        # 添加到缓冲区
        self.buffer += text

        # 如果包含换行符或缓冲区超过一定大小，则刷新
        if '\n' in self.buffer or len(self.buffer) > 100:
            self.flush()

    def flush(self):
        if self.buffer:
            # 使用主线程安全的方式更新UI
            if QApplication.instance():
                QMetaObject.invokeMethod(
                    self.text_widget,
                    "append",
                    Qt.QueuedConnection,
                    Q_ARG(str, self.buffer)
                )
            self.buffer = ""
        if not self.disable_terminal_output and hasattr(self.old_stdout, 'flush'):
            self.old_stdout.flush()


# Create a custom QPasswordLineEdit class for password input
class QPasswordLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEchoMode(QLineEdit.Password)


# Custom logger signal handler
class LogSignalHandler(QObject):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)

    def emit_log(self, message):
        self.log_signal.emit(message)

        # Check for document download progress messages
        if "下载文档" in message and "/" in message and ")" in message:
            try:
                # Extract current and total from "下载文档 (1/11): ..."
                parts = message.split("(")[1].split(")")[0].split("/")
                current = int(parts[0])
                total = int(parts[1])
                self.progress_signal.emit(current, total)
            except Exception:
                pass

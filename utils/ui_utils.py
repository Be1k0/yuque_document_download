import sys
from io import StringIO
from PyQt6.QtCore import Qt, pyqtSignal, QMetaObject, Q_ARG, QObject, QSize, QRect, QPoint
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath
from PyQt6.QtWidgets import QLayout, QLineEdit, QApplication
from src.libs.path_utils import get_resource_path, get_bundled_resource_path
    
def resource_path(relative_path):
    """获取用户数据文件的绝对路径
    
    Args:
        relative_path: 相对于资源目录的路径
    """
    return get_resource_path(relative_path)


def static_resource_path(relative_path):
    """获取静态资源文件的绝对路径
    
    Args:
        relative_path: 相对于资源目录的路径
    """
    return get_bundled_resource_path(relative_path)


def create_circular_pixmap(pixmap, size):
    """创建圆形头像
    
    Args:
        pixmap: 原始图像
        size: 圆形大小
    """
    # 创建一个正方形的透明图像
    circular_pixmap = QPixmap(size, size)
    circular_pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(circular_pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    path = QPainterPath()
    path.addEllipse(0, 0, size, size)

    painter.setClipPath(path)

    painter.drawPixmap(0, 0, size, size, pixmap)
    painter.end()

    return circular_pixmap

class FlowLayout(QLayout):
    """自定义FlowLayout布局类，实现自适应排列
    
    参考：https://doc.qt.io/qt-6/qtwidgets-layouts-flowlayout-example.html
    """
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

        """向项目列表中添加一个新的项目
        
        Args:
            item: 要添加到列表中的项目
        """
        self.itemList.append(item)

    def count(self):
        """返回项目列表中的项目数量"""
        return len(self.itemList)

    def itemAt(self, index):
        """返回指定索引处的项目"""
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        """从项目列表中移除并返回指定索引处的项目"""
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        """返回扩展方向"""
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        """检查布局是否具有高度以适应宽度"""
        return True

    def heightForWidth(self, width):
        """根据给定的宽度计算布局所需的高度
        
         Args:
            width: 布局的宽度
        """
        height = self.doLayout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        """设置布局的几何形状，并根据给定的矩形调整子项的位置和大小
        
        Args:
            rect: 布局的矩形
        """
        super(FlowLayout, self).setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        """返回布局的推荐大小"""
        return self.minimumSize()

    def minimumSize(self):
        """计算并返回布局的最小大小"""
        size = QSize()

        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())

        margin = self.contentsMargins()
        size += QSize(margin.left() + margin.right(), margin.top() + margin.bottom())
        return size

    def doLayout(self, rect, testOnly):
        """执行布局计算和调整子项的位置和大小

        Args:
            rect: 布局的矩形
            testOnly: 如果为True，则仅计算布局所需的高度，而不调整子项的位置和大小
        """
        x = rect.x()
        y = rect.y()
        lineHeight = 0

        for item in self.itemList:
            wid = item.widget()
            spaceX = self.spacing() + wid.style().layoutSpacing(
                wid.sizePolicy().controlType(),
                wid.sizePolicy().controlType(),
                Qt.Orientation.Horizontal)
            spaceY = self.spacing() + wid.style().layoutSpacing(
                wid.sizePolicy().controlType(),
                wid.sizePolicy().controlType(),
                Qt.Orientation.Vertical)

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


class StdoutRedirector(StringIO):
    """重定向stdout和stderr到GUI文本框的类"""
    def __init__(self, text_widget, disable_terminal_output=True):
        super().__init__()
        self.text_widget = text_widget
        self.old_stdout = sys.stdout
        self.old_stderr = sys.stderr
        self.buffer = ""
        self.disable_terminal_output = disable_terminal_output

    def write(self, text):
        """重写write方法，将输出文本添加到缓冲区并刷新文本框
        
         Args:
            text: 要写入的文本
        """
        if not self.disable_terminal_output:
            self.old_stdout.write(text)

        self.buffer += text

        # 如果包含换行符或缓冲区超过一定大小，则刷新
        if '\n' in self.buffer or len(self.buffer) > 100:
            self.flush()

    def flush(self):
        """刷新缓冲区，将缓冲区内容写入文本框"""
        if self.buffer:
            if QApplication.instance():
                QMetaObject.invokeMethod(
                    self.text_widget,
                    "append",
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, self.buffer)
                )
            self.buffer = ""
        if not self.disable_terminal_output and hasattr(self.old_stdout, 'flush'):
            self.old_stdout.flush()

class QPasswordLineEdit(QLineEdit):
    """自定义密码输入框类"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEchoMode(QLineEdit.EchoMode.Password)


# 自定义记录器信号处理程序
class LogSignalHandler(QObject):
    """日志信号处理器类，用于处理和发射日志信号和进度信号"""
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    def emit_log(self, message):
        """发射日志信号，并检查是否包含下载进度消息
        
         Args:
            message: 日志消息
        """
        self.log_signal.emit(message)

        # 检查文档下载进度消息
        if "下载文档" in message and "/" in message and ")" in message:
            try:
                parts = message.split("(")[1].split(")")[0].split("/")
                current = int(parts[0])
                total = int(parts[1])
                self.progress_signal.emit(current, total)
            except Exception:
                pass

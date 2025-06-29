import asyncio
import os
import sys
import time
from io import StringIO

import nest_asyncio
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QMetaObject, Q_ARG, QObject, QSize, QRect, QPoint
from PyQt5.QtGui import QPixmap, QFont, QIcon, QPainter, QPainterPath, QColor, QIntValidator
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QCheckBox, QListWidget, QFileDialog,
    QMessageBox, QGroupBox, QLineEdit, QProgressBar, QTextEdit, QTabWidget, QSplitter, QListWidgetItem, QLayout,
    QRadioButton,
    QDialog, QComboBox, QButtonGroup
)

# from src.core.command import YCommand  # 已移除CLI支持
from src.core.scheduler import Scheduler
from src.libs.constants import GLOBAL_CONFIG, MutualAnswer, YuqueAccount
from src.libs.log import Log


def resource_path(relative_path):
    """获取用户数据文件的绝对路径，兼容PyInstaller打包"""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller打包后，使用可执行文件所在目录
        base_path = os.path.dirname(sys.executable)
    else:
        # 开发环境，使用当前脚本所在目录
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def static_resource_path(relative_path):
    """获取静态资源文件的绝对路径，兼容PyInstaller打包"""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller打包后，静态资源在临时目录中
        return os.path.join(sys._MEIPASS, relative_path)
    else:
        # 开发环境，使用当前脚本所在目录
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


from src.libs.tools import get_local_cookies, get_cache_books_info  # get_user_config已移除
from src.core.yuque import YuqueApi
from src.libs.threaded_image_downloader import ThreadedImageDownloader

nest_asyncio.apply()


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


# 文章选择对话框
class ArticleSelectionDialog(QDialog):
    def __init__(self, parent=None, books_info=None):
        super().__init__(parent)
        self.books_info = books_info or []
        self.selected_articles = {}  # 知识库名称 -> 选中的文章ID列表
        self.current_namespace = ""
        self.current_book_name = ""

        self.setWindowTitle("选择要下载的文章")
        self.setMinimumSize(800, 600)

        # 创建主布局
        layout = QVBoxLayout(self)

        # 添加说明文本
        desc_label = QLabel("请选择要下载的具体文章，先从左侧选择知识库，再从右侧选择文章：")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        # 创建主内容区域（移除左侧知识库列表）
        content_layout = QVBoxLayout()

        # 文章列表区域（原右侧面板现在成为主面板）
        main_panel = QGroupBox("文章列表")
        main_layout = QVBoxLayout(main_panel)

        # 知识库选择区域（新增）
        book_selection_layout = QHBoxLayout()
        book_selection_label = QLabel("选择知识库:")
        self.book_dropdown = QComboBox()
        self.book_dropdown.setMinimumWidth(200)
        self.book_dropdown.currentTextChanged.connect(self.load_articles_for_book_dropdown)

        # 全选知识库按钮（从主窗口移动到这里）
        self.select_all_books_btn = QPushButton("全选知识库")
        self.select_all_books_btn.clicked.connect(self.select_all_books_in_dialog)

        book_selection_layout.addWidget(book_selection_label)
        book_selection_layout.addWidget(self.book_dropdown)
        book_selection_layout.addWidget(self.select_all_books_btn)
        book_selection_layout.addStretch()
        main_layout.addLayout(book_selection_layout)

        # 文章搜索框
        article_search_layout = QHBoxLayout()
        article_search_label = QLabel("搜索文章:")
        self.article_search_input = QLineEdit()
        self.article_search_input.setPlaceholderText("输入关键词过滤文章")
        self.article_search_input.textChanged.connect(self.filter_articles)
        article_search_layout.addWidget(article_search_label)
        article_search_layout.addWidget(self.article_search_input)
        main_layout.addLayout(article_search_layout)

        # 文章列表
        self.article_list = QListWidget()
        self.article_list.setSelectionMode(QListWidget.MultiSelection)
        self.article_list.itemSelectionChanged.connect(self.update_article_selection)
        main_layout.addWidget(self.article_list)

        # 添加选择控制按钮
        article_buttons_layout = QHBoxLayout()
        self.select_all_articles_btn = QPushButton("全选文章")
        self.select_all_articles_btn.clicked.connect(self.select_all_articles)

        self.deselect_all_articles_btn = QPushButton("取消全选")
        self.deselect_all_articles_btn.clicked.connect(self.deselect_all_articles)

        self.selected_count_label = QLabel("已选: 0")

        article_buttons_layout.addWidget(self.select_all_articles_btn)
        article_buttons_layout.addWidget(self.deselect_all_articles_btn)
        article_buttons_layout.addStretch()
        article_buttons_layout.addWidget(self.selected_count_label)

        main_layout.addLayout(article_buttons_layout)

        # 添加主面板到内容区域
        content_layout.addWidget(main_panel)

        layout.addLayout(content_layout, 1)

        # 状态标签 - 显示当前加载和选择状态
        self.status_label = QLabel("准备就绪")
        self.status_label.setStyleSheet("color: #0d6efd;")
        layout.addWidget(self.status_label)

        # 添加按钮
        button_layout = QHBoxLayout()
        self.total_selected_label = QLabel("总计已选: 0篇文章")
        button_layout.addWidget(self.total_selected_label)

        # 添加清除所有选择按钮
        self.clear_all_selections_btn = QPushButton("清除所有选择")
        self.clear_all_selections_btn.clicked.connect(self.clear_all_selections)
        button_layout.addWidget(self.clear_all_selections_btn)

        button_layout.addStretch()

        self.ok_button = QPushButton("确定")
        self.ok_button.clicked.connect(self.accept)
        self.ok_button.setMinimumWidth(100)

        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.reject)
        self.cancel_button.setMinimumWidth(100)

        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

        # 加载知识库列表
        self.load_books()

        # 初始禁用右侧面板，直到选择了知识库
        self.article_list.setEnabled(False)
        self.article_search_input.setEnabled(False)
        self.select_all_articles_btn.setEnabled(False)
        self.deselect_all_articles_btn.setEnabled(False)

    def load_books(self):
        """加载知识库列表到下拉框"""
        self.book_dropdown.clear()

        # 添加默认选项
        self.book_dropdown.addItem("请选择知识库...")

        # 按所有者类型和名称排序
        owner_books = []
        other_books = []

        for item in self.books_info:
            if hasattr(item, 'book_type') and item.book_type == "owner":
                owner_books.append(item)
            else:
                other_books.append(item)

        # 按名称排序
        owner_books.sort(key=lambda x: x.name)
        other_books.sort(key=lambda x: x.name)

        # 先添加个人知识库
        for item in owner_books:
            display_name = f"👤 {item.name}"
            # 存储namespace信息
            namespace = ""
            if hasattr(item, 'namespace') and item.namespace:
                namespace = item.namespace
            elif hasattr(item, 'user_login') and hasattr(item, 'slug'):
                namespace = f"{item.user_login}/{item.slug}"
            elif hasattr(item, 'user') and hasattr(item, 'slug'):
                if isinstance(item.user, dict) and 'login' in item.user:
                    namespace = f"{item.user['login']}/{item.slug}"

            self.book_dropdown.addItem(display_name)
            # 存储namespace和原始名称到下拉框项的数据中
            index = self.book_dropdown.count() - 1
            self.book_dropdown.setItemData(index, namespace, Qt.UserRole)
            self.book_dropdown.setItemData(index, item.name, Qt.UserRole + 1)

        # 再添加团队知识库
        for item in other_books:
            display_name = f"👥 {item.name}"
            # 存储namespace信息
            namespace = ""
            if hasattr(item, 'namespace') and item.namespace:
                namespace = item.namespace
            elif hasattr(item, 'user_login') and hasattr(item, 'slug'):
                namespace = f"{item.user_login}/{item.slug}"
            elif hasattr(item, 'user') and hasattr(item, 'slug'):
                if isinstance(item.user, dict) and 'login' in item.user:
                    namespace = f"{item.user['login']}/{item.slug}"

            self.book_dropdown.addItem(display_name)
            # 存储namespace和原始名称到下拉框项的数据中
            index = self.book_dropdown.count() - 1
            self.book_dropdown.setItemData(index, namespace, Qt.UserRole)
            self.book_dropdown.setItemData(index, item.name, Qt.UserRole + 1)

        # 更新状态
        self.status_label.setText(f"已加载 {len(self.books_info)} 个知识库")

    def filter_books(self, text):
        """根据输入过滤知识库列表"""
        filter_text = text.lower()
        for i in range(self.book_list.count()):
            item = self.book_list.item(i)
            # 去掉emoji前缀后再比较
            book_name = item.text()[2:].strip().lower()
            item.setHidden(filter_text not in book_name)

    def load_articles_for_book(self, current, previous):
        """加载选中知识库的文章列表"""
        if not current:
            return

        # 清空文章列表
        self.article_list.clear()

        # 获取知识库namespace和名称
        namespace = current.data(Qt.UserRole)
        book_name = current.data(Qt.UserRole + 1)

        if not namespace:
            self.status_label.setText(f"知识库 {book_name} 缺少必要的命名空间信息")
            return

        # 更新当前知识库信息
        self.current_namespace = namespace
        self.current_book_name = book_name

        # 更新状态
        self.status_label.setText(f"正在加载知识库 {book_name} 的文章...")

        # 启用右侧面板的控件
        self.article_list.setEnabled(True)
        self.article_search_input.setEnabled(True)
        self.select_all_articles_btn.setEnabled(True)
        self.deselect_all_articles_btn.setEnabled(True)

        # 异步加载文章列表
        self.load_articles_worker = AsyncWorker(YuqueApi.get_book_docs, namespace)
        self.load_articles_worker.taskFinished.connect(lambda docs: self.display_articles(docs, book_name))
        self.load_articles_worker.taskError.connect(lambda err: self.handle_articles_error(err, book_name))
        self.load_articles_worker.start()

    def display_articles(self, articles, book_name):
        """显示文章列表"""
        try:
            self.article_list.clear()

            # 检查是否有错误信息
            if isinstance(articles, dict) and "error" in articles:
                error_msg = articles.get("message", "未知错误")
                error_item = QListWidgetItem(f"加载失败: {error_msg}")
                error_item.setFlags(Qt.NoItemFlags)
                error_item.setForeground(QColor("#dc3545"))
                self.article_list.addItem(error_item)

                # 更新状态
                self.status_label.setText(f"知识库 {book_name} 文章加载失败")
                if hasattr(self, 'log_handler'):
                    self.log_handler.emit_log(f"知识库 {book_name} 文章加载失败: {error_msg}")

                # 如果是登录过期，提示用户重新登录
                if articles.get("error") == "cookies_expired":
                    QMessageBox.warning(self, "登录已过期", "您的登录已过期，请重新登录")

                    # 切换到登录标签页
                    tabs = self.findChild(QTabWidget)
                    if tabs:
                        tabs.setCurrentIndex(0)

                return

            if not articles:
                empty_item = QListWidgetItem(f"知识库 {book_name} 没有文章")
                empty_item.setFlags(Qt.NoItemFlags)
                empty_item.setForeground(QColor("#6c757d"))
                self.article_list.addItem(empty_item)

                self.status_label.setText(f"知识库 {book_name} 没有文章")
                if hasattr(self, 'log_handler'):
                    self.log_handler.emit_log(f"知识库 {book_name} 没有文章")
                return

            # 按更新时间排序文章（如果有更新时间字段）
            try:
                sorted_articles = articles
                if len(articles) > 0 and isinstance(articles[0], dict):
                    # API返回的是字典列表
                    if all('updated_at' in doc for doc in articles):
                        sorted_articles = sorted(articles, key=lambda x: x.get('updated_at', ''), reverse=True)

                    for article in sorted_articles:
                        title = article.get('title', 'Untitled')
                        updated_at = article.get('updated_at', '')

                        # 创建列表项
                        item = QListWidgetItem(title)

                        # 设置提示文本
                        if updated_at:
                            try:
                                # 格式化更新时间为可读形式
                                updated_date = updated_at.split('T')[0]  # 简单处理，仅显示日期部分
                                item.setToolTip(f"标题: {title}\n更新时间: {updated_date}")
                            except:
                                item.setToolTip(f"标题: {title}")
                        else:
                            item.setToolTip(f"标题: {title}")

                        # 存储文章ID和其他必要信息
                        item.setData(Qt.UserRole, article.get('id', ''))
                        item.setData(Qt.UserRole + 1, article)  # 存储完整的文章对象

                        # 检查是否已经选择过该文章
                        if hasattr(self, '_current_answer') and hasattr(self._current_answer, 'selected_docs') and \
                                book_name in self._current_answer.selected_docs and \
                                article.get('id', '') in self._current_answer.selected_docs[book_name]:
                            item.setSelected(True)

                        self.article_list.addItem(item)
                else:
                    # API返回的是对象列表
                    if len(articles) > 0 and hasattr(articles[0], 'updated_at'):
                        sorted_articles = sorted(articles, key=lambda x: getattr(x, 'updated_at', ''), reverse=True)

                    for article in sorted_articles:
                        title = getattr(article, 'title', 'Untitled')
                        updated_at = getattr(article, 'updated_at', '')

                        # 创建列表项
                        item = QListWidgetItem(title)

                        # 设置提示文本
                        if updated_at:
                            try:
                                # 格式化更新时间为可读形式
                                updated_date = updated_at.split('T')[0]  # 简单处理，仅显示日期部分
                                item.setToolTip(f"标题: {title}\n更新时间: {updated_date}")
                            except:
                                item.setToolTip(f"标题: {title}")
                        else:
                            item.setToolTip(f"标题: {title}")

                        # 存储文章ID和其他必要信息
                        item.setData(Qt.UserRole, getattr(article, 'id', ''))
                        item.setData(Qt.UserRole + 1, article)  # 存储完整的文章对象

                        # 检查是否已经选择过该文章
                        if hasattr(self, '_current_answer') and hasattr(self._current_answer, 'selected_docs') and \
                                book_name in self._current_answer.selected_docs and \
                                getattr(article, 'id', '') in self._current_answer.selected_docs[book_name]:
                            item.setSelected(True)

                        self.article_list.addItem(item)
            except Exception as sorting_error:
                # 如果排序或处理文章过程中出错，显示原始列表
                if hasattr(self, 'log_handler'):
                    self.log_handler.emit_log(f"处理文章列表时出错: {str(sorting_error)}，显示未排序列表")
                self.article_list.clear()

                # 简单显示文章标题
                for article in articles:
                    try:
                        if isinstance(article, dict):
                            title = article.get('title', 'Untitled')
                            item = QListWidgetItem(title)
                            item.setData(Qt.UserRole, article.get('id', ''))
                        else:
                            title = getattr(article, 'title', 'Untitled')
                            item = QListWidgetItem(title)
                            item.setData(Qt.UserRole, getattr(article, 'id', ''))
                        self.article_list.addItem(item)
                    except:
                        # 跳过无法处理的文章
                        continue

            # 更新状态
            self.status_label.setText(f"知识库 {book_name} 共有 {len(articles)} 篇文章")
            if hasattr(self, 'log_handler'):
                self.log_handler.emit_log(f"知识库 {book_name} 共有 {len(articles)} 篇文章")
            self.update_article_selection()

        except Exception as e:
            # 捕获所有未处理的异常
            error_msg = str(e)
            self.article_list.clear()
            error_item = QListWidgetItem(f"显示文章列表出错: {error_msg}")
            error_item.setFlags(Qt.NoItemFlags)
            error_item.setForeground(QColor("#dc3545"))
            self.article_list.addItem(error_item)

            self.status_label.setText(f"显示文章列表出错")
            if hasattr(self, 'log_handler'):
                self.log_handler.emit_log(f"显示文章列表出错: {error_msg}")

    def handle_articles_error(self, error_msg, book_name):
        """处理获取文章列表错误"""
        self.article_list.clear()
        error_item = QListWidgetItem(f"加载失败: {error_msg}")
        error_item.setFlags(Qt.NoItemFlags)
        error_item.setForeground(QColor("#dc3545"))
        self.article_list.addItem(error_item)

        # 记录错误到日志
        if hasattr(self, 'log_handler'):
            self.log_handler.emit_log(f"获取知识库 {book_name} 文章列表失败: {error_msg}")
        self.status_label.setText(f"获取知识库 {book_name} 文章列表失败")

        # 检查是否为cookies过期问题
        if "cookies已过期" in str(error_msg):
            QMessageBox.warning(self, "登录已过期", "您的登录已过期，请重新登录")

            # 切换到登录标签页
            tabs = self.findChild(QTabWidget)
            if tabs:
                tabs.setCurrentIndex(0)

    def filter_articles(self, text):
        """根据输入过滤文章列表"""
        filter_text = text.lower()
        for i in range(self.article_list.count()):
            item = self.article_list.item(i)
            item.setHidden(filter_text not in item.text().lower())

    def select_all_articles(self):
        """全选当前显示的所有文章"""
        for i in range(self.article_list.count()):
            item = self.article_list.item(i)
            if not item.isHidden():  # 只选择可见项目
                item.setSelected(True)

    def deselect_all_articles(self):
        """取消选择当前知识库的所有文章"""
        for i in range(self.article_list.count()):
            self.article_list.item(i).setSelected(False)

    def update_article_selection(self):
        """更新选中的文章"""
        try:
            count = len(self.article_list.selectedItems())
            self.selected_article_count_label.setText(f"已选: {count}")

            # 如果有文章被选中，则创建或更新MutualAnswer对象来存储选中的文章
            if hasattr(self, 'current_book_name') and self.current_book_name:
                # 获取当前选中的所有文章ID
                selected_ids = []
                for item in self.article_list.selectedItems():
                    article_id = item.data(Qt.UserRole)
                    if article_id:
                        selected_ids.append(article_id)

                # 存储选择的文章ID
                if not hasattr(self, '_current_answer'):
                    self._current_answer = MutualAnswer(
                        toc_range=[],
                        skip=self.skip_local_checkbox.isChecked(),
                        line_break=self.keep_linebreak_checkbox.isChecked(),
                        download_range="selected"
                    )
                    self._current_answer.selected_docs = {}

                # 更新选中状态
                if selected_ids:
                    self._current_answer.selected_docs[self.current_book_name] = selected_ids
                    if hasattr(self, 'log_handler'):
                        self.log_handler.emit_log(f"已选择 {len(selected_ids)} 篇 {self.current_book_name} 的文章")
                elif self.current_book_name in self._current_answer.selected_docs:
                    # 如果没有选中任何文章，从已选字典中删除该知识库
                    del self._current_answer.selected_docs[self.current_book_name]
                    if hasattr(self, 'log_handler'):
                        self.log_handler.emit_log(f"已清除 {self.current_book_name} 的所有选择")

                # 计算并显示总共选择的文章数量
                if hasattr(self, '_current_answer') and hasattr(self._current_answer, 'selected_docs'):
                    total_selected = sum(len(ids) for ids in self._current_answer.selected_docs.values())
                    if total_selected > 0:
                        self.status_label.setText(f"总计已选: {total_selected} 篇文章")
                    else:
                        self.status_label.setText("未选择任何文章")
        except Exception as e:
            # 捕获任何可能的异常以防止崩溃
            error_msg = str(e)
            if hasattr(self, 'log_handler'):
                self.log_handler.emit_log(f"更新文章选择状态时出错: {error_msg}")
            self.status_label.setText("更新文章选择状态时出错")

    def select_all_books_in_dialog(self):
        """在对话框中全选所有知识库的文章"""
        if not hasattr(self, 'books_info') or not self.books_info:
            self.status_label.setText("没有可用的知识库")
            return

        self.status_label.setText("正在加载所有知识库的文章...")

        # 清空当前选择
        self.selected_articles = {}

        # 为每个知识库加载文章
        self.books_to_process = []
        for item in self.books_info:
            namespace = ""
            if hasattr(item, 'namespace') and item.namespace:
                namespace = item.namespace
            elif hasattr(item, 'user_login') and hasattr(item, 'slug'):
                namespace = f"{item.user_login}/{item.slug}"
            elif hasattr(item, 'user') and hasattr(item, 'slug'):
                if isinstance(item.user, dict) and 'login' in item.user:
                    namespace = f"{item.user['login']}/{item.slug}"

            if namespace:
                self.books_to_process.append((namespace, item.name))

        # 开始处理第一个知识库
        if self.books_to_process:
            self.current_book_index = 0
            self.process_next_book_for_all_selection()

    def process_next_book_for_all_selection(self):
        """处理下一个知识库的文章加载"""
        if self.current_book_index >= len(self.books_to_process):
            # 所有知识库处理完成
            self.status_label.setText(
                f"已选择所有知识库的文章，共 {sum(len(articles) for articles in self.selected_articles.values())} 篇")
            self.update_total_selected()
            return

        namespace, book_name = self.books_to_process[self.current_book_index]

        # 异步加载当前知识库的文章
        self.load_all_articles_worker = AsyncWorker(YuqueApi.get_book_docs, namespace)
        self.load_all_articles_worker.taskFinished.connect(
            lambda docs: self.handle_all_articles_loaded(docs, namespace, book_name))
        self.load_all_articles_worker.taskError.connect(
            lambda err: self.handle_all_articles_error(err, namespace, book_name))
        self.load_all_articles_worker.start()

    def handle_all_articles_loaded(self, docs, namespace, book_name):
        """处理全选时单个知识库文章加载完成"""
        if docs:
            # 将所有文章添加到选择列表
            self.selected_articles[namespace] = docs

        # 处理下一个知识库
        self.current_book_index += 1
        self.process_next_book_for_all_selection()

    def handle_all_articles_error(self, error, namespace, book_name):
        """处理全选时单个知识库文章加载错误"""
        Log.error(f"加载知识库 {book_name} 的文章时出错: {error}")

        # 继续处理下一个知识库
        self.current_book_index += 1
        self.process_next_book_for_all_selection()

    def handle_articles_error(self, error, book_name):
        """处理文章加载错误"""
        self.status_label.setText(f"加载知识库 {book_name} 的文章失败: {str(error)}")
        self.article_list.clear()

    def load_articles_for_book_dropdown(self, book_text):
        """根据下拉框选择加载文章列表"""
        if book_text == "请选择知识库..." or not book_text:
            self.article_list.clear()
            self.status_label.setText("请选择知识库")
            return

        # 获取当前选中项的索引
        current_index = self.book_dropdown.currentIndex()
        if current_index <= 0:  # 0是默认选项
            return

        # 获取namespace和书名
        namespace = self.book_dropdown.itemData(current_index, Qt.UserRole)
        book_name = self.book_dropdown.itemData(current_index, Qt.UserRole + 1)

        if not namespace:
            self.status_label.setText(f"知识库 {book_name} 缺少必要的命名空间信息")
            return

        # 更新当前知识库信息
        self.current_namespace = namespace
        self.current_book_name = book_name

        # 更新状态
        self.status_label.setText(f"正在加载知识库 {book_name} 的文章...")

        # 启用文章相关控件
        self.article_list.setEnabled(True)
        self.article_search_input.setEnabled(True)
        self.select_all_articles_btn.setEnabled(True)
        self.deselect_all_articles_btn.setEnabled(True)

        # 异步加载文章列表
        self.load_articles_worker = AsyncWorker(YuqueApi.get_book_docs, namespace)
        self.load_articles_worker.taskFinished.connect(lambda docs: self.display_articles(docs, book_name))
        self.load_articles_worker.taskError.connect(lambda err: self.handle_articles_error(err, book_name))
        self.load_articles_worker.start()


class YuqueGUI(QMainWindow):
    # 用于安全更新日志文本框的信号
    appendLogSignal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("语雀知识库导出工具")

        # 响应式窗口大小设置
        screen = QApplication.primaryScreen().geometry()
        screen_width = screen.width()
        screen_height = screen.height()

        # 根据屏幕分辨率自适应窗口大小
        if screen_width >= 1920:  # 高分辨率屏幕
            window_width = 1400
            window_height = 900
            min_width = 900
            min_height = 650
        elif screen_width >= 1366:  # 中等分辨率屏幕
            window_width = 1200
            window_height = 800
            min_width = 800
            min_height = 600
        elif screen_width >= 1024:  # 小分辨率屏幕
            window_width = min(1000, int(screen_width * 0.95))
            window_height = min(700, int(screen_height * 0.85))
            min_width = 700
            min_height = 500
        else:  # 极小分辨率屏幕
            window_width = min(800, int(screen_width * 0.98))
            window_height = min(600, int(screen_height * 0.9))
            min_width = 600
            min_height = 450

        # 居中显示
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2

        self.setGeometry(x, y, window_width, window_height)
        self.setMinimumSize(min_width, min_height)

        # 设置应用程序图标为当前目录下的icon.ico文件
        self.setWindowIcon(QIcon(static_resource_path('favicon.ico')))

        # 初始化设置变量
        self.download_threads = 5  # 默认下载线程数
        self.doc_image_prefix = ''  # 文档图片前缀
        self.image_rename_mode = 'asc'  # 图片重命名模式
        self.image_file_prefix = 'image-'  # 图片文件前缀
        self.yuque_cdn_domain = 'cdn.nlark.com'  # 语雀CDN域名

        # 应用样式表
        self.apply_stylesheet()

        # 初始化用户界面
        self.init_ui()

        # 连接信号到更新日志的槽函数
        self.appendLogSignal.connect(self.append_to_log)

        # 初始化日志信号处理程序
        self.log_handler = LogSignalHandler()
        self.log_handler.log_signal.connect(self.update_progress_label)
        self.log_handler.progress_signal.connect(self.update_progress_bar)

        # 设置日志重定向
        self.redirector = StdoutRedirector(self.log_text_edit, disable_terminal_output=True)
        sys.stdout = self.redirector
        sys.stderr = self.redirector

        # 检查Cookie
        self.check_login_status()

        # 设置日志拦截
        self.setup_log_interception()

    def apply_stylesheet(self):
        """样式表"""
        stylesheet = """
            QMainWindow, QWidget {
            background-color: #f8f9fa;
            color: #212529;
        }
        
        QTabWidget::pane {
            border: 1px solid #dee2e6;
            border-radius: 4px;
            background-color: #ffffff;
            top: -1px;
        }
        
        QTabBar {
            border-bottom: none;
        }
        
        QTabBar::tab {
            background-color: #e9ecef;
            color: #495057;
            padding: 8px 16px;
            border: 1px solid #dee2e6;
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            margin-right: 2px;
        }
        
        QTabBar::tab:selected {
            background-color: #ffffff;
            color: #0d6efd;
            border-bottom: none;
        }
        
        QTabBar::tab:hover:!selected {
            background-color: #dee2e6;
        }
        
        QPushButton {
            background-color: #0d6efd;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 6px 12px;
            min-width: 80px;
        }
        
        QPushButton:hover {
            background-color: #0b5ed7;
        }
        
        QPushButton:pressed {
            background-color: #0a58ca;
        }
        
        QPushButton:disabled {
            background-color: #6c757d;
            color: #e9ecef;
        }
        
        QLineEdit, QTextEdit {
            border: 1px solid #ced4da;
            border-radius: 4px;
            padding: 6px;
            background-color: white;
        }
        
        QLineEdit:focus, QTextEdit:focus {
            border: 1px solid #0d6efd;
        }
        
        /* 更新列表框样式 */
        QListWidget {
            border: 1px solid #ced4da;
            border-radius: 4px;
            padding: 2px;
            background-color: white;
            outline: none;
            selection-background-color: transparent;
        }
        
        QListWidget::item {
            height: 30px;
            padding-left: 5px;
            border-radius: 4px;
            margin: 2px;
            padding: 5px;
            border: 1px solid transparent;
        }
        
        QListWidget::item:hover {
            background-color: #f0f7ff;
            border: 1px solid #e7f3ff;
        }
        
        QListWidget::item:selected {
            background-color: #e7f3ff;
            color: #0d6efd;
            border: 1px solid #0d6efd;
            border-radius: 4px;
        }
        
        QProgressBar {
            border: 1px solid #ced4da;
            border-radius: 4px;
            background-color: #e9ecef;
            text-align: center;
            height: 24px;
            font-size: 13px;
            font-weight: bold;
        }
        
        QProgressBar::chunk {
            background-color: #0d6efd;
            border-radius: 3px;
        }
        
        QCheckBox {
            spacing: 8px;
            font-size: 13px;
            min-height: 20px;
            padding: 0;
            margin: 0;
        }
        
        QCheckBox::indicator {
            width: 18px;
            height: 18px;
        }
        

        QGroupBox {
            border: 1px solid #dee2e6;
            border-radius: 4px;
            margin-top: 16px;
            padding-top: 16px;
        }
        
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 5px;
            color: #495057;
        }
        
        QLabel {
            color: #212529;
        }
        
        /* 下拉框样式 */
        QComboBox {
            border: 1px solid #ced4da;
            border-radius: 4px;
            padding: 6px 12px;
            background-color: white;
            color: #212529;
            font-size: 13px;
            min-width: 120px;
            min-height: 20px;
        }
        
        QComboBox:hover {
            border: 1px solid #0d6efd;
            background-color: #f8f9ff;
        }
        
        QComboBox:focus {
            border: 1px solid #0d6efd;
            background-color: white;
        }
        
        QComboBox::drop-down {
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 20px;
            border-left-width: 1px;
            border-left-color: #ced4da;
            border-left-style: solid;
            border-top-right-radius: 4px;
            border-bottom-right-radius: 4px;
            background-color: #f8f9fa;
        }
        
        QComboBox::drop-down:hover {
            background-color: #e9ecef;
            border-left-color: #0d6efd;
        }
        
        QComboBox::down-arrow {
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 6px solid #6c757d;
            width: 0;
            height: 0;
        }
        
        QComboBox::down-arrow:hover {
            border-top-color: #0d6efd;
        }
        
        QComboBox QAbstractItemView {
            border: 1px solid #ced4da;
            border-radius: 4px;
            background-color: white;
            selection-background-color: #e7f3ff;
            selection-color: #0d6efd;
            outline: none;
            padding: 2px;
        }
        
        QComboBox QAbstractItemView::item {
            height: 28px;
            padding: 4px 8px;
            border-radius: 2px;
            margin: 1px;
        }
        
        QComboBox QAbstractItemView::item:hover {
            background-color: #f0f7ff;
            color: #0d6efd;
        }
        
        QComboBox QAbstractItemView::item:selected {
            background-color: #e7f3ff;
            color: #0d6efd;
        }
        
        QSplitter::handle {
            background-color: #dee2e6;
            height: 1px;
        }
        
        QSplitter::handle:hover {
            background-color: #0d6efd;
        }
        
        /* 滚动条样式 */
        QScrollBar:vertical {
            border: none;
            background: #f1f3f5;
            width: 10px;
            margin: 0px 0px 0px 0px;
            border-radius: 5px;
        }
        
        QScrollBar::handle:vertical {
            background: #adb5bd;
            min-height: 20px;
            border-radius: 5px;
        }
        
        QScrollBar::handle:vertical:hover {
            background: #6c757d;
        }
        
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical {
            height: 0px;
        }
        
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical {
            background: none;
        }
        
        QScrollBar:horizontal {
            border: none;
            background: #f1f3f5;
            height: 10px;
            margin: 0px 0px 0px 0px;
            border-radius: 5px;
        }
        
        QScrollBar::handle:horizontal {
            background: #adb5bd;
            min-width: 20px;
            border-radius: 5px;
        }
        
        QScrollBar::handle:horizontal:hover {
            background: #6c757d;
        }
        
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {
            width: 0px;
        }
        
        QScrollBar::add-page:horizontal,
        QScrollBar::sub-page:horizontal {
            background: none;
        }
        """
        self.setStyleSheet(stylesheet)

    def closeEvent(self, event):
        """当窗口关闭时恢复标准输出流"""
        if hasattr(self, 'redirector'):
            # 确保刷新缓冲区
            self.redirector.flush()
            # 恢复标准流
            sys.stdout = self.redirector.old_stdout
            sys.stderr = self.redirector.old_stderr
        super().closeEvent(event)

    def append_to_log(self, text):
        """使用信号槽机制安全地追加文本到日志窗口，根据类型设置不同颜色"""
        # 根据日志类型设置不同颜色
        color = "#f8f8f8"  # 默认白色

        if "错误" in text:
            color = "#ff6b6b"  # 错误信息用红色
        elif "成功" in text or "完成" in text:
            color = "#69db7c"  # 成功信息用绿色
        elif "警告" in text:
            color = "#ffd43b"  # 警告信息用黄色
        elif "调试" in text:
            color = "#a5d8ff"  # 调试信息用浅蓝色
        elif "加载" in text or "准备" in text:
            color = "#da77f2"  # 加载/准备信息用紫色
        elif "导出" in text:
            color = "#74c0fc"  # 导出信息用蓝色

        # 使用HTML格式化文本颜色
        formatted_text = f'<span style="color:{color};">{text}</span>'
        self.log_text_edit.append(formatted_text)

        # 同时记录到调试日志文件（如果启用）
        if Log.is_debug_mode():
            try:
                from src.libs.debug_logger import DebugLogger
                if DebugLogger._initialized:
                    DebugLogger.log_info(text)
            except ImportError:
                pass

    def update_progress_label(self, message):
        """Update progress label with message (called from main thread)"""
        # 不显示在进度标签，只记录到日志
        # self.progress_label.setText(message)

        # 同时添加到日志文本框，使用信号槽机制
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        log_text = f"[{timestamp}] {message}"
        self.appendLogSignal.emit(log_text)

        # 同时记录到调试日志文件（如果启用）
        if Log.is_debug_mode():
            try:
                from src.libs.debug_logger import DebugLogger
                if DebugLogger._initialized:
                    DebugLogger.log_info(message)
            except ImportError:
                pass

    def update_progress_bar(self, current, total):
        """Update progress bar with current and total values (called from main thread)"""
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        # 在进度条上直接显示当前状态
        self.progress_bar.setFormat(f"已导出: {current}/{total} ({int(current / total * 100 if total > 0 else 0)}%)")

    def setup_log_interception(self):
        """Set up log interception by monkey patching Log class"""
        original_info = Log.info
        original_success = Log.success
        original_error = Log.error
        original_debug = Log.debug
        original_warn = Log.warn

        # Try to import DebugLogger
        try:
            from src.libs.debug_logger import DebugLogger
            has_debug_logger = True
        except ImportError:
            has_debug_logger = False

        def patched_info(message):
            # Redirect to GUI instead of terminal
            # original_info(message)
            self.log_handler.emit_log(message)
            if has_debug_logger and Log.is_debug_mode():
                DebugLogger.log_info(message)

        def patched_success(message):
            # Redirect to GUI instead of terminal
            # original_success(message)
            self.log_handler.emit_log(message)
            if has_debug_logger and Log.is_debug_mode():
                DebugLogger.log_info(message)
            if "下载完成" in message:
                # Ensure progress bar is at maximum on completion
                if hasattr(self, 'progress_bar'):
                    self.log_handler.progress_signal.emit(
                        self.progress_bar.maximum(),
                        self.progress_bar.maximum()
                    )

        def patched_error(message, detailed=False):
            # Redirect to GUI instead of terminal
            # original_error(message, detailed)
            self.log_handler.emit_log(f"错误: {message}")
            if has_debug_logger and Log.is_debug_mode():
                DebugLogger.log_error(message)

        def patched_debug(message):
            # Redirect to GUI instead of terminal
            # original_debug(message)
            if Log.is_debug_mode():
                self.log_handler.emit_log(f"调试: {message}")
                if has_debug_logger:
                    DebugLogger.log_debug(message)

        def patched_warn(message, detailed=False):
            # Redirect to GUI instead of terminal
            # original_warn(message, detailed)
            self.log_handler.emit_log(f"警告: {message}")
            if has_debug_logger and Log.is_debug_mode():
                DebugLogger.log_warning(message)

        # Apply the patches
        Log.info = staticmethod(patched_info)
        Log.success = staticmethod(patched_success)
        Log.error = staticmethod(patched_error)
        Log.debug = staticmethod(patched_debug)
        Log.warn = staticmethod(patched_warn)

    def create_settings_page(self):
        """创建设置页面"""
        settings_page = QWidget()
        settings_layout = QVBoxLayout(settings_page)
        settings_layout.setContentsMargins(15, 15, 15, 15)
        settings_layout.setSpacing(15)

        # 图片设置组
        image_group = QGroupBox("图片设置")
        image_layout = QVBoxLayout()
        image_layout.setContentsMargins(10, 0, 0, 15)
        image_layout.setSpacing(15)

        # 下载线程数设置
        threads_layout = QHBoxLayout()
        threads_label = QLabel("下载线程数:")
        threads_label.setMinimumWidth(100)
        self.threads_input = QLineEdit(str(self.download_threads))
        self.threads_input.setValidator(QIntValidator(1, 30))
        self.threads_input.setMaximumWidth(100)
        self.threads_input.textChanged.connect(self.auto_save_settings)
        threads_help = QLabel("(1-30，默认5)")
        threads_help.setStyleSheet("color: #6c757d; font-size: 12px;")
        threads_layout.addWidget(threads_label)
        threads_layout.addWidget(self.threads_input)
        threads_layout.addWidget(threads_help)
        threads_layout.addStretch()
        image_layout.addLayout(threads_layout)

        # 图片重命名模式设置
        rename_layout = QHBoxLayout()
        rename_label = QLabel("图片重命名模式:")
        rename_label.setMinimumWidth(100)

        # 创建单选按钮组
        self.rename_button_group = QButtonGroup()
        self.rename_radio1 = QRadioButton("递增命名")
        self.rename_radio2 = QRadioButton("保持图片原名")

        # 添加到按钮组
        self.rename_button_group.addButton(self.rename_radio1, 0)
        self.rename_button_group.addButton(self.rename_radio2, 1)

        # 设置默认选中状态
        if self.image_rename_mode == "asc":
            self.rename_radio1.setChecked(True)
        else:
            self.rename_radio2.setChecked(True)

        # 连接信号
        self.rename_button_group.buttonClicked.connect(self.auto_save_settings)

        rename_layout.addWidget(rename_label)
        rename_layout.addWidget(self.rename_radio1)
        rename_layout.addWidget(self.rename_radio2)
        rename_layout.addStretch()
        image_layout.addLayout(rename_layout)

        # 图片文件前缀设置
        file_prefix_layout = QHBoxLayout()
        file_prefix_label = QLabel("图片文件前缀:")
        file_prefix_label.setMinimumWidth(100)
        self.file_prefix_input = QLineEdit(self.image_file_prefix)
        self.file_prefix_input.setMaximumWidth(150)
        self.file_prefix_input.textChanged.connect(self.auto_save_settings)
        file_prefix_help = QLabel("(递增模式下的文件名前缀)")
        file_prefix_help.setStyleSheet("color: #6c757d; font-size: 12px;")
        file_prefix_layout.addWidget(file_prefix_label)
        file_prefix_layout.addWidget(self.file_prefix_input)
        file_prefix_layout.addWidget(file_prefix_help)
        file_prefix_layout.addStretch()
        image_layout.addLayout(file_prefix_layout)

        # CDN域名设置
        cdn_layout = QHBoxLayout()
        cdn_label = QLabel("语雀CDN域名:")
        cdn_label.setMinimumWidth(100)
        self.cdn_input = QLineEdit(self.yuque_cdn_domain)
        self.cdn_input.setMaximumWidth(200)
        self.cdn_input.textChanged.connect(self.auto_save_settings)
        cdn_help = QLabel("(语雀图片CDN域名)")
        cdn_help.setStyleSheet("color: #6c757d; font-size: 12px;")
        cdn_layout.addWidget(cdn_label)
        cdn_layout.addWidget(self.cdn_input)
        cdn_layout.addWidget(cdn_help)
        cdn_layout.addStretch()
        image_layout.addLayout(cdn_layout)

        image_group.setLayout(image_layout)
        settings_layout.addWidget(image_group)

        # 调试设置组
        debug_group = QGroupBox("其他设置")
        debug_layout = QVBoxLayout()
        debug_layout.setContentsMargins(20, 20, 20, 20)
        debug_layout.setSpacing(15)

        self.enable_debug_checkbox = QCheckBox("调试模式")
        self.enable_debug_checkbox.setToolTip("记录详细日志到文件")
        self.enable_debug_checkbox.setChecked(False)
        self.enable_debug_checkbox.stateChanged.connect(self.toggle_debug_mode)
        debug_layout.addWidget(self.enable_debug_checkbox)

        debug_group.setLayout(debug_layout)
        settings_layout.addWidget(debug_group)

        settings_layout.addStretch()
        return settings_page

    def auto_save_settings(self):
        """自动保存设置"""
        try:
            # 验证线程数输入
            threads_text = self.threads_input.text()
            if threads_text:
                threads = int(threads_text)
                if 1 <= threads <= 30:
                    self.download_threads = threads
                else:
                    # 显示错误提示并恢复到有效值
                    QMessageBox.warning(self, "输入错误", "下载线程数必须在1-30之间！")
                    self.threads_input.setText(str(self.download_threads))
                    return  # 无效值，不保存

            # 保存其他设置
            # 获取选中的单选按钮文本并转换为底层代码期望的值
            if self.rename_radio1.isChecked():
                self.image_rename_mode = "asc"  # 递增命名对应asc
            else:
                self.image_rename_mode = "raw"  # 保持图片原名对应raw
            self.image_file_prefix = self.file_prefix_input.text()
            self.yuque_cdn_domain = self.cdn_input.text()

        except ValueError:
            # 输入无效时显示提示并恢复到有效值
            QMessageBox.warning(self, "输入错误", "下载线程数必须是1-30之间的数字！")
            self.threads_input.setText(str(self.download_threads))

    def create_about_page(self):
        """创建关于页面"""
        about_page = QWidget()
        about_layout = QVBoxLayout(about_page)
        about_layout.setContentsMargins(20, 15, 20, 15)
        about_layout.setSpacing(15)

        # 页面标题
        title_label = QLabel("关于本软件")
        title_label.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(20)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #0d6efd; margin-bottom: 10px;")
        about_layout.addWidget(title_label)

        # 主要信息區域
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(15)

        # 作者信息部分
        author_section = QWidget()
        author_layout = QHBoxLayout(author_section)
        author_layout.setContentsMargins(0, 0, 0, 0)
        author_layout.setSpacing(15)

        # 作者头像 - 使用程序图标
        author_avatar = QLabel()
        author_avatar.setFixedSize(70, 70)
        author_avatar.setStyleSheet("""
            QLabel {
                border: 2px solid #0d6efd;
                border-radius: 35px;
                background-color: white;
                padding: 3px;
            }
        """)
        author_avatar.setAlignment(Qt.AlignCenter)
        author_avatar.setScaledContents(True)

        # 加载程序图标作为作者头像
        try:
            icon_path = static_resource_path("favicon.ico")
            if os.path.exists(icon_path):
                pixmap = QPixmap(icon_path)
                if not pixmap.isNull():
                    # 缩放图标到合适大小
                    scaled_pixmap = pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    # 创建圆形头像
                    circular_pixmap = self.create_circular_pixmap(scaled_pixmap, 64)
                    author_avatar.setPixmap(circular_pixmap)
                else:
                    author_avatar.setText("Be1k0")
                    author_avatar.setStyleSheet("""
                        QLabel {
                            border: 2px solid #0d6efd;
                            border-radius: 35px;
                            background-color: white;
                            color: #0d6efd;
                            font-weight: bold;
                            font-size: 12px;
                            padding: 3px;
                        }
                    """)
            else:
                author_avatar.setText("Be1k0")
                author_avatar.setStyleSheet("""
                    QLabel {
                        border: 2px solid #0d6efd;
                        border-radius: 35px;
                        background-color: white;
                        color: #0d6efd;
                        font-weight: bold;
                        font-size: 12px;
                        padding: 3px;
                    }
                """)
        except Exception as e:
            author_avatar.setText("Be1k0")
            author_avatar.setStyleSheet("""
                QLabel {
                    border: 2px solid #0d6efd;
                    border-radius: 35px;
                    background-color: white;
                    color: #0d6efd;
                    font-weight: bold;
                    font-size: 12px;
                    padding: 3px;
                }
            """)

        author_layout.addWidget(author_avatar)

        # 作者信息文本
        author_info_layout = QVBoxLayout()
        author_info_layout.setContentsMargins(0, 5, 0, 0)
        author_info_layout.setSpacing(8)

        # 作者名称
        author_name = QLabel("作者: Be1k0")
        author_name.setFont(QFont("", 15, QFont.Bold))
        author_name.setStyleSheet("color: #333;")
        author_info_layout.addWidget(author_name)

        # 项目地址
        project_url = QLabel(
            "项目地址: <a href='https://github.com/Be1k0/yuque_document_download/' style='color: #0d6efd; text-decoration: none;'>https://github.com/Be1k0/yuque_document_download/</a>")
        project_url.setOpenExternalLinks(True)
        project_url.setWordWrap(False)
        project_url.setFont(QFont("", 14))
        project_url.setStyleSheet("color: #666;")
        author_info_layout.addWidget(project_url)

        author_layout.addLayout(author_info_layout)
        author_layout.addStretch()

        info_layout.addWidget(author_section)

        # 添加一些間距
        info_layout.addSpacing(10)

        # 项目简介
        description_title = QLabel("简介")
        description_title.setFont(QFont("", 15, QFont.Bold))
        description_title.setStyleSheet("color: #333;")
        info_layout.addWidget(description_title)

        description_text = QLabel("一款功能强大的语雀知识库批量导出工具，支持一键导出语雀知识库中的所有文档。")
        description_text.setWordWrap(True)
        description_text.setFont(QFont("", 14))
        description_text.setStyleSheet("color: #666; padding: 5px 0;")
        info_layout.addWidget(description_text)

        about_layout.addWidget(info_widget)

        # 版本信息
        version_label = QLabel("版本: v1.0.0")
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setFont(QFont("", 13))
        version_label.setStyleSheet("color: #6c757d; margin-top: 10px;")
        about_layout.addWidget(version_label)

        about_layout.addStretch()
        return about_page

    def init_ui(self):
        # Main container
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Banner/Header
        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(5)

        header_label = QLabel("语雀知识库导出工具")
        header_label.setAlignment(Qt.AlignCenter)
        header_font = QFont()
        header_font.setBold(True)
        header_font.setPointSize(16)
        header_label.setFont(header_font)
        header_label.setStyleSheet("color: #0d6efd;")
        header_layout.addWidget(header_label)

        subtitle_label = QLabel("支持一键导出语雀知识库所有文档")
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setStyleSheet("color: #495057; margin-bottom: 10px;")
        header_layout.addWidget(subtitle_label)

        main_layout.addWidget(header_widget)

        # 创建主分割器
        main_splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(main_splitter, 1)  # 占据大部分空间

        # 上半部分 - 操作区域
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_widget.setMinimumHeight(410)  # 设置最小高度防止上半部分变小

        # 创建Tab小部件
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.setStyleSheet("""
            QTabWidget::tab-bar {
                alignment: center;
            }
            QTabWidget::pane {
                border-top: 0px;
            }
        """)

        # 登录表单页
        login_page = QWidget()
        login_layout = QVBoxLayout(login_page)
        login_layout.setContentsMargins(15, 15, 15, 15)
        login_layout.setSpacing(15)

        # 登录表单组（未登录时显示）
        self.login_group = QGroupBox("账号登录")
        login_form_layout = QVBoxLayout()
        login_form_layout.setContentsMargins(20, 20, 20, 20)
        login_form_layout.setSpacing(15)

        username_layout = QHBoxLayout()
        username_label = QLabel("用户名:")
        username_label.setMinimumWidth(60)
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("请输入语雀账号")
        username_layout.addWidget(username_label)
        username_layout.addWidget(self.username_input)
        login_form_layout.addLayout(username_layout)

        password_layout = QHBoxLayout()
        password_label = QLabel("密码:")
        password_label.setMinimumWidth(60)
        self.password_input = QPasswordLineEdit()
        self.password_input.setPlaceholderText("请输入语雀密码")
        password_layout.addWidget(password_label)
        password_layout.addWidget(self.password_input)
        login_form_layout.addLayout(password_layout)

        # 添加一些间距
        login_form_layout.addSpacing(10)

        self.login_button = QPushButton("登录")
        self.login_button.setMinimumHeight(36)
        self.login_button.clicked.connect(self.login)
        login_form_layout.addWidget(self.login_button)

        self.login_group.setLayout(login_form_layout)
        login_layout.addWidget(self.login_group)

        # Add some explanation text
        login_help = QLabel("请输入您的语雀账号和密码进行登录。登录信息仅用于获取知识库数据，不会被发送到第三方。")
        login_help.setWordWrap(True)
        login_help.setStyleSheet("color: #6c757d; padding: 10px;")
        login_layout.addWidget(login_help)

        # 用户信息组（已登录时显示）
        self.user_info_group = QGroupBox("当前账号")
        user_info_layout = QVBoxLayout()
        user_info_layout.setContentsMargins(20, 20, 20, 20)
        user_info_layout.setSpacing(15)

        # 用户头像和基本信息
        user_header_layout = QHBoxLayout()

        # 头像标签
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(80, 80)
        self.avatar_label.setStyleSheet("""
            QLabel {
                border: 2px solid #ddd;
                border-radius: 40px;
                background-color: #f8f9fa;
            }
        """)
        self.avatar_label.setAlignment(Qt.AlignCenter)
        self.avatar_label.setScaledContents(True)
        user_header_layout.addWidget(self.avatar_label)

        # 用户信息
        user_details_layout = QVBoxLayout()

        self.user_name_label = QLabel("用户名: --")
        self.user_name_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        user_details_layout.addWidget(self.user_name_label)

        self.user_id_label = QLabel("用户ID: --")
        self.user_id_label.setStyleSheet("color: #666;")
        user_details_layout.addWidget(self.user_id_label)

        user_header_layout.addLayout(user_details_layout)
        user_header_layout.addStretch()

        user_info_layout.addLayout(user_header_layout)

        # 注销按钮
        user_info_layout.addSpacing(10)
        self.logout_button = QPushButton("注销")
        self.logout_button.setMinimumHeight(36)
        self.logout_button.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:pressed {
                background-color: #bd2130;
            }
        """)
        self.logout_button.clicked.connect(self.logout)
        user_info_layout.addWidget(self.logout_button)

        self.user_info_group.setLayout(user_info_layout)
        login_layout.addWidget(self.user_info_group)

        # 默认隐藏用户信息组
        self.user_info_group.hide()

        login_layout.addStretch(1)  # Add stretch to push content up

        # 知识库选择页
        selection_page = QWidget()
        selection_layout = QVBoxLayout(selection_page)
        selection_layout.setContentsMargins(10, 10, 10, 10)  # 减少边距以节省空间
        selection_layout.setSpacing(15)  # 减少间距

        # 添加状态标签
        self.status_label = QLabel("准备就绪")
        self.status_label.setStyleSheet("color: #0d6efd;")
        selection_layout.addWidget(self.status_label)

        # 水平布局将三个部分分开
        selection_horizontal = QHBoxLayout()
        selection_layout.addLayout(selection_horizontal)

        # 左侧：知识库列表
        left_panel = QGroupBox("知识库列表")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 15, 10, 10)  # 减少边距以节省空间
        left_layout.setSpacing(8)  # 减少间距

        # 搜索框
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索:")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词过滤知识库")
        self.search_input.textChanged.connect(self.filter_books)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        left_layout.addLayout(search_layout)

        # 知识库列表
        self.book_list = QListWidget()
        self.book_list.setSelectionMode(QListWidget.MultiSelection)
        self.book_list.setMinimumHeight(100)  # 减少最小高度以适应小分辨率
        self.book_list.setMinimumWidth(180)  # 减少最小宽度
        left_layout.addWidget(self.book_list)

        # 知识库选择按钮区域
        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(5)

        # 第一行：全选和取消全选按钮
        select_buttons_layout = QHBoxLayout()
        select_buttons_layout.setSpacing(5)

        self.select_all_books_btn = QPushButton("全选")
        self.select_all_books_btn.setMinimumHeight(28)  # 减少按钮高度
        self.select_all_books_btn.setMaximumHeight(32)  # 限制最大高度
        self.select_all_books_btn.clicked.connect(self.select_all_books)
        select_buttons_layout.addWidget(self.select_all_books_btn)

        self.deselect_all_books_btn = QPushButton("取消全选")
        self.deselect_all_books_btn.setMinimumHeight(28)  # 减少按钮高度
        self.deselect_all_books_btn.setMaximumHeight(32)  # 限制最大高度
        self.deselect_all_books_btn.clicked.connect(self.deselect_all_books)
        select_buttons_layout.addWidget(self.deselect_all_books_btn)

        buttons_layout.addLayout(select_buttons_layout)

        # 第二行：已选数量标签
        count_layout = QHBoxLayout()
        count_layout.addStretch()

        self.selected_count_label = QLabel("已选: 0")
        self.selected_count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.selected_count_label.setStyleSheet("color: #0d6efd; font-weight: bold;")
        count_layout.addWidget(self.selected_count_label)

        buttons_layout.addLayout(count_layout)
        left_layout.addLayout(buttons_layout)

        # 连接选择变化的信号
        self.book_list.itemSelectionChanged.connect(self.update_selected_count)

        # 右侧：导出设置
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 0, 0, 15)
        right_panel.setMinimumHeight(400)
        right_layout.setSpacing(15)

        # Options in a group box with regular layout
        options_group = QGroupBox("导出选项")
        options_layout = QVBoxLayout()
        options_layout.setContentsMargins(10, 0, 10, 15)  # 减少边距以节省空间
        options_group.setLayout(options_layout)

        # 创建常规复选框样式的选项
        self.skip_local_checkbox = QCheckBox("跳过本地文件")
        self.skip_local_checkbox.setToolTip("如果文件已经存在则不重新下载")
        self.skip_local_checkbox.setChecked(True)
        options_layout.addWidget(self.skip_local_checkbox)

        self.keep_linebreak_checkbox = QCheckBox("保留语雀换行标识")
        self.keep_linebreak_checkbox.setToolTip("保留语雀文档中的换行标记")
        self.keep_linebreak_checkbox.setChecked(True)
        options_layout.addWidget(self.keep_linebreak_checkbox)

        self.download_images_checkbox = QCheckBox("下载图片到本地")
        self.download_images_checkbox.setToolTip("将Markdown文档中的图片下载到本地，并更新图片链接")
        self.download_images_checkbox.setChecked(True)
        options_layout.addWidget(self.download_images_checkbox)

        # 输出目录设置
        output_layout = QHBoxLayout()
        output_label = QLabel("输出目录:")
        self.output_input = QLineEdit()
        self.output_input.setReadOnly(True)

        # 设置默认输出目录（CLI配置已移除，直接使用全局配置）
        self.output_input.setText(GLOBAL_CONFIG.target_output_dir)

        output_button = QPushButton("选择")
        output_button.setMinimumHeight(32)
        output_button.clicked.connect(self.select_output_dir)

        output_layout.addWidget(output_label)
        output_layout.addWidget(self.output_input)
        output_layout.addWidget(output_button)
        output_layout.addStretch()

        options_layout.addLayout(output_layout)

        right_layout.addWidget(options_group)

        # 进度条
        progress_layout = QVBoxLayout()
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(10)
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)  # 隐藏进度标签

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("已导出: %v/%m (%p%)")
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                text-align: center;
                color: #495057;
                font-weight: bold;
                font-size: 12px;
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 4px;
                height: 22px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0d6efd, stop:1 #0b5ed7);
                border-radius: 3px;
                margin: 1px;
            }
        """)
        progress_layout.addWidget(self.progress_bar)

        right_layout.addLayout(progress_layout)

        # 导出操作按钮区域
        export_actions_layout = QVBoxLayout()
        # 最小高度 
        export_actions_layout.setContentsMargins(0, 0, 0, 50)

        # 开始导出按钮
        self.export_button = QPushButton("开始导出")
        self.export_button.setMinimumHeight(32)  # 减少按钮高度
        self.export_button.setMaximumHeight(36)  # 限制最大高度
        self.export_button.setStyleSheet("""
            QPushButton {
                background-color: #0d6efd;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0b5ed7;
            }
            QPushButton:pressed {
                background-color: #0a58ca;
            }
        """)
        self.export_button.clicked.connect(self.start_export)
        export_actions_layout.addWidget(self.export_button)

        # 清除缓存按钮
        self.clean_button = QPushButton("清理缓存")
        self.clean_button.setMinimumHeight(32)  # 减少按钮高度
        self.clean_button.setMaximumHeight(36)  # 限制最大高度
        self.clean_button.clicked.connect(self.clean_cache)
        self.clean_button.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5c636a;
            }
            QPushButton:pressed {
                background-color: #565e64;
            }
        """)
        export_actions_layout.addWidget(self.clean_button)

        right_layout.addLayout(export_actions_layout)

        # 中间面板：选择文章
        center_panel = QGroupBox("文章列表")
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(10, 15, 10, 10)  # 减少边距以节省空间
        center_layout.setSpacing(8)  # 减少间距

        # 文章搜索框
        article_search_layout = QHBoxLayout()
        article_search_label = QLabel("搜索文章:")
        self.article_search_input = QLineEdit()
        self.article_search_input.setPlaceholderText("输入关键词过滤文章")
        self.article_search_input.textChanged.connect(self.filter_articles)
        article_search_layout.addWidget(article_search_label)
        article_search_layout.addWidget(self.article_search_input)
        center_layout.addLayout(article_search_layout)

        # 文章列表
        self.article_list = QListWidget()
        self.article_list.setSelectionMode(QListWidget.MultiSelection)
        self.article_list.itemSelectionChanged.connect(self.update_article_selection)
        center_layout.addWidget(self.article_list)

        # 文章选择控制区域
        article_control_layout = QVBoxLayout()
        article_control_layout.setSpacing(5)

        # 第一行：全选和取消全选按钮
        article_buttons_layout = QHBoxLayout()
        article_buttons_layout.setSpacing(5)

        self.select_all_articles_btn = QPushButton("全选文章")
        self.select_all_articles_btn.setMinimumHeight(28)  # 减少按钮高度
        self.select_all_articles_btn.setMaximumHeight(32)  # 限制最大高度
        self.select_all_articles_btn.clicked.connect(self.select_all_articles)
        article_buttons_layout.addWidget(self.select_all_articles_btn)

        self.deselect_all_articles_btn = QPushButton("取消全选")
        self.deselect_all_articles_btn.setMinimumHeight(28)  # 减少按钮高度
        self.deselect_all_articles_btn.setMaximumHeight(32)  # 限制最大高度
        self.deselect_all_articles_btn.clicked.connect(self.deselect_all_articles)
        article_buttons_layout.addWidget(self.deselect_all_articles_btn)

        article_control_layout.addLayout(article_buttons_layout)

        # 第二行：已选数量标签
        article_count_layout = QHBoxLayout()
        article_count_layout.addStretch()

        self.selected_article_count_label = QLabel("已选: 0")
        self.selected_article_count_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.selected_article_count_label.setStyleSheet("color: #0d6efd; font-weight: bold;")
        article_count_layout.addWidget(self.selected_article_count_label)

        article_control_layout.addLayout(article_count_layout)
        center_layout.addLayout(article_control_layout)

        # 添加三个面板到水平布局 - 优化小分辨率下的比例
        selection_horizontal.addWidget(left_panel, 30)  # 左侧占30%
        selection_horizontal.addWidget(center_panel, 45)  # 中间占45%
        selection_horizontal.addWidget(right_panel, 25)  # 右侧占25%

        # 设置页面
        settings_page = self.create_settings_page()

        # 关于页面
        about_page = self.create_about_page()

        # 添加标签页
        tabs.addTab(login_page, "登录")
        tabs.addTab(selection_page, "知识库选择")
        tabs.addTab(settings_page, "设置")
        tabs.addTab(about_page, "关于")

        top_layout.addWidget(tabs)
        main_splitter.addWidget(top_widget)

        # 下半部分 - 日志区域
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout()
        # 最小高度
        log_group.setMinimumHeight(120)
        log_layout.setContentsMargins(15, 0, 15, 15)

        self.log_text_edit = QTextEdit()
        self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setLineWrapMode(QTextEdit.NoWrap)
        self.log_text_edit.setFont(QFont("Consolas", 9))
        self.log_text_edit.setMinimumHeight(30)

        # 设置日志窗口样式 - 黑色背景，不同日志颜色
        self.log_text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #f8f8f8;
                border: 1px solid #2d2d2d;
                border-radius: 4px;
            }
        """)

        log_layout.addWidget(self.log_text_edit)

        # 添加日志控制按钮
        log_button_layout = QHBoxLayout()
        log_button_layout.setSpacing(10)

        clear_log_button = QPushButton("清空日志")
        clear_log_button.clicked.connect(self.clear_log)
        clear_log_button.setStyleSheet("""
            background-color: #6c757d;
        """)
        log_button_layout.addWidget(clear_log_button)

        save_log_button = QPushButton("保存日志")
        save_log_button.clicked.connect(self.save_log)
        save_log_button.setStyleSheet("""
            background-color: #198754;
        """)
        log_button_layout.addWidget(save_log_button)

        log_layout.addLayout(log_button_layout)

        log_group.setLayout(log_layout)
        bottom_layout.addWidget(log_group)

        main_splitter.addWidget(bottom_widget)
        main_splitter.setHandleWidth(0)

        # Add copyright info
        copyright_label = QLabel("Copyright © 2025 By Be1k0 | https://github.com/Be1k0")
        copyright_label.setAlignment(Qt.AlignCenter)
        copyright_label.setStyleSheet("color: #6c757d; padding: 5px;")
        main_layout.addWidget(copyright_label)

    def clear_log(self):
        """清空日志文本框"""
        self.log_text_edit.clear()

    def save_log(self):
        """保存日志到文件"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存日志文件",
            os.path.join(os.path.expanduser("~"), "yuque_export_log.txt"),
            "文本文件 (*.txt);;所有文件 (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.log_text_edit.toPlainText())
                QMessageBox.information(self, "保存成功", f"日志已保存到: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "保存失败", f"保存日志出错: {str(e)}")

    def check_login_status(self):
        """检查是否已经登录"""
        cookies = get_local_cookies()
        if cookies:
            # 显示用户信息，隐藏登录表单
            self.show_user_info()
            # 选择第二个标签页（知识库选择）
            tabs = self.findChild(QTabWidget)
            if tabs:
                tabs.setCurrentIndex(1)
            self.load_books()
        else:
            # 显示登录表单，隐藏用户信息
            self.show_login_form()
            # 检查我们是否已保存凭据
            # CLI配置已移除，不再自动填充用户名密码
            pass

    def login(self):
        """处理登录"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "输入错误", "用户名和密码不能为空")
            return

        # 禁用登录按钮并显示状态
        self.login_button.setEnabled(False)
        self.login_button.setText("登录中...")

        # 创建帐户对象
        account = YuqueAccount(username=username, password=password)

        # 在单独的线程中启动登录过程
        self.login_worker = AsyncWorker(YuqueApi.login, username, password)
        self.login_worker.taskFinished.connect(self.on_login_finished)
        self.login_worker.taskError.connect(self.on_login_error)
        self.login_worker.start()

    def on_login_finished(self, result):
        """登录完成后的回调"""
        self.login_button.setEnabled(True)
        self.login_button.setText("登录")

        if result:
            # 登录成功
            QMessageBox.information(self, "登录成功", "成功登录到语雀账号")

            # 显示用户信息，隐藏登录表单
            self.show_user_info()

            # 切换到知识库选择标签页
            tabs = self.findChild(QTabWidget)
            if tabs:
                tabs.setCurrentIndex(1)
            self.load_books()
        else:
            QMessageBox.warning(self, "登录失败", "登录失败，请检查用户名和密码")

    def on_login_error(self, error_msg):
        """登录出错的回调"""
        self.login_button.setEnabled(True)
        self.login_button.setText("登录")
        QMessageBox.critical(self, "登录错误", f"登录过程出错: {error_msg}")

    def show_login_form(self):
        """显示登录表单，隐藏用户信息"""
        self.login_group.show()
        self.user_info_group.hide()

    def show_user_info(self):
        """显示用户信息，隐藏登录表单"""
        self.login_group.hide()
        self.user_info_group.show()
        self.update_user_info_display()

    def update_user_info_display(self):
        """更新用户信息显示"""
        try:
            from src.libs.tools import get_cache_user_info
            import json
            import os

            # 读取用户信息文件
            user_info_path = resource_path(os.path.join('.meta', 'user_info.json'))
            if os.path.exists(user_info_path):
                with open(user_info_path, 'r', encoding='utf-8') as f:
                    user_data = json.load(f)
                    user_info = user_data.get('user_info', {})

                    # 更新用户信息显示
                    name = user_info.get('name', '--')
                    login = user_info.get('login', '--')
                    avatar_url = user_info.get('avatar', '')

                    self.user_name_label.setText(f"用户名: {name}")
                    self.user_id_label.setText(f"用户ID: {login}")

                    # 加载头像
                    if avatar_url:
                        self.load_avatar(avatar_url)
                    else:
                        # 设置默认头像
                        self.avatar_label.setText("头像")
                        self.avatar_label.setStyleSheet("""
                            QLabel {
                                border: 2px solid #ddd;
                                border-radius: 40px;
                                background-color: #f8f9fa;
                                color: #666;
                                font-size: 12px;
                            }
                        """)
            else:
                # 如果文件不存在，显示默认信息
                self.user_name_label.setText("用户名: --")
                self.user_id_label.setText("用户ID: --")
                self.avatar_label.setText("头像")

        except Exception as e:
            Log.error(f"更新用户信息显示时出错: {e}")

    def load_avatar(self, avatar_url):
        """加载用户头像"""
        try:
            from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
            from PyQt5.QtCore import QUrl

            Log.debug(f"开始加载头像: {avatar_url}")

            # 创建网络管理器
            if not hasattr(self, 'network_manager'):
                self.network_manager = QNetworkAccessManager()
                self.network_manager.finished.connect(self.on_avatar_loaded)
                Log.debug("网络管理器创建成功")

            # 发起网络请求
            request = QNetworkRequest(QUrl(avatar_url))
            # 设置用户代理，避免被服务器拒绝
            request.setRawHeader(b'User-Agent', b'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            self.network_manager.get(request)
            Log.debug("网络请求已发起")

        except Exception as e:
            Log.error(f"加载头像时出错: {e}")
            import traceback
            traceback.print_exc()
            # 设置默认头像
            self.avatar_label.setText("头像")

    def on_avatar_loaded(self, reply):
        """头像加载完成的回调"""
        try:
            Log.debug(f"头像请求完成，错误码: {reply.error()}")
            if reply.error() == reply.NoError:
                data = reply.readAll()
                Log.debug(f"接收到头像数据，大小: {len(data)} 字节")
                pixmap = QPixmap()
                if pixmap.loadFromData(data):
                    Log.debug("头像数据加载成功，开始处理")
                    # 缩放头像到合适大小
                    scaled_pixmap = pixmap.scaled(76, 76, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    # 创建圆形头像
                    circular_pixmap = self.create_circular_pixmap(scaled_pixmap, 76)
                    self.avatar_label.setPixmap(circular_pixmap)
                    Log.debug("头像设置成功")
                else:
                    Log.warn("头像数据加载失败")
                    self.avatar_label.setText("头像")
            else:
                Log.error(f"网络请求失败: {reply.errorString()}")
                self.avatar_label.setText("头像")
        except Exception as e:
            Log.error(f"处理头像数据时出错: {e}")
            import traceback
            traceback.print_exc()
            self.avatar_label.setText("头像")
        finally:
            reply.deleteLater()

    def create_circular_pixmap(self, pixmap, size):
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

    def logout(self):
        """注销登录"""
        reply = QMessageBox.question(self, "确认注销", "确定要注销当前账号吗？",
                                     QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.No)

        if reply == QMessageBox.Yes:
            try:
                import os
                import shutil

                # 删除.meta文件夹下的所有文件
                meta_dir = resource_path('.meta')
                if os.path.exists(meta_dir):
                    # 删除文件夹内所有内容
                    for filename in os.listdir(meta_dir):
                        file_path = os.path.join(meta_dir, filename)
                        try:
                            if os.path.isfile(file_path) or os.path.islink(file_path):
                                os.unlink(file_path)
                            elif os.path.isdir(file_path):
                                shutil.rmtree(file_path)
                        except Exception as e:
                            Log.error(f"删除 {file_path} 时出错: {e}")

                # 清空输入框
                self.username_input.clear()
                self.password_input.clear()

                # 清空知识库列表
                self.book_list.clear()

                # 清空文章列表
                self.article_list.clear()

                # 显示登录表单
                self.show_login_form()

                # 切换到登录标签页
                tabs = self.findChild(QTabWidget)
                if tabs:
                    tabs.setCurrentIndex(0)

                QMessageBox.information(self, "注销成功", "已成功注销账号")

            except Exception as e:
                QMessageBox.critical(self, "注销失败", f"注销过程中出错: {str(e)}")

    def load_books(self):
        """加载知识库列表"""
        self.book_list.clear()
        self.progress_label.setText("正在加载知识库列表...")

        # Try to get cached books info
        books_info = get_cache_books_info()

        if not books_info:
            # If no cached info, fetch from API
            self.books_worker = AsyncWorker(YuqueApi.get_user_bookstacks)
            self.books_worker.taskFinished.connect(self.on_books_loaded)
            self.books_worker.taskError.connect(self.on_books_error)
            self.books_worker.start()
            return

        # Display books from cache
        self.display_books(books_info)

    def on_books_loaded(self, result):
        """知识库加载完成后的回调"""
        if result:
            books_info = get_cache_books_info()  # Refresh from cache
            self.display_books(books_info)
        else:
            QMessageBox.warning(self, "加载失败", "无法获取知识库列表")
            self.progress_label.setText("加载知识库失败")

    def on_books_error(self, error_msg):
        """知识库加载出错的回调"""
        QMessageBox.critical(self, "加载错误", f"获取知识库出错: {error_msg}")
        self.progress_label.setText(f"加载知识库出错: {error_msg}")

    def display_books(self, books_info):
        """显示知识库列表"""
        # 断开知识库选择变化的信号，避免在批量选择时触发文章加载
        try:
            self.book_list.itemSelectionChanged.disconnect()
        except:
            pass

        self.book_list.clear()

        # 先按所有者类型和名称排序
        owner_books = []
        other_books = []

        for item in books_info:
            if hasattr(item, 'book_type') and item.book_type == "owner":
                owner_books.append(item)
            else:
                other_books.append(item)

        # 按名称排序
        owner_books.sort(key=lambda x: x.name)
        other_books.sort(key=lambda x: x.name)

        # 先添加个人知识库
        for item in owner_books:
            list_item = QListWidgetItem(f"👤 {item.name}")
            list_item.setToolTip(f"个人知识库: {item.name}\n包含 {item.items_count} 篇文档")
            # 存储namespace信息用于后续加载文章
            namespace = ""
            if hasattr(item, 'namespace') and item.namespace:
                namespace = item.namespace
            elif hasattr(item, 'user_login') and hasattr(item, 'slug'):
                namespace = f"{item.user_login}/{item.slug}"
            elif hasattr(item, 'user') and hasattr(item, 'slug'):
                if isinstance(item.user, dict) and 'login' in item.user:
                    namespace = f"{item.user['login']}/{item.slug}"

            list_item.setData(Qt.UserRole, namespace)
            list_item.setData(Qt.UserRole + 1, item.name)  # 存储原始名称
            self.book_list.addItem(list_item)

        # 再添加团队知识库
        for item in other_books:
            list_item = QListWidgetItem(f"👥 {item.name}")
            list_item.setToolTip(f"团队知识库: {item.name}\n包含 {item.items_count} 篇文档")
            # 存储namespace信息
            namespace = ""
            if hasattr(item, 'namespace') and item.namespace:
                namespace = item.namespace
            elif hasattr(item, 'user_login') and hasattr(item, 'slug'):
                namespace = f"{item.user_login}/{item.slug}"
            elif hasattr(item, 'user') and hasattr(item, 'slug'):
                if isinstance(item.user, dict) and 'login' in item.user:
                    namespace = f"{item.user['login']}/{item.slug}"

            list_item.setData(Qt.UserRole, namespace)
            list_item.setData(Qt.UserRole + 1, item.name)  # 存储原始名称
            self.book_list.addItem(list_item)

        # 记录到日志中
        self.appendLogSignal.emit(f"已加载 {len(books_info)} 个知识库")
        self.progress_bar.setValue(0)

        # 首次加载完成后显示默认提示
        self.article_list.clear()
        hint_item = QListWidgetItem("请从左侧选择一个知识库以加载文章列表")
        hint_item.setFlags(Qt.NoItemFlags)
        hint_item.setForeground(QColor("#6c757d"))
        self.article_list.addItem(hint_item)

        # 重置文章选择状态
        self.selected_article_count_label.setText("已选: 0")
        self.update_selected_count()

        # 重新连接知识库选择变化的信号
        self.book_list.itemSelectionChanged.connect(self.book_selection_changed)

        # 如果有搜索文本，应用过滤
        if hasattr(self, 'search_input') and self.search_input.text():
            self.filter_books(self.search_input.text())

    def filter_books(self, text):
        """根据输入过滤知识库列表"""
        filter_text = text.lower()
        for i in range(self.book_list.count()):
            item = self.book_list.item(i)
            # 去掉emoji前缀后再比较
            book_name = item.text()[2:].strip().lower()
            item.setHidden(filter_text not in book_name)

    def load_articles_for_book(self, current, previous):
        """加载选中知识库的文章列表"""
        if not current:
            return

        # 清空文章列表
        self.article_list.clear()

        # 获取知识库namespace和名称
        namespace = current.data(Qt.UserRole)
        book_name = current.data(Qt.UserRole + 1)

        if not namespace:
            self.status_label.setText(f"知识库 {book_name} 缺少必要的命名空间信息")
            return

        # 更新当前知识库信息
        self.current_namespace = namespace
        self.current_book_name = book_name

        # 更新状态
        self.status_label.setText(f"正在加载知识库 {book_name} 的文章...")

        # 启用右侧面板的控件
        self.article_list.setEnabled(True)
        self.article_search_input.setEnabled(True)
        self.select_all_articles_btn.setEnabled(True)
        self.deselect_all_articles_btn.setEnabled(True)

        # 异步加载文章列表
        self.load_articles_worker = AsyncWorker(YuqueApi.get_book_docs, namespace)
        self.load_articles_worker.taskFinished.connect(lambda docs: self.display_articles(docs, book_name))
        self.load_articles_worker.taskError.connect(lambda err: self.handle_articles_error(err, book_name))
        self.load_articles_worker.start()

    def display_articles(self, articles, book_name):
        """显示文章列表"""
        try:
            self.article_list.clear()

            # 检查是否有错误信息
            if isinstance(articles, dict) and "error" in articles:
                error_msg = articles.get("message", "未知错误")
                error_item = QListWidgetItem(f"加载失败: {error_msg}")
                error_item.setFlags(Qt.NoItemFlags)
                error_item.setForeground(QColor("#dc3545"))
                self.article_list.addItem(error_item)

                # 更新状态
                self.status_label.setText(f"知识库 {book_name} 文章加载失败")
                if hasattr(self, 'log_handler'):
                    self.log_handler.emit_log(f"知识库 {book_name} 文章加载失败: {error_msg}")

                # 如果是登录过期，提示用户重新登录
                if articles.get("error") == "cookies_expired":
                    QMessageBox.warning(self, "登录已过期", "您的登录已过期，请重新登录")

                    # 切换到登录标签页
                    tabs = self.findChild(QTabWidget)
                    if tabs:
                        tabs.setCurrentIndex(0)

                return

            if not articles:
                empty_item = QListWidgetItem(f"知识库 {book_name} 没有文章")
                empty_item.setFlags(Qt.NoItemFlags)
                empty_item.setForeground(QColor("#6c757d"))
                self.article_list.addItem(empty_item)

                self.status_label.setText(f"知识库 {book_name} 没有文章")
                if hasattr(self, 'log_handler'):
                    self.log_handler.emit_log(f"知识库 {book_name} 没有文章")
                return

            # 按更新时间排序文章（如果有更新时间字段）
            try:
                sorted_articles = articles
                if len(articles) > 0 and isinstance(articles[0], dict):
                    # API返回的是字典列表
                    if all('updated_at' in doc for doc in articles):
                        sorted_articles = sorted(articles, key=lambda x: x.get('updated_at', ''), reverse=True)

                    for article in sorted_articles:
                        title = article.get('title', 'Untitled')
                        updated_at = article.get('updated_at', '')

                        # 创建列表项
                        item = QListWidgetItem(title)

                        # 设置提示文本
                        if updated_at:
                            try:
                                # 格式化更新时间为可读形式
                                updated_date = updated_at.split('T')[0]  # 简单处理，仅显示日期部分
                                item.setToolTip(f"标题: {title}\n更新时间: {updated_date}")
                            except:
                                item.setToolTip(f"标题: {title}")
                        else:
                            item.setToolTip(f"标题: {title}")

                        # 存储文章ID和其他必要信息
                        item.setData(Qt.UserRole, article.get('id', ''))
                        item.setData(Qt.UserRole + 1, article)  # 存储完整的文章对象

                        # 检查是否已经选择过该文章
                        if hasattr(self, '_current_answer') and hasattr(self._current_answer, 'selected_docs') and \
                                book_name in self._current_answer.selected_docs and \
                                article.get('id', '') in self._current_answer.selected_docs[book_name]:
                            item.setSelected(True)

                        self.article_list.addItem(item)
                else:
                    # API返回的是对象列表
                    if len(articles) > 0 and hasattr(articles[0], 'updated_at'):
                        sorted_articles = sorted(articles, key=lambda x: getattr(x, 'updated_at', ''), reverse=True)

                    for article in sorted_articles:
                        title = getattr(article, 'title', 'Untitled')
                        updated_at = getattr(article, 'updated_at', '')

                        # 创建列表项
                        item = QListWidgetItem(title)

                        # 设置提示文本
                        if updated_at:
                            try:
                                # 格式化更新时间为可读形式
                                updated_date = updated_at.split('T')[0]  # 简单处理，仅显示日期部分
                                item.setToolTip(f"标题: {title}\n更新时间: {updated_date}")
                            except:
                                item.setToolTip(f"标题: {title}")
                        else:
                            item.setToolTip(f"标题: {title}")

                        # 存储文章ID和其他必要信息
                        item.setData(Qt.UserRole, getattr(article, 'id', ''))
                        item.setData(Qt.UserRole + 1, article)  # 存储完整的文章对象

                        # 检查是否已经选择过该文章
                        if hasattr(self, '_current_answer') and hasattr(self._current_answer, 'selected_docs') and \
                                book_name in self._current_answer.selected_docs and \
                                getattr(article, 'id', '') in self._current_answer.selected_docs[book_name]:
                            item.setSelected(True)

                        self.article_list.addItem(item)
            except Exception as sorting_error:
                # 如果排序或处理文章过程中出错，显示原始列表
                if hasattr(self, 'log_handler'):
                    self.log_handler.emit_log(f"处理文章列表时出错: {str(sorting_error)}，显示未排序列表")
                self.article_list.clear()

                # 简单显示文章标题
                for article in articles:
                    try:
                        if isinstance(article, dict):
                            title = article.get('title', 'Untitled')
                            item = QListWidgetItem(title)
                            item.setData(Qt.UserRole, article.get('id', ''))
                        else:
                            title = getattr(article, 'title', 'Untitled')
                            item = QListWidgetItem(title)
                            item.setData(Qt.UserRole, getattr(article, 'id', ''))
                        self.article_list.addItem(item)
                    except:
                        # 跳过无法处理的文章
                        continue

            # 更新状态
            self.status_label.setText(f"知识库 {book_name} 共有 {len(articles)} 篇文章")
            if hasattr(self, 'log_handler'):
                self.log_handler.emit_log(f"知识库 {book_name} 共有 {len(articles)} 篇文章")
            self.update_article_selection()

        except Exception as e:
            # 捕获所有未处理的异常
            error_msg = str(e)
            self.article_list.clear()
            error_item = QListWidgetItem(f"显示文章列表出错: {error_msg}")
            error_item.setFlags(Qt.NoItemFlags)
            error_item.setForeground(QColor("#dc3545"))
            self.article_list.addItem(error_item)

            self.status_label.setText(f"显示文章列表出错")
            if hasattr(self, 'log_handler'):
                self.log_handler.emit_log(f"显示文章列表出错: {error_msg}")

    def handle_articles_error(self, error_msg, book_name):
        """处理获取文章列表错误"""
        self.article_list.clear()
        error_item = QListWidgetItem(f"加载失败: {error_msg}")
        error_item.setFlags(Qt.NoItemFlags)
        error_item.setForeground(QColor("#dc3545"))
        self.article_list.addItem(error_item)

        # 记录错误到日志
        if hasattr(self, 'log_handler'):
            self.log_handler.emit_log(f"获取知识库 {book_name} 文章列表失败: {error_msg}")
        self.status_label.setText(f"获取知识库 {book_name} 文章列表失败")

        # 检查是否为cookies过期问题
        if "cookies已过期" in str(error_msg):
            QMessageBox.warning(self, "登录已过期", "您的登录已过期，请重新登录")

            # 切换到登录标签页
            tabs = self.findChild(QTabWidget)
            if tabs:
                tabs.setCurrentIndex(0)

    def filter_articles(self, text):
        """根据输入过滤文章列表"""
        filter_text = text.lower()
        for i in range(self.article_list.count()):
            item = self.article_list.item(i)
            item.setHidden(filter_text not in item.text().lower())

    def select_all_articles(self):
        """全选当前显示的所有文章"""
        for i in range(self.article_list.count()):
            item = self.article_list.item(i)
            if not item.isHidden():  # 只选择可见项目
                item.setSelected(True)

    def deselect_all_articles(self):
        """取消选择当前知识库的所有文章"""
        for i in range(self.article_list.count()):
            self.article_list.item(i).setSelected(False)

    def update_article_selection(self):
        """更新选中的文章"""
        try:
            count = len(self.article_list.selectedItems())
            self.selected_article_count_label.setText(f"已选: {count}")

            # 如果有文章被选中，则创建或更新MutualAnswer对象来存储选中的文章
            if hasattr(self, 'current_book_name') and self.current_book_name:
                # 获取当前选中的所有文章ID
                selected_ids = []
                for item in self.article_list.selectedItems():
                    article_id = item.data(Qt.UserRole)
                    if article_id:
                        selected_ids.append(article_id)

                # 存储选择的文章ID
                if not hasattr(self, '_current_answer'):
                    self._current_answer = MutualAnswer(
                        toc_range=[],
                        skip=self.skip_local_checkbox.isChecked(),
                        line_break=self.keep_linebreak_checkbox.isChecked(),
                        download_range="selected"
                    )
                    self._current_answer.selected_docs = {}

                # 更新选中状态
                if selected_ids:
                    self._current_answer.selected_docs[self.current_book_name] = selected_ids
                    if hasattr(self, 'log_handler'):
                        self.log_handler.emit_log(f"已选择 {len(selected_ids)} 篇 {self.current_book_name} 的文章")
                elif self.current_book_name in self._current_answer.selected_docs:
                    # 如果没有选中任何文章，从已选字典中删除该知识库
                    del self._current_answer.selected_docs[self.current_book_name]
                    if hasattr(self, 'log_handler'):
                        self.log_handler.emit_log(f"已清除 {self.current_book_name} 的所有选择")

                # 计算并显示总共选择的文章数量
                if hasattr(self, '_current_answer') and hasattr(self._current_answer, 'selected_docs'):
                    total_selected = sum(len(ids) for ids in self._current_answer.selected_docs.values())
                    if total_selected > 0:
                        self.status_label.setText(f"总计已选: {total_selected} 篇文章")
                    else:
                        self.status_label.setText("未选择任何文章")
        except Exception as e:
            # 捕获任何可能的异常以防止崩溃
            error_msg = str(e)
            if hasattr(self, 'log_handler'):
                self.log_handler.emit_log(f"更新文章选择状态时出错: {error_msg}")
            self.status_label.setText("更新文章选择状态时出错")

    def select_all_books_in_dialog(self):
        """在对话框中全选所有知识库的文章"""
        if not hasattr(self, 'books_info') or not self.books_info:
            self.status_label.setText("没有可用的知识库")
            return

        self.status_label.setText("正在加载所有知识库的文章...")

        # 清空当前选择
        self.selected_articles = {}

        # 为每个知识库加载文章
        self.books_to_process = []
        for item in self.books_info:
            namespace = ""
            if hasattr(item, 'namespace') and item.namespace:
                namespace = item.namespace
            elif hasattr(item, 'user_login') and hasattr(item, 'slug'):
                namespace = f"{item.user_login}/{item.slug}"
            elif hasattr(item, 'user') and hasattr(item, 'slug'):
                if isinstance(item.user, dict) and 'login' in item.user:
                    namespace = f"{item.user['login']}/{item.slug}"

            if namespace:
                self.books_to_process.append((namespace, item.name))

        # 开始处理第一个知识库
        if self.books_to_process:
            self.current_book_index = 0
            self.process_next_book_for_all_selection()

    def process_next_book_for_all_selection(self):
        """处理下一个知识库的文章加载"""
        if self.current_book_index >= len(self.books_to_process):
            # 所有知识库处理完成
            self.status_label.setText(
                f"已选择所有知识库的文章，共 {sum(len(articles) for articles in self.selected_articles.values())} 篇")
            self.update_total_selected()
            return

        namespace, book_name = self.books_to_process[self.current_book_index]

        # 异步加载当前知识库的文章
        self.load_all_articles_worker = AsyncWorker(YuqueApi.get_book_docs, namespace)
        self.load_all_articles_worker.taskFinished.connect(
            lambda docs: self.handle_all_articles_loaded(docs, namespace, book_name))
        self.load_all_articles_worker.taskError.connect(
            lambda err: self.handle_all_articles_error(err, namespace, book_name))
        self.load_all_articles_worker.start()

    def handle_all_articles_loaded(self, docs, namespace, book_name):
        """处理全选时单个知识库文章加载完成"""
        if docs:
            # 将所有文章添加到选择列表
            self.selected_articles[namespace] = docs

        # 处理下一个知识库
        self.current_book_index += 1
        self.process_next_book_for_all_selection()

    def handle_all_articles_error(self, error, namespace, book_name):
        """处理全选时单个知识库文章加载错误"""
        Log.error(f"加载知识库 {book_name} 的文章时出错: {error}")

        # 继续处理下一个知识库
        self.current_book_index += 1
        self.process_next_book_for_all_selection()

    def handle_articles_error(self, error, book_name):
        """处理文章加载错误"""
        self.status_label.setText(f"加载知识库 {book_name} 的文章失败: {str(error)}")
        self.article_list.clear()

    def load_articles_for_book_dropdown(self, book_text):
        """根据下拉框选择加载文章列表"""
        if book_text == "请选择知识库..." or not book_text:
            self.article_list.clear()
            self.status_label.setText("请选择知识库")
            return

        # 获取当前选中项的索引
        current_index = self.book_dropdown.currentIndex()
        if current_index <= 0:  # 0是默认选项
            return

        # 获取namespace和书名
        namespace = self.book_dropdown.itemData(current_index, Qt.UserRole)
        book_name = self.book_dropdown.itemData(current_index, Qt.UserRole + 1)

        if not namespace:
            self.status_label.setText(f"知识库 {book_name} 缺少必要的命名空间信息")
            return

        # 更新当前知识库信息
        self.current_namespace = namespace
        self.current_book_name = book_name

        # 更新状态
        self.status_label.setText(f"正在加载知识库 {book_name} 的文章...")

        # 启用文章相关控件
        self.article_list.setEnabled(True)
        self.article_search_input.setEnabled(True)
        self.select_all_articles_btn.setEnabled(True)
        self.deselect_all_articles_btn.setEnabled(True)

        # 异步加载文章列表
        self.load_articles_worker = AsyncWorker(YuqueApi.get_book_docs, namespace)
        self.load_articles_worker.taskFinished.connect(lambda docs: self.display_articles(docs, book_name))
        self.load_articles_worker.taskError.connect(lambda err: self.handle_articles_error(err, book_name))
        self.load_articles_worker.start()

    def select_output_dir(self):
        """选择输出目录"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择输出目录",
            self.output_input.text() or os.path.expanduser("~")
        )

        if dir_path:
            self.output_input.setText(dir_path)
            GLOBAL_CONFIG.target_output_dir = dir_path

    def start_export(self):
        """开始导出知识库"""
        # 获取选中的知识库
        selected_items = self.book_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "错误", "请先选择要导出的知识库")
            return

        try:
            # 检查是否有选择的文章
            has_selected_articles = hasattr(self, '_current_answer') and hasattr(self._current_answer,
                                                                                 'selected_docs') and self._current_answer.selected_docs

            # 创建并配置MutualAnswer对象
            answer = MutualAnswer(
                toc_range=[],  # 稍后根据选择设置
                skip=self.skip_local_checkbox.isChecked(),
                line_break=self.keep_linebreak_checkbox.isChecked(),
                download_range="selected" if has_selected_articles else "all"  # 根据是否选择了具体文章来决定
            )

            # 设置知识库列表
            if has_selected_articles:
                # 使用已选择的文章
                answer.selected_docs = self._current_answer.selected_docs
                # 知识库列表应该是所有包含选中文章的知识库
                answer.toc_range = list(answer.selected_docs.keys())
            else:
                # 导出整个知识库
                answer.toc_range = [item.data(Qt.UserRole + 1) for item in selected_items]

            if not answer.toc_range:
                QMessageBox.warning(self, "错误", "无法确定选中的知识库")
                return

            # 计算总文章数量提示信息
            if has_selected_articles:
                total_articles = sum(len(ids) for ids in answer.selected_docs.values())
                export_info = f"{total_articles} 篇选定文章，来自 {len(answer.toc_range)} 个知识库"
            else:
                total_articles = 0  # 未知总数，会在导出过程中更新
                export_info = f"{len(answer.toc_range)} 个完整知识库"

            # 设置输出目录
            output_dir = self.output_input.text()
            if output_dir:
                GLOBAL_CONFIG.target_output_dir = output_dir

            # 设置调试模式
            debug_mode = self.enable_debug_checkbox.isChecked()
            Log.set_debug_mode(debug_mode)

            if debug_mode:
                try:
                    from src.libs.debug_logger import DebugLogger
                    # 确保初始化调试日志
                    DebugLogger.initialize()
                    self.log_handler.emit_log("调试模式已启用，详细日志将被记录到文件")

                    # 记录当前导出设置
                    DebugLogger.log_info(f"导出设置: {export_info}")
                    DebugLogger.log_info(f"跳过本地文件: {answer.skip}")
                    DebugLogger.log_info(f"保留语雀换行标识: {answer.line_break}")
                    DebugLogger.log_info(f"输出目录: {GLOBAL_CONFIG.target_output_dir}")
                except ImportError as e:
                    self.log_handler.emit_log(f"无法导入调试日志模块: {str(e)}")

            # 重置进度条
            self.progress_bar.setValue(0)
            self.progress_bar.setMaximum(total_articles if total_articles > 0 else 100)  # 如果未选定具体文章，先使用100作为最大值
            self.progress_bar.setFormat(f"准备导出: {export_info}")

            # 禁用UI元素
            self.export_button.setEnabled(False)
            self.export_button.setText("导出中...")
            self.book_list.setEnabled(False)
            self.skip_local_checkbox.setEnabled(False)
            self.keep_linebreak_checkbox.setEnabled(False)
            self.clean_button.setEnabled(False)
            self.article_list.setEnabled(False)
            self.article_search_input.setEnabled(False)
            self.select_all_articles_btn.setEnabled(False)
            self.deselect_all_articles_btn.setEnabled(False)

            # 启动导出线程
            self.export_worker = AsyncWorker(self.safe_export_task, answer)
            self.export_worker.taskFinished.connect(self.on_export_finished)
            self.export_worker.taskError.connect(self.on_export_error)
            self.export_worker.start()

            # 更新日志
            self.log_handler.emit_log(f"正在导出 {export_info}...")
        except Exception as e:
            error_msg = str(e)
            self.log_handler.emit_log(f"准备导出任务时出错: {error_msg}")
            QMessageBox.critical(self, "导出错误", f"准备导出任务时出错: {error_msg}")

    async def safe_export_task(self, answer):
        """安全执行导出任务，添加错误处理和恢复机制"""
        try:
            # 使用Scheduler执行下载任务
            result = await Scheduler._start_download_task(answer)
            return result
        except Exception as e:
            error_msg = str(e)
            Log.error(f"导出任务失败: {error_msg}")

            # 检查是否为cookies过期问题
            if "cookies已过期" in error_msg:
                return {"error": "cookies_expired", "message": "登录已过期，请重新登录"}

            # 其他错误直接返回错误信息
            return {"error": "export_failed", "message": f"导出失败: {error_msg}"}

    def on_export_finished(self, result):
        """导出完成后的回调"""
        # 启用UI元素
        self.export_button.setEnabled(True)
        self.export_button.setText("开始导出")
        self.book_list.setEnabled(True)
        self.skip_local_checkbox.setEnabled(True)
        self.keep_linebreak_checkbox.setEnabled(True)
        self.clean_button.setEnabled(True)

        # 启用文章面板控件
        self.article_list.setEnabled(True)
        self.article_search_input.setEnabled(True)
        self.select_all_articles_btn.setEnabled(True)
        self.deselect_all_articles_btn.setEnabled(True)

        # 检查是否有错误信息
        if isinstance(result, dict) and "error" in result:
            error_msg = result.get("message", "未知错误")
            self.log_handler.emit_log(f"导出出错: {error_msg}")

            # 进度条显示错误状态
            self.progress_bar.setFormat("导出出错")

            # 如果是登录过期，提示用户重新登录
            if result.get("error") == "cookies_expired":
                QMessageBox.warning(self, "登录已过期", "您的登录已过期，请重新登录")

                # 切换到登录标签页
                tabs = self.findChild(QTabWidget)
                if tabs:
                    tabs.setCurrentIndex(0)
            else:
                QMessageBox.critical(self, "导出错误", f"导出过程出错: {error_msg}")

            return

        # 更新进度条为完成状态
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.progress_bar.setFormat("导出完成! (100%)")

        # 记录到日志
        self.log_handler.emit_log("导出完成!")
        self.status_label.setText("导出完成!")

        # 检查是否需要下载图片
        if self.download_images_checkbox.isChecked():
            self.process_images_after_export()
        else:
            # 显示导出完成消息
            QMessageBox.information(self, "导出完成", "所有知识库导出完成！")

    def update_image_download_progress(self, downloaded, total):
        """更新图片下载进度（线程安全版本）"""
        if total > 0:
            progress = int((downloaded / total) * 100)
            # 使用QTimer.singleShot确保在主线程中更新UI
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._update_progress_ui(downloaded, total, progress))

    def _update_progress_ui(self, downloaded, total, progress):
        """在主线程中更新进度条UI"""
        self.progress_bar.setValue(downloaded)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setFormat(f"正在下载图片: {downloaded}/{total} ({progress}%)")

    def process_images_after_export(self):
        """导出完成后处理图片下载"""
        try:
            output_dir = self.output_input.text() or GLOBAL_CONFIG.target_output_dir

            # 更新进度条状态
            self.progress_bar.setFormat("正在扫描图片...")
            self.log_handler.emit_log("开始下载图片到本地...")

            # 查找所有Markdown文件
            md_files = []
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    if file.endswith('.md'):
                        md_files.append(os.path.join(root, file))

            if not md_files:
                self.log_handler.emit_log("未找到Markdown文件，跳过图片下载")
                QMessageBox.information(self, "导出完成", "所有知识库导出完成！\n未找到Markdown文件，跳过图片下载。")
                return

            # 创建多线程下载器
            downloader = ThreadedImageDownloader(
                max_workers=self.download_threads,
                progress_callback=self.update_image_download_progress
            )

            total_images = 0
            processed_files = 0

            self.log_handler.emit_log(
                f"找到 {len(md_files)} 个Markdown文件，使用 {self.download_threads} 个线程下载图片")

            # 处理每个Markdown文件
            for md_file in md_files:
                try:
                    # 使用多线程下载器和用户设置的参数
                    image_count = downloader.process_single_file(
                        md_file_path=md_file,
                        image_url_prefix=self.doc_image_prefix,
                        image_rename_mode=self.image_rename_mode,
                        image_file_prefix=self.image_file_prefix,
                        yuque_cdn_domain=self.yuque_cdn_domain
                    )
                    total_images += image_count
                    processed_files += 1

                    if image_count > 0:
                        self.log_handler.emit_log(f"处理文件 {os.path.basename(md_file)}，下载了 {image_count} 张图片")

                except Exception as e:
                    self.log_handler.emit_log(f"处理文件 {md_file} 时出错: {str(e)}")
                    continue

            # 更新进度条为完成状态
            self.progress_bar.setFormat("图片下载完成! (100%)")
            self.progress_bar.setValue(self.progress_bar.maximum())

            # 记录完成信息
            self.log_handler.emit_log(f"图片下载完成！共处理 {processed_files} 个文件，下载了 {total_images} 张图片")

            # 显示完成消息
            QMessageBox.information(self, "导出完成",
                                    f"所有知识库导出完成！\n\n图片下载统计：\n" +
                                    f"处理文件数：{processed_files}\n" +
                                    f"下载图片数：{total_images}\n" +
                                    f"下载线程数：{self.download_threads}")

        except Exception as e:
            error_msg = str(e)
            self.log_handler.emit_log(f"图片下载过程中出错: {error_msg}")
            QMessageBox.warning(self, "图片下载错误",
                                f"导出完成，但图片下载过程中出错：\n{error_msg}")

    def on_export_error(self, error_msg):
        """导出出错的回调"""
        # 启用UI元素
        self.export_button.setEnabled(True)
        self.export_button.setText("开始导出")
        self.book_list.setEnabled(True)
        self.skip_local_checkbox.setEnabled(True)
        self.keep_linebreak_checkbox.setEnabled(True)
        self.clean_button.setEnabled(True)
        self.article_list.setEnabled(True)
        self.article_search_input.setEnabled(True)
        self.select_all_articles_btn.setEnabled(True)
        self.deselect_all_articles_btn.setEnabled(True)

        # 进度条显示错误状态
        self.progress_bar.setFormat("导出出错")

        # 记录错误到日志
        self.log_handler.emit_log(f"导出出错: {error_msg}")

        # 检查是否为cookies过期问题
        if "cookies已过期" in error_msg:
            QMessageBox.warning(self, "登录已过期", "您的登录已过期，请重新登录")

            # 切换到登录标签页
            tabs = self.findChild(QTabWidget)
            if tabs:
                tabs.setCurrentIndex(0)
        else:
            QMessageBox.critical(self, "导出错误", f"导出过程出错: {error_msg}")

    def clean_cache(self):
        """清理缓存"""
        confirm = QMessageBox.question(
            self, "确认清理", "确定要清理本地缓存吗？\n注意：这将清除知识库和文章缓存，但保留登录信息。",
            QMessageBox.Yes | QMessageBox.No
        )

        if confirm == QMessageBox.Yes:
            try:
                from src.libs.tools import clean_cache
                if clean_cache():
                    # 清空知识库列表和文章列表
                    self.book_list.clear()
                    self.article_list.clear()

                    # 重新加载知识库信息
                    self.load_books()

                    QMessageBox.information(self, "清理完成", "缓存清理完成，知识库信息已重新加载")
                else:
                    QMessageBox.warning(self, "清理失败", "缓存清理失败或无缓存文件")
            except Exception as e:
                QMessageBox.critical(self, "清理出错", f"清理缓存出错: {str(e)}")

    def toggle_debug_mode(self, state):
        """处理调试模式切换"""
        debug_enabled = state == Qt.Checked
        Log.set_debug_mode(debug_enabled)

        if debug_enabled:
            try:
                from src.libs.debug_logger import DebugLogger
                # 确保调试日志记录器已初始化
                DebugLogger.initialize()
                self.log_handler.emit_log("调试模式已启用，详细日志将被记录到文件")
            except ImportError as e:
                self.log_handler.emit_log(f"无法导入调试日志模块: {str(e)}")
        else:
            self.log_handler.emit_log("调试模式已关闭")

    def filter_books(self, text):
        """根据输入过滤知识库列表"""
        filter_text = text.lower()
        for i in range(self.book_list.count()):
            item = self.book_list.item(i)
            # 去掉emoji前缀后再比较
            book_name = item.text()[2:].strip().lower()
            item.setHidden(filter_text not in book_name)

    def update_selected_count(self):
        """更新已选知识库数量"""
        count = len(self.book_list.selectedItems())
        self.selected_count_label.setText(f"已选: {count}")

        # 当选择多个知识库时，更新文章面板显示
        if count > 1:
            self.article_list.clear()
            hint_item = QListWidgetItem("已选择多个知识库，将导出所有知识库的全部文章")
            hint_item.setFlags(Qt.NoItemFlags)  # 不可选择
            hint_item.setForeground(QColor("#6c757d"))
            self.article_list.addItem(hint_item)
            self.selected_article_count_label.setText("已选: 全部")
        elif count == 0:
            # 如果没有选择知识库，清空文章列表
            self.article_list.clear()
            self.selected_article_count_label.setText("已选: 0")
        # 如果只选择了一个知识库，book_selection_changed会处理显示对应的文章

    def select_articles(self):
        """打开文章选择界面"""
        # 创建并显示文章选择对话框
        books_info = get_cache_books_info()
        if not books_info:
            QMessageBox.warning(self, "无法获取知识库信息", "请重新登录")
            return

        dialog = ArticleSelectionDialog(self, books_info)
        result = dialog.exec_()

        if result == QDialog.Accepted:
            selected_articles = dialog.get_selected_articles()
            if selected_articles:
                # 计算总选择数量
                total_articles = sum(len(ids) for book, ids in selected_articles.items())
                self.log_handler.emit_log(f"已选择 {total_articles} 篇文章进行下载")
                self.article_select_status.setText(f"已选择 {total_articles} 篇文章")

                # 存储选择的文章ID
                if not hasattr(self, '_current_answer'):
                    self._current_answer = MutualAnswer(
                        toc_range=[],
                        skip=self.skip_local_checkbox.isChecked(),
                        line_break=self.keep_linebreak_checkbox.isChecked(),
                        download_range="selected"
                    )
                self._current_answer.selected_docs = selected_articles

                # 如果用户选择了文章，自动将相应的知识库添加到选择列表中
                selected_book_names = list(selected_articles.keys())

                # 清除知识库列表上的当前选择
                self.book_list.clearSelection()

                # 选择包含所选文章的知识库
                for i in range(self.book_list.count()):
                    item = self.book_list.item(i)
                    book_name = item.text()[2:].strip()  # 去掉emoji前缀
                    if book_name in selected_book_names:
                        item.setSelected(True)

                # 更新已选知识库数量
                self.update_selected_count()
            else:
                self.log_handler.emit_log("未选择任何文章进行下载")
                self.article_select_status.setText("未选择任何文章")
                if hasattr(self, '_current_answer'):
                    self._current_answer.selected_docs = {}

    def clear_article_selection(self):
        """清除文章选择"""
        # 清空所有已选择的文章记录
        if hasattr(self, '_current_answer'):
            self._current_answer.selected_docs = {}

        # 清空当前显示的文章列表选择
        for i in range(self.article_list.count()):
            self.article_list.item(i).setSelected(False)

        # 更新选择计数
        self.update_article_selection()

        # 更新日志
        self.log_handler.emit_log("已清除所有文章选择")

    def filter_articles(self, text):
        """根据输入过滤文章列表"""
        filter_text = text.lower()
        for i in range(self.article_list.count()):
            item = self.article_list.item(i)
            item.setHidden(filter_text not in item.text().lower())

    def select_all_articles(self):
        """全选当前显示的所有文章"""
        for i in range(self.article_list.count()):
            item = self.article_list.item(i)
            if not item.isHidden():  # 只选择可见项目
                item.setSelected(True)

    def deselect_all_articles(self):
        """取消选择当前知识库的所有文章"""
        for i in range(self.article_list.count()):
            self.article_list.item(i).setSelected(False)

    def update_article_selection(self):
        """更新选中的文章"""
        count = len(self.article_list.selectedItems())
        self.selected_article_count_label.setText(f"已选: {count}")

        # 如果有文章被选中，则创建或更新MutualAnswer对象来存储选中的文章
        if hasattr(self, 'current_book_name') and self.current_book_name:
            # 获取当前选中的所有文章ID
            selected_ids = []
            for item in self.article_list.selectedItems():
                article_id = item.data(Qt.UserRole)
                if article_id:
                    selected_ids.append(article_id)

            # 存储选择的文章ID
            if not hasattr(self, '_current_answer'):
                self._current_answer = MutualAnswer(
                    toc_range=[],
                    skip=self.skip_local_checkbox.isChecked(),
                    line_break=self.keep_linebreak_checkbox.isChecked(),
                    download_range="selected"
                )
                self._current_answer.selected_docs = {}

            # 更新选中状态
            if selected_ids:
                self._current_answer.selected_docs[self.current_book_name] = selected_ids
                self.log_handler.emit_log(f"已选择 {len(selected_ids)} 篇 {self.current_book_name} 的文章")
            elif self.current_book_name in self._current_answer.selected_docs:
                # 如果没有选中任何文章，从已选字典中删除该知识库
                del self._current_answer.selected_docs[self.current_book_name]
                self.log_handler.emit_log(f"已清除 {self.current_book_name} 的所有选择")

            # 计算并显示总共选择的文章数量
            if hasattr(self, '_current_answer') and hasattr(self._current_answer, 'selected_docs'):
                total_selected = sum(len(ids) for ids in self._current_answer.selected_docs.values())
                if total_selected > 0:
                    self.status_label.setText(f"总计已选: {total_selected} 篇文章")
                else:
                    self.status_label.setText("未选择任何文章")

    def book_selection_changed(self):
        """当知识库选择改变时，加载相应的文章列表"""
        try:
            # 使用更健壮的文章加载方法
            self.load_articles_for_selected_books()
        except Exception as e:
            # 捕获所有异常，防止程序崩溃
            error_msg = str(e)
            self.status_label.setText(f"加载文章列表出错: {error_msg}")
            if hasattr(self, 'log_handler'):
                self.log_handler.emit_log(f"加载文章列表出错: {error_msg}")

            # 清空文章列表并显示错误
            self.article_list.clear()
            error_item = QListWidgetItem(f"加载失败: {error_msg}")
            error_item.setFlags(Qt.NoItemFlags)
            error_item.setForeground(QColor("#dc3545"))
            self.article_list.addItem(error_item)

    def select_all_books(self):
        """全选所有知识库"""
        self.book_list.selectAll()

    def deselect_all_books(self):
        """取消全选所有知识库"""
        self.book_list.clearSelection()

    def load_articles_for_selected_books(self):
        """为选中的知识库加载文章列表"""
        selected_items = self.book_list.selectedItems()

        if not selected_items:
            # 没有选中的知识库，清空文章列表
            self.article_list.clear()
            self.article_search_input.setEnabled(False)
            self.select_all_articles_btn.setEnabled(False)
            self.deselect_all_articles_btn.setEnabled(False)
            self.selected_article_count_label.setText("已选: 0")

            # 添加提示信息
            hint_item = QListWidgetItem("请从左侧选择一个知识库以加载文章列表")
            hint_item.setFlags(Qt.NoItemFlags)
            hint_item.setForeground(QColor("#6c757d"))
            self.article_list.addItem(hint_item)
            return

        # 启用文章相关控件
        self.article_search_input.setEnabled(True)
        self.select_all_articles_btn.setEnabled(True)
        self.deselect_all_articles_btn.setEnabled(True)

        # 如果只选中一个知识库，加载其文章列表
        if len(selected_items) == 1:
            item = selected_items[0]
            book_name = item.text()[2:].strip()  # 去掉emoji前缀
            namespace = item.data(Qt.UserRole)
            if not namespace:
                self.article_list.clear()
                error_item = QListWidgetItem("该知识库缺少必要的命名空间信息")
                error_item.setFlags(Qt.NoItemFlags)
                error_item.setForeground(QColor("#dc3545"))
                self.article_list.addItem(error_item)
                return

            self.load_articles_for_book(namespace, book_name)
        else:
            # 选中多个知识库，检查是否为全选
            total_books = self.book_list.count()
            selected_count = len(selected_items)

            if selected_count == total_books:
                # 全选状态，显示提示信息而不加载具体文章
                self.display_all_books_selected_message()
            else:
                # 部分选择，只显示已选择的知识库名称
                self.display_selected_books_only(selected_items)

    def display_selected_books_only(self, selected_items):
        """显示已选择的知识库名称，不显示具体文章"""
        self.article_list.clear()

        # 添加说明信息
        info_item = QListWidgetItem("已选择以下知识库（将导出所选知识库内的全部文章）:")
        info_item.setFlags(Qt.NoItemFlags)
        info_item.setForeground(QColor("#0d6efd"))
        info_item.setFont(QFont("Arial", 10, QFont.Bold))
        self.article_list.addItem(info_item)

        # 显示选中的知识库
        for item in selected_items:
            book_name = item.text()[2:].strip()  # 去掉emoji前缀
            book_item = QListWidgetItem(f"📚 {book_name}")
            book_item.setFlags(Qt.NoItemFlags)
            book_item.setForeground(QColor("#28a745"))
            self.article_list.addItem(book_item)

        # 添加提示信息
        tip_item = QListWidgetItem("\n提示: 导出时将包含所选知识库的全部文章")
        tip_item.setFlags(Qt.NoItemFlags)
        tip_item.setForeground(QColor("#6c757d"))
        self.article_list.addItem(tip_item)

        # 更新状态
        self.status_label.setText(f"已选择 {len(selected_items)} 个知识库")
        self.selected_article_count_label.setText("已选: 全部")
        self.log_handler.emit_log(f"已选择 {len(selected_items)} 个知识库，将导出全部文章")

        # 启用相关控件
        self.article_search_input.setEnabled(False)  # 禁用搜索，因为没有显示具体文章
        self.select_all_articles_btn.setEnabled(False)
        self.deselect_all_articles_btn.setEnabled(False)

    def display_all_books_selected_message(self):
        """显示全选知识库时的提示信息"""
        self.article_list.clear()

        # 添加提示信息
        info_item = QListWidgetItem("当前已全选知识库，将导出所有知识库的全部文章")
        info_item.setFlags(Qt.NoItemFlags)
        info_item.setForeground(QColor("#0d6efd"))
        info_item.setFont(QFont("Arial", 12, QFont.Bold))
        self.article_list.addItem(info_item)

        # 禁用文章相关控件
        self.article_search_input.setEnabled(False)
        self.select_all_articles_btn.setEnabled(False)
        self.deselect_all_articles_btn.setEnabled(False)

        # 更新状态标签
        total_books = self.book_list.count()
        self.selected_article_count_label.setText("已选: 全部")
        self.status_label.setText(f"已全选 {total_books} 个知识库，将导出所有文章")
        self.log_handler.emit_log(f"已全选 {total_books} 个知识库，将导出所有文章")

    def load_articles_for_multiple_books(self, selected_items):
        """为多个选中的知识库加载文章列表"""
        self.article_list.clear()

        # 显示加载提示
        loading_item = QListWidgetItem("正在加载多个知识库的文章列表...")
        loading_item.setFlags(Qt.NoItemFlags)
        loading_item.setForeground(QColor("#0d6efd"))
        self.article_list.addItem(loading_item)

        # 更新状态
        book_names = [item.text()[2:].strip() for item in selected_items]
        self.status_label.setText(f"正在加载 {len(book_names)} 个知识库的文章...")
        self.log_handler.emit_log(f"正在加载多个知识库的文章: {', '.join(book_names)}")

        # 启用文章面板的控件
        self.article_list.setEnabled(True)
        self.article_search_input.setEnabled(True)
        self.select_all_articles_btn.setEnabled(True)
        self.deselect_all_articles_btn.setEnabled(True)

        # 准备要加载的知识库信息
        books_to_load = []
        for item in selected_items:
            book_name = item.text()[2:].strip()
            namespace = item.data(Qt.UserRole)
            if namespace:
                books_to_load.append((namespace, book_name))

        # 异步加载多个知识库的文章列表
        self.load_multiple_articles_worker = AsyncWorker(self.safe_get_multiple_book_docs, books_to_load)
        self.load_multiple_articles_worker.taskFinished.connect(self.display_multiple_books_articles)
        self.load_multiple_articles_worker.taskError.connect(lambda err: self.handle_articles_error(err, "多个知识库"))
        self.load_multiple_articles_worker.start()

    async def safe_get_multiple_book_docs(self, books_to_load):
        """安全地获取多个知识库的文章列表"""
        from src.libs.tools import get_docs_cache, save_docs_cache

        all_articles = []

        for namespace, book_name in books_to_load:
            try:
                # 首先尝试从缓存获取
                cached_docs = get_docs_cache(namespace)
                if cached_docs:
                    Log.info(f"从缓存加载知识库 {book_name} 的文章列表")
                    # 为每篇文章添加知识库信息
                    for doc in cached_docs:
                        doc['book_name'] = book_name
                        doc['namespace'] = namespace
                    all_articles.extend(cached_docs)
                else:
                    # 缓存中没有数据，从API获取
                    docs = await YuqueApi.get_book_docs(namespace)
                    if docs:
                        # 保存到缓存
                        save_docs_cache(namespace, docs)
                        Log.info(f"已缓存知识库 {book_name} 的文章列表")
                        # 为每篇文章添加知识库信息
                        for doc in docs:
                            doc['book_name'] = book_name
                            doc['namespace'] = namespace
                        all_articles.extend(docs)
                    else:
                        Log.warn(f"知识库 {book_name} 没有获取到文章")

            except Exception as e:
                error_msg = str(e)
                Log.error(f"获取知识库 {book_name} 文章列表失败: {error_msg}")
                # 继续处理其他知识库，不因为一个失败而中断
                continue

        return all_articles

    def display_multiple_books_articles(self, all_articles):
        """显示多个知识库的文章列表"""
        try:
            self.article_list.clear()

            if not all_articles:
                no_articles_item = QListWidgetItem("所选知识库中没有找到文章")
                no_articles_item.setFlags(Qt.NoItemFlags)
                no_articles_item.setForeground(QColor("#6c757d"))
                self.article_list.addItem(no_articles_item)
                self.status_label.setText("没有找到文章")
                return

            # 按知识库分组显示文章
            books_articles = {}
            for article in all_articles:
                book_name = article.get('book_name', '未知知识库')
                if book_name not in books_articles:
                    books_articles[book_name] = []
                books_articles[book_name].append(article)

            total_count = 0
            for book_name, articles in books_articles.items():
                # 添加知识库标题
                book_header = QListWidgetItem(f"📚 {book_name} ({len(articles)}篇)")
                book_header.setFlags(Qt.NoItemFlags)
                book_header.setForeground(QColor("#0d6efd"))
                book_header.setFont(QFont("Arial", 10, QFont.Bold))
                self.article_list.addItem(book_header)

                # 添加该知识库的文章
                for article in articles:
                    title = article.get('title', '无标题')
                    slug = article.get('slug', '')
                    namespace = article.get('namespace', '')

                    item = QListWidgetItem(f"  📄 {title}")
                    item.setData(Qt.UserRole, {
                        'slug': slug,
                        'namespace': namespace,
                        'title': title,
                        'book_name': book_name
                    })
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    self.article_list.addItem(item)
                    total_count += 1

            # 更新状态
            self.status_label.setText(f"已加载 {len(books_articles)} 个知识库的 {total_count} 篇文章")
            self.selected_article_count_label.setText(f"已选: 0")
            self.log_handler.emit_log(f"成功加载 {len(books_articles)} 个知识库的 {total_count} 篇文章")

        except Exception as e:
            error_msg = str(e)
            self.article_list.clear()
            error_item = QListWidgetItem(f"显示文章列表出错: {error_msg}")
            error_item.setFlags(Qt.NoItemFlags)
            error_item.setForeground(QColor("#dc3545"))
            self.article_list.addItem(error_item)

            self.status_label.setText(f"显示文章列表出错")
            self.log_handler.emit_log(f"显示文章列表出错: {error_msg}")

    def load_articles_for_book(self, namespace, book_name):
        """加载指定知识库的文章列表"""
        # 清空文章列表
        self.article_list.clear()

        # 显示加载提示
        loading_item = QListWidgetItem("正在加载文章列表...")
        loading_item.setFlags(Qt.NoItemFlags)
        loading_item.setForeground(QColor("#0d6efd"))
        self.article_list.addItem(loading_item)

        # 更新当前知识库信息
        self.current_namespace = namespace
        self.current_book_name = book_name

        # 更新状态
        self.status_label.setText(f"正在加载知识库 {book_name} 的文章...")
        self.log_handler.emit_log(f"正在加载知识库 {book_name} 的文章...")

        # 启用文章面板的控件
        self.article_list.setEnabled(True)
        self.article_search_input.setEnabled(True)
        self.select_all_articles_btn.setEnabled(True)
        self.deselect_all_articles_btn.setEnabled(True)

        # 异步加载文章列表
        self.load_articles_worker = AsyncWorker(self.safe_get_book_docs, namespace)
        self.load_articles_worker.taskFinished.connect(lambda docs: self.display_articles(docs, book_name))
        self.load_articles_worker.taskError.connect(lambda err: self.handle_articles_error(err, book_name))
        self.load_articles_worker.start()

    async def safe_get_book_docs(self, namespace):
        """安全地获取知识库文章列表，添加重试和错误处理，支持缓存"""
        from src.libs.tools import get_docs_cache, save_docs_cache

        # 首先尝试从缓存获取
        cached_docs = get_docs_cache(namespace)
        if cached_docs:
            Log.info(f"从缓存加载知识库 {namespace} 的文章列表")
            return cached_docs

        # 缓存中没有数据，从API获取
        max_retries = 3
        retry_delay = 1.0

        for attempt in range(max_retries):
            try:
                # 使用YuqueApi获取文档列表
                docs = await YuqueApi.get_book_docs(namespace)
                if docs:
                    # 保存到缓存
                    save_docs_cache(namespace, docs)
                    Log.info(f"已缓存知识库 {namespace} 的文章列表")
                    return docs

                # 如果没有获取到文档，但没有抛出异常，尝试重试
                Log.warn(f"未获取到文档，将在 {retry_delay} 秒后重试 (尝试 {attempt + 1}/{max_retries})")
                await asyncio.sleep(retry_delay)
                retry_delay *= 1.5  # 增加延迟时间

            except Exception as e:
                error_msg = str(e)
                Log.error(f"获取文档列表失败: {error_msg}")

                # 检查是否为cookies过期问题
                if "cookies已过期" in error_msg:
                    return {"error": "cookies_expired", "message": "登录已过期，请重新登录"}

                # 检查是否为网络问题
                if "ClientConnectorError" in error_msg or "TimeoutError" in error_msg or "ConnectionResetError" in error_msg:
                    Log.warn(f"网络连接问题，将在 {retry_delay} 秒后重试 (尝试 {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
                    continue

                # 对于其他类型的错误，如果不是最后一次尝试，继续重试
                if attempt < max_retries - 1:
                    Log.warn(f"发生错误，将在 {retry_delay} 秒后重试 (尝试 {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 1.5
                    continue
                else:
                    # 最后一次尝试失败，返回错误信息
                    return {"error": "fetch_failed", "message": f"获取文档列表失败: {error_msg}"}

        # 所有重试都失败
        return {"error": "all_retries_failed", "message": "多次尝试获取文档列表均失败"}

    def display_articles(self, articles, book_name):
        """显示文章列表"""
        try:
            self.article_list.clear()

            # 检查是否有错误信息
            if isinstance(articles, dict) and "error" in articles:
                error_msg = articles.get("message", "未知错误")
                error_item = QListWidgetItem(f"加载失败: {error_msg}")
                error_item.setFlags(Qt.NoItemFlags)
                error_item.setForeground(QColor("#dc3545"))
                self.article_list.addItem(error_item)

                # 更新状态
                self.status_label.setText(f"知识库 {book_name} 文章加载失败")
                if hasattr(self, 'log_handler'):
                    self.log_handler.emit_log(f"知识库 {book_name} 文章加载失败: {error_msg}")

                # 如果是登录过期，提示用户重新登录
                if articles.get("error") == "cookies_expired":
                    QMessageBox.warning(self, "登录已过期", "您的登录已过期，请重新登录")

                    # 切换到登录标签页
                    tabs = self.findChild(QTabWidget)
                    if tabs:
                        tabs.setCurrentIndex(0)

                return

            if not articles:
                empty_item = QListWidgetItem(f"知识库 {book_name} 没有文章")
                empty_item.setFlags(Qt.NoItemFlags)
                empty_item.setForeground(QColor("#6c757d"))
                self.article_list.addItem(empty_item)

                self.status_label.setText(f"知识库 {book_name} 没有文章")
                if hasattr(self, 'log_handler'):
                    self.log_handler.emit_log(f"知识库 {book_name} 没有文章")
                return

            # 按更新时间排序文章（如果有更新时间字段）
            try:
                sorted_articles = articles
                if len(articles) > 0 and isinstance(articles[0], dict):
                    # API返回的是字典列表
                    if all('updated_at' in doc for doc in articles):
                        sorted_articles = sorted(articles, key=lambda x: x.get('updated_at', ''), reverse=True)

                    for article in sorted_articles:
                        title = article.get('title', 'Untitled')
                        updated_at = article.get('updated_at', '')

                        # 创建列表项
                        item = QListWidgetItem(title)

                        # 设置提示文本
                        if updated_at:
                            try:
                                # 格式化更新时间为可读形式
                                updated_date = updated_at.split('T')[0]  # 简单处理，仅显示日期部分
                                item.setToolTip(f"标题: {title}\n更新时间: {updated_date}")
                            except:
                                item.setToolTip(f"标题: {title}")
                        else:
                            item.setToolTip(f"标题: {title}")

                        # 存储文章ID和其他必要信息
                        item.setData(Qt.UserRole, article.get('id', ''))
                        item.setData(Qt.UserRole + 1, article)  # 存储完整的文章对象

                        # 检查是否已经选择过该文章
                        if hasattr(self, '_current_answer') and hasattr(self._current_answer, 'selected_docs') and \
                                book_name in self._current_answer.selected_docs and \
                                article.get('id', '') in self._current_answer.selected_docs[book_name]:
                            item.setSelected(True)

                        self.article_list.addItem(item)
                else:
                    # API返回的是对象列表
                    if len(articles) > 0 and hasattr(articles[0], 'updated_at'):
                        sorted_articles = sorted(articles, key=lambda x: getattr(x, 'updated_at', ''), reverse=True)

                    for article in sorted_articles:
                        title = getattr(article, 'title', 'Untitled')
                        updated_at = getattr(article, 'updated_at', '')

                        # 创建列表项
                        item = QListWidgetItem(title)

                        # 设置提示文本
                        if updated_at:
                            try:
                                # 格式化更新时间为可读形式
                                updated_date = updated_at.split('T')[0]  # 简单处理，仅显示日期部分
                                item.setToolTip(f"标题: {title}\n更新时间: {updated_date}")
                            except:
                                item.setToolTip(f"标题: {title}")
                        else:
                            item.setToolTip(f"标题: {title}")

                        # 存储文章ID和其他必要信息
                        item.setData(Qt.UserRole, getattr(article, 'id', ''))
                        item.setData(Qt.UserRole + 1, article)  # 存储完整的文章对象

                        # 检查是否已经选择过该文章
                        if hasattr(self, '_current_answer') and hasattr(self._current_answer, 'selected_docs') and \
                                book_name in self._current_answer.selected_docs and \
                                getattr(article, 'id', '') in self._current_answer.selected_docs[book_name]:
                            item.setSelected(True)

                        self.article_list.addItem(item)
            except Exception as sorting_error:
                # 如果排序或处理文章过程中出错，显示原始列表
                if hasattr(self, 'log_handler'):
                    self.log_handler.emit_log(f"处理文章列表时出错: {str(sorting_error)}，显示未排序列表")
                self.article_list.clear()

                # 简单显示文章标题
                for article in articles:
                    try:
                        if isinstance(article, dict):
                            title = article.get('title', 'Untitled')
                            item = QListWidgetItem(title)
                            item.setData(Qt.UserRole, article.get('id', ''))
                        else:
                            title = getattr(article, 'title', 'Untitled')
                            item = QListWidgetItem(title)
                            item.setData(Qt.UserRole, getattr(article, 'id', ''))
                        self.article_list.addItem(item)
                    except:
                        # 跳过无法处理的文章
                        continue

            # 更新状态
            self.status_label.setText(f"知识库 {book_name} 共有 {len(articles)} 篇文章")
            if hasattr(self, 'log_handler'):
                self.log_handler.emit_log(f"知识库 {book_name} 共有 {len(articles)} 篇文章")
            self.update_article_selection()

        except Exception as e:
            # 捕获所有未处理的异常
            error_msg = str(e)
            self.article_list.clear()
            error_item = QListWidgetItem(f"显示文章列表出错: {error_msg}")
            error_item.setFlags(Qt.NoItemFlags)
            error_item.setForeground(QColor("#dc3545"))
            self.article_list.addItem(error_item)

            self.status_label.setText(f"显示文章列表出错")
            if hasattr(self, 'log_handler'):
                self.log_handler.emit_log(f"显示文章列表出错: {error_msg}")


def excepthook(exc_type, exc_value, exc_traceback):
    """Global exception handler to log unhandled exceptions"""
    import traceback

    # Format the exception and traceback
    exception_text = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))

    # Log to stderr and a file
    sys.stderr.write(f"Unhandled exception: {exception_text}\n")

    # Try to write to a log file
    try:
        log_dir = os.path.join(os.path.expanduser("~"), ".yuque_export")
        os.makedirs(log_dir, exist_ok=True)
        crash_log_file = os.path.join(log_dir, "crash_log.txt")

        with open(crash_log_file, "a", encoding="utf-8") as f:
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"\n[{timestamp}] Unhandled exception:\n{exception_text}\n")
    except:
        pass  # Don't crash the exception handler if file writing fails

    # Show a message box with the error if QApplication exists
    try:
        if QApplication.instance():
            QMessageBox.critical(None, "程序错误",
                                 f"程序发生错误，请联系开发者并提供以下信息：\n\n{str(exc_value)}\n\n"
                                 f"详细错误日志已保存到: {crash_log_file}")
    except:
        pass  # If showing the dialog fails, at least we logged the error


def main():
    # Install the global exception handler
    sys.excepthook = excepthook

    # 允许在高DPI屏幕上正确缩放
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    try:
        # Create Qt application
        app = QApplication(sys.argv)

        # Create and show the main window
        window = YuqueGUI()
        window.show()

        # Start the event loop
        sys.exit(app.exec_())
    except Exception as e:
        # If we can't even start the application, show the error
        import traceback
        Log.error(f"启动失败: {str(e)}\n{traceback.format_exc()}")

        # Try to show a message box if possible
        try:
            if QApplication.instance():
                QMessageBox.critical(None, "启动失败", f"程序启动失败: {str(e)}")
        except:
            pass


# 添加程序入口点以支持PyInstaller打包
if __name__ == "__main__":
    # 确保相对路径在打包后仍然有效
    if getattr(sys, 'frozen', False):
        # 打包后的情况
        os.chdir(os.path.dirname(sys.executable))

    main()

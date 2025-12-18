import asyncio
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QGroupBox, QHBoxLayout, 
    QComboBox, QPushButton, QLineEdit, QListWidget, QListWidgetItem, 
    QMessageBox, QTabWidget
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont

from src.core.yuque import YuqueApi
from src.libs.tools import get_docs_cache, save_docs_cache
from src.libs.constants import MutualAnswer
from src.libs.log import Log
from utils import AsyncWorker

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
                return

            if not articles:
                empty_item = QListWidgetItem(f"知识库 {book_name} 没有文章")
                empty_item.setFlags(Qt.NoItemFlags)
                empty_item.setForeground(QColor("#6c757d"))
                self.article_list.addItem(empty_item)
                return

            # 按更新时间排序文章
            sorted_articles = articles
            if len(articles) > 0 and isinstance(articles[0], dict):
                 if all('updated_at' in doc for doc in articles):
                    sorted_articles = sorted(articles, key=lambda x: x.get('updated_at', ''), reverse=True)

            for article in sorted_articles:
                if isinstance(article, dict):
                    title = article.get('title', 'Untitled')
                    article_id = article.get('id', '')
                else:
                    title = getattr(article, 'title', 'Untitled')
                    article_id = getattr(article, 'id', '')
                
                item = QListWidgetItem(title)
                item.setData(Qt.UserRole, article_id)
                item.setData(Qt.UserRole + 1, article)

                # 检查是否已经选择过该文章
                if self.current_book_name in self.selected_articles and \
                        article_id in self.selected_articles[self.current_book_name]:
                    item.setSelected(True)

                self.article_list.addItem(item)

            # 更新状态
            self.status_label.setText(f"知识库 {book_name} 共有 {len(articles)} 篇文章")
            self.update_article_selection()

        except Exception as e:
            error_msg = str(e)
            self.article_list.clear()
            error_item = QListWidgetItem(f"显示文章列表出错: {error_msg}")
            error_item.setFlags(Qt.NoItemFlags)
            error_item.setForeground(QColor("#dc3545"))
            self.article_list.addItem(error_item)

    def handle_articles_error(self, error_msg, book_name):
        """处理获取文章列表错误"""
        self.article_list.clear()
        error_item = QListWidgetItem(f"加载失败: {error_msg}")
        error_item.setFlags(Qt.NoItemFlags)
        error_item.setForeground(QColor("#dc3545"))
        self.article_list.addItem(error_item)
        self.status_label.setText(f"获取知识库 {book_name} 文章列表失败")

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
            if not item.isHidden():
                item.setSelected(True)

    def deselect_all_articles(self):
        """取消选择当前知识库的所有文章"""
        for i in range(self.article_list.count()):
            self.article_list.item(i).setSelected(False)

    def update_article_selection(self):
        """更新选中的文章"""
        count = len(self.article_list.selectedItems())
        self.selected_article_count_label.setText(f"已选: {count}")

        if self.current_book_name:
            selected_ids = []
            for item in self.article_list.selectedItems():
                article_id = item.data(Qt.UserRole)
                if article_id:
                    selected_ids.append(article_id)
            
            if selected_ids:
                self.selected_articles[self.current_book_name] = selected_ids
            elif self.current_book_name in self.selected_articles:
                del self.selected_articles[self.current_book_name]
            
            self.update_total_selected()

    def update_total_selected(self):
        """更新总共选中的文章数量"""
        total = sum(len(ids) for ids in self.selected_articles.values())
        self.total_selected_label.setText(f"总计已选: {total} 篇文章")

    def clear_all_selections(self):
        """清除所有选择"""
        self.selected_articles = {}
        self.article_list.clearSelection()
        self.update_total_selected()
        self.status_label.setText("已清除所有选择")

    def get_selected_articles(self):
        """获取选中的文章字典"""
        return self.selected_articles

    def select_all_books_in_dialog(self):
        """在对话框中全选所有知识库的文章"""
        if not hasattr(self, 'books_info') or not self.books_info:
            self.status_label.setText("没有可用的知识库")
            return

        self.status_label.setText("正在加载所有知识库的文章...")
        self.selected_articles = {}
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

        if self.books_to_process:
            self.current_book_index = 0
            self.process_next_book_for_all_selection()

    def process_next_book_for_all_selection(self):
        """处理下一个知识库的文章加载"""
        if self.current_book_index >= len(self.books_to_process):
            self.status_label.setText(
                f"已选择所有知识库的文章，共 {sum(len(articles) for articles in self.selected_articles.values())} 篇")
            self.update_total_selected()
            return

        namespace, book_name = self.books_to_process[self.current_book_index]
        self.load_all_articles_worker = AsyncWorker(YuqueApi.get_book_docs, namespace)
        self.load_all_articles_worker.taskFinished.connect(
            lambda docs: self.handle_all_articles_loaded(docs, namespace, book_name))
        self.load_all_articles_worker.taskError.connect(
            lambda err: self.handle_all_articles_error(err, namespace, book_name))
        self.load_all_articles_worker.start()

    def handle_all_articles_loaded(self, docs, namespace, book_name):
        if docs:
            self.selected_articles[namespace] = docs
        self.current_book_index += 1
        self.process_next_book_for_all_selection()

    def handle_all_articles_error(self, error, namespace, book_name):
        Log.error(f"加载知识库 {book_name} 的文章时出错: {error}")
        self.current_book_index += 1
        self.process_next_book_for_all_selection()


class ArticleManagerMixin:
    def select_articles(self):
        """打开文章选择界面"""
        from src.libs.tools import get_cache_books_info
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
                # self.article_select_status.setText(f"已选择 {total_articles} 篇文章") # This might not exist in main window if not created

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
                # self.article_select_status.setText("未选择任何文章")
                if hasattr(self, '_current_answer'):
                    self._current_answer.selected_docs = {}

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

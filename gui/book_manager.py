from PyQt5.QtWidgets import QMessageBox, QListWidgetItem
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from src.core.yuque import YuqueApi
from src.libs.tools import get_cache_books_info
from utils import AsyncWorker

class BookManagerMixin:
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

    def select_all_books(self):
        """全选所有知识库"""
        self.book_list.selectAll()
        self.update_selected_count()

    def deselect_all_books(self):
        """取消全选所有知识库"""
        self.book_list.clearSelection()
        self.update_selected_count()

    def book_selection_changed(self):
        """当知识库选择改变时，加载相应的文章列表"""
        try:
            # 更新已选知识库数量
            self.update_selected_count()
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
            # 更新已选数量（即使出错）
            self.update_selected_count()
            error_item = QListWidgetItem(f"加载失败: {error_msg}")
            error_item.setFlags(Qt.NoItemFlags)
            error_item.setForeground(QColor("#dc3545"))
            self.article_list.addItem(error_item)

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

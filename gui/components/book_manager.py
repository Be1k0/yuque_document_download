from qasync import asyncSlot
from PyQt6.QtWidgets import QMessageBox, QListWidgetItem, QTreeWidgetItem
from PyQt6.QtCore import Qt

class BookManagerMixin:
    """知识库管理器类

    提供一个界面让用户选择知识库，并加载文章列表。
    """
    @property
    def book_controller(self):
        """获取 BookController 实例，使用懒加载方式"""
        if not hasattr(self, '_book_controller'):
            from gui.controllers.book_controller import BookController
            self._book_controller = BookController()
        return self._book_controller

    @asyncSlot()
    async def load_books(self):
        """加载知识库列表"""
        self.book_list.clear()
        self.progress_label.setText("正在加载知识库列表...")

        # 使用 controller 异步获取数据
        books_info = await self.book_controller.get_books()

        if books_info:
            self.display_books(books_info)
        else:
            QMessageBox.warning(self, "加载失败", "无法获取知识库列表")
            self.progress_label.setText("加载知识库失败")

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
            list_item = QListWidgetItem(f"📚 {item.name}")
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

            list_item.setData(Qt.ItemDataRole.UserRole, namespace)
            list_item.setData(Qt.ItemDataRole.UserRole + 1, item.name)
            self.book_list.addItem(list_item)

        # 再添加团队知识库
        for item in other_books:
            list_item = QListWidgetItem(f"📚 {item.name}")
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

            list_item.setData(Qt.ItemDataRole.UserRole, namespace)
            list_item.setData(Qt.ItemDataRole.UserRole + 1, item.name)
            self.book_list.addItem(list_item)

        # 记录到日志中
        self.progress_bar.setValue(0)

        # 首次加载完成后显示默认提示
        self.article_list.clear()
        hint_item = QTreeWidgetItem(self.article_list, ["请从左侧选择一个知识库以加载文章列表"])
        hint_item.setFlags(Qt.ItemFlag.NoItemFlags)

        # 重置文章选择状态
        self.selected_article_count_label.setText("已选: 0")
        self.update_selected_count()

        # 重新连接知识库选择变化的信号
        self.book_list.itemSelectionChanged.connect(self.book_selection_changed)

        # 如果有搜索文本，应用过滤
        if hasattr(self, 'search_input') and self.search_input.text():
            self.filter_books(self.search_input.text())

    def filter_books(self, text):
        """根据输入过滤知识库列表
        
        Args:
            text: 输入的过滤文本
        """
        filter_text = text.lower()
        for i in range(self.book_list.count()):
            item = self.book_list.item(i)
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
            self.update_selected_count()
            self.load_articles_for_selected_books()
        except Exception as e:
            error_msg = str(e)
            self.status_label.setText(f"加载文章列表出错: {error_msg}")
            if hasattr(self, 'log_handler'):
                self.log_handler.emit_log(f"加载文章列表出错: {error_msg}")

            self.article_list.clear()
            self.update_selected_count()
            error_item = QTreeWidgetItem(self.article_list, [f"加载失败: {error_msg}"])
            error_item.setFlags(Qt.ItemFlag.NoItemFlags)

    def update_selected_count(self):
        """更新已选知识库数量"""
        count = len(self.book_list.selectedItems())
        self.selected_count_label.setText(f"已选: {count}")

        if count > 1:
            self.article_list.clear()
            hint_item = QTreeWidgetItem(self.article_list, ["已选择多个知识库，将导出所有知识库的全部文章"])
            hint_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.selected_article_count_label.setText("已选: 全部")
        elif count == 0:
            self.article_list.clear()
            self.selected_article_count_label.setText("已选: 0")
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QGroupBox, QHBoxLayout, 
    QComboBox, QPushButton, QLineEdit,
    QMessageBox, QAbstractItemView, QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator
)
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QCursor, QIcon
from PyQt6.QtWidgets import QStyleOptionViewItem
from src.libs.log import Log
from src.libs.constants import MutualAnswer
from src.libs.debug_logger import DebugLogger
from src.libs.tools import resolve_book_namespace
from src.ui.font_utils import stabilize_combo_box_font
from qasync import asyncSlot
from gui.controllers.article_controller import ArticleController
from src.ui.theme_manager import THEME_MANAGER
from utils import static_resource_path

class ArticleTreeWidget(QTreeWidget):
    """文章树控件类
    
    用于展示文章列表，并实现父子节点的级联选中。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setAnimated(True)
        self.setExpandsOnDoubleClick(False)
        self.setMouseTracking(True)
        self.itemClicked.connect(self._on_item_clicked)

    def drawRow(self, painter: QPainter, option: QStyleOptionViewItem, index):
        """自定义绘制行，添加选中和悬停的背景效果
        
        Args:
            painter: 画笔对象
            option: 选项对象
            index: 行索引
        """
        is_selected = self.selectionModel().isSelected(index)
        
        # 判断是否悬停
        pos = self.viewport().mapFromGlobal(QCursor.pos())
        is_hovered = (self.indexAt(pos) == index)

        if is_selected or is_hovered:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            if is_selected:
                # 浅蓝色透明背景和科技蓝实线边框
                bg_hex = THEME_MANAGER.get_color("list_selected", "#2e86c1")
                bg_color = QColor(bg_hex)
                border_color = QColor(bg_hex)
                bg_color.setAlphaF(0.15)  
                painter.setPen(QPen(border_color, 1))
            else:
                # 悬停灰底
                bg_hex = THEME_MANAGER.get_color("list_hover", "#eaecee")
                bg_color = QColor(bg_hex)
                painter.setPen(Qt.PenStyle.NoPen)

            painter.setBrush(QBrush(bg_color))
            rect = QRect(0, option.rect.y(), self.viewport().width(), option.rect.height())
            
            # 绘制圆角矩形
            margin_x = 4
            margin_y = 2
            draw_rect = rect.adjusted(margin_x, margin_y, -margin_x, -margin_y)
            
            painter.drawRoundedRect(draw_rect, 6, 6)
            painter.restore()

        # 调用父类方法绘制行
        super().drawRow(painter, option, index)

    def _on_item_clicked(self, item):
        """处理单击操作，自动选中/取消选中所有子节点
        
        Args:
            item: 被点击的项
            column: 列索引
        """
        is_selected = item.isSelected()
        
        def update_children_selection(parent_item, selected):
            """递归更新子节点的选中状态
            Args:
                parent_item: 父节点项
                selected: 是否选中
            """
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                child.setSelected(selected)
                update_children_selection(child, selected)
                
        update_children_selection(item, is_selected)


def get_article_icon(item_type: str, item=None):
    doc_type = ''
    if item and isinstance(item, dict):
        doc_type = item.get('type', '').upper()
    elif hasattr(item, 'type'):
        doc_type = getattr(item, 'type', '').upper()
    
    if item_type == 'TITLE':
        return QIcon(static_resource_path("src/ui/themes/resources/icons/folder.svg"))
    elif doc_type == 'SHEET':
        return QIcon(static_resource_path("src/ui/themes/resources/icons/yuque-sheet.svg"))
    elif doc_type == 'TABLE' or doc_type == 'LAKETABLE':
        return QIcon(static_resource_path("src/ui/themes/resources/icons/yuque-table.svg"))
    elif doc_type == 'BOARD':
        return QIcon(static_resource_path("src/ui/themes/resources/icons/yuque-board.svg"))
    else:
        return QIcon(static_resource_path("src/ui/themes/resources/icons/yuque-doc.svg"))

class ArticleSelectionDialog(QDialog):
    """文章选择对话框

    用于选择要下载的文章。
    """
    def __init__(self, parent=None, books_info=None, controller=None):
        super().__init__(parent)
        self.books_info = books_info or []
        self.controller = controller or ArticleController()
        self.selected_articles = {}
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

        # 创建主内容区域
        content_layout = QVBoxLayout()

        # 文章列表区域
        main_panel = QGroupBox("文章列表")
        main_layout = QVBoxLayout(main_panel)

        # 知识库选择区域
        book_selection_layout = QHBoxLayout()
        book_selection_label = QLabel("选择知识库:")
        self.book_dropdown = QComboBox()
        self.book_dropdown.setMinimumWidth(200)
        stabilize_combo_box_font(self.book_dropdown)
        self.book_dropdown.currentTextChanged.connect(self.load_articles_for_book_dropdown)

        # 全选知识库按钮
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
        self.article_list = ArticleTreeWidget()
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

        book_icon = QIcon(static_resource_path("src/ui/themes/resources/icons/yuque-book.svg"))
        # 先添加个人知识库
        for item in owner_books:
            display_name = item.name
            namespace = resolve_book_namespace(item)

            self.book_dropdown.addItem(book_icon, display_name)

            # 存储namespace和原始名称到下拉框项的数据中
            index = self.book_dropdown.count() - 1
            self.book_dropdown.setItemData(index, namespace, Qt.ItemDataRole.UserRole)
            self.book_dropdown.setItemData(index, item.name, Qt.ItemDataRole.UserRole + 1)

        # 再添加团队知识库
        for item in other_books:
            display_name = item.name
            namespace = resolve_book_namespace(item)

            self.book_dropdown.addItem(display_name)

            # 存储namespace和原始名称到下拉框项的数据中
            index = self.book_dropdown.count() - 1
            self.book_dropdown.setItemData(index, namespace, Qt.ItemDataRole.UserRole)
            self.book_dropdown.setItemData(index, item.name, Qt.ItemDataRole.UserRole + 1)

    @asyncSlot()
    async def load_articles_for_book_dropdown(self, book_text):
        """根据下拉框选择加载文章列表
        
        Args:
            book_text: 下拉框选择的文本
        """
        if book_text == "请选择知识库..." or not book_text:
            self.article_list.clear()
            self.status_label.setText("请选择知识库")
            return

        # 获取当前选中项的索引
        current_index = self.book_dropdown.currentIndex()
        if current_index <= 0:
            return

        # 获取namespace和书名
        namespace = self.book_dropdown.itemData(current_index, Qt.ItemDataRole.UserRole)
        book_name = self.book_dropdown.itemData(current_index, Qt.ItemDataRole.UserRole + 1)

        if not namespace:
            self.status_label.setText(f"知识库 {book_name} 缺少必要的命名空间信息")
            return

        # 更新当前知识库信息
        self.current_namespace = namespace
        self.current_book_name = book_name
        Log.info(f"对话框加载文章: {book_name} -> {namespace}")

        # 更新状态
        self.status_label.setText(f"正在加载知识库 {book_name} 的文章...")

        # 启用文章相关控件
        self.article_list.setEnabled(True)
        self.article_search_input.setEnabled(True)
        self.select_all_articles_btn.setEnabled(True)
        self.deselect_all_articles_btn.setEnabled(True)

        # 异步加载文章列表
        docs = await self.controller.get_articles(namespace)
        self.display_articles(docs, book_name)

    def display_articles(self, articles, book_name):
        """显示文章列表
        
        Args:
            articles: 文章列表
            book_name: 知识库名称
        """
        try:
            self.article_list.clear()

            # 检查是否有错误信息
            if isinstance(articles, dict) and "error" in articles:
                error_msg = articles.get("message", "未知错误")
                error_item = QTreeWidgetItem(self.article_list, [f"加载失败: {error_msg}"])
                error_item.setFlags(Qt.ItemFlag.NoItemFlags)
                return

            if not articles:
                empty_item = QTreeWidgetItem(self.article_list, [f"知识库 {book_name} 没有文章"])
                empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
                return

            # 处理层级关系
            try:
                # 确保articles是字典列表
                if not isinstance(articles[0], dict):
                    articles = [{k: v for k, v in obj.__dict__.items() if not k.startswith('_')} for obj in articles]
                
                # 构建UUID到文章的映射
                uuid_to_article = {}
                for article in articles:
                    uuid = article.get('uuid')
                    if uuid:
                        uuid_to_article[uuid] = article
                
                # 构建层级结构
                def build_hierarchy(items):
                    """构建文章的层级结构，父子关系通过 parent_uuid 字段确定"""
                    for item in items:
                        item['children'] = []
                    
                    for item in items:
                        parent_uuid = item.get('parent_uuid')
                        if parent_uuid and parent_uuid in uuid_to_article:
                            parent = uuid_to_article[parent_uuid]
                            parent['children'].append(item)
                    
                    root_items = [item for item in items if item.get('level') == 0]
                    root_items.sort(key=lambda x: ((x.get('type', 'DOC') != 'TITLE'), x.get('title', '')))
                    
                    def sort_children_recursive(items):
                        """递归排序子项，确保标题在前，文档在后，并按标题字母顺序排序"""
                        for item in items:
                            if item['children']:
                                item['children'].sort(key=lambda x: ((x.get('type', 'DOC') != 'TITLE'), x.get('title', '')))
                                sort_children_recursive(item['children'])
                    
                    sort_children_recursive(root_items)
                    return root_items
                
                hierarchy = build_hierarchy(articles)
                
                # 3. 递归显示层级结构
                def add_items_recursive(items, parent_item):
                    """递归添加文章项到树控件中
                    
                    Args:
                        items: 文章项列表
                        parent_item: 父项
                    """
                    for item in items:
                        title = item.get('title', 'Untitled')
                        item_type = item.get('type', 'DOC').upper()
                        
                        display_title = title
                        
                        if parent_item == self.article_list:
                            tree_item = QTreeWidgetItem(self.article_list, [display_title])
                        else:
                            tree_item = QTreeWidgetItem(parent_item, [display_title])
                        
                        tree_item.setIcon(0, get_article_icon(item_type, item))
                        
                        # 设置样式
                        if item_type == 'TITLE':
                            font = tree_item.font(0)
                            font.setBold(True)
                            tree_item.setFont(0, font)
                        
                        # 存储文章ID和其他必要信息
                        tree_item.setData(0, Qt.ItemDataRole.UserRole, item.get('id', ''))
                        tree_item.setData(0, Qt.ItemDataRole.UserRole + 1, item)
                        
                        # 检查是否已经选择过该文章
                        if self.current_namespace in self.selected_articles and \
                                item.get('id', '') in self.selected_articles[self.current_namespace]:
                            tree_item.setSelected(True)
                        
                        # 递归添加子项
                        if 'children' in item and item['children']:
                            add_items_recursive(item['children'], tree_item)
                
                add_items_recursive(hierarchy, self.article_list)
                self.article_list.expandAll() # 默认展开所有层级
                
            except Exception as hierarchy_error:
                # 如果层级处理过程中出错，显示原始列表
                self.article_list.clear()

                for article in articles:
                    try:
                        if isinstance(article, dict):
                            title = article.get('title', 'Untitled')
                            item_type = article.get('type', 'DOC').upper()
                            article_id = article.get('id', '')
                        else:
                            title = getattr(article, 'title', 'Untitled')
                            item_type = getattr(article, 'type', 'DOC').upper()
                            article_id = getattr(article, 'id', '')
                        
                        display_title = title
                        
                        tree_item = QTreeWidgetItem(self.article_list, [display_title])
                        tree_item.setIcon(0, get_article_icon(item_type, article))
                        
                        if item_type == 'TITLE':
                            font = tree_item.font(0)
                            font.setBold(True)
                            tree_item.setFont(0, font)
                        
                        tree_item.setData(0, Qt.ItemDataRole.UserRole, article_id)
                        tree_item.setData(0, Qt.ItemDataRole.UserRole + 1, article)

                        if self.current_namespace in self.selected_articles and \
                                article_id in self.selected_articles[self.current_namespace]:
                            tree_item.setSelected(True)

                    except:
                        continue

            self.status_label.setText(f"知识库 {book_name} 共有 {len(articles)} 篇文章")
            self.update_article_selection()

        except Exception as e:
            error_msg = str(e)
            self.article_list.clear()
            error_item = QTreeWidgetItem(self.article_list, [f"显示文章列表出错: {error_msg}"])
            error_item.setFlags(Qt.ItemFlag.NoItemFlags)

    def handle_articles_error(self, error_msg, book_name):
        """处理获取文章列表错误
        
        Args:
            error_msg: 错误信息
            book_name: 知识库名称
        """
        self.article_list.clear()
        error_item = QTreeWidgetItem(self.article_list, [f"加载失败: {error_msg}"])
        error_item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.status_label.setText(f"获取知识库 {book_name} 文章列表失败")

    def filter_articles(self, text):
        """根据输入过滤文章列表
        
        Args:
            text: 过滤文本
        """
        filter_text = text.lower()
        
        def update_visibility(item):
            """更新文章可见性"""
            # 默认自身是否匹配
            is_match = filter_text in item.text(0).lower()
            
            # 检查是否有任何子节点匹配
            child_match = False
            for i in range(item.childCount()):
                if update_visibility(item.child(i)):
                    child_match = True
            
            # 如果自身匹配，或者有子节点匹配，则必须可见
            should_show = is_match or child_match
            item.setHidden(not should_show)
            
            # 如果因为子节点匹配而显示自身，将其展开方便查看
            if child_match and not is_match:
                item.setExpanded(True)
                
            return should_show

        for i in range(self.article_list.topLevelItemCount()):
            update_visibility(self.article_list.topLevelItem(i))

    def select_all_articles(self):
        """全选当前显示的所有文章"""
        iterator = QTreeWidgetItemIterator(self.article_list)
        while iterator.value():
            item = iterator.value()
            if not item.isHidden():
                item.setSelected(True)
            iterator += 1

    def deselect_all_articles(self):
        """取消选择当前知识库的所有文章"""
        iterator = QTreeWidgetItemIterator(self.article_list)
        while iterator.value():
            item = iterator.value()
            item.setSelected(False)
            iterator += 1

    def update_article_selection(self):
        """更新选中的文章"""
        count = len(self.article_list.selectedItems())
        self.selected_article_count_label.setText(f"已选: {count}")

        if self.current_namespace:
            selected_ids = []
            for item in self.article_list.selectedItems():
                article_id = item.data(0, Qt.ItemDataRole.UserRole)
                if article_id:
                    selected_ids.append(article_id)
            
            if selected_ids:
                self.selected_articles[self.current_namespace] = selected_ids
            elif self.current_namespace in self.selected_articles:
                del self.selected_articles[self.current_namespace]
            
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

    @asyncSlot()
    async def select_all_books_in_dialog(self):
        """在对话框中全选所有知识库的文章"""
        if not hasattr(self, 'books_info') or not self.books_info:
            self.status_label.setText("没有可用的知识库")
            return

        self.status_label.setText("正在加载所有知识库的文章...")
        self.selected_articles = {}
        
        self.select_all_books_btn.setEnabled(False)
        self.ok_button.setEnabled(False)

        count = 0
        total = len(self.books_info)
        
        for item in self.books_info:
            namespace = resolve_book_namespace(item)
            
            if namespace:
                self.status_label.setText(f"正在加载({count+1}/{total}): {item.name}")
                # 强制刷新 UI
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()
                
                docs = await self.controller.get_articles(namespace)
                if docs:
                    self.selected_articles[namespace] = [
                        doc.get('id') for doc in docs if isinstance(doc, dict) and doc.get('id')
                    ]
            count += 1

        self.status_label.setText(
            f"已选择所有知识库的文章，共 {sum(len(articles) for articles in self.selected_articles.values())} 篇")
        self.update_total_selected()
        
        self.select_all_books_btn.setEnabled(True)
        self.ok_button.setEnabled(True)


class ArticleManagerMixin:
    """文章管理功能混入类，提供文章选择和加载功能"""
    @property
    def article_controller(self):
        """文章控制器"""
        if not hasattr(self, '_article_controller'):
            from gui.controllers.article_controller import ArticleController
            self._article_controller = ArticleController()
        return self._article_controller

    def select_articles(self):
        """打开文章选择界面"""
        from src.libs.tools import get_cache_books_info
        # 创建并显示文章选择对话框
        books_info = get_cache_books_info()
        if not books_info:
            QMessageBox.warning(self, "无法获取知识库信息", "请重新登录")
            return

        dialog = ArticleSelectionDialog(self, books_info, controller=self.article_controller)
        result = dialog.exec()

        if result == QDialog.DialogCode.Accepted:
            selected_articles = dialog.get_selected_articles()
            if selected_articles:
                # 计算总选择数量
                total_articles = sum(len(ids) for _, ids in selected_articles.items())
                DebugLogger.log_debug(f"已选择 {total_articles} 篇文章进行下载")

                # 存储选择的文章ID
                if not hasattr(self, '_current_answer'):
                    self._current_answer = MutualAnswer(
                        toc_range=[],
                        skip=self.skip_local_checkbox.isChecked(),
                        line_break=self.keep_linebreak_checkbox.isChecked()
                    )
                self._current_answer.selected_docs = selected_articles

                # 如果用户选择了文章，自动将相应的知识库添加到选择列表中
                selected_namespaces = list(selected_articles.keys())

                # 清除知识库列表上的当前选择
                self.book_list.clearSelection()

                # 选择包含所选文章的知识库
                for i in range(self.book_list.count()):
                    item = self.book_list.item(i)
                    namespace = item.data(Qt.ItemDataRole.UserRole)
                    if namespace in selected_namespaces:
                        item.setSelected(True)

                # 更新已选知识库数量
                self.update_selected_count()
            else:
                self.log_handler.emit_log("未选择任何文章进行下载")
                if hasattr(self, '_current_answer'):
                    self._current_answer.selected_docs = {}

    def load_articles_for_selected_books(self):
        """为选中的知识库加载文章列表"""
        selected_items = self.book_list.selectedItems()

        # 没有选中的知识库，清空文章列表
        if not selected_items:
            self.article_list.clear()
            self.article_search_input.setEnabled(False)
            self.select_all_articles_btn.setEnabled(False)
            self.deselect_all_articles_btn.setEnabled(False)
            self.selected_article_count_label.setText("已选: 0")

            # 添加提示信息
            hint_item = QTreeWidgetItem(self.article_list, ["请从左侧选择一个知识库以加载文章列表"])
            hint_item.setFlags(Qt.ItemFlag.NoItemFlags)
            return

        # 启用文章相关控件
        self.article_search_input.setEnabled(True)
        self.select_all_articles_btn.setEnabled(True)
        self.deselect_all_articles_btn.setEnabled(True)

        # 如果只选中一个知识库，加载其文章列表
        if len(selected_items) == 1:
            item = selected_items[0]
            name_data = item.data(Qt.ItemDataRole.UserRole + 1)
            book_name = name_data if name_data else item.text().strip()
            namespace = item.data(Qt.ItemDataRole.UserRole)
            if not namespace:
                self.article_list.clear()
                error_item = QTreeWidgetItem(self.article_list, ["该知识库缺少必要的命名空间信息"])
                error_item.setFlags(Qt.ItemFlag.NoItemFlags)
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

    @asyncSlot()
    async def load_articles_for_book(self, namespace, book_name):
        """加载指定知识库的文章列表
        
        Args:
            namespace: 知识库的命名空间
            book_name: 知识库的名称
        """
        self.article_list.clear()

        loading_item = QTreeWidgetItem(self.article_list, ["正在加载文章列表..."])
        loading_item.setFlags(Qt.ItemFlag.NoItemFlags)

        # 更新状态
        self.current_namespace = namespace
        self.current_book_name = book_name
        Log.info(f"主界面加载文章: {book_name} -> {namespace}")

        # 更新状态
        self.status_label.setText(f"正在加载知识库 {book_name} 的文章...")
        if hasattr(self, 'log_handler'):
            self.log_handler.emit_log(f"正在加载知识库 {book_name} 的文章...")

        # 启用文章面板的控件
        self.article_list.setEnabled(True)
        self.article_search_input.setEnabled(True)
        self.select_all_articles_btn.setEnabled(True)
        self.deselect_all_articles_btn.setEnabled(True)

        # 异步加载文章列表
        docs = await self.article_controller.get_articles(namespace)
        self.display_articles(docs, book_name)

    def display_articles(self, articles, book_name):
        """显示文章列表，支持层级显示
        
        Args:
            articles: 文章列表
            book_name: 知识库名称
        """
        try:
            self.article_list.clear()

            # 检查是否有错误信息
            if isinstance(articles, dict) and "error" in articles:
                error_msg = articles.get("message", "未知错误")
                error_item = QTreeWidgetItem(self.article_list, [f"加载失败: {error_msg}"])
                error_item.setFlags(Qt.ItemFlag.NoItemFlags)

                # 更新状态
                self.status_label.setText(f"知识库 {book_name} 文章加载失败")
                if hasattr(self, 'log_handler'):
                    self.log_handler.emit_log(f"知识库 {book_name} 文章加载失败: {error_msg}")

                if articles.get("error") == "cookies_expired":
                    QMessageBox.warning(self, "登录已过期", "您的登录已过期，请重新登录")
                    if hasattr(self, "logout"):
                        self.logout(force=True)
                return

            if not articles:
                empty_item = QTreeWidgetItem(self.article_list, [f"知识库 {book_name} 没有文章"])
                empty_item.setFlags(Qt.ItemFlag.NoItemFlags)

                self.status_label.setText(f"知识库 {book_name} 没有文章")
                if hasattr(self, 'log_handler'):
                    self.log_handler.emit_log(f"知识库 {book_name} 没有文章")
                return

            # 处理层级关系
            try:
                if not isinstance(articles[0], dict):
                    articles = [{k: v for k, v in obj.__dict__.items() if not k.startswith('_')} for obj in articles]
                
                uuid_to_article = {}
                for article in articles:
                    uuid = article.get('uuid')
                    if uuid:
                        uuid_to_article[uuid] = article
                
                def build_hierarchy(items):
                    for item in items:
                        item['children'] = []
                    
                    for item in items:
                        parent_uuid = item.get('parent_uuid')
                        if parent_uuid and parent_uuid in uuid_to_article:
                            parent = uuid_to_article[parent_uuid]
                            parent['children'].append(item)
                    
                    root_items = [item for item in items if item.get('level') == 0]
                    root_items.sort(key=lambda x: ((x.get('type', 'DOC') != 'TITLE'), x.get('title', '')))
                    
                    def sort_children_recursive(items):
                        for item in items:
                            if item['children']:
                                item['children'].sort(key=lambda x: ((x.get('type', 'DOC') != 'TITLE'), x.get('title', '')))
                                sort_children_recursive(item['children'])
                    
                    sort_children_recursive(root_items)
                    return root_items
                
                hierarchy = build_hierarchy(articles)
                
                def add_items_recursive(items, parent_item):
                    for item in items:
                        title = item.get('title', 'Untitled')
                        item_type = item.get('type', 'DOC').upper()
                        updated_at = item.get('updated_at', '')
                        
                        display_title = title
                        
                        if parent_item == self.article_list:
                            tree_item = QTreeWidgetItem(self.article_list, [display_title])
                        else:
                            tree_item = QTreeWidgetItem(parent_item, [display_title])
                        
                        tree_item.setIcon(0, get_article_icon(item_type, item))
                        
                        font = QFont()
                        if item_type == 'TITLE':
                            font.setBold(True)
                        else:
                            tree_item.setFont(0, font)
                        
                        if updated_at:
                            try:
                                updated_date = updated_at.split('T')[0]
                                tree_item.setToolTip(0, f"标题: {title}\n类型: {item_type}\n更新时间: {updated_date}")
                            except:
                                tree_item.setToolTip(0, f"标题: {title}\n类型: {item_type}")
                        else:
                            tree_item.setToolTip(0, f"标题: {title}\n类型: {item_type}")
                        
                        tree_item.setData(0, Qt.ItemDataRole.UserRole, item.get('id', ''))
                        tree_item.setData(0, Qt.ItemDataRole.UserRole + 1, item)
                        
                        if hasattr(self, '_current_answer') and hasattr(self._current_answer, 'selected_docs') and \
                                self.current_namespace in self._current_answer.selected_docs and \
                                item.get('id', '') in self._current_answer.selected_docs[self.current_namespace]:
                            tree_item.setSelected(True)
                        
                        if 'children' in item and item['children']:
                            add_items_recursive(item['children'], tree_item)
                
                add_items_recursive(hierarchy, self.article_list)
                self.article_list.expandAll()
                
            except Exception as hierarchy_error:
                if hasattr(self, 'log_handler'):
                    self.log_handler.emit_log(f"处理文章层级时出错: {str(hierarchy_error)}，显示未分级列表")
                self.article_list.clear()

                for article in articles:
                    try:
                        if isinstance(article, dict):
                            title = article.get('title', 'Untitled')
                            item_type = article.get('type', 'DOC').upper()
                        else:
                            title = getattr(article, 'title', 'Untitled')
                            item_type = getattr(article, 'type', 'DOC').upper()
                        
                        display_title = title
                        
                        tree_item = QTreeWidgetItem(self.article_list, [display_title])
                        tree_item.setIcon(0, get_article_icon(item_type, article))
                        
                        if item_type == 'TITLE':
                            font = tree_item.font(0)
                            font.setBold(True)
                            tree_item.setFont(0, font)
                        
                        if isinstance(article, dict):
                            tree_item.setData(0, Qt.ItemDataRole.UserRole, article.get('id', ''))
                        else:
                            tree_item.setData(0, Qt.ItemDataRole.UserRole, getattr(article, 'id', ''))
                    except:
                        continue

            self.status_label.setText(f"知识库 {book_name} 共有 {len(articles)} 篇文章")
            if hasattr(self, 'log_handler'):
                self.log_handler.emit_log(f"知识库 {book_name} 共有 {len(articles)} 篇文章")
            self.update_article_selection()

        except Exception as e:
            error_msg = str(e)
            self.article_list.clear()
            error_item = QTreeWidgetItem(self.article_list, [f"显示文章列表出错: {error_msg}"])
            error_item.setFlags(Qt.ItemFlag.NoItemFlags)

            self.status_label.setText(f"显示文章列表出错")
            if hasattr(self, 'log_handler'):
                self.log_handler.emit_log(f"显示文章列表出错: {error_msg}")

    def handle_articles_error(self, error_msg, book_name):
        """处理获取文章列表错误
        
        Args:
            error_msg: 错误信息
            book_name: 知识库名称
        """
        self.article_list.clear()
        error_item = QTreeWidgetItem(self.article_list, [f"加载失败: {error_msg}"])
        error_item.setFlags(Qt.ItemFlag.NoItemFlags)

        # 记录错误到日志
        if hasattr(self, 'log_handler'):
            self.log_handler.emit_log(f"获取知识库 {book_name} 文章列表失败: {error_msg}")
        self.status_label.setText(f"获取知识库 {book_name} 文章列表失败")

        # 检查是否为cookies过期问题
        if "cookies已过期" in str(error_msg) or "登录已过期" in str(error_msg):
            QMessageBox.warning(self, "登录已过期", "您的登录已过期，请重新登录")
            if hasattr(self, "logout"):
                self.logout(force=True)

    def filter_articles(self, text):
        """根据输入过滤文章列表
        
        Args:
            text: 过滤文本
        """
        filter_text = text.lower()
        
        def update_visibility(item):
            """更新文章可见性"""
            is_match = filter_text in item.text(0).lower()
            
            child_match = False
            for i in range(item.childCount()):
                if update_visibility(item.child(i)):
                    child_match = True
            
            should_show = is_match or child_match
            item.setHidden(not should_show)
            
            if child_match and not is_match:
                item.setExpanded(True)
                
            return should_show

        for i in range(self.article_list.topLevelItemCount()):
            update_visibility(self.article_list.topLevelItem(i))

    def select_all_articles(self):
        """全选当前显示的所有文章"""
        iterator = QTreeWidgetItemIterator(self.article_list)
        while iterator.value():
            item = iterator.value()
            if not item.isHidden():  # 只选择可见项目
                item.setSelected(True)
            iterator += 1

    def deselect_all_articles(self):
        """取消选择当前知识库的所有文章"""
        iterator = QTreeWidgetItemIterator(self.article_list)
        while iterator.value():
            item = iterator.value()
            item.setSelected(False)
            iterator += 1

    def update_article_selection(self):
        """更新选中的文章"""
        try:
            count = len(self.article_list.selectedItems())
            self.selected_article_count_label.setText(f"已选: {count}")

            # 如果有文章被选中，则创建或更新MutualAnswer对象来存储选中的文章
            if hasattr(self, 'current_namespace') and self.current_namespace:
                # 获取当前选中的所有文章ID
                selected_ids = []
                for item in self.article_list.selectedItems():
                    article_id = item.data(0, Qt.ItemDataRole.UserRole)
                    if article_id:
                        selected_ids.append(article_id)

                # 存储选择的文章ID
                if not hasattr(self, '_current_answer'):
                    self._current_answer = MutualAnswer(
                        toc_range=[],
                        skip=self.skip_local_checkbox.isChecked(),
                        line_break=self.keep_linebreak_checkbox.isChecked()
                    )
                    self._current_answer.selected_docs = {}

                # 更新选中状态
                if selected_ids:
                    self._current_answer.selected_docs[self.current_namespace] = selected_ids
                    if hasattr(self, 'log_handler'):
                        DebugLogger.log_debug(
                            f"已选择 {len(selected_ids)} 篇文章: {self.current_book_name} -> {self.current_namespace}"
                        )
                        Log.info(f"已选择 {len(selected_ids)} 篇文章: {self.current_book_name} -> {self.current_namespace}")
                elif self.current_namespace in self._current_answer.selected_docs:
                    # 如果没有选中任何文章，从已选字典中删除该知识库
                    del self._current_answer.selected_docs[self.current_namespace]
                    if hasattr(self, 'log_handler'):
                        DebugLogger.log_debug(f"已清除文章选择: {self.current_book_name} -> {self.current_namespace}")
                        Log.info(f"已清除文章选择: {self.current_book_name} -> {self.current_namespace}")

                # 计算并显示总共选择的文章数量
                if hasattr(self, '_current_answer') and hasattr(self._current_answer, 'selected_docs'):
                    total_selected = sum(len(ids) for ids in self._current_answer.selected_docs.values())
                    if total_selected > 0:
                        self.status_label.setText(f"总计已选: {total_selected} 篇文章")
                    else:
                        self.status_label.setText("未选择任何文章")
        except Exception as e:
            error_msg = str(e)
            if hasattr(self, 'log_handler'):
                self.log_handler.emit_log(f"更新文章选择状态时出错: {error_msg}")
            self.status_label.setText("更新文章选择状态时出错")

    def display_all_books_selected_message(self):
        """显示全选知识库时的提示信息"""
        self.article_list.clear()

        # 添加提示信息
        info_item = QTreeWidgetItem(self.article_list, ["当前已全选知识库，将导出所有知识库的全部文章"])
        info_item.setFlags(Qt.ItemFlag.NoItemFlags)
        info_item.setFont(0, QFont("Arial", 12, QFont.Weight.Bold))

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
        info_item = QTreeWidgetItem(self.article_list, ["已选择以下知识库（将导出所选知识库内的全部文章）:"])
        info_item.setFlags(Qt.ItemFlag.NoItemFlags)
        info_item.setFont(0, QFont("Arial", 10, QFont.Weight.Bold))

        # 显示选中的知识库
        book_icon = QIcon(static_resource_path("src/ui/themes/resources/icons/yuque-book.svg"))
        for item in selected_items:
            name_data = item.data(Qt.ItemDataRole.UserRole + 1)
            book_name = name_data if name_data else item.text().strip()
            book_item = QTreeWidgetItem(self.article_list, [book_name])
            book_item.setIcon(0, book_icon)
            book_item.setFlags(Qt.ItemFlag.NoItemFlags)

        # 添加提示信息
        tip_item = QTreeWidgetItem(self.article_list, ["提示: 导出时将包含所选知识库的全部文章"])
        tip_item.setFlags(Qt.ItemFlag.NoItemFlags)

        # 更新状态
        self.status_label.setText(f"已选择 {len(selected_items)} 个知识库")
        self.selected_article_count_label.setText("已选: 全部")
        DebugLogger.log_debug(f"已选择 {len(selected_items)} 个知识库，将导出全部文章")

        # 启用相关控件
        self.article_search_input.setEnabled(False)
        self.select_all_articles_btn.setEnabled(False)
        self.deselect_all_articles_btn.setEnabled(False)

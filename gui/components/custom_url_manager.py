from qasync import asyncSlot
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QCheckBox, QGroupBox, QMessageBox, QAbstractItemView, QFileDialog, QTreeWidgetItem, QTreeWidgetItemIterator
)
from PyQt6.QtCore import Qt

class CustomUrlManagerMixin:
    """公开知识库导出管理器类

    提供一个界面让用户输入公开知识库的URL,解析文档列表,选择要导出的文章,并执行导出操作。
    """

    def init_custom_url_ui(self):
        """初始化公开知识库导出UI"""
        page = QWidget()
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # 添加状态标签
        self.custom_status_label = QLabel("准备就绪")
        self.custom_status_label.setObjectName("StatusLabel")
        main_layout.addWidget(self.custom_status_label)

        #顶部面板
        parse_panel = QGroupBox("解析设置")
        parse_layout = QHBoxLayout(parse_panel)
        parse_layout.setContentsMargins(10, 10, 10, 10)
        parse_layout.setSpacing(10)

        #URL 输入
        self.custom_url_input = QLineEdit()
        self.custom_url_input.setPlaceholderText("请输入公开的语雀知识库地址")
        parse_layout.addWidget(self.custom_url_input, 3)

        #选项和按钮
        from PyQt6.QtGui import QRegularExpressionValidator
        from PyQt6.QtCore import QRegularExpression
        self.custom_password_input = QLineEdit()
        self.custom_password_input.setPlaceholderText("知识库密码(无密码则留空)")
        self.custom_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.custom_password_input.setToolTip("如果需要密码，请在此输入（4位 a-z/0-9 组合，无密码留空）")
        self.custom_password_input.setFixedWidth(200)
        
        # 限制长度和格式
        self.custom_password_input.setMaxLength(4)
        reg_ex = QRegularExpression("^[a-z0-9]{0,4}$")
        validator = QRegularExpressionValidator(reg_ex, self.custom_password_input)
        self.custom_password_input.setValidator(validator)

        parse_layout.addWidget(self.custom_password_input)
        
        self.parse_btn = QPushButton("开始解析")
        self.parse_btn.setMinimumHeight(30)
        self.parse_btn.setMinimumWidth(160)
        self.parse_btn.setObjectName("PrimaryButton")
        self.parse_btn.clicked.connect(self.on_parse_clicked)
        parse_layout.addWidget(self.parse_btn)

        main_layout.addWidget(parse_panel)

        # 下方区域: 左右分栏
        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)

        # 左侧: 解析结果
        left_panel = QGroupBox("解析结果")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(10)

        # 搜索框
        search_layout = QHBoxLayout()
        search_label = QLabel("搜索文章:")
        self.custom_article_search_input = QLineEdit()
        self.custom_article_search_input.setPlaceholderText("输入关键词过滤文章")
        self.custom_article_search_input.textChanged.connect(self.filter_custom_articles)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.custom_article_search_input)
        left_layout.addLayout(search_layout)

        # 文章列表
        from gui.components.article_manager import ArticleTreeWidget
        self.custom_article_list = ArticleTreeWidget()
        left_layout.addWidget(self.custom_article_list)

        # 操作按钮 (水平布局)
        action_control_layout = QHBoxLayout()
        self.cust_select_all_btn = QPushButton("全选")
        self.cust_select_all_btn.setMinimumWidth(300)
        self.cust_select_all_btn.clicked.connect(self.select_all_custom_articles)
        action_control_layout.addWidget(self.cust_select_all_btn)

        self.cust_deselect_all_btn = QPushButton("取消选择")
        self.cust_deselect_all_btn.setMinimumWidth(300)
        self.cust_deselect_all_btn.setObjectName("SecondaryButton")
        self.cust_deselect_all_btn.clicked.connect(self.deselect_all_custom_articles)
        action_control_layout.addWidget(self.cust_deselect_all_btn)
        
        action_control_layout.addStretch(1)
        self.custom_selected_count_label = QLabel("已选: 0")
        action_control_layout.addWidget(self.custom_selected_count_label)
        left_layout.addLayout(action_control_layout)

        content_layout.addWidget(left_panel, 2)

        # 右侧: 导出选项
        right_panel = QGroupBox("导出选项")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(15)
        
        # 输出目录
        output_group = QVBoxLayout()
        output_group.setSpacing(5)
        output_group.addWidget(QLabel("输出目录:"))
        
        output_input_layout = QHBoxLayout()
        self.custom_output_input = QLineEdit()

        # 设置默认输出目录
        from src.libs.constants import GLOBAL_CONFIG
        self.custom_output_input.setText(GLOBAL_CONFIG.target_output_dir)
        output_input_layout.addWidget(self.custom_output_input)
        
        self.custom_output_btn = QPushButton("浏览")
        self.custom_output_btn.setMinimumWidth(80)
        self.custom_output_btn.clicked.connect(self.select_custom_output_dir)
        output_input_layout.addWidget(self.custom_output_btn)
        
        output_group.addLayout(output_input_layout)
        right_layout.addLayout(output_group)
        
        # 选项开关
        self.custom_skip_local_checkbox = QCheckBox("跳过已存在的文件")
        self.custom_skip_local_checkbox.setChecked(True)
        right_layout.addWidget(self.custom_skip_local_checkbox)

        self.custom_keep_linebreak_checkbox = QCheckBox("保留语雀换行标识")
        self.custom_keep_linebreak_checkbox.setChecked(True)
        right_layout.addWidget(self.custom_keep_linebreak_checkbox)

        self.custom_download_images_checkbox = QCheckBox("下载图片到本地")
        self.custom_download_images_checkbox.setChecked(True)
        right_layout.addWidget(self.custom_download_images_checkbox)
        
        right_layout.addStretch(1)
        
        # 导出按钮
        self.cust_download_btn = QPushButton("开始导出")
        self.cust_download_btn.setMinimumHeight(40)
        self.cust_download_btn.setObjectName("PrimaryButton")
        self.cust_download_btn.clicked.connect(self.on_custom_download_clicked)
        self.cust_download_btn.setEnabled(False)
        right_layout.addWidget(self.cust_download_btn)
        
        content_layout.addWidget(right_panel, 1)
        
        main_layout.addLayout(content_layout)

        # 初始化控制器
        from gui.controllers.custom_url_controller import CustomUrlController
        self.custom_url_controller = CustomUrlController()
        
        # 连接信号
        self.custom_url_controller.parse_started.connect(self.on_parse_started)
        self.custom_url_controller.browser_launched.connect(self.on_browser_launched)
        self.custom_url_controller.parse_finished.connect(self.on_parse_finished)
        self.custom_url_controller.parse_failed.connect(self.on_parse_failed)
        self.custom_url_controller.download_progress.connect(self.on_custom_download_progress)
        self.custom_url_controller.download_progress_update.connect(self.on_custom_download_progress_update)
        self.custom_url_controller.download_finished.connect(self.on_custom_download_finished)

        # 列表选择变化连接
        self.custom_article_list.itemSelectionChanged.connect(self.on_custom_selection_changed)

        return page
    
    @asyncSlot()
    async def on_parse_clicked(self):
        """点击解析"""
        url = self.custom_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请输入知识库链接")
            return
            
        # URL 简单校验
        if not url.startswith("http") or "yuque.com" not in url:
             QMessageBox.warning(self, "格式错误", "请输入有效的语雀知识库链接 (包含 yuque.com)")
             return

        password = self.custom_password_input.text().strip()
        if password and len(password) != 4:
             QMessageBox.warning(self, "格式错误", "请输入正确的4位知识库密码 (a-z 0-9)")
             return

        try:
            await self.custom_url_controller.start_parse(url, password=password)
        except Exception as e:
            self.on_parse_failed(f"启动解析出错: {e}")

    @asyncSlot()
    async def on_parse_started(self):
        """解析开始"""
        self.parse_btn.setEnabled(False)
        self.custom_article_list.clear()
        QTreeWidgetItem(self.custom_article_list, ["正在解析，请稍候..."])
        self.custom_status_label.setText("正在解析...")

    def on_browser_launched(self):
        """浏览器启动"""
        self.custom_article_list.clear()
        QTreeWidgetItem(self.custom_article_list, ["请在浏览器中输入知识库密码..."])
        QTreeWidgetItem(self.custom_article_list, ["输入正确密码后软件将自动开始解析..."])
        self.custom_status_label.setText("等待输入密码...")

    def on_parse_finished(self, docs):
        """解析完成,显示文档列表"""
        self.parse_btn.setEnabled(True)
        self.custom_article_list.clear()
        self.custom_status_label.setText(f"解析完成,共找到 {len(docs)} 篇文档")
        
        if not docs:
            QTreeWidgetItem(self.custom_article_list, ["未找到文档"])
            return

        self._display_docs_with_hierarchy(docs)

    def on_parse_failed(self, error):
        """解析失败"""
        self.parse_btn.setEnabled(True)
        self.custom_article_list.clear()
        QTreeWidgetItem(self.custom_article_list, [f"解析失败: {error}"])
        QMessageBox.critical(self, "错误", f"{error}")
        self.custom_status_label.setText("解析失败")

    def on_custom_selection_changed(self):
        """当自定义文章选择改变时更新UI"""
        count = len(self.custom_article_list.selectedItems())
        self.cust_download_btn.setEnabled(count > 0)
        if count > 0:
            self.cust_download_btn.setText(f"开始导出")
        else:
            self.cust_download_btn.setText("开始导出")
        
        # 更新已选数量标签
        if hasattr(self, 'custom_selected_count_label'):
            self.custom_selected_count_label.setText(f"已选: {count}")

    @asyncSlot()
    async def on_custom_download_clicked(self):
        """点击下载"""
        items = self.custom_article_list.selectedItems()
        if not items:
            QMessageBox.warning(self, "提示", "请先选择要导出的文章")
            return

        docs = [item.data(0, Qt.ItemDataRole.UserRole) for item in items]
        
        output_dir = self.custom_output_input.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "提示", "请先选择输出目录")
            return
        
        self.cust_download_btn.setEnabled(False)
        self.parse_btn.setEnabled(False)
        
        # 重置进度条格式
        if hasattr(self, 'progress_bar'):
             self.progress_bar.setFormat("导出进度: %p%")
        
        options = {
            "skip": self.custom_skip_local_checkbox.isChecked(),
            "linebreak": self.custom_keep_linebreak_checkbox.isChecked(),
            "download_images": self.custom_download_images_checkbox.isChecked()
        }
        
        await self.custom_url_controller.download_docs(docs, output_dir, options)

    def on_custom_download_progress(self, msg):
        """更新下载进度"""
        self.custom_status_label.setText(msg)
        if hasattr(self, 'progress_bar'):
             self.progress_bar.setFormat(msg)

    def on_custom_download_progress_update(self, current, total):
        """更新进度条数值"""
        if hasattr(self, 'progress_bar') and hasattr(self, 'progress_widget'):
            if not self.progress_widget.isVisible():
                 self.progress_widget.setVisible(True)
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)

    def on_custom_download_finished(self):
        """导出完成"""
        self.cust_download_btn.setEnabled(True)
        self.parse_btn.setEnabled(True)
        self.custom_status_label.setText("导出完成")
        
        if hasattr(self, 'progress_bar'):
             self.progress_bar.setValue(self.progress_bar.maximum())
             self.progress_bar.setFormat("全部完成!")
        
        # 获取统计信息并显示弹窗
        downloaded = self.custom_url_controller._downloaded_count
        skipped = self.custom_url_controller._skipped_count
        failed = self.custom_url_controller._failed_count
        
        msg = f"导出完成!\n成功下载: {downloaded}\n跳过文件: {skipped}\n失败文件: {failed}"
        QMessageBox.information(self, "导出完成", msg)

    def filter_custom_articles(self, text):
        """根据输入过滤文章列表
        
        Args:
            text: 输入的过滤文本
        """
        filter_text = text.lower()
        iterator = QTreeWidgetItemIterator(self.custom_article_list)
        while iterator.value():
            item = iterator.value()

            # 检查文档项是否匹配
            doc = item.data(0, Qt.ItemDataRole.UserRole)
            if doc and isinstance(doc, dict):
                title = doc.get('title', '').lower()
                match = filter_text in title
            else:
                match = True
                    
            item.setHidden(not match)
            iterator += 1
            
    def select_all_custom_articles(self):
        """全选当前显示的公开知识库文章"""
        iterator = QTreeWidgetItemIterator(self.custom_article_list)
        while iterator.value():
            item = iterator.value()
            if not item.isHidden():
                item.setSelected(True)
            iterator += 1

    def deselect_all_custom_articles(self):
        """取消选择所有公开知识库文章"""
        self.custom_article_list.clearSelection()
    
    def _display_docs_with_hierarchy(self, docs):
        """显示文档列表,支持层级结构"""
        try:
            from PyQt6.QtGui import QFont
            
            # 构建UUID到文档的映射
            uuid_to_doc = {}
            for doc in docs:
                uuid = doc.get('uuid')
                if uuid:
                    uuid_to_doc[uuid] = doc
                    doc['children'] = []
            
            # 构建层级结构
            for doc in docs:
                parent_uuid = doc.get('parent_uuid')
                if parent_uuid and parent_uuid in uuid_to_doc:
                    parent = uuid_to_doc[parent_uuid]
                    parent['children'].append(doc)
            
            # 找出根级文档
            root_docs = [doc for doc in docs if doc.get('level') == 0]
            
            # 按类型和标题排序
            root_docs.sort(key=lambda x: ((x.get('type', 'doc') != 'TITLE'), x.get('title', '')))
            
            # 递归排序子文档
            def sort_children_recursive(items):
                for item in items:
                    if item.get('children'):
                        item['children'].sort(key=lambda x: ((x.get('type', 'doc') != 'TITLE'), x.get('title', '')))
                        sort_children_recursive(item['children'])
            
            sort_children_recursive(root_docs)
            
            # 递归显示层级结构
            def add_items_recursive(items, parent_item):
                for item in items:
                    title = item.get('title', '无标题')
                    item_type = item.get('type', 'doc').upper()
                    
                    display_title = title
                    
                    if parent_item == self.custom_article_list:
                        tree_item = QTreeWidgetItem(self.custom_article_list, [display_title])
                    else:
                        tree_item = QTreeWidgetItem(parent_item, [display_title])
                    
                    from gui.components.article_manager import get_article_icon
                    tree_item.setIcon(0, get_article_icon(item_type, item))
                    
                    # 设置样式
                    font = QFont()
                    if item_type == 'TITLE':
                        font.setBold(True)
                    tree_item.setFont(0, font)
                    
                    # 存储完整的文档数据
                    tree_item.setData(0, Qt.ItemDataRole.UserRole, item)
                    tree_item.setData(0, Qt.ItemDataRole.UserRole + 1, item)
                    
                    # 递归添加子项
                    if item.get('children'):
                        add_items_recursive(item['children'], tree_item)
            
            # 添加层级结构到列表
            add_items_recursive(root_docs, self.custom_article_list)
            self.custom_article_list.expandAll()
            
        except Exception as e:
            # 如果层级处理失败,使用简单显示
            self.log_handler.emit_log(f"层级显示失败,使用简单模式: {str(e)}")
            for doc in docs:
                title = doc.get('title', '无标题')
                item_type = doc.get('type', 'doc').upper()
                display_title = title
                
                tree_item = QTreeWidgetItem(self.custom_article_list, [display_title])
                from gui.components.article_manager import get_article_icon
                tree_item.setIcon(0, get_article_icon(item_type, doc))
                tree_item.setData(0, Qt.ItemDataRole.UserRole, doc)
    
    def select_custom_output_dir(self):
        """选择公开知识库导出导出的输出目录"""
        import os
        
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择输出目录",
            self.custom_output_input.text() or os.path.expanduser("~")
        )

        if dir_path:
            self.custom_output_input.setText(dir_path)
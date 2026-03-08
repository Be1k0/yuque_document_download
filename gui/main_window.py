import sys
from PyQt6.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QCheckBox, QListWidget, QGroupBox, 
    QLineEdit, QProgressBar, QTabWidget, QSplitter, QSizePolicy, QAbstractItemView
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, pyqtSignal
from src.libs.constants import GLOBAL_CONFIG
from utils import static_resource_path, StdoutRedirector, QPasswordLineEdit
from .components.login_manager import LoginManagerMixin
from .components.book_manager import BookManagerMixin
from .components.article_manager import ArticleManagerMixin, ArticleTreeWidget
from .components.export_manager import ExportManagerMixin
from .components.log_manager import LogManagerMixin
from .components.settings_manager import SettingsManagerMixin
from .components.custom_url_manager import CustomUrlManagerMixin

class YuqueGUI(QMainWindow, LoginManagerMixin, BookManagerMixin, ArticleManagerMixin, 
               ExportManagerMixin, LogManagerMixin, SettingsManagerMixin, CustomUrlManagerMixin):
    # 用于安全更新日志文本框的信号
    appendLogSignal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        from main import __version__
        self.setWindowTitle(f"语雀知识库导出工具 {__version__} By Be1k0")

        # 响应式窗口大小设置
        screen = QApplication.primaryScreen().geometry()
        screen_width = screen.width()
        screen_height = screen.height()

        # 根据屏幕分辨率自适应窗口大小
        if screen_width >= 1920:
            window_width = 1400
            window_height = 800  
            min_width = 900
            min_height = 600  
        elif screen_width >= 1366:
            window_width = 1200
            window_height = 700  
            min_width = 800
            min_height = 550  
        elif screen_width >= 1024:
            window_width = min(1000, int(screen_width * 0.95))
            window_height = min(650, int(screen_height * 0.8))  
            min_width = 700
            min_height = 480  
        else:
            window_width = min(800, int(screen_width * 0.98))
            window_height = min(550, int(screen_height * 0.85))  
            min_width = 600
            min_height = 430  

        # 居中显示
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2

        self.setGeometry(x, y, window_width, window_height)
        self.setMinimumSize(min_width, min_height)

        # 设置应用程序图标
        self.setWindowIcon(QIcon(static_resource_path('favicon.ico')))

        # 初始化设置变量
        self.download_threads = 10  # 默认下载线程数
        self.doc_image_prefix = ''  # 文档图片前缀
        self.image_rename_mode = 'asc'  # 图片重命名模式
        self.image_file_prefix = 'image-'  # 图片文件前缀
        self.yuque_cdn_domain = 'cdn.nlark.com'  # 语雀CDN域名
        self.enable_debug = False  # 调试模式
        self.disable_ssl = GLOBAL_CONFIG.disable_ssl # 禁用SSL验证

        # 初始化用户界面
        self.init_ui()

        # 初始化日志管理器
        self.init_log_manager()

        # 设置日志重定向
        self.redirector = StdoutRedirector(self.log_text_edit, disable_terminal_output=True)
        sys.stdout = self.redirector
        sys.stderr = self.redirector

        # 检查Cookie
        self.check_login_status()

    def closeEvent(self, event):
        """当窗口关闭时恢复标准输出流"""
        if hasattr(self, 'redirector'):
            self.redirector.flush()
            sys.stdout = self.redirector.old_stdout
            sys.stderr = self.redirector.old_stderr
        super().closeEvent(event)
    
    def on_tab_changed(self, index):
        """标签页切换时的处理"""
        show_progress = (index == self.selection_tab_index) or (index == self.selection_tab_index + 1)
        self.progress_widget.setVisible(show_progress)

    def init_ui(self):
        # 主界面布局
        central_widget = QWidget()
        central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # 创建主分割器
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(main_splitter, 1) 

        # 上半部分 - 操作区域
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_widget.setMinimumHeight(410)

        # 创建Tab小部件
        tabs = QTabWidget()

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
        login_form_layout.addSpacing(10)

        self.login_button = QPushButton("登录")
        self.login_button.setMinimumHeight(36)
        self.login_button.clicked.connect(self.login)
        login_form_layout.addWidget(self.login_button)
        login_form_layout.addSpacing(5)

        self.web_login_button = QPushButton("网页端登录")
        self.web_login_button.setMinimumHeight(36)
        self.web_login_button.setObjectName("SecondaryButton")
        self.web_login_button.clicked.connect(self.web_login)
        login_form_layout.addWidget(self.web_login_button)

        self.login_group.setLayout(login_form_layout)
        login_layout.addWidget(self.login_group)

        login_help = QLabel("请输入您的语雀账号和密码进行登录，或使用网页端登录。登录信息仅用于获取知识库数据，不会被发送到第三方。")
        login_help.setWordWrap(True)
        login_help.setProperty("class", "help-text")
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
        self.avatar_label.setObjectName("AvatarLabel")
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setScaledContents(True)
        user_header_layout.addWidget(self.avatar_label)

        # 用户信息
        user_details_layout = QVBoxLayout()
        self.user_name_label = QLabel("用户名: --")
        self.user_name_label.setObjectName("UserNameLabel")
        user_details_layout.addWidget(self.user_name_label)

        self.user_id_label = QLabel("用户ID: --")
        self.user_id_label.setObjectName("UserIdLabel")
        user_details_layout.addWidget(self.user_id_label)
        user_header_layout.addLayout(user_details_layout)
        user_header_layout.addStretch()
        user_info_layout.addLayout(user_header_layout)

        # 注销按钮
        user_info_layout.addSpacing(10)
        self.logout_button = QPushButton("注销")
        self.logout_button.setMinimumHeight(36)
        self.logout_button.setObjectName("DangerButton")
        self.logout_button.clicked.connect(self.logout)
        user_info_layout.addWidget(self.logout_button)

        self.user_info_group.setLayout(user_info_layout)
        login_layout.addWidget(self.user_info_group)

        # 默认隐藏用户信息组
        self.user_info_group.hide()

        login_layout.addStretch(1)

        # 知识库选择页
        selection_page = QWidget()
        selection_layout = QVBoxLayout(selection_page)
        selection_layout.setContentsMargins(10, 10, 10, 10)
        selection_layout.setSpacing(12)

        # 添加状态标签
        self.status_label = QLabel("准备就绪")
        self.status_label.setObjectName("StatusLabel")
        selection_layout.addWidget(self.status_label)

        # 水平布局将三个部分分开
        selection_horizontal = QHBoxLayout()
        selection_horizontal.setSpacing(15)
        selection_layout.addLayout(selection_horizontal)

        # 左侧：知识库列表
        left_panel = QGroupBox("知识库列表")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 15, 10, 15)
        left_layout.setSpacing(10)

        # 搜索框
        search_layout = QHBoxLayout()
        search_layout.setSpacing(8)
        search_label = QLabel("搜索:")
        search_label.setMinimumWidth(50)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词过滤知识库")
        self.search_input.textChanged.connect(self.filter_books)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        left_layout.addLayout(search_layout)

        # 知识库列表
        self.book_list = QListWidget()
        self.book_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.book_list.setMinimumHeight(120)  
        self.book_list.setMinimumWidth(200) 
        left_layout.addWidget(self.book_list)

        # 知识库选择按钮区域
        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(8) 

        # 第一行：全选和取消全选按钮
        select_buttons_layout = QHBoxLayout()
        select_buttons_layout.setSpacing(8)  

        self.select_all_books_btn = QPushButton("全选")
        self.select_all_books_btn.setMinimumHeight(30)  
        self.select_all_books_btn.setMaximumHeight(34)  
        self.select_all_books_btn.clicked.connect(self.select_all_books)
        select_buttons_layout.addWidget(self.select_all_books_btn)

        self.deselect_all_books_btn = QPushButton("取消选择")
        self.deselect_all_books_btn.setMinimumHeight(30)  
        self.deselect_all_books_btn.setMaximumHeight(34)  
        self.deselect_all_books_btn.setObjectName("SecondaryButton")
        self.deselect_all_books_btn.clicked.connect(self.deselect_all_books)
        select_buttons_layout.addWidget(self.deselect_all_books_btn)

        buttons_layout.addLayout(select_buttons_layout)

        # 第二行：已选数量标签
        count_layout = QHBoxLayout()
        self.selected_count_label = QLabel("已选: 0")
        self.selected_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count_layout.addWidget(self.selected_count_label)

        buttons_layout.addLayout(count_layout)
        left_layout.addLayout(buttons_layout)

        # 连接选择变化的信号
        self.book_list.itemSelectionChanged.connect(self.update_selected_count)

        # 中间面板：选择文章
        center_panel = QGroupBox("文章列表")
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(10, 15, 10, 15)  
        center_layout.setSpacing(10)  

        # 文章搜索框
        article_search_layout = QHBoxLayout()
        article_search_layout.setSpacing(8)  
        article_search_label = QLabel("搜索文章:")
        article_search_label.setMinimumWidth(70)
        self.article_search_input = QLineEdit()
        self.article_search_input.setPlaceholderText("输入关键词过滤文章")
        self.article_search_input.textChanged.connect(self.filter_articles)
        article_search_layout.addWidget(article_search_label)
        article_search_layout.addWidget(self.article_search_input)
        center_layout.addLayout(article_search_layout)

        # 文章列表
        self.article_list = ArticleTreeWidget()
        self.article_list.itemSelectionChanged.connect(self.update_article_selection)
        center_layout.addWidget(self.article_list)

        # 文章选择控制区域
        article_control_layout = QVBoxLayout()
        article_control_layout.setSpacing(8)  

        # 第一行：全选和取消全选按钮
        article_buttons_layout = QHBoxLayout()
        article_buttons_layout.setSpacing(8)  

        self.select_all_articles_btn = QPushButton("全选文章")
        self.select_all_articles_btn.setMinimumHeight(30)  
        self.select_all_articles_btn.setMaximumHeight(34)  
        self.select_all_articles_btn.clicked.connect(self.select_all_articles)
        article_buttons_layout.addWidget(self.select_all_articles_btn)

        self.deselect_all_articles_btn = QPushButton("取消选择")
        self.deselect_all_articles_btn.setMinimumHeight(30)  
        self.deselect_all_articles_btn.setMaximumHeight(34)  
        self.deselect_all_articles_btn.setObjectName("SecondaryButton")
        self.deselect_all_articles_btn.clicked.connect(self.deselect_all_articles)
        article_buttons_layout.addWidget(self.deselect_all_articles_btn)

        article_control_layout.addLayout(article_buttons_layout)

        # 第二行：已选数量标签
        article_count_layout = QHBoxLayout()
        self.selected_article_count_label = QLabel("已选: 0")
        self.selected_article_count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        article_count_layout.addWidget(self.selected_article_count_label)

        article_control_layout.addLayout(article_count_layout)
        center_layout.addLayout(article_control_layout)

        # 右侧：导出设置
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_panel.setMinimumHeight(250)  
        right_layout.setSpacing(8)  

        # 导出选项组
        options_group = QGroupBox("导出选项")
        options_layout = QVBoxLayout()
        options_layout.setContentsMargins(10, 10, 10, 10)  
        options_layout.setSpacing(4)  
        options_group.setLayout(options_layout)

        # 创建常规复选框样式的选项
        self.skip_local_checkbox = QCheckBox("跳过本地文件")
        self.skip_local_checkbox.setToolTip("如果文件已经存在则不重新下载")
        self.skip_local_checkbox.setChecked(True)
        self.skip_local_checkbox.setStyleSheet("font-size: 12px; padding: 3px 0; margin: 0;")
        options_layout.addWidget(self.skip_local_checkbox)

        self.keep_linebreak_checkbox = QCheckBox("保留语雀换行标识")
        self.keep_linebreak_checkbox.setToolTip("保留语雀文档中的换行标记")
        self.keep_linebreak_checkbox.setChecked(True)
        self.keep_linebreak_checkbox.setStyleSheet("font-size: 12px; padding: 3px 0; margin: 0;")
        options_layout.addWidget(self.keep_linebreak_checkbox)

        self.download_images_checkbox = QCheckBox("下载图片到本地")
        self.download_images_checkbox.setToolTip("将Markdown文档中的图片下载到本地，并更新图片链接")
        self.download_images_checkbox.setChecked(True)
        self.download_images_checkbox.setStyleSheet("font-size: 12px; padding: 3px 0; margin: 0 0 2px 0;")  
        options_layout.addWidget(self.download_images_checkbox)

        # 输出目录设置
        output_label = QLabel("输出目录:")
        output_label.setStyleSheet("font-weight: bold; font-size: 12px; margin: 0 0 2px 0;")  
        options_layout.addWidget(output_label)
        
        self.output_input = QLineEdit()
        self.output_input.setReadOnly(True)
        self.output_input.setMinimumHeight(26)  
        self.output_input.setMaximumHeight(26)  
        self.output_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)  
        self.output_input.setToolTip(GLOBAL_CONFIG.target_output_dir)  
        self.output_input.setCursorPosition(0)  
        options_layout.addWidget(self.output_input)

        # 设置默认输出目录
        self.output_input.setText(GLOBAL_CONFIG.target_output_dir)

        output_button = QPushButton("选择")
        output_button.setMinimumHeight(26)  
        output_button.setMaximumHeight(26)  
        output_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)  
        output_button.setObjectName("SecondaryButton")
        output_button.clicked.connect(self.select_output_dir)
        
        options_layout.addWidget(output_button)

        right_layout.addWidget(options_group)

        # 添加伸展空间，将导出选项顶上去
        right_layout.addStretch(1)

        # 导出操作按钮区域
        export_actions_layout = QVBoxLayout()
        export_actions_layout.setContentsMargins(0, 0, 0, 0)
        export_actions_layout.setSpacing(10)  

        # 开始导出按钮
        self.export_button = QPushButton("开始导出")
        self.export_button.setMinimumHeight(36)
        self.export_button.setObjectName("PrimaryButton")
        self.export_button.clicked.connect(self.start_export)
        export_actions_layout.addWidget(self.export_button)

        # 清除缓存按钮
        self.clean_button = QPushButton("清理缓存")
        self.clean_button.setMinimumHeight(32)
        self.clean_button.setObjectName("DangerButton")
        self.clean_button.clicked.connect(self.clean_cache)
        export_actions_layout.addWidget(self.clean_button)

        right_layout.addLayout(export_actions_layout)

        # 添加三个面板到水平布局 - 优化面板比例
        selection_horizontal.addWidget(left_panel, 1)  
        selection_horizontal.addWidget(center_panel, 2)  
        selection_horizontal.addWidget(right_panel, 1)  

        # 设置页面
        settings_page = self.create_settings_page()

        # 关于页面
        about_page = self.create_about_page()

        # 公开知识库导出页
        custom_url_page = self.init_custom_url_ui()

        # 添加标签页
        tabs.addTab(login_page, "登录")
        self.selection_tab_index = tabs.addTab(selection_page, "知识库导出")
        tabs.addTab(custom_url_page, "公开知识库导出")
        tabs.addTab(settings_page, "设置")
        log_page = self.create_log_page()
        tabs.addTab(log_page, "运行日志")
        tabs.addTab(about_page, "关于")

        # 连接标签页切换信号
        tabs.currentChanged.connect(self.on_tab_changed)

        top_layout.addWidget(tabs)
        main_splitter.addWidget(top_widget)

        # 添加进度条到底部 - 仅在知识库选择页可见
        self.progress_widget = QWidget()
        progress_layout = QVBoxLayout(self.progress_widget)
        progress_layout.setContentsMargins(10, 10, 10, 10)
        progress_layout.setSpacing(8)

        self.progress_label = QLabel("")
        self.progress_label.setVisible(False) 
        progress_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("已导出: %v/%m (%p%)")
        self.progress_bar.setObjectName("ExportProgressBar")
        progress_layout.addWidget(self.progress_bar)

        main_layout.addWidget(self.progress_widget)
        
        # 默认隐藏进度条，仅在知识库选择页显示
        self.progress_widget.setVisible(False)

        copyright_label = QLabel("Copyright © 2025-2026 By Be1k0")
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copyright_label.setObjectName("CopyrightLabel")
        main_layout.addWidget(copyright_label)

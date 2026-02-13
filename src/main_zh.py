import sys
import os
import subprocess
import logging
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QCheckBox, QFileDialog, QMessageBox,
    QGroupBox, QProgressBar, QTabWidget, QComboBox, QHeaderView,
    QListWidget, QListWidgetItem, QAbstractItemView, QTableWidget, QTableWidgetItem
)
from PySide6.QtCore import Qt, QThread, Signal, QSettings
from PySide6.QtGui import QFont, QIcon, QTextCursor

# 设置日志格式
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

class PackageThread(QThread):
    """执行打包命令的线程"""
    log_signal = Signal(str)
    progress_signal = Signal(int)
    finished_signal = Signal(bool)

    def __init__(self, command, parent=None):
        super().__init__(parent)
        self.command = command
        self.running = True
        self.process = None  # 添加对子进程的引用

    def run(self):
        """执行打包命令并捕获输出"""
        self.log_signal.emit(f"开始执行打包命令: {' '.join(self.command)}\n")
        try:
            # 创建子进程执行命令
            self.process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1
            )

            # 实时读取输出
            for line in iter(self.process.stdout.readline, ''):
                if not self.running:
                    break
                self.log_signal.emit(line.strip())

            # 等待进程结束
            return_code = self.process.wait()
            if return_code == 0:
                self.log_signal.emit("\n✅ 打包成功完成！")
                self.finished_signal.emit(True)
            else:
                self.log_signal.emit(f"\n❌ 打包失败，错误代码: {return_code}")
                self.finished_signal.emit(False)
        except Exception as e:
            self.log_signal.emit(f"\n❌ 执行过程中发生错误: {str(e)}")
            self.finished_signal.emit(False)

    def stop(self):
        """停止打包过程"""
        self.running = False
        self.log_signal.emit("\n🛑 用户请求停止打包...")

        # 尝试终止子进程
        if self.process:
            try:
                self.process.terminate()
            except Exception as e:
                self.log_signal.emit(f"⚠️ 终止进程失败: {str(e)}")


class NuitkaPackager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nuitka 高级打包工具")
        self.setGeometry(300, 50, 1200, 850)

        # 设置窗口图标
        self.setWindowIcon(QIcon("../icons/382_128x128.ico"))  # 替换为你的图标文件路径

        # 初始化QSettings用于持久化设置
        self.settings = QSettings("MyCompanyOrName", "NuitkaPackager")  # 根据需要调整名称

        # 加载主题设置，默认为深色主题
        # 设置以字符串形式加载("true"/"false")并转换为布尔值
        self.is_dark_theme = self.settings.value("dark_theme", True, type=bool)

        # 在QMainWindow上直接应用样式表

        # 初始化UI
        self.init_ui()

        self.plugins_info_label = None
        self.flags_info_label = None

        # 初始化状态
        self.python_path = ""
        self.main_file = ""
        self.icon_file = ""
        self.output_dir = ""
        self.package_thread = None
        self.plugins = []

        # 设置样式
        self.set_style()

        # 更新命令
        self.update_command()

    def init_ui(self):
        """初始化用户界面"""
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        # 主布局
        main_layout = QVBoxLayout(main_widget)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 标题行与主题切换按钮
        title_layout = QHBoxLayout()

        # 标题
        title_label = QLabel("Nuitka 高级打包工具")
        title_label.setFont(QFont("Arial", 18, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #2c3e50; margin-bottom: 15px;")

        # 主题切换按钮
        self.theme_toggle_btn = QPushButton("🌙 深色主题")
        self.theme_toggle_btn.setFixedHeight(30)
        self.theme_toggle_btn.setFixedWidth(120)
        self.theme_toggle_btn.clicked.connect(self.toggle_theme)

        title_layout.addWidget(title_label)
        title_layout.addWidget(self.theme_toggle_btn)
        main_layout.addLayout(title_layout)

        # 使用选项卡组织整个界面
        main_tab = QTabWidget()
        main_layout.addWidget(main_tab)

        # ===== 文件配置标签页 =====
        file_config_tab = QWidget()
        file_config_layout = QVBoxLayout(file_config_tab)
        file_config_layout.setContentsMargins(10, 10, 10, 10)
        file_config_layout.setSpacing(15)

        # 文件配置区域
        config_group = QGroupBox("文件路径配置")
        config_layout = QGridLayout(config_group)
        config_layout.setSpacing(10)
        config_layout.setContentsMargins(15, 15, 15, 15)

        # Python解释器选择
        self.python_label = QLabel("Python解释器:")
        self.python_input = QLineEdit()
        self.python_input.setPlaceholderText("请选择Python解释器 (位于venv/Scripts/python.exe)")
        self.python_btn = QPushButton("浏览...")
        self.python_btn.clicked.connect(self.select_python)

        # 主文件选择
        self.file_label = QLabel("主文件:")
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("请选择要打包的Python主文件")
        self.file_btn = QPushButton("浏览...")
        self.file_btn.clicked.connect(self.select_main_file)

        # 图标文件选择
        self.icon_label = QLabel("图标文件:")
        self.icon_input = QLineEdit()
        self.icon_input.setPlaceholderText("可选 - 选择程序图标(.ico)")
        self.icon_btn = QPushButton("浏览...")
        self.icon_btn.clicked.connect(self.select_icon)

        # 输出目录选择
        self.output_label = QLabel("输出目录:")
        self.output_input = QLineEdit()
        self.output_input.setPlaceholderText("选择打包结果输出目录")
        self.output_btn = QPushButton("浏览...")
        self.output_btn.clicked.connect(self.select_output_dir)

        # --- 数据文件/目录配置区域 ---
        data_group = QGroupBox("附加资源配置")
        data_layout = QVBoxLayout(data_group)

        # 使用表格展示：[类型, 源路径, 目标路径, 操作]
        self.data_table = QTableWidget(0, 3)
        self.data_table.setHorizontalHeaderLabels(["类型", "源路径", "目标相对路径"])
        self.data_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        data_layout.addWidget(self.data_table)

        # 按钮操作栏
        btn_layout = QHBoxLayout()
        self.add_dir_btn = QPushButton("添加目录")
        self.add_file_btn = QPushButton("添加文件")
        self.del_row_btn = QPushButton("删除选中项")

        btn_layout.addWidget(self.add_dir_btn)
        btn_layout.addWidget(self.add_file_btn)
        btn_layout.addStretch() # 弹簧
        btn_layout.addWidget(self.del_row_btn)
        data_layout.addLayout(btn_layout)

        self.add_dir_btn.clicked.connect(lambda: self.add_resource("dir"))
        self.add_file_btn.clicked.connect(lambda: self.add_resource("file"))
        self.del_row_btn.clicked.connect(self.remove_resource)

        # 添加配置项到布局
        config_layout.addWidget(self.python_label, 0, 0)
        config_layout.addWidget(self.python_input, 0, 1)
        config_layout.addWidget(self.python_btn, 0, 2)

        config_layout.addWidget(self.file_label, 1, 0)
        config_layout.addWidget(self.file_input, 1, 1)
        config_layout.addWidget(self.file_btn, 1, 2)

        config_layout.addWidget(self.icon_label, 2, 0)
        config_layout.addWidget(self.icon_input, 2, 1)
        config_layout.addWidget(self.icon_btn, 2, 2)

        config_layout.addWidget(self.output_label, 3, 0)
        config_layout.addWidget(self.output_input, 3, 1)
        config_layout.addWidget(self.output_btn, 3, 2)

        file_config_layout.addWidget(config_group)
        file_config_layout.addWidget(data_group)
        file_config_layout.addStretch()

        # 将文件配置标签页添加到主选项卡
        main_tab.addTab(file_config_tab, "文件配置")

        # ===== 常用选项标签页 =====
        common_tab = QWidget()
        common_layout = QVBoxLayout(common_tab)
        common_layout.setContentsMargins(10, 10, 10, 10)
        common_layout.setSpacing(15)

        # 常用选项组
        common_group = QGroupBox("常用打包选项")
        common_group_layout = QGridLayout(common_group)
        common_group_layout.setSpacing(10)

        # 常用选项
        self.onefile_check = QCheckBox("--onefile (打包为单个可执行文件)")
        self.onefile_check.setChecked(False)
        self.onefile_check.stateChanged.connect(self.update_command)

        self.standalone_check = QCheckBox("--standalone (独立模式，包含所有依赖)")
        self.standalone_check.setChecked(True)
        self.standalone_check.stateChanged.connect(self.update_command)

        self.disable_console_check = QCheckBox("--windows-disable-console (禁用控制台窗口)")
        self.disable_console_check.setChecked(True)
        self.disable_console_check.stateChanged.connect(self.update_command)

        self.remove_output_check = QCheckBox("--remove-output (打包后删除输出目录)")
        self.remove_output_check.setChecked(True)
        self.remove_output_check.stateChanged.connect(self.update_command)

        self.include_qt_check = QCheckBox("--include-qt (包含Qt插件，适用于PySide6/PyQt6)")
        self.include_qt_check.setChecked(False)
        self.include_qt_check.stateChanged.connect(self.update_command)

        self.show_progress_check = QCheckBox("--show-progress (显示打包进度)")
        self.show_progress_check.setChecked(True)
        self.show_progress_check.stateChanged.connect(self.update_command)

        self.show_memory_check = QCheckBox("--show-memory (显示内存使用情况)")
        self.show_memory_check.setChecked(False)
        self.show_memory_check.stateChanged.connect(self.update_command)

        # 添加常用选项到布局
        common_group_layout.addWidget(self.onefile_check, 0, 0)
        common_group_layout.addWidget(self.standalone_check, 0, 1)
        common_group_layout.addWidget(self.disable_console_check, 0, 2)

        common_group_layout.addWidget(self.remove_output_check, 1, 0)
        common_group_layout.addWidget(self.include_qt_check, 1, 1)
        common_group_layout.addWidget(self.show_progress_check, 1, 2)

        common_group_layout.addWidget(self.show_memory_check, 2, 0)

        common_layout.addWidget(common_group)
        common_layout.addStretch()

        # 将常用选项标签页添加到主选项卡
        main_tab.addTab(common_tab, "常用选项")

        # ===== 插件选项标签页 =====
        plugins_tab = QWidget()
        plugins_layout = QVBoxLayout(plugins_tab)
        plugins_layout.setContentsMargins(10, 10, 10, 10)
        plugins_layout.setSpacing(15)

        # 插件选项组
        plugins_group = QGroupBox("插件选项")
        plugins_group_layout = QVBoxLayout(plugins_group)

        # 添加插件说明
        plugins_info = QLabel("选择要启用的Nuitka插件。常用插件：\n"
                              "- pyside6: 支持PySide6框架\n"
                              "- tk-inter: 支持Tkinter GUI库\n"
                              "- numpy: 支持NumPy科学计算库\n"
                              "- multiprocessing: 支持多进程模块")
        plugins_info.setWordWrap(True)
        self.plugins_info_label = plugins_info
        plugins_group_layout.addWidget(plugins_info)

        self.plugins_list = QListWidget()
        self.plugins_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.plugins_list.setMinimumHeight(250)

        # 添加常见插件
        common_plugins = [
            "pyside6", "tk-inter", "numpy", "multiprocessing",
            "dill-compat", "gevent", "pylint-warnings", "qt-plugins",
            "anti-bloat", "playwright", "spacy", "pandas"
        ]
        for plugin in common_plugins:
            item = QListWidgetItem(f"--enable-plugin={plugin}")
            self.plugins_list.addItem(item)

        plugins_group_layout.addWidget(self.plugins_list)
        self.plugins_list.itemSelectionChanged.connect(self.update_command)

        plugins_layout.addWidget(plugins_group)
        plugins_layout.addStretch()

        # 将插件选项标签页添加到主选项卡
        main_tab.addTab(plugins_tab, "插件选项")

        # ===== Python标志标签页 =====
        flags_tab = QWidget()
        flags_layout = QVBoxLayout(flags_tab)
        flags_layout.setContentsMargins(10, 10, 10, 10)
        flags_layout.setSpacing(15)

        # Python标志选项组
        flags_group = QGroupBox("Python标志")
        flags_group_layout = QVBoxLayout(flags_group)
        flags_group_layout.setSpacing(10)

        # 添加标志说明
        flags_info = QLabel("Python标志用于设置Python解释器的运行时选项：\n"
                            "- no_site: 禁用site模块的导入\n"
                            "- no_warnings: 禁用警告信息\n"
                            "- no_asserts: 禁用assert语句\n"
                            "- no_docstrings: 禁用文档字符串\n"
                            "- unbuffered: 禁用输出缓冲\n"
                            "- static_hashes: 使用静态哈希值")
        flags_info.setWordWrap(True)
        self.flags_info_label = flags_info
        flags_group_layout.addWidget(flags_info)

        # 标志选择和添加按钮
        flags_selector_layout = QHBoxLayout()

        self.flags_combo = QComboBox()
        self.flags_combo.addItems([
            "--python-flag=no_site",
            "--python-flag=no_warnings",
            "--python-flag=no_asserts",
            "--python-flag=no_docstrings",
            "--python-flag=unbuffered",
            "--python-flag=static_hashes"
        ])
        self.flags_combo.setCurrentIndex(-1)
        self.flags_combo.setMinimumWidth(250)

        self.add_flag_btn = QPushButton("添加标志")
        self.add_flag_btn.clicked.connect(self.add_python_flag)
        self.add_flag_btn.setFixedWidth(100)

        self.remove_flag_btn = QPushButton("移除标志")
        self.remove_flag_btn.clicked.connect(self.remove_python_flag)
        self.remove_flag_btn.setFixedWidth(100)
        self.remove_flag_btn.setEnabled(False)

        flags_selector_layout.addWidget(self.flags_combo)
        flags_selector_layout.addWidget(self.add_flag_btn)
        flags_selector_layout.addWidget(self.remove_flag_btn)
        flags_selector_layout.addStretch()

        flags_group_layout.addLayout(flags_selector_layout)

        # 已选标志列表
        self.flags_list = QListWidget()
        self.flags_list.setMinimumHeight(120)
        self.flags_list.itemSelectionChanged.connect(self.toggle_remove_button)
        flags_group_layout.addWidget(self.flags_list)

        flags_layout.addWidget(flags_group)
        flags_layout.addStretch()

        # 将Python标志标签页添加到主选项卡
        main_tab.addTab(flags_tab, "Python标志")

        # ===== 高级选项标签页 =====
        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout(advanced_tab)
        advanced_layout.setContentsMargins(10, 10, 10, 10)
        advanced_layout.setSpacing(15)

        # 高级选项组
        advanced_group = QGroupBox("高级打包选项")
        advanced_group_layout = QGridLayout(advanced_group)
        advanced_group_layout.setSpacing(10)

        # 高级选项
        self.follow_imports_check = QCheckBox("--follow-imports (包含所有导入的模块)")
        self.follow_imports_check.setChecked(True)
        self.follow_imports_check.stateChanged.connect(self.update_command)

        self.follow_stdlib_check = QCheckBox("--follow-stdlib (包含标准库模块)")
        self.follow_stdlib_check.setChecked(False)
        self.follow_stdlib_check.stateChanged.connect(self.update_command)

        self.module_mode_check = QCheckBox("--module (创建可导入的二进制扩展模块)")
        self.module_mode_check.setChecked(False)
        self.module_mode_check.stateChanged.connect(self.update_command)

        self.lto_check = QCheckBox("--lto (启用链接时间优化)")
        self.lto_check.setChecked(False)
        self.lto_check.stateChanged.connect(self.update_command)

        self.disable_ccache_check = QCheckBox("--disable-ccache (禁用ccache缓存)")
        self.disable_ccache_check.setChecked(False)
        self.disable_ccache_check.stateChanged.connect(self.update_command)

        self.assume_yes_check = QCheckBox("--assume-yes (对所有问题回答yes)")
        self.assume_yes_check.setChecked(False)
        self.assume_yes_check.stateChanged.connect(self.update_command)

        self.windows_uac_admin_check = QCheckBox("--windows-uac-admin (请求管理员权限)")
        self.windows_uac_admin_check.setChecked(False)
        self.windows_uac_admin_check.stateChanged.connect(self.update_command)

        self.windows_uac_uiaccess_check = QCheckBox("--windows-uac-uiaccess (允许提升的应用程序与桌面交互)")
        self.windows_uac_uiaccess_check.setChecked(False)
        self.windows_uac_uiaccess_check.stateChanged.connect(self.update_command)

        # 添加高级选项到布局
        advanced_group_layout.addWidget(self.follow_imports_check, 0, 0)
        advanced_group_layout.addWidget(self.follow_stdlib_check, 0, 1)
        advanced_group_layout.addWidget(self.module_mode_check, 0, 2)

        advanced_group_layout.addWidget(self.lto_check, 1, 0)
        advanced_group_layout.addWidget(self.disable_ccache_check, 1, 1)
        advanced_group_layout.addWidget(self.assume_yes_check, 1, 2)

        advanced_group_layout.addWidget(self.windows_uac_admin_check, 2, 0)
        advanced_group_layout.addWidget(self.windows_uac_uiaccess_check, 2, 1)

        advanced_layout.addWidget(advanced_group)

        # 包含选项组
        include_group = QGroupBox("包含选项")
        include_layout = QGridLayout(include_group)
        include_layout.setSpacing(10)

        # 包含包
        self.include_package_label = QLabel("包含包:")
        self.include_package_input = QLineEdit()
        self.include_package_input.setPlaceholderText("包名 (e.g., mypackage)")
        self.include_package_input.setMinimumWidth(300)  # 防止压缩
        self.include_package_input.setMinimumHeight(20)  # 设置最小高度
        self.include_package_input.textChanged.connect(self.update_command)

        # 包含包数据
        self.include_package_data_label = QLabel("包含包数据:")
        self.include_package_data_input = QLineEdit()
        self.include_package_data_input.setPlaceholderText("包名:文件模式 (e.g., mypackage:*.txt)")
        self.include_package_data_input.setMinimumWidth(300)  # 防止压缩
        self.include_package_data_input.setMinimumHeight(20)  # 设置最小高度
        self.include_package_data_input.textChanged.connect(self.update_command)

        # 包含模块
        self.include_module_label = QLabel("包含模块:")
        self.include_module_input = QLineEdit()
        self.include_module_input.setPlaceholderText("模块名 (e.g., mymodule)")
        self.include_module_input.setMinimumWidth(300)  # 防止压缩
        self.include_module_input.setMinimumHeight(20)  # 设置最小高度
        self.include_module_input.textChanged.connect(self.update_command)

        # 排除数据文件
        self.noinclude_data_label = QLabel("排除数据文件:")
        self.noinclude_data_input = QLineEdit()
        self.noinclude_data_input.setPlaceholderText("文件模式 (e.g., *.tmp)")
        self.noinclude_data_input.setMinimumWidth(300)  # 防止压缩
        self.noinclude_data_input.setMinimumHeight(20)  # 设置最小高度
        self.noinclude_data_input.textChanged.connect(self.update_command)

        # 单文件外部数据
        self.include_onefile_ext_label = QLabel("单文件外部数据:")
        self.include_onefile_ext_input = QLineEdit()
        self.include_onefile_ext_input.setPlaceholderText("文件模式 (e.g., large_files/*)")
        self.include_onefile_ext_input.setMinimumWidth(300)  # 防止压缩
        self.include_onefile_ext_input.setMinimumHeight(20)  # 设置最小高度
        self.include_onefile_ext_input.textChanged.connect(self.update_command)

        # 包含原始目录
        self.include_raw_dir_label = QLabel("包含原始目录:")
        self.include_raw_dir_input = QLineEdit()
        self.include_raw_dir_input.setPlaceholderText("目录路径 (e.g., ./raw_data)")
        self.include_raw_dir_input.setMinimumWidth(300)  # 防止压缩
        self.include_raw_dir_input.setMinimumHeight(20)  # 设置最小高度
        self.include_raw_dir_input.textChanged.connect(self.update_command)

        # 添加包含选项到布局
        include_layout.addWidget(self.include_package_label, 0, 0)
        include_layout.addWidget(self.include_package_input, 0, 1)

        include_layout.addWidget(self.include_package_data_label, 1, 0)
        include_layout.addWidget(self.include_package_data_input, 1, 1)

        include_layout.addWidget(self.include_module_label, 2, 0)
        include_layout.addWidget(self.include_module_input, 2, 1)

        include_layout.addWidget(self.noinclude_data_label, 3, 0)
        include_layout.addWidget(self.noinclude_data_input, 3, 1)

        include_layout.addWidget(self.include_onefile_ext_label, 4, 0)
        include_layout.addWidget(self.include_onefile_ext_input, 4, 1)

        include_layout.addWidget(self.include_raw_dir_label, 5, 0)
        include_layout.addWidget(self.include_raw_dir_input, 5, 1)

        advanced_layout.addWidget(include_group)
        advanced_layout.addStretch()

        # 将高级选项标签页添加到主选项卡
        main_tab.addTab(advanced_tab, "高级选项")

        # ===== 元数据标签页 =====
        metadata_tab = QWidget()
        metadata_layout = QVBoxLayout(metadata_tab)
        metadata_layout.setContentsMargins(10, 10, 10, 10)
        metadata_layout.setSpacing(15)

        # 元数据选项组
        metadata_group = QGroupBox("元数据信息")
        metadata_group_layout = QGridLayout(metadata_group)
        metadata_group_layout.setSpacing(10)

        # 元数据选项
        self.company_label = QLabel("公司名称:")
        self.company_input = QLineEdit()
        self.company_input.setPlaceholderText("可选 - 公司名称")
        self.company_input.textChanged.connect(self.update_command)

        self.product_label = QLabel("产品名称:")
        self.product_input = QLineEdit()
        self.product_input.setPlaceholderText("可选 - 产品名称")
        self.product_input.textChanged.connect(self.update_command)

        self.file_version_label = QLabel("文件版本:")
        self.file_version_input = QLineEdit()
        self.file_version_input.setPlaceholderText("格式: X.Y.Z.W")
        self.file_version_input.textChanged.connect(self.update_command)

        self.product_version_label = QLabel("产品版本:")
        self.product_version_input = QLineEdit()
        self.product_version_input.setPlaceholderText("格式: X.Y.Z.W")
        self.product_version_input.textChanged.connect(self.update_command)

        self.file_description_label = QLabel("文件描述:")
        self.file_description_input = QLineEdit()
        self.file_description_input.setPlaceholderText("可选 - 文件描述")
        self.file_description_input.textChanged.connect(self.update_command)

        self.copyright_label = QLabel("版权信息:")
        self.copyright_input = QLineEdit()
        self.copyright_input.setPlaceholderText("可选 - 版权信息")
        self.copyright_input.textChanged.connect(self.update_command)

        # 添加元数据选项到布局
        metadata_group_layout.addWidget(self.company_label, 0, 0)
        metadata_group_layout.addWidget(self.company_input, 0, 1)

        metadata_group_layout.addWidget(self.product_label, 1, 0)
        metadata_group_layout.addWidget(self.product_input, 1, 1)

        metadata_group_layout.addWidget(self.file_version_label, 2, 0)
        metadata_group_layout.addWidget(self.file_version_input, 2, 1)

        metadata_group_layout.addWidget(self.product_version_label, 3, 0)
        metadata_group_layout.addWidget(self.product_version_input, 3, 1)

        metadata_group_layout.addWidget(self.file_description_label, 4, 0)
        metadata_group_layout.addWidget(self.file_description_input, 4, 1)

        metadata_group_layout.addWidget(self.copyright_label, 5, 0)
        metadata_group_layout.addWidget(self.copyright_input, 5, 1)

        metadata_layout.addWidget(metadata_group)

        # 环境控制组
        env_group = QGroupBox("环境控制")
        env_layout = QGridLayout(env_group)

        # 环境控制选项
        self.force_env_label = QLabel("强制环境变量:")
        self.force_env_input = QLineEdit()
        self.force_env_input.setPlaceholderText("变量名=值 (e.g., MY_VAR=123)")
        self.force_env_input.textChanged.connect(self.update_command)

        # 添加环境控制选项到布局
        env_layout.addWidget(self.force_env_label, 0, 0)
        env_layout.addWidget(self.force_env_input, 0, 1)

        metadata_layout.addWidget(env_group)
        metadata_layout.addStretch()

        # 将元数据标签页添加到主选项卡
        main_tab.addTab(metadata_tab, "元数据")

        # ===== 调试选项标签页 =====
        debug_tab = QWidget()
        debug_layout = QVBoxLayout(debug_tab)
        debug_layout.setContentsMargins(10, 10, 10, 10)
        debug_layout.setSpacing(15)

        # 调试选项组
        debug_group = QGroupBox("调试选项")
        debug_group_layout = QGridLayout(debug_group)
        debug_group_layout.setSpacing(10)

        # 调试选项
        self.debug_check = QCheckBox("--debug (启用调试模式)")
        self.debug_check.setChecked(False)
        self.debug_check.stateChanged.connect(self.update_command)

        self.unstripped_check = QCheckBox("--unstripped (保留调试信息)")
        self.unstripped_check.setChecked(False)
        self.unstripped_check.stateChanged.connect(self.update_command)

        self.trace_execution_check = QCheckBox("--trace-execution (跟踪执行)")
        self.trace_execution_check.setChecked(False)
        self.trace_execution_check.stateChanged.connect(self.update_command)

        self.warn_implicit_check = QCheckBox("--warn-implicit-exceptions (警告隐式异常)")
        self.warn_implicit_check.setChecked(False)
        self.warn_implicit_check.stateChanged.connect(self.update_command)

        self.warn_unusual_check = QCheckBox("--warn-unusual-code (警告非常规代码)")
        self.warn_unusual_check.setChecked(False)
        self.warn_unusual_check.stateChanged.connect(self.update_command)

        # 添加调试选项到布局
        debug_group_layout.addWidget(self.debug_check, 0, 0)
        debug_group_layout.addWidget(self.unstripped_check, 0, 1)

        debug_group_layout.addWidget(self.trace_execution_check, 1, 0)
        debug_group_layout.addWidget(self.warn_implicit_check, 1, 1)

        debug_group_layout.addWidget(self.warn_unusual_check, 2, 0)

        debug_layout.addWidget(debug_group)

        # 部署控制组
        deployment_group = QGroupBox("部署控制")
        deployment_layout = QGridLayout(deployment_group)

        # 部署控制选项
        self.deployment_check = QCheckBox("--deployment (启用部署模式)")
        self.deployment_check.setChecked(False)
        self.deployment_check.stateChanged.connect(self.update_command)

        # 添加部署控制选项到布局
        deployment_layout.addWidget(self.deployment_check, 0, 0)

        debug_layout.addWidget(deployment_group)
        debug_layout.addStretch()

        # 将调试选项标签页添加到主选项卡
        main_tab.addTab(debug_tab, "调试选项")

        # ===== 操作日志标签页 =====
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        log_layout.setContentsMargins(10, 10, 10, 10)
        log_layout.setSpacing(15)

        # 日志区域
        log_group = QGroupBox("操作日志")
        log_group_layout = QVBoxLayout(log_group)
        log_group_layout.setContentsMargins(15, 15, 15, 15)
        log_group.setMinimumHeight(450)  # 关键设置：固定最小高度

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Consolas", 9))
        log_group_layout.addWidget(self.log_edit)

        # 添加日志框到布局
        log_layout.addWidget(log_group)
        log_layout.addStretch()

        # 将操作日志标签页添加到主选项卡
        main_tab.addTab(log_tab, "操作日志")

        # 命令区域
        command_group = QGroupBox("打包命令")
        command_layout = QVBoxLayout(command_group)
        command_layout.setContentsMargins(15, 15, 15, 15)
        command_group.setMinimumHeight(150)  # 关键设置：固定最小高度

        self.command_edit = QTextEdit()
        self.command_edit.setPlaceholderText("生成的打包命令将显示在这里...")
        self.command_edit.setFont(QFont("Consolas", 10))
        self.command_edit.setMinimumHeight(80)
        command_layout.addWidget(self.command_edit)

        main_layout.addWidget(command_group)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)
        main_layout.addWidget(self.progress_bar)

        # 按钮区域
        button_layout = QHBoxLayout()

        self.execute_btn = QPushButton("开始打包")
        self.execute_btn.setFixedHeight(40)
        self.execute_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
            }
        """)
        self.execute_btn.clicked.connect(self.execute_package)

        self.stop_btn = QPushButton("停止打包")
        self.stop_btn.setFixedHeight(40)
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
            }
        """)
        self.stop_btn.clicked.connect(self.stop_package)
        self.stop_btn.setEnabled(False)

        self.clear_btn = QPushButton("清除日志")
        self.clear_btn.setFixedHeight(40)
        self.clear_btn.clicked.connect(self.clear_log)

        button_layout.addWidget(self.execute_btn)
        button_layout.addWidget(self.stop_btn)
        button_layout.addWidget(self.clear_btn)

        main_layout.addLayout(button_layout)

        # 状态栏
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("就绪 - 请配置打包选项")

    def toggle_theme(self):
        """在深色和浅色主题之间切换"""
        self.is_dark_theme = not self.is_dark_theme
        # 更新按钮文本和图标
        if self.is_dark_theme:
            self.theme_toggle_btn.setText("🌙 深色主题")
        else:
            self.theme_toggle_btn.setText("☀️ 浅色主题")
        # 应用新主题
        self.set_style()
        # 持久保存当前主题设置
        self.settings.setValue("dark_theme", self.is_dark_theme)
        # 记录主题更改
        theme_name = "深色" if self.is_dark_theme else "浅色"
        self.log_message(f"🎨 切换到{theme_name}主题并保存偏好设置")

    def add_python_flag(self):
        """添加Python标志到列表"""
        flag = self.flags_combo.currentText()
        if flag and not self.flag_exists(flag):
            self.flags_list.addItem(flag)
            self.update_command()

    def remove_python_flag(self):
        """移除选中的Python标志"""
        selected_items = self.flags_list.selectedItems()
        if not selected_items:
            return

        for item in selected_items:
            self.flags_list.takeItem(self.flags_list.row(item))
        self.update_command()

    def toggle_remove_button(self):
        """根据选择状态启用/禁用移除按钮"""
        self.remove_flag_btn.setEnabled(bool(self.flags_list.selectedItems()))

    def flag_exists(self, flag):
        """检查标志是否已存在"""
        for i in range(self.flags_list.count()):
            if self.flags_list.item(i).text() == flag:
                return True
        return False

    def set_style(self):
        """设置应用程序样式基于主题"""
        # 存储对信息标签的引用（如果尚未完成）
        # 这些行确保引用存在。它们是幂等的。
        if not hasattr(self, 'plugins_info_label') or self.plugins_info_label is None:
            # 查找插件信息标签。它在插件选项卡的组框内。
            # 假设选项卡顺序：文件配置(0), 常用选项(1), 插件(2), Python标志(3)...
            try:
                plugins_tab = self.centralWidget().findChild(QWidget, "qt_tabwidget_stackedwidget").widget(2)
                if plugins_tab:
                    # 查找第一个QLabel，应该是信息标签
                    self.plugins_info_label = plugins_tab.findChild(QLabel)
            except Exception:
                self.plugins_info_label = None  # 如果找不到则回退

        if not hasattr(self, 'flags_info_label') or self.flags_info_label is None:
            # 查找标志信息标签。它在Python标志选项卡的组框内。
            try:
                flags_tab = self.centralWidget().findChild(QWidget, "qt_tabwidget_stackedwidget").widget(3)
                if flags_tab:
                    # 查找第一个QLabel，应该是信息标签
                    self.flags_info_label = flags_tab.findChild(QLabel)
            except Exception:
                self.flags_info_label = None  # 如果找不到则回退

        if self.is_dark_theme:
            # 深色主题
            # 定义主窗口背景（包括潜在的QStatusBar基础）
            main_bg = """
            QMainWindow {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #0d0d0f,
                    stop: 0.4 #1a1a1f,
                    stop: 0.7 #0f1f2f,
                    stop: 1 #0d0d0f
                );
            }
            """
            # 为深色主题定义QStatusBar样式
            # 这将直接应用于QMainWindow
            statusbar_style = """
            QStatusBar {
                background-color: #333; /* 深色背景，匹配QGroupBox */
                color: #ffffff;        /* 白色文本 */
                border-top: 1px solid #555; /* 可选：顶部分隔线 */
            }
            QStatusBar QLabel { /* 确保状态栏内的标签为白色 */
                color: #ffffff;
            }
            """
            # 定义小部件样式（不含QStatusBar规则）
            widget_style = """
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555;
                border-radius: 8px;
                margin-top: 1.5em;
                background-color: #333;
                color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                background-color: transparent;
                color: #ffffff;
            }
            QTextEdit {
                background-color: #1e1e1e;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 5px;
                color: #ffffff;
            }
            QLineEdit, QComboBox, QListWidget {
                background-color: #1e1e1e;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 5px;
                color: #ffffff;
            }
            QLineEdit:disabled, QTextEdit:disabled {
                background-color: #444;
                color: #888;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #666;
            }
            QLabel {
                color: #ffffff;
            }
            QProgressBar {
                border: 1px solid #555;
                border-radius: 5px;
                background-color: #1e1e1e;
            }
            QProgressBar::chunk {
                background-color: #2ecc71;
                border-radius: 4px;
            }
            QTabWidget::pane {
                border: 1px solid #555;
                border-radius: 5px;
                background: #333;
            }
            QTabBar::tab {
                background: #444;
                border: 1px solid #555;
                border-bottom: none;
                padding: 8px 15px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                color: #ffffff;
            }
            QTabBar::tab:selected {
                background: #3498db;
                color: white;
            }
            QTabBar::tab:hover {
                background: #2980b9;
                color: white;
            }
            QListWidget::item:selected {
                background-color: #3498db;
                color: white;
                border-radius: 3px;
            }
            QCheckBox {
                color: #ffffff;
            }
            /* 表格整体样式 */
            QTableWidget {
                background-color: #1e1e1e;
                border: 1px solid #555;
                gridline-color: #444;
                color: #ffffff;
                border-radius: 4px;
                selection-background-color: #3498db;
                selection-color: white;
            }
            /* 表头样式 */
            QHeaderView::section {
                background-color: #2c2c2e;
                color: #ffffff;
                padding: 5px;
                border: 1px solid #555;
                font-weight: bold;
            }
            /* 表格左上角空白区域 */
            QTableCornerButton::section {
                background-color: #2c2c2e;
                border: 1px solid #555;
            }
            /* 滚动条美化（可选，增加一致性） */
            QScrollBar:vertical {
                border: none;
                background: #2c2c2e;
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background: #555;
                min-height: 20px;
                border-radius: 5px;
            }
            QSpinBox {
                background-color: #1e1e1e;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 5px;
                color: #ffffff;
                min-height: 20px;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background-color: #3498db;
                border: 1px solid #555;
                border-radius: 3px;
                width: 18px;
                height: 14px;
                margin: 2px;
                subcontrol-position: right;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background-color: #2980b9;
            }
            QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {
                background-color: #1c5980;
            }
            QSpinBox::up-button:disabled, QSpinBox::down-button:disabled {
                background-color: #666;
                border-color: #444;
            }
            QSpinBox::up-arrow {
                width: 6px;
                height: 6px;
                image: none;
                border-left: 2px solid #ffffff;
                border-bottom: 2px solid #ffffff;
                transform: rotate(45deg);
                margin: 3px;
            }
            QSpinBox::down-arrow {
                width: 6px;
                height: 6px;
                image: none;
                border-left: 2px solid #ffffff;
                border-top: 2px solid #ffffff;
                transform: rotate(45deg);
                margin: 3px;
            }
            """  # <--- widget_style字符串结束（QStatusBar规则已移除）

            # 为深色主题中的信息标签应用特定样式
            if hasattr(self, 'plugins_info_label') and self.plugins_info_label:
                self.plugins_info_label.setStyleSheet("""
                    background-color: #2c2c2e;
                    color: #ffffff;
                    padding: 8px;
                    border-radius: 4px;
                """)
            if hasattr(self, 'flags_info_label') and self.flags_info_label:
                self.flags_info_label.setStyleSheet("""
                    background-color: #2c2c2e;
                    color: #ffffff;
                    padding: 8px;
                    border-radius: 4px;
                """)

            # 应用样式
            # 将主背景和状态栏样式应用于QMainWindow
            self.setStyleSheet(main_bg + statusbar_style)
            # 将深色小部件样式应用于中央小部件
            self.centralWidget().setStyleSheet(widget_style)

        else:
            # 浅色主题
            # QMainWindow的简单背景
            main_light_bg = "QMainWindow { background-color: #f5f7fa; }"
            # 为浅色主题定义QStatusBar样式
            # 这将直接应用于QMainWindow
            statusbar_style = """
            QStatusBar {
                background-color: #f5f7fa; /* 浅色背景，匹配主窗口 */
                color: #2c3e50;           /* 深色文本 */
                border-top: 1px solid #dcdde1; /* 可选：顶部分隔线 */
            }
            """
            # 定义浅色小部件样式（不含QStatusBar规则）
            light_widget_style = """
            QGroupBox {
                font-weight: bold;
                border: 1px solid #dcdde1;
                border-radius: 8px;
                margin-top: 1.5em;
                background-color: white;
                color: #2c3e50;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                background-color: transparent;
                color: #2c3e50;
            }
            QTextEdit {
                background-color: white;
                border: 1px solid #dcdde1;
                border-radius: 4px;
                padding: 5px;
                color: #2c3e50;
            }
            QLineEdit, QComboBox, QListWidget {
                background-color: white;
                border: 1px solid #dcdde1;
                border-radius: 4px;
                padding: 5px;
                color: #2c3e50;
            }
            QLineEdit:disabled, QTextEdit:disabled {
                background-color: #ecf0f1;
                color: #7f8c8d;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
            }
            QLabel {
                color: #2c3e50;
            }
            QProgressBar {
                border: 1px solid #dcdde1;
                border-radius: 5px;
                background-color: white;
            }
            QProgressBar::chunk {
                background-color: #2ecc71;
                border-radius: 4px;
            }
            QTabWidget::pane {
                border: 1px solid #dcdde1;
                border-radius: 5px;
                background: white;
            }
            QTabBar::tab {
                background: #ecf0f1;
                border: 1px solid #dcdde1;
                border-bottom: none;
                padding: 8px 15px;
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                color: #2c3e50;
            }
            QTabBar::tab:selected {
                background: #3498db;
                color: white;
            }
            QTabBar::tab:hover {
                background: #2980b9;
                color: white;
            }
            QListWidget::item:selected {
                background-color: #3498db;
                color: white;
                border-radius: 3px;
            }
            QCheckBox {
                color: #2c3e50;
            }
            /* 表格整体样式 */
            QTableWidget {
                background-color: white;
                border: 1px solid #dcdde1;
                gridline-color: #f0f0f0;
                color: #2c3e50;
                border-radius: 4px;
                selection-background-color: #3498db;
                selection-color: white;
            }
            /* 表头样式 */
            QHeaderView::section {
                background-color: #ecf0f1;
                color: #2c3e50;
                padding: 5px;
                border: 1px solid #dcdde1;
                font-weight: bold;
            }
            /* 表格左上角空白区域 */
            QTableCornerButton::section {
                background-color: #ecf0f1;
                border: 1px solid #dcdde1;
            }
            QSpinBox {
                background-color: white;
                border: 1px solid #dcdde1;
                border-radius: 4px;
                padding: 5px;
                color: #2c3e50;
                min-height: 20px;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                background-color: #3498db;
                border: 1px solid #dcdde1;
                border-radius: 3px;
                width: 18px;
                height: 14px;
                margin: 2px;
                subcontrol-position: right;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background-color: #2980b9;
            }
            QSpinBox::up-button:pressed, QSpinBox::down-button:pressed {
                background-color: #1c5980;
            }
            QSpinBox::up-button:disabled, QSpinBox::down-button:disabled {
                background-color: #bdc3c7;
                border-color: #95a5a6;
            }
            QSpinBox::up-arrow {
                width: 6px;
                height: 6px;
                image: none;
                border-left: 2px solid #ffffff;
                border-bottom: 2px solid #ffffff;
                transform: rotate(45deg);
                margin: 3px;
            }
            QSpinBox::down-arrow {
                width: 6px;
                height: 6px;
                image: none;
                border-left: 2px solid #ffffff;
                border-top: 2px solid #ffffff;
                transform: rotate(45deg);
                margin: 3px;
            }
            """  # <--- light_widget_style字符串结束（QStatusBar规则已移除）

            # 为浅色主题中的信息标签应用特定样式
            # 如果需要，重置为默认或浅色特定样式
            if hasattr(self, 'plugins_info_label') and self.plugins_info_label:
                # 重新应用原始浅色样式或合适的样式
                self.plugins_info_label.setStyleSheet("""
                    background-color: #f8f9fa;
                    color: #2c3e50;
                    padding: 8px;
                    border-radius: 4px;
                """)
            if hasattr(self, 'flags_info_label') and self.flags_info_label:
                # 重新应用原始浅色样式或合适的样式
                self.flags_info_label.setStyleSheet("""
                    background-color: #f8f9fa;
                    color: #2c3e50;
                    padding: 8px;
                    border-radius: 4px;
                """)

            # 应用样式
            # 将浅色背景和状态栏样式应用于QMainWindow
            self.setStyleSheet(main_light_bg + statusbar_style)
            # 将浅色小部件样式应用于中央小部件
            self.centralWidget().setStyleSheet(light_widget_style)

    def get_messagebox_style(self):
        """根据当前主题生成QMessageBox的样式表"""
        if self.is_dark_theme:
            # QMessageBox的深色主题样式表
            return """
            QMessageBox {
                background-color: #2c2c2e; /* 深色背景 */
                color: #ffffff;           /* 白色文本 */
            }
            QMessageBox QLabel {
                color: #ffffff; /* 确保消息文本为白色 */
            }
            QMessageBox QPushButton {
                background-color: #3498db; /* 蓝色按钮背景 */
                color: white;             /* 白色按钮文本 */
                border: 1px solid #555;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QMessageBox QPushButton:hover {
                background-color: #2980b9; /* 悬停时更深的蓝色 */
            }
            QMessageBox QPushButton:pressed {
                background-color: #1c5980; /* 按下时更深的蓝色 */
            }
            /* 如果需要，设置图标样式，但通常不需要 */
            """
        else:
            # 如果需要，定义特定的浅色主题样式，或返回空字符串
            # 使用默认的操作系统/应用程序浅色主题。
            # 通常，默认的浅色主题就可以了，但你可以自定义它。
            return """
            QMessageBox {
                background-color: #f5f7fa; /* 浅色背景 */
                color: #2c3e50;           /* 深色文本 */
            }
            QMessageBox QLabel {
                color: #2c3e50; /* 确保消息文本为深色 */
            }
            QMessageBox QPushButton {
                background-color: #3498db; /* 蓝色按钮背景 */
                color: white;             /* 白色按钮文本 */
                border: 1px solid #dcdde1;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QMessageBox QPushButton:hover {
                background-color: #2980b9; /* 悬停时更深的蓝色 */
            }
            QMessageBox QPushButton:pressed {
                background-color: #1c5980; /* 按下时更深的蓝色 */
            }
            """

    def log_message(self, message):
        """在日志框中添加消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_edit.append(f"[{timestamp}] {message}")
        self.log_edit.moveCursor(QTextCursor.End)

        # 在状态栏显示最后一条消息
        self.status_bar.showMessage(message)

    def select_python(self):
        """选择Python解释器"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择Python解释器", "", "Python 解释器 (python.exe python.cmd);;所有文件 (*)"
        )
        if file_path:
            self.python_path = file_path
            self.python_input.setText(file_path)

            # 检查是否安装了Nuitka
            if not self.check_nuitka_installed():
                QMessageBox.warning(
                    self,
                    "Nuitka未安装",
                    "在选定的Python环境中未检测到Nuitka。\n请使用以下命令安装: pip install nuitka",
                    QMessageBox.Ok
                )
            else:
                self.log_message("✓ Nuitka已安装在选定的Python环境中")

    def check_nuitka_installed(self):
        """检查选定的Python环境中是否安装了Nuitka"""
        try:
            # 方法1：检查解释器路径是否直接指向nuitka（特殊情况处理）
            if "nuitka" in self.python_path.lower():
                return True

            # 方法2：最可靠的方法 - 尝试执行 nuitka --version
            try:
                result = subprocess.run(
                    [self.python_path, "-m", "nuitka", "--version"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=2,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                if result.returncode == 0:
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

            # 方法3：检查虚拟环境的可执行文件目录
            # 获取虚拟环境的基础目录
            env_base = os.path.dirname(os.path.dirname(self.python_path))

            # 确定脚本目录名称 (Windows: Scripts, Unix: bin)
            scripts_dir = "Scripts" if sys.platform.startswith("win") else "bin"
            scripts_path = os.path.join(env_base, scripts_dir)

            # 检查可能的可执行文件
            for exe_name in ["nuitka", "nuitka.exe", "nuitka.cmd", "nuitka-script.py"]:
                exe_path = os.path.join(scripts_path, exe_name)
                if os.path.exists(exe_path):
                    return True

            # 方法4：检查包元数据（兼容uv/pip）
            # 优先尝试uv，再尝试pip
            for module in ["uv", "pip"]:
                try:
                    result = subprocess.run(
                        [self.python_path, "-m", module, "show", "nuitka"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=2,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    # 检查是否成功且包含包信息
                    if result.returncode == 0 and "Name: nuitka" in result.stdout:
                        return True
                except:
                    continue

            return False
        except Exception:
            return False

    def select_main_file(self):
        """选择主Python文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择主Python文件", "", "Python 文件 (*.py);;所有文件 (*)"
        )
        if file_path:
            self.main_file = file_path
            self.file_input.setText(file_path)

    def select_icon(self):
        """选择图标文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图标文件", "", "图标文件 (*.ico);;所有文件 (*)"
        )
        if file_path:
            self.icon_file = file_path
            self.icon_input.setText(file_path)

    def select_output_dir(self):
        """选择输出目录"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择输出目录", "", QFileDialog.ShowDirsOnly
        )
        if dir_path:
            self.output_dir = dir_path
            self.output_input.setText(dir_path)
    
    def add_resource(self, mode):
        """选择资源并添加到表格"""
        if mode == "dir":
            path = QFileDialog.getExistingDirectory(self, "选择数据目录")
            type_text = "目录"
        else:
            path, _ = QFileDialog.getOpenFileName(self, "选择数据文件")
            type_text = "文件"

        if path:
            import os
            row = self.data_table.rowCount()
            self.data_table.insertRow(row)
            
            # 设置类型和路径
            self.data_table.setItem(row, 0, QTableWidgetItem(type_text))
            self.data_table.setItem(row, 1, QTableWidgetItem(path))
            
            # 设置默认目标路径：如果是目录则用原目录名，如果是文件则用原文件名
            default_dest = os.path.basename(path)
            self.data_table.setItem(row, 2, QTableWidgetItem(default_dest))

    def remove_resource(self):
        """删除选中行"""
        curr = self.data_table.currentRow()
        if curr >= 0:
            self.data_table.removeRow(curr)

    def update_command(self):
        """根据用户选择更新打包命令"""
        if not self.python_path or not self.main_file:
            self.command_edit.setPlainText("1.请先选择Python解释器和主文件 \n2.选择常用选项以更新打包命令")
            return

        # 构建基本命令
        command = [
            self.python_path,
            "-m", "nuitka"
        ]

        # 如果是uv环境，直接使用nuitka.cmd
        if self.python_path.endswith("nuitka.cmd"):
            command = [self.python_path]

        # ===== 常用选项 =====
        if self.onefile_check.isChecked():
            command.append("--onefile")

        if self.standalone_check.isChecked():
            command.append("--standalone")

        if self.disable_console_check.isChecked():
            command.append("--windows-disable-console")

        if self.remove_output_check.isChecked():
            command.append("--remove-output")

        if self.include_qt_check.isChecked():
            command.append("--include-qt-plugins=sensible,styles")

        if self.show_progress_check.isChecked():
            command.append("--show-progress")

        if self.show_memory_check.isChecked():
            command.append("--show-memory")

        # 添加图标
        if self.icon_file:
            command.append(f"--windows-icon-from-ico={self.icon_file}")

        # 添加输出目录
        if self.output_dir:
            command.append(f"--output-dir={self.output_dir}")
        
        # 处理表格中的附加资源
        for row in range(self.data_table.rowCount()):
            res_type = self.data_table.item(row, 0).text()
            src_path = self.data_table.item(row, 1).text()
            dst_path = self.data_table.item(row, 2).text()
            
            # 根据类型选择参数名
            arg_name = "--include-data-dir" if res_type == "目录" else "--include-data-files"
            
            if src_path and dst_path:
                command.append(f"{arg_name}={src_path}={dst_path}")

        # ===== 插件选项 =====
        selected_plugins = [item.text().split('=')[1] for item in self.plugins_list.selectedItems()]
        for plugin in selected_plugins:
            command.append(f"--enable-plugin={plugin}")

        # ===== 高级选项 =====
        if self.follow_imports_check.isChecked():
            command.append("--follow-imports")

        if self.follow_stdlib_check.isChecked():
            command.append("--follow-stdlib")

        if self.module_mode_check.isChecked():
            command.append("--module")

        if self.lto_check.isChecked():
            command.append("--lto=yes")

        if self.disable_ccache_check.isChecked():
            command.append("--disable-ccache")

        if self.assume_yes_check.isChecked():
            command.append("--assume-yes")

        if self.windows_uac_admin_check.isChecked():
            command.append("--windows-uac-admin")

        if self.windows_uac_uiaccess_check.isChecked():
            command.append("--windows-uac-uiaccess")

        # ===== 包含选项 =====
        # 包含包
        if self.include_package_input.text():
            packages = [pkg.strip() for pkg in self.include_package_input.text().split(',') if pkg.strip()]
            for pkg in packages:
                command.append(f"--include-package={pkg}")

        # 包含包数据
        if self.include_package_data_input.text():
            package_data = [pd.strip() for pd in self.include_package_data_input.text().split(',') if pd.strip()]
            for pd in package_data:
                command.append(f"--include-package-data={pd}")

        # 包含模块
        if self.include_module_input.text():
            modules = [mod.strip() for mod in self.include_module_input.text().split(',') if mod.strip()]
            for mod in modules:
                command.append(f"--include-module={mod}")
  
        # 排除数据文件
        if self.noinclude_data_input.text():
            exclude_data = [ed.strip() for ed in self.noinclude_data_input.text().split(',') if ed.strip()]
            for ed in exclude_data:
                command.append(f"--noinclude-data-files={ed}")

        # 单文件外部数据 (仅当单文件模式启用时添加)
        if self.onefile_check.isChecked() and self.include_onefile_ext_input.text():
            onefile_ext = [oe.strip() for oe in self.include_onefile_ext_input.text().split(',') if oe.strip()]
            for oe in onefile_ext:
                command.append(f"--include-onefile-external-data={oe}")

        # 包含原始目录
        if self.include_raw_dir_input.text():
            raw_dirs = [rd.strip() for rd in self.include_raw_dir_input.text().split(',') if rd.strip()]
            for rd in raw_dirs:
                command.append(f"--include-raw-dir={rd}")

        # ===== Python标志 =====
        for i in range(self.flags_list.count()):
            command.append(self.flags_list.item(i).text())

        # ===== 元数据 =====
        if self.company_input.text():
            command.append(f"--company-name={self.company_input.text()}")

        if self.product_input.text():
            command.append(f"--product-name={self.product_input.text()}")

        if self.file_version_input.text():
            command.append(f"--file-version={self.file_version_input.text()}")

        if self.product_version_input.text():
            command.append(f"--product-version={self.product_version_input.text()}")

        if self.file_description_input.text():
            command.append(f"--file-description={self.file_description_input.text()}")

        if self.copyright_input.text():
            command.append(f"--copyright={self.copyright_input.text()}")

        # ===== 环境控制 =====
        if self.force_env_input.text():
            command.append(f"--force-runtime-environment-variable={self.force_env_input.text()}")

        # ===== 调试选项 =====
        if self.debug_check.isChecked():
            command.append("--debug")

        if self.unstripped_check.isChecked():
            command.append("--unstripped")

        if self.trace_execution_check.isChecked():
            command.append("--trace-execution")

        if self.warn_implicit_check.isChecked():
            command.append("--warn-implicit-exceptions")

        if self.warn_unusual_check.isChecked():
            command.append("--warn-unusual-code")

        if self.deployment_check.isChecked():
            command.append("--deployment")

        # 添加主文件
        command.append(self.main_file)

        # 显示命令
        self.command_edit.setPlainText(" ".join(command))

    def execute_package(self):
        """执行打包命令"""
        # 检查是否有正在运行的打包线程
        if self.package_thread and self.package_thread.isRunning():
            self.log_message("⚠️ 已有打包任务在进行中")
            return

        # 验证必要输入
        if not self.python_path:
            QMessageBox.warning(self, "缺少配置", "请选择Python解释器")
            return

        if not self.main_file:
            QMessageBox.warning(self, "缺少配置", "请选择主文件")
            return

        if not self.output_dir:
            QMessageBox.warning(self, "缺少配置", "请选择输出目录")
            return

        # 检查Nuitka是否安装
        if not self.check_nuitka_installed():
            QMessageBox.warning(
                self,
                "Nuitka未安装",
                "在选定的Python环境中未检测到Nuitka。\n请使用以下命令安装: pip install nuitka",
                QMessageBox.Ok
            )
            return

        # 获取命令
        command = self.command_edit.toPlainText().split()

        # 创建并启动打包线程
        self.package_thread = PackageThread(command)
        self.package_thread.log_signal.connect(self.log_message)
        self.package_thread.finished_signal.connect(self.package_finished)

        # 更新UI状态
        self.execute_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)

        # 启动线程
        self.package_thread.start()
        self.log_message("▶ 开始打包进程...")

        # 模拟进度更新（实际进度需要从输出中解析）
        self.progress_timer = self.startTimer(1000)

        # 自动切换到日志标签页 - 修复版
        # 获取主选项卡控件
        main_tab = self.findChild(QTabWidget)
        if main_tab:
            # 查找"操作日志"标签页的索引
            for i in range(main_tab.count()):
                if main_tab.tabText(i) == "操作日志":
                    main_tab.setCurrentIndex(i)
                    break

    def timerEvent(self, event):
        """定时器事件，用于更新进度条"""
        if self.progress_bar.value() < 90:
            self.progress_bar.setValue(self.progress_bar.value() + 5)

    def stop_package(self):
        """停止打包过程"""
        if self.package_thread and self.package_thread.isRunning():
            self.package_thread.stop()
            self.log_message("🛑 用户请求停止打包...")
            self.stop_btn.setEnabled(False)

            # 尝试正常等待线程结束
            if not self.package_thread.wait(2000):  # 等待2秒
                # 如果线程仍在运行，强制终止
                self.package_thread.terminate()
                self.log_message("⚠️ 强制终止打包线程")

            # 立即重置按钮状态
            self.execute_btn.setEnabled(True)
            self.progress_bar.setValue(0)

            # 停止进度更新
            if hasattr(self, 'progress_timer'):
                self.killTimer(self.progress_timer)

    def package_finished(self, success):
        """打包完成后的处理"""
        # 总是更新UI状态
        self.execute_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        # 完成进度条
        self.progress_bar.setValue(100 if success else 0)

        # 停止进度更新
        if hasattr(self, 'progress_timer'):
            self.killTimer(self.progress_timer)

        if success:
            self.log_message("✅ 打包成功完成！")
            self.log_message(f"输出目录: {self.output_dir}")

            # 询问是否打开输出目录
            msg_box = QMessageBox(QMessageBox.Question,  # 显式设置图标
                                  "打包成功",
                                  "打包已完成！是否打开输出目录？",
                                  QMessageBox.Yes | QMessageBox.No,
                                  self)  # 传递'self'作为父级
            # 应用主题特定的样式表
            msg_box.setStyleSheet(self.get_messagebox_style())
            reply = msg_box.exec()  # 使用exec()而不是静态方法
            if reply == QMessageBox.Yes:
                os.startfile(self.output_dir)
        else:
            self.log_message("❌ 打包过程中出现错误，请检查日志")

    def clear_log(self):
        """清除日志"""
        self.log_edit.clear()
        self.log_message("日志已清除")
        self.progress_bar.setValue(0)

    def closeEvent(self, event):
        """处理窗口关闭事件"""
        if self.package_thread and self.package_thread.isRunning():
            # 使用实例化的方式创建 QMessageBox 以便应用样式
            msg_box = QMessageBox(
                QMessageBox.Question,  # 设置图标
                "打包正在进行",
                "打包过程仍在运行，确定要退出吗？",
                QMessageBox.Yes | QMessageBox.No,
                self  # 设置父窗口
            )
            # 应用与当前主题匹配的样式
            msg_box.setStyleSheet(self.get_messagebox_style())
            reply = msg_box.exec()  # 使用 exec() 显示对话框

            if reply == QMessageBox.Yes:
                self.package_thread.stop()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = NuitkaPackager()
    window.show()
    sys.exit(app.exec())

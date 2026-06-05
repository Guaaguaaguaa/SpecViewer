# -*- coding: utf-8 -*-
"""
文件路径: ui/main_window.py
功能描述: 整个光谱查看软件的主窗体。
          构建宏大的菜单栏、工具栏及状态栏布局。
          状态栏分为三个区域，最右侧设有可自适应缩略并支持悬停 Tooltip 完整显示的路径展示标签。
          使用 QSplitter 实现可左右拉伸的分栏，并打通左树和右图的双向联动交互逻辑。
"""

import sys
import os

# ----------------------------------------------------
# 路径兼容性注入：将项目根目录动态添加到 sys.path
# 确保在任何工作目录下通过外层 main.py 启动时均能正确解析 'ui' 包
# ----------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, 
                             QSplitter, QFileDialog, QMessageBox, QStatusBar,
                             QLabel, QFrame)
from PyQt6.QtGui import QAction, QIcon, QFontMetrics, QPalette, QColor

# 导入已经调通的左右两个核心组件
from ui.sidebar_tree import SidebarTree
from ui.plot_canvas import PlotCanvas


class ElidedPathLabel(QLabel):
    """
    专门为长文件路径定制的高级标签控件。
    支持在有限的像素宽度下自动对路径进行中间省略（Elide），
    并且在鼠标悬停时提供完美的 Tooltip 全路径浮窗显示。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.full_path = ""
        # 设置最小宽度和固定高度，防止状态栏高度抖动
        self.setMinimumWidth(100)
        self.setMaximumWidth(400) # 限制路径标签最宽占 400 像素
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setStyleSheet("color: #555555; font-weight: bold; font-family: 'Consolas', 'Segoe UI';")
        self.set_path("")

    def set_path(self, path):
        """
        设置新路径，并刷新 Tooltip 内容
        """
        self.full_path = path if path else "未设置输出路径"
        self.setToolTip(self.full_path) # 设置 Qt 原生悬停 Tooltip 小气泡框
        self.update_elided_text()

    def update_elided_text(self):
        """
        利用 Qt 的 QFontMetrics 自动计算当前宽度，并将路径智能省略
        """
        # 获取当前控件的宽度限制
        width = self.width()
        if width <= 0:
            width = 300 # 初始默认保护宽度
            
        font_metrics = QFontMetrics(self.font())
        # 在有限像素宽度下，智能在中间部分使用 '...' 代替路径中间名（Qt 专为路径省略设计的模式）
        elided_text = font_metrics.elidedText(
            self.full_path, 
            Qt.TextElideMode.ElideMiddle, 
            width
        )
        self.setText(elided_text)

    def resizeEvent(self, event):
        """
        当窗口或者状态栏尺寸发生拉伸变化时，动态重新计算文字缩略
        """
        super().resizeEvent(event)
        self.update_elided_text()


class MainWindow(QMainWindow):
    """
    光谱查看软件的主窗体类。
    """
    def __init__(self):
        super().__init__()
        self.output_directory = "" # 记录当前设置的计算输出绝对路径
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("光谱高性能通用分析与可视化系统 Pro")
        self.resize(1100, 750)

        # ----------------------------------------------------
        # 1. 核心布局：先创建左侧树和右侧画布，确保 Action 绑定时对象已存在
        # ----------------------------------------------------
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 实例化子组件
        self.sidebar = SidebarTree()
        self.canvas = PlotCanvas()
        
        # 将组件装载入 Splitter
        main_splitter.addWidget(self.sidebar)
        main_splitter.addWidget(self.canvas)
        
        # 设置 Splitter 初始分配比例：左侧25%，右侧75%
        main_splitter.setSizes([250, 850])
        main_splitter.setCollapsible(0, False) # 不允许左侧树被彻底收缩隐藏
        main_splitter.setCollapsible(1, False) # 不允许右侧图区被彻底收缩隐藏

        # 核心主控视口容器装载
        self.setCentralWidget(main_splitter)

        # ----------------------------------------------------
        # 2. 宏大叙事：在组件创建完成后，再初始化菜单、工具栏及动作绑定
        # ----------------------------------------------------
        self.create_actions()
        self.create_menu_bar()
        self.create_tool_bar()

        # ----------------------------------------------------
        # 3. 状态栏分区改造（左、中、右三分区自适应）
        # ----------------------------------------------------
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # 区域 1 (左侧)：使用 status_bar 自带的 showMessage 处理临时操作提示
        self.status_bar.showMessage("系统就绪。请通过 [文件] -> [打开] 载入光谱数据")

        # 区域 2 (中部)：用于展示当前载入/选中状态的信息标签
        self.info_status_label = QLabel(" 状态: 正常模式")
        self.info_status_label.setStyleSheet("color: #666666; padding-left: 10px; border-left: 1px solid #CCCCCC;")
        
        # 区域 3 (最右侧)：我们专门定制的自适应省略路径展示标签
        self.path_status_label = ElidedPathLabel()
        
        # 将中部和右侧组件作为 permanent (永久性永久常驻) 控件添加到状态栏右侧
        # stretch 参数控制空间占比
        self.status_bar.addPermanentWidget(self.info_status_label, stretch=0)
        self.status_bar.addPermanentWidget(self.path_status_label, stretch=1) # 给予更大弹拉权重

        # ----------------------------------------------------
        # 4. 双向联动信号链条
        # ----------------------------------------------------
        # 联动 1：当用户在左侧目录树上勾选/去勾选曲线时，右侧画布对应更新选中/高亮状态
        self.sidebar.tree_selection_changed.connect(self.on_sidebar_selection_changed)
        
        # 联动 2：当用户在右侧画布上鼠标点击、多选或取消选中曲线时，左侧树对应的勾选框同步状态
        self.canvas.selection_changed.connect(self.on_canvas_selection_changed)
        
        # 联动 3：当用户在左侧右键请求关闭文件时
        self.sidebar.file_close_requested.connect(self.close_file_by_name)

    def create_actions(self):
        """
        初始化所有动作项（Actions），方便菜单栏和工具栏共享同一套逻辑。
        """
        # ==================== 文件菜单 Actions ====================
        self.open_action = QAction("打开文件(&O)...", self)
        self.open_action.setStatusTip("打开并自动识别多种格式的光谱数据文件")
        self.open_action.triggered.connect(self.open_file_dialog)

        self.close_action = QAction("关闭所有文件(&C)", self)
        self.close_action.setStatusTip("关闭当前所有载入的文件并清空画布")
        self.close_action.triggered.connect(self.clear_all_data)

        self.export_action = QAction("导出计算结果(&E)...", self)
        self.export_action.setStatusTip("将当前的计算结果数据导出为标准 CSV 文件")
        self.export_action.triggered.connect(self.export_data_placeholder)

        self.exit_action = QAction("退出(&X)", self)
        self.exit_action.triggered.connect(self.close)

        # ==================== 查看菜单 Actions ====================
        self.view_data_action = QAction("查看数据曲线", self)
        self.view_data_action.setCheckable(True)
        self.view_data_action.setChecked(True)
        self.view_data_action.setStatusTip("展示当前选中的原始光谱曲线")

        self.view_header_action = QAction("头文件查看 (预留)", self)
        self.view_header_action.setStatusTip("查看已打开光谱文件的仪器元数据头文件信息（功能预留中）")
        self.view_header_action.triggered.connect(self.show_not_implemented_message)

        # ==================== 统计菜单 Actions ====================
        self.algo_ratio_action = QAction("比值计算 (Ratio)...", self)
        self.algo_ratio_action.setStatusTip("对选中的两条数据执行智能化 Ratio 比值计算")
        self.algo_ratio_action.triggered.connect(self.run_ratio_calculation_placeholder)

        self.algo_mean_action = QAction("平均值 (Mean) (预留)", self)
        self.algo_mean_action.setStatusTip("计算选中多条曲线的平均波段强度（功能预留中）")
        self.algo_mean_action.triggered.connect(self.show_not_implemented_message)

        self.algo_std_action = QAction("标准差 (Std) (预留)", self)
        self.algo_std_action.setStatusTip("计算选中光谱曲线的波动标准差（功能预留中）")
        self.algo_std_action.triggered.connect(self.show_not_implemented_message)

        # ==================== 设置菜单 Actions ====================
        self.set_path_action = QAction("设置输出路径...", self)
        self.set_path_action.setStatusTip("设置计算和导出的全局默认输出目录")
        self.set_path_action.triggered.connect(self.set_output_directory_placeholder)

        # ==================== 额外快捷控制 Actions ====================
        self.toggle_legend_action = QAction("显示/隐藏图例", self)
        self.toggle_legend_action.setStatusTip("切换主图区图例的可见性")
        self.toggle_legend_action.triggered.connect(self.toggle_canvas_legend)

        self.auto_scale_action = QAction("自适应图区", self)
        self.auto_scale_action.setStatusTip("重置视图，使所有曲线自适应完整居中呈现")
        self.auto_scale_action.triggered.connect(self.canvas.auto_scale_view)

    def create_menu_bar(self):
        """
        构建顶部的树状层次菜单栏。
        """
        menu_bar = self.menuBar()

        # 1. 文件菜单
        file_menu = menu_bar.addMenu("文件(&F)")
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.close_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        # 2. 查看菜单
        view_menu = menu_bar.addMenu("查看(&V)")
        view_menu.addAction(self.view_data_action)
        view_menu.addAction(self.view_header_action)

        # 3. 统计算法菜单
        stats_menu = menu_bar.addMenu("统计(&S)")
        stats_menu.addAction(self.algo_ratio_action)
        stats_menu.addSeparator()
        stats_menu.addAction(self.algo_mean_action)
        stats_menu.addAction(self.algo_std_action)

        # 4. 设置菜单
        settings_menu = menu_bar.addMenu("设置(&C)")
        settings_menu.addAction(self.set_path_action)

    def create_tool_bar(self):
        """
        构建快捷工具栏。
        """
        tool_bar = self.addToolBar("常用工具")
        tool_bar.setMovable(False)
        tool_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)

        # 在工具栏中添加与菜单对应的核心动作按钮
        tool_bar.addAction(self.open_action)
        tool_bar.addSeparator()
        tool_bar.addAction(self.auto_scale_action)
        tool_bar.addAction(self.toggle_legend_action)
        tool_bar.addSeparator()
        tool_bar.addAction(self.algo_ratio_action)

    # ----------------------------------------------------
    # 联动联动机制（信号响应槽函数）
    # ----------------------------------------------------
    def on_sidebar_selection_changed(self, checked_curve_names):
        """
        当左侧树状目录勾选发生变化：通过名称反向控制右侧画布哪些曲线应该高亮选中。
        """
        self.canvas.select_curves_by_names(checked_curve_names)
        num_checked = len(checked_curve_names)
        self.status_bar.showMessage(f"当前选中了 {num_checked} 条光谱曲线")
        self.info_status_label.setText(f" 选中曲线: {num_checked} 条")

    def on_canvas_selection_changed(self, selected_curves):
        """
        当右侧画布改变了曲线状态：反向同步勾选左侧目录树对应的复选框。
        """
        self.sidebar.sync_selection_from_canvas(selected_curves)
        num_selected = len(selected_curves)
        self.status_bar.showMessage(f"当前画布高亮曲线数量: {num_selected} 条")
        self.info_status_label.setText(f" 选中曲线: {num_selected} 条")

    def toggle_canvas_legend(self):
        """
        图例一键显示/隐藏切换。
        """
        self.canvas.toggle_legend()
        self.status_bar.showMessage("图例可见状态已更新", 2000)

    # ----------------------------------------------------
    # 以下为尚未连接解析器的预留槽函数接口（留出接口，支持后续格式随时补入）
    # ----------------------------------------------------
    def open_file_dialog(self):
        """
        打开文件弹窗接口，未来将与 Core 层的 Parser Factory 数据中台打通。
        """
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "请选择要载入的光谱数据文件", "", 
            "光谱文件 (*.csv *.txt *.dat);;所有文件 (*.*)"
        )
        if file_paths:
            self.status_bar.showMessage(f"用户选择了 {len(file_paths)} 个文件，准备载入中...")
            
            # 【临时测试演示逻辑】：在没有连接真正的解析层前，我们手动注入模拟数据以供测试联动。
            for path in file_paths:
                import os
                filename = os.path.basename(path)
                
                # 模拟不同列数据
                curve_1 = f"{filename}_通道1"
                curve_2 = f"{filename}_通道2"
                
                # 同步树形列表
                self.sidebar.add_file(filename, [curve_1, curve_2])
                
                # 模拟在右侧画板中绘制临时测试曲线
                import numpy as np
                x = np.linspace(350, 1000, 1000)
                y1 = np.sin(x / 50) * 10000 + 15000 + np.random.normal(0, 100, 1000)
                y2 = np.cos(x / 50) * 8000 + 12000 + np.random.normal(0, 100, 1000)
                
                self.canvas.plot_data(x, y1, curve_1, normal_color='#1f77b4')
                self.canvas.plot_data(x, y2, curve_2, normal_color='#2ca02c')

    def close_file_by_name(self, filename):
        """
        移除单个文件及对应曲线数据。
        """
        self.sidebar.remove_file(filename)
        active_curves = []
        for c_name in self.sidebar.curve_items.keys():
            active_curves.append(c_name)
            
        self.canvas.select_curves_by_names(active_curves)
        self.status_bar.showMessage(f"已成功关闭文件: {filename}")

    def clear_all_data(self):
        """
        一键清理全局数据
        """
        self.sidebar.clear_all()
        self.canvas.clear_canvas()
        self.status_bar.showMessage("已清空所有载入的文件和曲线数据")
        self.info_status_label.setText(" 状态: 正常模式")

    def run_ratio_calculation_placeholder(self):
        """
        比值(Ratio)计算功能接口。
        """
        selected = self.canvas.get_selected_curves()
        if len(selected) != 2:
            QMessageBox.warning(
                self, "比值计算提示", 
                f"进行比值(Ratio)计算前，您必须且只能选中两条数据曲线！\n当前选中数量: {len(selected)} 条。"
            )
            return
            
        self.status_bar.showMessage(f"正在对比选的两条曲线 [ {selected[0].curve_name} ] 和 [ {selected[1].curve_name} ] 执行 Ratio 计算...")

    def export_data_placeholder(self):
        """
        文件菜单 -> 导出数据预留接口。
        """
        if not self.output_directory:
            QMessageBox.warning(self, "导出提示", "导出数据前，请先设置好全局数据输出路径！")
            return
        self.status_bar.showMessage(f"已将结果写入全局设置目录中: {self.output_directory}", 3000)

    def set_output_directory_placeholder(self):
        """
        设置菜单 -> 设置输出目录预留接口。
        """
        dir_path = QFileDialog.getExistingDirectory(self, "请选择计算结果的全局默认输出目录")
        if dir_path:
            self.output_directory = dir_path
            # 更新状态栏最右侧的定制路径显示
            self.path_status_label.set_path(f"输出目录: {dir_path}")
            self.status_bar.showMessage(f"输出路径更新成功：{dir_path}", 3000)

    def show_not_implemented_message(self):
        """
        弹窗提示未实现功能的预留信息
        """
        QMessageBox.information(self, "宏大叙事预留", "该功能已在我们的系统架构白皮书中留出了标准化接口。\n将在后续阶段根据需要开发特定的算法或窗口并无缝补入。")
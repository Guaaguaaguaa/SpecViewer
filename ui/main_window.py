# -*- coding: utf-8 -*-
"""
文件路径: ui/main_window.py
功能描述: 整个光谱查看软件的主窗体。
          构建宏大的菜单栏、工具栏及状态栏布局。
          状态栏分为三个区域，最右侧设有可自适应缩略并支持悬停 Tooltip 完整显示的路径展示标签。
          使用 QSplitter 实现可左右拉伸的分栏，并完美打通左树和右图的双向联动交互逻辑。
          【集成版】：完全打通数据中台 DataManager、ParserFactory 自动解析链条、
          统计算法引擎及导出模块，实现完整的数据载入、计算、导出闭环。
"""

import sys
import os

# ----------------------------------------------------
# 路径兼容性注入：将项目根目录动态添加到 sys.path
# ----------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QMainWindow, QSplitter, QFileDialog, QMessageBox,
                             QStatusBar, QLabel, QFrame, QTabWidget)
from PyQt6.QtGui import QAction, QFontMetrics

# 导入已经调通的左右两个核心组件
from ui.sidebar_tree import SidebarTree
from ui.plot_canvas import PlotCanvas
from ui.batch_task_panel import BatchTaskPanel

# 导入数据管理中台与自注册解析引擎
from core.data_manager import DataManager, SpectrumData
from core.parsers.base_parser import ParserFactory

# 显式导入具体解析器，激活它们的自动向工厂注册（极其重要）
import core.parsers.vertical_multi    # noqa: F401
import core.parsers.horizontal_row    # noqa: F401
import core.parsers.iris_binary       # noqa: F401

# 导入统计算法引擎（统一的 execute() 入口，无中间层）
from core.algorithms import MeanAlgorithm, StdAlgorithm, RatioAlgorithm, mean_from_files

# 导入导出模块
from core.exporters import (
    export_curve_to_csv, export_batch_to_csv,
    export_plot_dialog,
    export_single_header, export_batch_headers,
)

# 导入全局配置
from config.settings import AppSettings


class ElidedPathLabel(QLabel):
    """
    专门为长文件路径定制的高级标签控件。
    支持在有限的像素宽度下自动对路径进行中间省略（Elide），
    并且在鼠标悬停时提供完美的 Tooltip 全路径浮窗显示。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.full_path = ""
        self.setMinimumWidth(100)
        self.setMaximumWidth(400)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setStyleSheet(
            "color: #555555; font-weight: bold; font-family: 'Consolas', 'Segoe UI';"
        )
        self.set_path("")

    def set_path(self, path):
        self.full_path = path if path else "未设置输出路径"
        self.setToolTip(self.full_path)
        self.update_elided_text()

    def update_elided_text(self):
        width = self.width()
        if width <= 0:
            width = 300
        font_metrics = QFontMetrics(self.font())
        elided_text = font_metrics.elidedText(
            self.full_path,
            Qt.TextElideMode.ElideMiddle,
            width
        )
        self.setText(elided_text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_elided_text()


class MainWindow(QMainWindow):
    """
    光谱查看软件的主窗体类。
    """

    def __init__(self):
        super().__init__()
        # 初始化全局配置
        self.settings = AppSettings()

        # 初始化数据管理器单例
        self.data_manager = DataManager()

        # 工业级高雅调色板（来自全局配置）
        self.color_palette = self.settings.COLOR_PALETTE

        self.init_ui()

    def init_ui(self):
        self.setWindowTitle(self.settings.APP_DISPLAY_NAME)
        self.resize(self.settings.WINDOW_WIDTH, self.settings.WINDOW_HEIGHT)

        # 创建底部状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # ----------------------------------------------------
        # 1. 核心布局：标签页（文件浏览 / 批量处理）+ 右侧画布
        # ----------------------------------------------------
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        self.sidebar = SidebarTree()
        self.canvas = PlotCanvas()
        self.batch_panel = BatchTaskPanel()

        self.tabs = QTabWidget()
        self.tabs.addTab(self.sidebar, "📂 文件浏览")
        self.tabs.addTab(self.batch_panel, "⚙️ 批量处理")

        main_splitter.addWidget(self.tabs)
        main_splitter.addWidget(self.canvas)

        main_splitter.setSizes([
            self.settings.SPLITTER_LEFT_RATIO,
            self.settings.SPLITTER_RIGHT_RATIO
        ])
        main_splitter.setCollapsible(0, False)
        main_splitter.setCollapsible(1, False)

        self.setCentralWidget(main_splitter)

        # ----------------------------------------------------
        # 2. 菜单、工具栏及动作绑定
        # ----------------------------------------------------
        self.create_actions()
        self.create_menu_bar()
        self.create_tool_bar()

        # ----------------------------------------------------
        # 3. 状态栏分区改造
        # ----------------------------------------------------
        self.status_bar.showMessage(
            "系统就绪。请通过 [文件] -> [打开] 载入光谱数据"
        )

        self.info_status_label = QLabel(" 状态: 正常模式")
        self.info_status_label.setStyleSheet(
            "color: #666666; padding-left: 10px; border-left: 1px solid #CCCCCC;"
        )

        self.path_status_label = ElidedPathLabel()

        # 恢复上次持久化的输出路径显示
        saved_path = self.data_manager.get_output_path()
        if saved_path:
            self.path_status_label.set_path(f"输出目录: {saved_path}")

        self.status_bar.addPermanentWidget(self.info_status_label, stretch=0)
        self.status_bar.addPermanentWidget(self.path_status_label, stretch=1)

        # ----------------------------------------------------
        # 4. 双向联动信号链条
        # ----------------------------------------------------
        self.sidebar.tree_selection_changed.connect(
            self.on_sidebar_selection_changed
        )
        self.canvas.selection_changed.connect(self.on_canvas_selection_changed)
        self.sidebar.file_close_requested.connect(self.close_file_by_name)

        self.batch_panel.request_plot_data.connect(self.on_batch_plot_data)
        self.batch_panel.request_clear_canvas.connect(self.canvas.clear_canvas)
        self.batch_panel.request_batch_calc.connect(self.handle_batch_calculation)
        self.sidebar.request_batch_calc.connect(self.handle_batch_calculation)

    # ==================================================================
    # Actions / 菜单 / 工具栏
    # ==================================================================

    def create_actions(self):
        # ---- 文件菜单 ----
        self.open_action = QAction("打开文件(&O)...", self)
        self.open_action.setStatusTip("打开并自动识别多种格式的光谱数据文件")
        self.open_action.triggered.connect(self.open_file_dialog)

        self.close_action = QAction("关闭所有文件(&C)", self)
        self.close_action.setStatusTip("关闭当前所有载入的文件并清空画布")
        self.close_action.triggered.connect(self.clear_all_data)

        # ---- 导出子菜单项 ----
        self.export_csv_single_action = QAction("导出选中曲线 (CSV)...", self)
        self.export_csv_single_action.setStatusTip("将选中的单条曲线导出为 CSV 文件")
        self.export_csv_single_action.triggered.connect(self._export_csv_single_wrapper)

        self.export_csv_batch_action = QAction("导出所有画布曲线 (CSV)...", self)
        self.export_csv_batch_action.setStatusTip("将画布上所有曲线批量导出为一个 CSV 文件")
        self.export_csv_batch_action.triggered.connect(self._export_csv_batch_wrapper)

        self.export_image_action = QAction("导出画布为图片 (PNG/SVG)...", self)
        self.export_image_action.setStatusTip("将当前画布导出为 PNG / SVG / PDF 图片")
        self.export_image_action.triggered.connect(self._export_image_wrapper)

        self.export_header_single_action = QAction("导出选中文件头文件...", self)
        self.export_header_single_action.setStatusTip("导出选中曲线所属文件的元数据头信息")
        self.export_header_single_action.triggered.connect(self._export_header_single_wrapper)

        self.export_header_batch_action = QAction("导出所有文件头文件 (汇总)...", self)
        self.export_header_batch_action.setStatusTip("导出所有已载入文件的元数据头信息为一个汇总文件")
        self.export_header_batch_action.triggered.connect(self._export_header_batch_wrapper)

        self.exit_action = QAction("退出(&X)", self)
        self.exit_action.triggered.connect(self.close)

        # ---- 查看菜单 ----
        self.view_data_action = QAction("查看数据曲线", self)
        self.view_data_action.setCheckable(True)
        self.view_data_action.setChecked(True)
        self.view_data_action.setStatusTip("展示当前选中的原始光谱曲线")

        self.view_header_action = QAction("头文件查看 (预留)", self)
        self.view_header_action.setStatusTip(
            "查看已打开光谱文件的仪器元数据头文件信息（功能预留中）"
        )
        self.view_header_action.triggered.connect(self.show_not_implemented_message)

        # ---- 统计菜单（已全线接通算法引擎） ----
        self.algo_ratio_action = QAction("比值计算 (Ratio)...", self)
        self.algo_ratio_action.setStatusTip(
            "对选中的两条数据（或单文件双列）执行智能化 Ratio 比值计算"
        )
        self.algo_ratio_action.triggered.connect(self.run_ratio_calculation)

        self.algo_mean_action = QAction("平均值 (Mean)", self)
        self.algo_mean_action.setStatusTip("计算选中多条曲线的平均波段强度")
        self.algo_mean_action.triggered.connect(self.run_mean_calculation)

        self.algo_std_action = QAction("标准差 (Std)", self)
        self.algo_std_action.setStatusTip("计算选中光谱曲线的波动标准差")
        self.algo_std_action.triggered.connect(self.run_std_calculation)

        # ---- 设置菜单 ----
        self.set_path_action = QAction("设置输出路径...", self)
        self.set_path_action.setStatusTip("设置计算和导出的全局默认输出目录")
        self.set_path_action.triggered.connect(self.set_output_directory_placeholder)

        # ---- 快捷控制 ----
        self.toggle_legend_action = QAction("显示/隐藏图例", self)
        self.toggle_legend_action.setStatusTip("切换主图区图例的可见性")
        self.toggle_legend_action.triggered.connect(self.toggle_canvas_legend)

        self.auto_scale_action = QAction("自适应图区", self)
        self.auto_scale_action.setStatusTip("重置视图，使所有曲线自适应完整居中呈现")
        self.auto_scale_action.triggered.connect(self.canvas.auto_scale_view)

        self.rect_select_action = QAction("框选模式", self)
        self.rect_select_action.setCheckable(True)
        self.rect_select_action.setChecked(False)
        self.rect_select_action.setStatusTip(
            "切换矩形框选模式：拖拽鼠标框选画布上的曲线"
        )
        self.rect_select_action.triggered.connect(self.toggle_rect_select_mode)

        self.clear_canvas_action = QAction("清空图区", self)
        self.clear_canvas_action.setStatusTip("清空右侧绘图区域（不会删除已载入的文件数据）")
        self.clear_canvas_action.triggered.connect(self.canvas.clear_canvas)

    def create_menu_bar(self):
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("文件(&F)")
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.close_action)
        file_menu.addSeparator()

        # 导出 — 级联子菜单
        export_menu = file_menu.addMenu("导出(&E)")
        export_csv_menu = export_menu.addMenu("导出 CSV")
        export_csv_menu.addAction(self.export_csv_single_action)
        export_csv_menu.addAction(self.export_csv_batch_action)
        export_menu.addAction(self.export_image_action)
        export_menu.addSeparator()
        export_hdr_menu = export_menu.addMenu("导出头文件")
        export_hdr_menu.addAction(self.export_header_single_action)
        export_hdr_menu.addAction(self.export_header_batch_action)

        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        view_menu = menu_bar.addMenu("查看(&V)")
        view_menu.addAction(self.view_data_action)
        view_menu.addAction(self.view_header_action)

        stats_menu = menu_bar.addMenu("统计(&S)")
        stats_menu.addAction(self.algo_ratio_action)
        stats_menu.addSeparator()
        stats_menu.addAction(self.algo_mean_action)
        stats_menu.addAction(self.algo_std_action)

        settings_menu = menu_bar.addMenu("设置(&C)")
        settings_menu.addAction(self.set_path_action)

    def create_tool_bar(self):
        tool_bar = self.addToolBar("常用工具")
        tool_bar.setMovable(False)
        tool_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)

        tool_bar.addAction(self.open_action)
        tool_bar.addSeparator()
        tool_bar.addAction(self.auto_scale_action)
        tool_bar.addAction(self.toggle_legend_action)
        tool_bar.addAction(self.rect_select_action)
        tool_bar.addAction(self.clear_canvas_action)
        tool_bar.addSeparator()
        tool_bar.addAction(self.algo_ratio_action)

    # ==================================================================
    # 稳定哈希上色逻辑
    # ==================================================================

    def get_color_for_curve(self, curve_name):
        val = sum(ord(c) for c in curve_name)
        return self.color_palette[val % len(self.color_palette)]

    # ==================================================================
    # 联动机制核心实现
    # ==================================================================

    def on_sidebar_selection_changed(self, checked_curve_names):
        self.canvas.clear_canvas()
        for c_name in checked_curve_names:
            x, y = self.data_manager.get_curve_data(c_name)
            if x is not None and y is not None:
                color = self.get_color_for_curve(c_name)
                self.canvas.plot_data(x, y, c_name, normal_color=color)

        num_checked = len(checked_curve_names)
        self.status_bar.showMessage(f"当前画布呈现了 {num_checked} 条光谱曲线")
        self.info_status_label.setText(f" 展现曲线: {num_checked} 条")

    def on_canvas_selection_changed(self, selected_curves):
        self.sidebar.sync_selection_from_canvas(selected_curves)
        num_selected = len(selected_curves)
        self.status_bar.showMessage(f"当前画布高亮曲线数量: {num_selected} 条")
        self.info_status_label.setText(f" 高亮曲线: {num_selected} 条")

    # ==================================================================
    # 批量处理面板信号响应
    # ==================================================================

    def on_batch_plot_data(self, x, y, name):
        color = self.get_color_for_curve(name)
        self.canvas.plot_data(x, y, name, normal_color=color)
        self.status_bar.showMessage(f"批量面板绘图: {name}", 2000)

    def handle_batch_calculation(self, file_paths):
        """
        统一入口：接收批量面板 / 侧边栏多选文件路径，
        通过统一算法桥接器 mean_from_files() 执行均值计算，
        结果注册到 DataManager 并显示在侧边栏。
        """
        if not file_paths:
            return
        try:
            x, results, warn_msgs = mean_from_files(file_paths)
            if x is None or not results:
                return

            # 注册新结果到侧边栏（DataManager 自动处理同名去重）
            self.sidebar.begin_batch_load()
            for r in results:
                spec = self.data_manager.register_computed_result(
                    r['name'], x, r['y']
                )
                self.sidebar.add_file(spec.display_name, spec.column_names)
            self.sidebar.end_batch_load()

            if warn_msgs:
                QMessageBox.warning(self, "均值计算提示",
                                    "\n".join(warn_msgs))

            self.status_bar.showMessage(
                f"均值计算完成：{len(file_paths)} 个文件 → "
                f"{len(results)} 条结果（见侧边栏）", 5000
            )
        except Exception as e:
            QMessageBox.critical(self, "计算错误",
                                 f"无法完成批量计算:\n{str(e)}")

    # ==================================================================
    # 统计算法菜单槽函数（全部接通算法引擎）
    # ==================================================================

    def _resolve_curves_for_calc(self, min_curves=2):
        """
        获取待计算的曲线数据列表。
        优先使用画布上的显式选中；若无选中则回退到侧边栏所有勾选曲线。
        支持单文件内多条曲线的平均。

        :return: (x_list, y_list, name_list) 三个等长列表，或 (None, None, None)
        """
        canvas_selected = self.canvas.get_selected_curves()

        # 优先：画布上有显式选中 → 用选中的
        if canvas_selected:
            x_list, y_list, name_list = [], [], []
            for c in canvas_selected:
                x, y = self.data_manager.get_curve_data(c.curve_name)
                if x is not None and y is not None:
                    x_list.append(x)
                    y_list.append(y)
                    name_list.append(c.curve_name)
            return x_list, y_list, name_list

        # 回退：画布无选中 → 取侧边栏所有勾选的曲线
        checked = self.sidebar.get_checked_curve_names()
        if not checked:
            return None, None, None

        x_list, y_list, name_list = [], [], []
        for c_name in checked:
            x, y = self.data_manager.get_curve_data(c_name)
            if x is not None and y is not None:
                x_list.append(x)
                y_list.append(y)
                name_list.append(c_name)

        return x_list, y_list, name_list

    def run_mean_calculation(self):
        """
        统计菜单 -> 平均值。
        画布选中 → 计算选中曲线均值；无选中 → 计算侧边栏所有勾选曲线均值。
        支持单文件内多条曲线。
        """
        x_list, y_list, name_list = self._resolve_curves_for_calc()
        if not y_list or len(y_list) < 2:
            QMessageBox.warning(
                self, "平均值计算提示",
                f"进行均值计算前，至少需要选中/勾选 2 条数据曲线！\n"
                f"当前可用数量: {len(y_list) if y_list else 0} 条。\n"
                f"提示：在画布上点击曲线(加粗)，或勾选左侧栏复选框。"
            )
            return

        try:
            result = MeanAlgorithm().execute(y_list)
            label = f"Mean_({len(y_list)}curves)"
            self._register_and_show_result(label, x_list[0], result)
            self.status_bar.showMessage(
                f"成功计算 {len(y_list)} 条曲线的平均值", 3000
            )
        except ValueError as e:
            QMessageBox.critical(self, "计算错误",
                                 f"平均值计算失败:\n{str(e)}")

    def run_std_calculation(self):
        """
        统计菜单 -> 标准差。
        画布选中 → 计算选中曲线标准差；无选中 → 计算侧边栏所有勾选曲线标准差。
        """
        x_list, y_list, name_list = self._resolve_curves_for_calc()
        if not y_list or len(y_list) < 2:
            QMessageBox.warning(
                self, "标准差计算提示",
                f"进行标准差计算前，至少需要选中/勾选 2 条数据曲线！\n"
                f"当前可用数量: {len(y_list) if y_list else 0} 条。\n"
                f"提示：在画布上点击曲线(加粗)，或勾选左侧栏复选框。"
            )
            return

        try:
            result = StdAlgorithm().execute(y_list)
            label = f"Std_({len(y_list)}curves)"
            self._register_and_show_result(label, x_list[0], result)
            self.status_bar.showMessage(
                f"成功计算 {len(y_list)} 条曲线的标准差", 3000
            )
        except ValueError as e:
            QMessageBox.critical(self, "计算错误",
                                 f"标准差计算失败:\n{str(e)}")

    def run_ratio_calculation(self):
        """
        统计菜单 -> Ratio 比值计算。

        场景 1（单文件双列）：画布无选中，但存在恰好 2 条已勾选曲线属于同一文件
        → 自动执行列1 / 列2
        场景 2（双曲线）：画布恰好选中 2 条曲线
        → 跨曲线/跨文件比值计算
        场景 3：其他情况 → 提示用户
        """
        selected = self.canvas.get_selected_curves()

        # ----------------------------------------------------------------
        # 场景 1：单文件双列自动检测
        # ----------------------------------------------------------------
        if len(selected) == 0:
            checked_names = self.sidebar.get_checked_curve_names()
            file_groups = {}
            for c_name in checked_names:
                spec = self.data_manager.find_curve_source(c_name)
                if spec:
                    file_groups.setdefault(spec.display_name, []).append(c_name)

            for fname, names in file_groups.items():
                if len(names) == 2:
                    x1, y1 = self.data_manager.get_curve_data(names[0])
                    x2, y2 = self.data_manager.get_curve_data(names[1])
                    if x1 is None or y1 is None or x2 is None or y2 is None:
                        continue
                    try:
                        aligned_x, ratio_y = RatioAlgorithm().execute(
                            x1, y1, x2, y2
                        )
                        label = f"Ratio_({names[0]}/{names[1]})"
                        self._register_and_show_result(label, aligned_x, ratio_y)
                        self.status_bar.showMessage(
                            f"单文件双列比值: {names[0]} / {names[1]}", 3000
                        )
                        return
                    except ValueError as e:
                        QMessageBox.critical(self, "计算错误",
                                             f"比值计算失败:\n{str(e)}")
                        return

            QMessageBox.warning(
                self, "比值计算提示",
                "未检测到合适的比值计算场景。\n"
                "请在画布上选中 2 条曲线，或确保有文件恰好包含 2 列数据。"
            )
            return

        # ----------------------------------------------------------------
        # 场景 2：双曲线比值
        # ----------------------------------------------------------------
        if len(selected) != 2:
            QMessageBox.warning(
                self, "比值计算提示",
                f"进行比值(Ratio)计算前，必须且只能选中两条数据曲线！\n"
                f"当前选中数量: {len(selected)} 条。"
            )
            return

        c1, c2 = selected[0], selected[1]
        num_x, num_y = self.data_manager.get_curve_data(c1.curve_name)
        den_x, den_y = self.data_manager.get_curve_data(c2.curve_name)

        if num_x is None or num_y is None or den_x is None or den_y is None:
            QMessageBox.critical(self, "数据提取失败",
                                 "无法从选中曲线中提取有效数据。")
            return

        try:
            aligned_x, ratio_y = RatioAlgorithm().execute(
                num_x, num_y, den_x, den_y
            )
            label = f"Ratio_({c1.curve_name}/{c2.curve_name})"
            self._register_and_show_result(label, aligned_x, ratio_y)
            self.status_bar.showMessage(
                f"成功计算比值: {c1.curve_name} / {c2.curve_name}", 3000
            )
        except ValueError as e:
            QMessageBox.critical(self, "计算错误",
                                 f"比值计算失败:\n{str(e)}")

    # ==================================================================
    # 导出功能
    # ==================================================================

    # ==================================================================
    # 计算结果注册到侧边栏
    # ==================================================================

    def _register_and_show_result(self, label, x, y):
        """
        将计算结果注册到 DataManager 并添加到侧边栏（不清除旧结果）。
        DataManager.register_computed_result 会自动处理同名冲突（追加 #2, #3...）。
        多次计算结果依次累积，互不覆盖。
        """
        spec = self.data_manager.register_computed_result(label, x, y)
        self.sidebar.begin_batch_load()
        self.sidebar.add_file(spec.display_name, spec.column_names)
        self.sidebar.end_batch_load()

    # ==================================================================
    # 导出包装方法（获取数据 → 弹窗让用户指定文件名 → 保存）
    # ==================================================================

    def _get_default_export_dir(self):
        """获取保存弹窗的默认目录（优先使用已设置的输出路径）。"""
        saved = self.data_manager.get_output_path()
        return saved if saved else os.path.expanduser("~")

    def _export_csv_single_wrapper(self):
        selected = self.canvas.get_selected_curves()
        if not selected:
            QMessageBox.warning(self, "导出提示", "请先在画布上选中一条曲线。")
            return
        c = selected[0]
        x, y = self.data_manager.get_curve_data(c.curve_name)
        if x is None or y is None:
            QMessageBox.warning(self, "导出提示", "无法获取曲线数据。")
            return

        safe_name = c.curve_name.replace('/', '_').replace('\\', '_')
        suggested = os.path.join(
            self._get_default_export_dir(), safe_name + ".csv"
        )
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出选中曲线为 CSV", suggested,
            "CSV 文件 (*.csv);;所有文件 (*.*)"
        )
        if not filepath:
            return
        try:
            export_curve_to_csv(x, y, filepath)
            self.status_bar.showMessage(f"CSV 已导出: {filepath}", 5000)
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _export_csv_batch_wrapper(self):
        all_curves = self.canvas.curves
        if not all_curves:
            QMessageBox.warning(self, "导出提示", "画布上没有数据曲线。")
            return
        curves_dict = {}
        for c in all_curves:
            x, y = self.data_manager.get_curve_data(c.curve_name)
            if x is not None and y is not None:
                curves_dict[c.curve_name] = (x, y)
        if not curves_dict:
            QMessageBox.warning(self, "导出提示", "无法获取任何曲线数据。")
            return

        suggested = os.path.join(
            self._get_default_export_dir(), "batch_export.csv"
        )
        filepath, _ = QFileDialog.getSaveFileName(
            self, "批量导出曲线为 CSV", suggested,
            "CSV 文件 (*.csv);;所有文件 (*.*)"
        )
        if not filepath:
            return
        try:
            export_batch_to_csv(curves_dict, filepath)
            self.status_bar.showMessage(f"批量 CSV 已导出: {filepath}", 5000)
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _export_image_wrapper(self):
        filepath = export_plot_dialog(
            self.canvas.plot_widget, self,
            self._get_default_export_dir()
        )
        if filepath:
            self.status_bar.showMessage(f"图片已导出: {filepath}", 5000)

    def _export_header_single_wrapper(self):
        selected = self.canvas.get_selected_curves()
        if not selected:
            QMessageBox.warning(self, "导出提示", "请先在画布上选中一条曲线。")
            return
        c = selected[0]
        spec = self.data_manager.find_curve_source(c.curve_name)
        if not spec:
            QMessageBox.warning(self, "导出提示", "无法定位曲线所属文件。")
            return

        base = os.path.splitext(spec.filename)[0]
        suggested = os.path.join(
            self._get_default_export_dir(), f"{base}_header.txt"
        )
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出头文件", suggested,
            "文本文件 (*.txt);;所有文件 (*.*)"
        )
        if not filepath:
            return
        try:
            result = export_single_header(spec, filepath)
            if result:
                self.status_bar.showMessage(f"头文件已导出: {filepath}", 5000)
            else:
                QMessageBox.information(self, "导出提示", "该文件没有元数据可供导出。")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    def _export_header_batch_wrapper(self):
        spectra = self.data_manager.get_all_spectra()
        if not spectra:
            QMessageBox.warning(self, "导出提示", "没有已载入的文件。")
            return

        suggested = os.path.join(
            self._get_default_export_dir(), "batch_headers.txt"
        )
        filepath, _ = QFileDialog.getSaveFileName(
            self, "批量导出头文件", suggested,
            "文本文件 (*.txt);;所有文件 (*.*)"
        )
        if not filepath:
            return
        try:
            result = export_batch_headers(spectra, filepath)
            self.status_bar.showMessage(f"批量头文件已导出: {filepath}", 5000)
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    # ==================================================================
    # 视图控制
    # ==================================================================

    def toggle_canvas_legend(self):
        self.canvas.toggle_legend()
        self.status_bar.showMessage("图例可见状态已更新", 2000)

    def toggle_rect_select_mode(self):
        enabled = self.rect_select_action.isChecked()
        self.canvas.set_rect_select_mode(enabled)
        if enabled:
            self.status_bar.showMessage(
                "框选模式已开启 — 拖拽鼠标框选曲线", 2000
            )
        else:
            self.status_bar.showMessage("框选模式已关闭 — 回到平移模式", 2000)

    # ==================================================================
    # 核心数据载入
    # ==================================================================

    def open_file_dialog(self):
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "请选择要载入的光谱数据文件", "",
            "所有光谱文件 (*.csv *.txt *.dat);;所有文件 (*.*)"
        )
        if not file_paths:
            return

        # 批次模式：200 个文件只触发 1 次画布重绘，而非 200 次
        self.sidebar.begin_batch_load()
        success_count = 0
        try:
            for i, path in enumerate(file_paths):
                abs_path = os.path.abspath(path)

                status, msg, suggested_disp_name = \
                    self.data_manager.check_file_status(abs_path)

                if status == 'ALREADY_LOADED':
                    self.status_bar.showMessage(
                        f"[{i+1}/{len(file_paths)}] 跳过重复: {os.path.basename(abs_path)}", 2000
                    )
                    continue

                if status == 'NAME_CONFLICT':
                    self.status_bar.showMessage(msg, 4000)

                parser = ParserFactory.get_parser_for_file(abs_path)
                if not parser:
                    self.status_bar.showMessage(
                        f"[{i+1}/{len(file_paths)}] 格式不支持: {os.path.basename(abs_path)}", 2000
                    )
                    continue

                try:
                    spec_obj = parser.parse(abs_path,
                                            display_name=suggested_disp_name)
                    self.data_manager.add_spectrum(spec_obj)
                    self.sidebar.add_file(spec_obj.display_name,
                                          spec_obj.column_names)
                    success_count += 1
                    if success_count % 20 == 0:
                        self.status_bar.showMessage(
                            f"载入中... {success_count}/{len(file_paths)} 个文件", 1000
                        )
                except Exception as e:
                    self.status_bar.showMessage(
                        f"[{i+1}/{len(file_paths)}] 解析失败: {os.path.basename(abs_path)}", 2000
                    )
                    continue
        finally:
            # 批次结束：一次触发画布绘制所有曲线
            self.sidebar.end_batch_load()

        if success_count > 0:
            self.status_bar.showMessage(
                f"成功载入 {success_count} 个光谱文件", 5000
            )

    def close_file_by_name(self, display_name):
        self.data_manager.remove_spectrum_by_display_name(display_name)
        self.sidebar.remove_file(display_name)
        self.status_bar.showMessage(f"已成功关闭文件: {display_name}", 2000)

    def clear_all_data(self):
        self.data_manager.clear_all()
        self.sidebar.clear_all()
        self.canvas.clear_canvas()
        self.status_bar.showMessage("已清空所有载入的文件和曲线数据")
        self.info_status_label.setText(" 状态: 正常模式")

    # ==================================================================
    # 设置
    # ==================================================================

    def set_output_directory_placeholder(self):
        dir_path = QFileDialog.getExistingDirectory(
            self, "请选择计算结果的全局默认输出目录"
        )
        if dir_path:
            self.data_manager.set_output_path(dir_path)
            self.path_status_label.set_path(f"输出目录: {dir_path}")
            self.status_bar.showMessage(f"输出路径更新成功：{dir_path}", 3000)

    def show_not_implemented_message(self):
        QMessageBox.information(
            self, "宏大叙事预留",
            "该功能已在我们的系统架构白皮书中留出了标准化接口。\n"
            "将在后续阶段根据需要开发特定的算法并无缝补入。"
        )

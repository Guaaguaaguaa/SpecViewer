# -*- coding: utf-8 -*-
"""
文件路径: ui/batch_task_panel.py
功能描述: 批量处理工作区（融合完整版）。
          提供文件夹索引、树状展示、右键菜单、全选、双击预览、
          按钮预览、后台流式计算（QThread）以及一键清空任务列表。
          修复：清空/删除任务时同步清空画布；计算委托给统一算法层；
          预览改用 ParserFactory 自适应解析所有格式（含横向多曲线）；
          多文件预览遍历所有选中文件而非仅第一条。
"""

import sys
import os
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QPushButton, QTreeWidget,
                             QTreeWidgetItem, QHBoxLayout, QFileDialog,
                             QAbstractItemView, QMenu)

# ----------------------------------------------------
# 路径兼容性注入
# ----------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.algorithms.runner import mean_from_files
from core.parsers.base_parser import ParserFactory

# 触发解析器自注册
import core.parsers.vertical_multi    # noqa: F401
import core.parsers.horizontal_row    # noqa: F401
import core.parsers.iris_binary       # noqa: F401


class CalculationWorker(QThread):
    """后台计算工作线程：防止大规模文件读取和计算阻塞 GUI 界面。"""
    finished_calculation = pyqtSignal(object, list, list)  # x, results, warnings

    def __init__(self, file_paths):
        super().__init__()
        self.file_paths = file_paths

    def run(self):
        x, results, warn_msgs = self.calculate_mean_stream(self.file_paths)
        if x is not None and results:
            self.finished_calculation.emit(x, results, warn_msgs)

    @staticmethod
    def calculate_mean_stream(file_paths):
        """
        后台流式计算平均值。
        现已委托给统一算法桥接器 mean_from_files()。
        """
        return mean_from_files(file_paths)


class BatchTaskPanel(QWidget):
    """批量处理控制面板 — 融合全选、右键菜单、双击/按钮双通道预览、后台流式计算。"""
    request_plot_data = pyqtSignal(object, object, str)
    request_clear_canvas = pyqtSignal()
    request_batch_calc = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # ---- 任务树 ----
        self.task_tree = QTreeWidget()
        self.task_tree.setHeaderLabel("待处理任务列表")
        self.task_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        # 双击预览
        self.task_tree.itemDoubleClicked.connect(self.preview_file)

        # 右键菜单
        self.task_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.task_tree.customContextMenuRequested.connect(self.show_context_menu)

        layout.addWidget(self.task_tree)

        # ---- 功能区 1：基础文件操作 ----
        btn_layout_top = QHBoxLayout()

        self.btn_add_folder = QPushButton("添加文件夹")
        self.btn_add_folder.clicked.connect(self.add_directory)

        self.btn_select_all = QPushButton("全选")
        self.btn_select_all.clicked.connect(self.task_tree.selectAll)

        self.btn_remove_selected = QPushButton("删除选中")
        self.btn_remove_selected.clicked.connect(self.remove_selected_tasks)

        self.btn_clear_all = QPushButton("清空所有任务")
        self.btn_clear_all.clicked.connect(self.clear_all_tasks)

        for btn in [self.btn_add_folder, self.btn_select_all,
                     self.btn_remove_selected, self.btn_clear_all]:
            btn_layout_top.addWidget(btn)

        layout.addLayout(btn_layout_top)

        # ---- 功能区 2：预览 & 计算 ----
        self.btn_preview = QPushButton("预览选中文件")
        self.btn_preview.setStyleSheet(
            "background-color: #e3f2fd; font-weight: bold; padding: 10px;"
        )
        self.btn_preview.clicked.connect(self.preview_selected)
        layout.addWidget(self.btn_preview)

        self.btn_calc_mean = QPushButton("计算选中文件平均值")
        self.btn_calc_mean.setStyleSheet(
            "background-color: #e1f5fe; font-weight: bold; padding: 10px;"
        )
        self.btn_calc_mean.clicked.connect(self.run_mean_calculation)
        layout.addWidget(self.btn_calc_mean)

    # ----------------------------------------------------------------
    # 右键菜单
    # ----------------------------------------------------------------
    def show_context_menu(self, position):
        menu = QMenu()
        prev_act = menu.addAction("预览该文件")
        calc_act = menu.addAction("计算平均值")

        # 获取右键点击位置的文件项（而非当前选中项）
        clicked_item = self.task_tree.itemAt(position)

        action = menu.exec(self.task_tree.viewport().mapToGlobal(position))

        if action == prev_act:
            if clicked_item and clicked_item.parent() is not None:
                path = clicked_item.data(0, Qt.ItemDataRole.UserRole)
                if path and os.path.exists(path):
                    self._preview_paths([path])
        elif action == calc_act:
            self.run_mean_calculation()

    # ----------------------------------------------------------------
    # 文件夹索引（递归扫描子目录，树状结构）
    # ----------------------------------------------------------------
    def add_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择存放光谱数据的文件夹")
        if not dir_path:
            return

        folder_name = os.path.basename(dir_path)
        folder_item = QTreeWidgetItem(self.task_tree)
        folder_item.setText(0, f"\U0001F4C1 {folder_name}")
        folder_item.setData(0, Qt.ItemDataRole.UserRole, dir_path)
        folder_item.setExpanded(True)

        # 递归扫描：建立子目录节点映射，文件挂在对应目录下
        dir_nodes = {dir_path: folder_item}
        data_exts = ('.csv', '.txt')

        for root, dirs, files in os.walk(dir_path):
            # 排序保证展示一致性
            dirs.sort()
            files.sort()

            # 当前目录对应的树节点
            parent_node = dir_nodes.get(root, folder_item)

            # 子目录：创建树节点
            for d in dirs:
                sub_path = os.path.join(root, d)
                sub_item = QTreeWidgetItem(parent_node)
                sub_item.setText(0, f"\U0001F4C1 {d}")
                sub_item.setData(0, Qt.ItemDataRole.UserRole, sub_path)
                dir_nodes[sub_path] = sub_item

            # 文件：挂叶子节点
            for f in files:
                if f.lower().endswith(data_exts):
                    full_path = os.path.join(root, f)
                    file_item = QTreeWidgetItem(parent_node)
                    file_item.setText(0, f)
                    file_item.setData(0, Qt.ItemDataRole.UserRole, full_path)

        # 自动展开第一层子目录
        for i in range(folder_item.childCount()):
            child = folder_item.child(i)
            if child.data(0, Qt.ItemDataRole.UserRole):  # 是目录节点
                child.setExpanded(True)

    # ----------------------------------------------------------------
    # 预览：双击触发（通过 ParserFactory 自适应解析所有格式）
    # ----------------------------------------------------------------
    def preview_file(self, item, column):
        """双击任务树条目 → 用 ParserFactory 解析文件并绘制所有曲线"""
        if item.parent() is None:
            return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and os.path.exists(path):
            self._preview_paths([path])

    # ----------------------------------------------------------------
    # 预览：按钮触发（遍历所有选中文件，自适应解析并绘制全部曲线）
    # ----------------------------------------------------------------
    def preview_selected(self):
        """预览所有选中文件 → 遍历选中项，逐个解析并绘制所有曲线"""
        paths = []
        for item in self.task_tree.selectedItems():
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path and os.path.exists(path):
                paths.append(path)
        if not paths:
            return
        self._preview_paths(paths)

    def _preview_paths(self, paths):
        """
        核心预览逻辑：用 ParserFactory 自适应解析所有格式（纵向/横向/二进制），
        将每个文件的所有曲线逐一绘制到画布。
        """
        self.request_clear_canvas.emit()
        for path in paths:
            try:
                parser = ParserFactory.get_parser_for_file(path)
                if parser is None:
                    print(f"[预览] 无法识别文件格式: {os.path.basename(path)}")
                    continue
                spec = parser.parse(path)
                for col_name in spec.column_names:
                    x, y = spec.get_curve(col_name)
                    self.request_plot_data.emit(
                        x, y, f"预览: {col_name}"
                    )
            except Exception as e:
                print(f"[预览] 解析失败 ({os.path.basename(path)}): {e}")

    # ----------------------------------------------------------------
    # 任务管理
    # ----------------------------------------------------------------
    def remove_selected_tasks(self):
        for item in self.task_tree.selectedItems():
            parent = item.parent()
            if parent:
                parent.removeChild(item)
            else:
                self.task_tree.takeTopLevelItem(
                    self.task_tree.indexOfTopLevelItem(item)
                )
        # 修复：删除任务后同步清空画布，避免残留曲线
        self.request_clear_canvas.emit()

    def clear_all_tasks(self):
        self.task_tree.clear()
        # 修复：清空所有任务后同步清空画布，避免残留曲线
        self.request_clear_canvas.emit()

    # ----------------------------------------------------------------
    # 后台流式计算
    # ----------------------------------------------------------------
    def get_selected_file_paths(self):
        paths = []
        for item in self.task_tree.selectedItems():
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path:
                paths.append(path)
        return paths

    def run_mean_calculation(self):
        """触发批量均值计算：通过信号交由 MainWindow 统一调度（保留 QThread 作为独立运行后备）。"""
        paths = self.get_selected_file_paths()
        if not paths:
            return
        # 主路径：通过信号通知 MainWindow 调用统一算法桥接器计算并绘图
        self.request_batch_calc.emit(paths)

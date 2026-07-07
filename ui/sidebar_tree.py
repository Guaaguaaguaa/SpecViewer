# -*- coding: utf-8 -*-
"""
文件路径: ui/sidebar_tree.py
功能描述: 基于 PyQt6 QTreeWidget 构建的左侧文件/曲线目录树。
          支持文件-曲线两级层级展示、复选框多选状态、以及与右侧画布的双向状态同步联动。
          优化：加入数据去重对比机制，彻底解决自动三态引起的 itemChanged 级联重复触发问题。
"""

"""
import sys
"""
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTreeWidget,
                             QTreeWidgetItem, QHeaderView, QMenu, QMessageBox)


class SidebarTree(QWidget):
    """
    左侧数据树状目录组件，管理所有已打开的文件以及文件内包含的曲线列。
    """
    # 信号：当用户在左侧树中勾选/去勾选某些曲线时触发，通知右侧画布更新选中状态
    # 携带参数: 当前所有被勾选的曲线名称列表 [str, str, ...]
    tree_selection_changed = pyqtSignal(list)
    
    # 信号：当用户右键选择关闭某个文件时触发，通知主窗体清理内存并清空画布
    # 携带参数: 要关闭的文件名称 str
    file_close_requested = pyqtSignal(str)

    # 信号：当用户右键选择计算平均值时触发，携带文件绝对路径列表
    request_batch_calc = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_items = {}  # 缓存结构: { filename: QTreeWidgetItem_parent }
        self.curve_items = {} # 缓存结构: { curve_name: QTreeWidgetItem_child }
        self.block_signals = False # 用于防止双向联动时产生信号死循环的保护锁
        self.last_emitted_curves = None # 记录上一次成功广播的勾选曲线列表，用于去重
        self._batch_depth = 0    # 批次加载嵌套计数器，>0 时抑制 emit
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建树形控件
        self.tree = QTreeWidget()
        layout.addWidget(self.tree)

        # 配置树形外观
        self.tree.setHeaderLabel("数据列表")
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # 允许整行选中
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        
        # 绑定树节点复选框改变事件
        self.tree.itemChanged.connect(self.on_item_changed)
        
        # 开启右键菜单支持
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)

    def begin_batch_load(self):
        """
        开始批量加载：进入批次模式，抑制 add_file 触发画布重绘。
        与 end_batch_load() 配对使用，支持嵌套。
        """
        self._batch_depth += 1
        self.block_signals = True

    def end_batch_load(self):
        """
        结束批量加载：退出批次模式，发射一次变更信号触发画布重绘。
        """
        self._batch_depth = max(0, self._batch_depth - 1)
        if self._batch_depth == 0:
            self.block_signals = False
            self.emit_checked_curves()

    def add_file(self, filename, curve_names):
        """
        向树中添加一个新文件及其包含的所有曲线子项。
        :param filename: 文件名称 (如 "ATP6500_001.csv")
        :param curve_names: 该文件内的曲线列名称列表 (如 ["列1_value", "列2_value"])
        """
        self._batch_depth += 1
        self.block_signals = True
        try:
            # 防止同名文件重复添加
            if filename in self.file_items:
                self._remove_file_unsafe(filename)

            # 1. 创建顶层父节点（代表文件）
            file_item = QTreeWidgetItem(self.tree)
            file_item.setText(0, filename)
            file_item.setFlags(file_item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
            file_item.setCheckState(0, Qt.CheckState.Checked)

            self.file_items[filename] = file_item

            # 2. 创建子节点（代表该文件里的每一条数据曲线）
            for c_name in curve_names:
                child_item = QTreeWidgetItem(file_item)
                child_item.setText(0, c_name)
                child_item.setFlags(child_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                child_item.setCheckState(0, Qt.CheckState.Checked)

                self.curve_items[c_name] = child_item

            file_item.setExpanded(True)
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0:
                self.block_signals = False
                self.emit_checked_curves()

    def remove_file(self, filename):
        """
        从树中移除指定文件及其所有子项。
        支持批次模式：若在 begin_batch_load 内调用则推迟 emit。
        """
        if filename not in self.file_items:
            return

        self._batch_depth += 1
        self.block_signals = True
        try:
            self._remove_file_unsafe(filename)
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0:
                self.block_signals = False
                self.emit_checked_curves()

    def _remove_file_unsafe(self, filename):
        """remove_file 的内部实现（不含批次深度管理，供 add_file 去重复用）。"""
        parent_item = self.file_items[filename]
        index = self.tree.indexOfTopLevelItem(parent_item)
        self.tree.takeTopLevelItem(index)

        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            curve_name = child.text(0)
            if curve_name in self.curve_items:
                del self.curve_items[curve_name]

        del self.file_items[filename]

    def clear_all(self):
        """
        清空树状图中的所有文件和曲线。
        支持批次模式。
        """
        self._batch_depth += 1
        self.block_signals = True
        try:
            self.tree.clear()
            self.file_items.clear()
            self.curve_items.clear()
        finally:
            self._batch_depth -= 1
            if self._batch_depth == 0:
                self.block_signals = False
                self.emit_checked_curves()

    def on_item_changed(self, item, column):
        """
        响应树节点复选框状态改变的内部槽函数
        """
        if self.block_signals:
            return
        
        # 此时向外通知当前所有被勾选的曲线
        self.emit_checked_curves()

    def emit_checked_curves(self):
        """
        遍历当前树中所有被勾选的叶子节点（曲线），并通过信号发射出去。
        添加了基于集合的对比去重逻辑，防止级联触发引起的重复发射。
        """
        checked_curves = []
        for curve_name, item in self.curve_items.items():
            if item.checkState(0) == Qt.CheckState.Checked:
                checked_curves.append(curve_name)
        
        # 核心去重对比逻辑
        current_set = set(checked_curves)
        if self.last_emitted_curves is not None and self.last_emitted_curves == current_set:
            # 如果勾选内容与上一次广播完全一致，直接拦截并静默返回
            return
            
        # 记录并发送
        self.last_emitted_curves = current_set
        self.tree_selection_changed.emit(checked_curves)

    def get_checked_curve_names(self):
        """
        返回当前所有被勾选的曲线名称列表（不含去重逻辑，直接读取界面状态）。
        供 Ratio 计算等场景查询当前勾选状态。
        """
        checked = []
        for curve_name, item in self.curve_items.items():
            if item.checkState(0) == Qt.CheckState.Checked:
                checked.append(curve_name)
        return checked

    def sync_selection_from_canvas(self, selected_curves):
        """
        API：供外部调用。当用户在右侧画布上点击/框选曲线时，反向同步勾选左侧对应的复选框。
        注意：仅勾选被选中的曲线，不取消其他曲线的勾选状态。
              画布\"选中高亮\"与\"可见性\"是两个独立的概念。
        """
        self.block_signals = True

        selected_names = [c.curve_name for c in selected_curves]

        # 仅勾选被选中的项，不取消其他项（选中 ≠ 可见性）
        for curve_name in selected_names:
            if curve_name in self.curve_items:
                self.curve_items[curve_name].setCheckState(0, Qt.CheckState.Checked)

        self.block_signals = False

    def show_context_menu(self, position):
        """
        右键快捷菜单生成器。
        文件节点：关闭文件 / 计算平均值。
        曲线节点：查看曲线属性（预留）。
        """
        item = self.tree.itemAt(position)
        if not item:
            return

        menu = QMenu(self)

        # 判断点击的是父节点（文件）还是子节点（曲线）
        if item.parent() is None:
            # 选中了顶层文件节点
            filename = item.text(0)

            calc_action = menu.addAction(f"计算平均值: {filename}")
            menu.addSeparator()
            close_action = menu.addAction(f"关闭文件: {filename}")

            action = menu.exec(self.tree.mapToGlobal(position))

            if action == calc_action:
                self._emit_calc_for_file(filename)
            elif action == close_action:
                reply = QMessageBox.question(
                    self, '确认关闭',
                    f"是否确定关闭文件 {filename}？\n这会同时从图区移除相关曲线。",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.file_close_requested.emit(filename)
        else:
            # 选中了子曲线节点
            curve_name = item.text(0)
            info_action = menu.addAction(f"查看曲线属性 (预留)")
            menu.exec(self.tree.mapToGlobal(position))

    def _emit_calc_for_file(self, display_name):
        """
        根据文件的显示名反查绝对路径，发射计算平均值信号。
        支持多选：若用户选中了多个文件节点，则收集所有选中文件的路径。
        """
        from core.data_manager import DataManager
        dm = DataManager()

        # 建立 display_name → filepath 映射
        all_specs = dm.get_all_spectra()
        name_to_path = {s.display_name: s.filepath for s in all_specs}

        # 优先收集当前树中所有被选中的顶层文件节点
        selected_indices = self.tree.selectedIndexes()
        file_paths = []
        seen = set()
        for idx in selected_indices:
            tree_item = self.tree.itemFromIndex(idx)
            if tree_item is not None and tree_item.parent() is None:
                dname = tree_item.text(0)
                if dname in seen:
                    continue
                seen.add(dname)
                path = name_to_path.get(dname)
                if path:
                    file_paths.append(path)

        # 如果多选没收集到，回退到右键点击的那个文件
        if not file_paths:
            path = name_to_path.get(display_name)
            if path:
                file_paths.append(path)

        if file_paths:
            self.request_batch_calc.emit(file_paths)


"""
# 便于独立模块运行测试的入口
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = QWidget()
    window.resize(300, 500)
    window.setWindowTitle("左侧目录树单元测试")

    test_layout = QVBoxLayout(window)
    sidebar = SidebarTree()
    test_layout.addWidget(sidebar)

    # 模拟载入两个文件的数据树结构
    sidebar.add_file("ATP6500_22-001.csv", ["ATP6500-通道1_Value", "ATP6500-通道2_Value"])
    sidebar.add_file("JZh_4426-001-1.csv", ["JZh_4426_Spectral_Value"])

    # 监控左侧树状目录勾选事件的输出
    sidebar.tree_selection_changed.connect(lambda lst: print(f"[信号广播] 当前勾选了哪些曲线: {lst}"))
    sidebar.file_close_requested.connect(lambda f: print(f"[信号广播] 用户请求关闭文件: {f}"))

    window.show()
    sys.exit(app.exec())
"""
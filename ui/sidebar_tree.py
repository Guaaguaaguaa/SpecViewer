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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.file_items = {}  # 缓存结构: { filename: QTreeWidgetItem_parent }
        self.curve_items = {} # 缓存结构: { curve_name: QTreeWidgetItem_child }
        self.block_signals = False # 用于防止双向联动时产生信号死循环的保护锁
        self.last_emitted_curves = None # 记录上一次成功广播的勾选曲线列表，用于去重
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

    def add_file(self, filename, curve_names):
        """
        向树中添加一个新文件及其包含的所有曲线子项。
        :param filename: 文件名称 (如 "ATP6500_001.csv")
        :param curve_names: 该文件内的曲线列名称列表 (如 ["列1_value", "列2_value"])
        """
        # 临时锁住信号，防止添加节点初始化状态时频繁向外发送 tree_selection_changed 信号
        self.block_signals = True

        # 1. 创建顶层父节点（代表文件）
        file_item = QTreeWidgetItem(self.tree)
        file_item.setText(0, filename)
        # 使用 ItemIsAutoTristate 替换 ItemIsTristate，解决新版本 PyQt6 兼容问题
        file_item.setFlags(file_item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
        file_item.setCheckState(0, Qt.CheckState.Checked)  # 默认全选
        
        self.file_items[filename] = file_item

        # 2. 创建子节点（代表该文件里的每一条数据曲线）
        for c_name in curve_names:
            child_item = QTreeWidgetItem(file_item)
            child_item.setText(0, c_name)
            # 子节点只需要两态复选框
            child_item.setFlags(child_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            child_item.setCheckState(0, Qt.CheckState.Checked)  # 默认全部勾选
            
            # 建立曲线名称到子节点对象的全局索引
            self.curve_items[c_name] = child_item

        # 展开该文件节点，方便用户直接看到子曲线
        file_item.setExpanded(True)
        
        # 解锁信号
        self.block_signals = False
        
        # 触发一次选中状态改变的广播
        self.emit_checked_curves()

    def remove_file(self, filename):
        """
        从树中移除指定文件及其所有子项。
        """
        if filename in self.file_items:
            # 临时加锁，避免移除节点触发 itemChanged 信号
            self.block_signals = True
            
            # 从树控件中彻底移除顶层节点
            parent_item = self.file_items[filename]
            index = self.tree.indexOfTopLevelItem(parent_item)
            self.tree.takeTopLevelItem(index)
            
            # 清理子项缓存
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                curve_name = child.text(0)
                if curve_name in self.curve_items:
                    del self.curve_items[curve_name]
                    
            # 清理父项缓存
            del self.file_items[filename]
            
            self.block_signals = False
            self.emit_checked_curves()

    def clear_all(self):
        """
        清空树状图中的所有文件和曲线
        """
        self.block_signals = True
        self.tree.clear()
        self.file_items.clear()
        self.curve_items.clear()
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

    def sync_selection_from_canvas(self, selected_curves):
        """
        API：供外部调用。当用户在右侧画布上点击/框选曲线时，反向同步勾选左侧对应的复选框。
        :param selected_curves: 右侧当前被选中的 ClickablePlotDataItem 曲线对象列表
        """
        # 反向更新时必须锁住信号，否则树改变又会触发画布绘制，导致无限循环
        self.block_signals = True
        
        selected_names = [c.curve_name for c in selected_curves]
        
        for curve_name, child_item in self.curve_items.items():
            if curve_name in selected_names:
                child_item.setCheckState(0, Qt.CheckState.Checked)
            else:
                child_item.setCheckState(0, Qt.CheckState.Unchecked)
                
        # 同步更新上一次发送的缓存，防止锁解开后触发冗余广播
        self.last_emitted_curves = set(selected_names)
        self.block_signals = False

    def show_context_menu(self, position):
        """
        右键快捷菜单生成器
        """
        item = self.tree.itemAt(position)
        if not item:
            return
            
        menu = QMenu(self)
        
        # 判断点击的是父节点（文件）还是子节点（曲线）
        if item.parent() is None:
            # 选中了顶层文件节点
            filename = item.text(0)
            close_action = menu.addAction(f"关闭文件: {filename}")
            
            # 弹出菜单并阻塞等待选择
            action = menu.exec(self.tree.viewport().mapToGlobal(position))
            if action == close_action:
                # 确认是否关闭
                reply = QMessageBox.question(
                    self, '确认关闭', f"是否确定关闭文件 {filename}？\n这会同时从图区移除相关曲线。",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self.file_close_requested.emit(filename)
        else:
            # 选中了子曲线节点，未来可以拓展“显示曲线属性”等功能
            curve_name = item.text(0)
            info_action = menu.addAction(f"查看曲线属性 (预留)")
            menu.exec(self.tree.viewport().mapToGlobal(position))


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
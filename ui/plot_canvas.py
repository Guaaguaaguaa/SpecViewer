# -*- coding: utf-8 -*-
"""
文件路径: ui/plot_canvas.py
功能描述: 基于 PyQt6 和 pyqtgraph 构建的高性能光谱曲线绘制画布。
          采用底层 Qt 标准事件映射拦截与 `mapFromScene` 坐标映射技术，
          实现 100% 灵敏顺滑、带手势反馈的图例拖拽，并完美支持鼠标单选、多选及空白取消。
"""

import sys
import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QGraphicsItem
import pyqtgraph as pg

# 配置 pyqtgraph 使用抗锯齿和更现代的配色
pg.setConfigOption('background', 'w')       # 默认白色背景，更适合办公与导出
pg.setConfigOption('foreground', 'k')       # 黑色坐标轴与文字
pg.setConfigOption('antialias', True)       # 开启抗锯齿，使曲线更平滑


class ClickablePlotDataItem(pg.PlotDataItem):
    """
    自定义的 PlotDataItem，用于支持鼠标单选和多选交互。
    """
    # 当曲线被点击时触发，发送曲线自身的引用以及是否为多选模式 (Ctrl/Shift 键按下)
    sigCurveClicked = pyqtSignal(object, bool)

    def __init__(self, *args, **kwargs):
        # 强制允许触发点击事件
        kwargs['clickable'] = True
        super().__init__(*args, **kwargs)
        self.curve.setClickable(True)
        self.is_selected = False
        self.normal_pen = None
        self.selected_pen = None
        self.curve_name = ""

    def set_pens(self, normal_pen, selected_pen):
        """
        设置普通状态 and 选中状态的画笔样式
        """
        self.normal_pen = pg.mkPen(normal_pen)
        self.selected_pen = pg.mkPen(selected_pen)
        self.setPen(self.normal_pen)

    def set_selected(self, selected):
        """
        更新曲线的选中状态，并改变视觉样式（如加粗、改变颜色等）
        """
        self.is_selected = selected
        if self.is_selected:
            # 选中时加粗显示，并使用选中状态的画笔
            self.setPen(self.selected_pen)
            # 提升当前曲线的渲染层级，使其浮在最上面
            self.setZValue(10)
        else:
            self.setPen(self.normal_pen)
            self.setZValue(1)

    def mouseClickEvent(self, ev):
        """
        重写鼠标点击事件，判断是否按下了 Ctrl 或 Shift 键
        """
        if ev.button() == Qt.MouseButton.LeftButton:
            modifiers = QApplication.keyboardModifiers()
            is_multi = (modifiers == Qt.KeyboardModifier.ControlModifier or 
                        modifiers == Qt.KeyboardModifier.ShiftModifier)
            self.sigCurveClicked.emit(self, is_multi)
            ev.accept()
        else:
            super().mouseClickEvent(ev)


class DraggableLegend(pg.LegendItem):
    """
    可自由拖动的图例
    """

    def __init__(self, size=None, offset=None, **kwargs):
        super().__init__(size=size, offset=offset, **kwargs)

        self.drag_start_scene = None
        self.item_start_pos = None
        self.is_dragging = False

        # 开启悬停事件
        self.setAcceptHoverEvents(True)

    def hoverEvent(self, ev):
        """
        鼠标悬停时显示小手
        """
        if self.is_dragging:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        if not ev.isExit():
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, ev):
        """
        开始拖动
        """
        if ev.button() == Qt.MouseButton.LeftButton:

            self.drag_start_scene = ev.scenePos()
            self.item_start_pos = self.pos()

            self.is_dragging = True

            # 关键：解除 Legend 的自动锚定
            self.offset = None

            self.setCursor(Qt.CursorShape.ClosedHandCursor)

            ev.accept()
            return

        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        """
        拖动图例
        """
        if self.is_dragging and self.drag_start_scene is not None:

            delta = ev.scenePos() - self.drag_start_scene

            new_pos = self.item_start_pos + delta

            # 绕过 LegendItem 的定位逻辑
            pg.GraphicsWidget.setPos(self, new_pos)

            delta = ev.scenePos() - self.drag_start_scene
            new_pos = self.item_start_pos + delta
            pg.GraphicsWidget.setPos(self, new_pos)

            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        """
        结束拖动
        """
        if ev.button() == Qt.MouseButton.LeftButton:

            self.is_dragging = False

            self.setCursor(Qt.CursorShape.OpenHandCursor)

            ev.accept()
            return

        super().mouseReleaseEvent(ev)


class PlotCanvas(QWidget):
    """
    核心图形画布类，承载了所有数据曲线的绘制和交互。
    """
    # 当选中的曲线发生变化时，向外通知当前的选中曲线列表
    selection_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.curves = []  # 缓存当前画布上所有的曲线对象
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建 pyqtgraph 绘图窗口
        self.plot_widget = pg.PlotWidget()
        layout.addWidget(self.plot_widget)

        # 开启网格线，增强可读性
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('bottom', 'Wavelength (nm)', **{'color': '#333333', 'size': '11pt'})
        self.plot_widget.setLabel('left', 'Intensity (a.u.)', **{'color': '#333333', 'size': '11pt'})

        # 初始化自定义的可拖拽图例
        self.legend = DraggableLegend(offset=None)

        self.legend.setParentItem(self.plot_widget.plotItem)

        # 手动放到左上角
        pg.GraphicsWidget.setPos(self.legend, 30, 30)
        self.legend_visible = True

        # 绑定空白处点击事件
        self.view_box = self.plot_widget.plotItem.vb
        self.view_box.scene().sigMouseClicked.connect(self.on_scene_clicked)
        self.is_rect_select_mode = False

    def plot_data(self, x_data, y_data, label, normal_color='#1f77b4', selected_color='#ff7f0e'):
        """
        绘制一条新光谱曲线的核心方法。
        """
        curve_item = ClickablePlotDataItem()
        curve_item.setData(x_data, y_data)
        curve_item.curve_name = label

        # 设置画笔，普通状态线宽为 1.5，选中状态线宽为 3.0 且变色
        normal_pen = pg.mkPen(color=normal_color, width=1.5)
        selected_pen = pg.mkPen(color=selected_color, width=3.0)
        curve_item.set_pens(normal_pen, selected_pen)

        # 绑定点击信号
        curve_item.sigCurveClicked.connect(self.on_curve_clicked)

        # 将曲线添加到画布和图例中
        self.plot_widget.addItem(curve_item)
        self.legend.addItem(curve_item, label)
        
        # 默认打开时全部选中状态
        curve_item.set_selected(True)
        self.curves.append(curve_item)

        # 自适应调整坐标范围以显示所有曲线
        self.auto_scale_view()
        self.selection_changed.emit(self.get_selected_curves())

    def clear_canvas(self):
        """
        清空当前画布上所有的曲线和图例
        """
        for curve in self.curves:
            self.plot_widget.removeItem(curve)
        self.legend.clear()
        self.curves.clear()
        self.selection_changed.emit([])

    def get_selected_curves(self):
        """
        获取当前处于选中状态的所有曲线对象名称列表
        """
        return [c for c in self.curves if c.is_selected]

    def select_curves_by_names(self, names):
        """
        根据名称列表，从外部（如左侧树状目录勾选）控制右侧曲线的选中状态
        """
        for curve in self.curves:
            is_sel = curve.curve_name in names
            curve.set_selected(is_sel)
        self.selection_changed.emit(self.get_selected_curves())

    def on_curve_clicked(self, clicked_curve, is_multi):
        """
        单条曲线被点击时的响应槽函数
        """
        if not is_multi:
            for curve in self.curves:
                if curve != clicked_curve:
                    curve.set_selected(False)
            clicked_curve.set_selected(True)
        else:
            clicked_curve.set_selected(not clicked_curve.is_selected)

        self.selection_changed.emit(self.get_selected_curves())

    def on_scene_clicked(self, event):
        """
        捕获画布空白处的点击事件。
        """
        if event.button() == Qt.MouseButton.RightButton or event.isAccepted():
            return

        items = self.plot_widget.scene().items(event.scenePos())
        clicked_on_curve = False
        for item in items:
            if isinstance(item, pg.graphicsItems.PlotDataItem.PlotDataItem) or isinstance(item, ClickablePlotDataItem):
                clicked_on_curve = True
                break
        
        if not clicked_on_curve:
            for curve in self.curves:
                curve.set_selected(False)
            self.selection_changed.emit([])

    def toggle_legend(self):
        """
        切换图例的显示与隐藏
        """
        self.legend_visible = not self.legend_visible
        if self.legend_visible:
            self.legend.show()
        else:
            self.legend.hide()

    def set_rect_select_mode(self, enabled):
        """
        切换“平移模式”与“框选模式”。
        """
        self.is_rect_select_mode = enabled
        if enabled:
            self.plot_widget.setMouseEnabled(x=False, y=False)
        else:
            self.plot_widget.setMouseEnabled(x=True, y=True)

    def auto_scale_view(self):
        """
        自适应窗口大小，使所有曲线完整呈现
        """
        self.plot_widget.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)

    def zoom_in_api(self):
        """
        预留给工具栏的“放大”功能
        """
        self.view_box.scaleBy((0.8, 0.8))

    def zoom_out_api(self):
        """
        预留给工具栏的“缩小”功能
        """
        self.view_box.scaleBy((1.2, 1.2))


"""
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = QWidget()
    window.resize(800, 600)
    window.setWindowTitle("高性能光谱画布单元测试")

    test_layout = QVBoxLayout(window)
    canvas = PlotCanvas()
    test_layout.addWidget(canvas)

    x = np.linspace(350, 1000, 1000)
    y1 = np.sin(x / 50) * 10000 + 15000 + np.random.normal(0, 100, 1000)
    y2 = np.cos(x / 50) * 8000 + 12000 + np.random.normal(0, 100, 1000)

    canvas.plot_data(x, y1, "光谱测试曲线 A_ATP6500", normal_color='#1f77b4')
    canvas.plot_data(x, y2, "光谱测试曲线 B_JZh_001", normal_color='#2ca02c')

    window.show()
    sys.exit(app.exec())
"""
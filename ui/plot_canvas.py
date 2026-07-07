# -*- coding: utf-8 -*-
"""
文件路径: ui/plot_canvas.py
功能描述: 基于 PyQt6 和 pyqtgraph 构建的高性能光谱曲线绘制画布。
          采用底层 Qt 标准事件映射拦截与 `mapFromScene` 坐标映射技术，
          实现 100% 灵敏顺滑、带手势反馈的图例拖拽，并完美支持鼠标单选、多选及空白取消。
          增加右键菜单功能，支持选定曲线的批量计算触发。
          新增：Rubber-band 矩形框选（ROI）模式，通过工具栏按钮切换。
"""

import numpy as np
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout,
                             QRubberBand)
import pyqtgraph as pg

# 配置 pyqtgraph 使用抗锯齿和更现代的配色
pg.setConfigOption('background', 'w')       # 默认白色背景，更适合办公与导出
pg.setConfigOption('foreground', 'k')       # 黑色坐标轴与文字
pg.setConfigOption('antialias', True)       # 开启抗锯齿，使曲线更平滑


class ClickablePlotDataItem(pg.PlotDataItem):
    """
    自定义的 PlotDataItem，用于支持鼠标单选和多选交互。
    使用 pyqtgraph 原生 sigClicked 信号 + mousePressEvent accept
    确保点击事件不被场景空白点击处理器吞掉。
    """
    sigCurveClicked = pyqtSignal(object, bool)

    def __init__(self, *args, **kwargs):
        kwargs['clickable'] = True
        super().__init__(*args, **kwargs)
        self.curve.setClickable(True)
        self.is_selected = False
        self.normal_pen = None
        self.selected_pen = None
        self.curve_name = ""

        # 使用 pyqtgraph 原生 sigClicked，避免 mouseClickEvent 时序问题
        self.sigClicked.connect(self._on_pyqtgraph_clicked)

    def _on_pyqtgraph_clicked(self, item, ev=None):
        """pyqtgraph 原生点击回调 → 转为带多选信息的自定义信号"""
        modifiers = QApplication.keyboardModifiers()
        is_multi = bool(modifiers & (
            Qt.KeyboardModifier.ControlModifier |
            Qt.KeyboardModifier.ShiftModifier
        ))
        self.sigCurveClicked.emit(self, is_multi)

    def set_pens(self, normal_pen, selected_pen):
        """设置普通状态和选中状态的画笔样式"""
        self.normal_pen = pg.mkPen(normal_pen)
        self.selected_pen = pg.mkPen(selected_pen)
        self.setPen(self.normal_pen)

    def set_selected(self, selected):
        """更新曲线的选中状态，并改变视觉样式（加粗、高亮）"""
        self.is_selected = selected
        if self.is_selected:
            self.setPen(self.selected_pen)
            self.setZValue(10)
        else:
            self.setPen(self.normal_pen)
            self.setZValue(1)

    def mousePressEvent(self, ev):
        """重写 mousePress：提前 accept 防止场景 on_scene_clicked 误清选中"""
        if ev.button() == Qt.MouseButton.LeftButton:
            ev.accept()  # 标记为"已处理"，阻止 on_scene_clicked 清除选中
        super().mousePressEvent(ev)


class DraggableLegend(pg.LegendItem):
    """
    可自由拖动的图例
    """

    def __init__(self, size=None, offset=None, **kwargs):
        super().__init__(size=size, offset=offset, **kwargs)

        self.drag_start_scene = None
        self.item_start_pos = None
        self.is_dragging = False
        self.setAcceptHoverEvents(True)

    def hoverEvent(self, ev):
        if self.is_dragging:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if not ev.isExit():
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.drag_start_scene = ev.scenePos()
            self.item_start_pos = self.pos()
            self.is_dragging = True
            self.offset = None
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self.is_dragging and self.drag_start_scene is not None:
            delta = ev.scenePos() - self.drag_start_scene
            new_pos = self.item_start_pos + delta
            self.setPos(new_pos)
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            ev.accept()
            return
        super().mouseReleaseEvent(ev)


class PlotCanvas(QWidget):
    """
    核心图形画布类，承载了所有数据曲线的绘制和交互。
    支持：单击单选、Ctrl/Shift 多选、Rubber-band 框选。
    （右键菜单由 pyqtgraph 原生提供：View All、导出等）
    """
    # 当选中的曲线发生变化时，向外通知当前的选中曲线列表
    selection_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.curves = []  # 缓存当前画布上所有的曲线对象

        # ---- Rubber-band 框选状态 ----
        self.is_rect_select_mode = False
        self._rubber_band = None
        self._rb_origin = None

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建 pyqtgraph 绘图窗口
        self.plot_widget = pg.PlotWidget()
        layout.addWidget(self.plot_widget)

        # 开启网格线，增强可读性
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('bottom', 'Wavelength (nm)',
                                  **{'color': '#333333', 'size': '11pt'})
        self.plot_widget.setLabel('left', 'Intensity (a.u.)',
                                  **{'color': '#333333', 'size': '11pt'})

        # 初始化自定义的可拖拽图例
        self.legend = DraggableLegend(offset=None)
        self.legend.setParentItem(self.plot_widget.plotItem)
        self.legend.setPos(30, 30)
        self.legend_visible = True

        # 绑定空白处点击事件（用于取消选中）
        self.view_box = self.plot_widget.plotItem.vb
        self.view_box.scene().sigMouseClicked.connect(self.on_scene_clicked)

        # 创建 rubber-band 控件（依附于 plot_widget）
        self._rubber_band = QRubberBand(
            QRubberBand.Shape.Rectangle, self.plot_widget
        )

    # ==================================================================
    # 绘制与清空
    # ==================================================================

    def plot_data(self, x_data, y_data, label,
                  normal_color='#1f77b4', selected_color='#ff7f0e'):
        """绘制一条新光谱曲线的核心方法。曲线初始为未选中（normal_color）。"""
        curve_item = ClickablePlotDataItem()
        curve_item.setData(x_data, y_data)
        curve_item.curve_name = label

        normal_pen = pg.mkPen(color=normal_color, width=1.5)
        selected_pen = pg.mkPen(color=selected_color, width=3.0)
        curve_item.set_pens(normal_pen, selected_pen)

        curve_item.sigCurveClicked.connect(self.on_curve_clicked)

        self.plot_widget.addItem(curve_item)
        self.legend.addItem(curve_item, label)

        # 初始状态：未选中，显示曲线本色
        self.curves.append(curve_item)
        self.auto_scale_view()

    def clear_canvas(self):
        """清空当前画布上所有的曲线和图例"""
        for curve in self.curves:
            self.plot_widget.removeItem(curve)
        self.legend.clear()
        self.curves.clear()
        self.selection_changed.emit([])

    def get_selected_curves(self):
        """获取当前处于选中状态的所有曲线对象列表"""
        return [c for c in self.curves if c.is_selected]

    def select_curves_by_names(self, names):
        """根据名称列表，从外部控制右侧曲线的选中状态"""
        for curve in self.curves:
            is_sel = curve.curve_name in names
            curve.set_selected(is_sel)
        self.selection_changed.emit(self.get_selected_curves())

    # ==================================================================
    # 点击交互：单选 / 多选 / 空白取消
    # ==================================================================

    def on_curve_clicked(self, clicked_curve, is_multi):
        """单条曲线被点击时的响应槽函数"""
        if self.is_rect_select_mode:
            return  # 框选模式下忽略单击

        if not is_multi:
            for curve in self.curves:
                if curve != clicked_curve:
                    curve.set_selected(False)
            clicked_curve.set_selected(True)
        else:
            clicked_curve.set_selected(not clicked_curve.is_selected)

        self.selection_changed.emit(self.get_selected_curves())

    def on_scene_clicked(self, event):
        """捕获画布空白处的点击事件 — 取消所有选中。"""
        if event.button() == Qt.MouseButton.RightButton or event.isAccepted():
            return

        items = self.plot_widget.scene().items(event.scenePos())
        clicked_on_curve = False
        for item in items:
            if isinstance(item, (pg.graphicsItems.PlotDataItem.PlotDataItem,
                                 ClickablePlotDataItem)):
                clicked_on_curve = True
                break

        if not clicked_on_curve:
            for curve in self.curves:
                curve.set_selected(False)
            self.selection_changed.emit([])

    # ==================================================================
    # Rubber-band 框选（ROI）
    # ==================================================================

    def set_rect_select_mode(self, enabled):
        """
        切换"平移模式"与"框选模式"。
        框选模式下禁用平移/缩放，鼠标拖拽将绘制矩形框选区域。
        """
        self.is_rect_select_mode = enabled
        if enabled:
            self.plot_widget.setMouseEnabled(x=False, y=False)
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.plot_widget.setMouseEnabled(x=True, y=True)
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event):
        """框选模式下记录 rubber-band 起点。"""
        if (self.is_rect_select_mode and
                event.button() == Qt.MouseButton.LeftButton):
            self._rb_origin = event.pos()
            self._rubber_band.setGeometry(QRect(self._rb_origin, QPoint()))
            self._rubber_band.show()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """框选模式下更新 rubber-band 矩形。"""
        if self.is_rect_select_mode and self._rb_origin is not None:
            self._rubber_band.setGeometry(
                QRect(self._rb_origin, event.pos()).normalized()
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """框选模式下：隐藏 rubber-band，选中矩形内的曲线。"""
        if (self.is_rect_select_mode and
                event.button() == Qt.MouseButton.LeftButton and
                self._rb_origin is not None):
            self._rubber_band.hide()

            # 将 rubber-band 的 widget 坐标矩形映射到 view 坐标
            rect = QRect(self._rb_origin, event.pos()).normalized()
            if rect.width() < 5 and rect.height() < 5:
                # 矩形太小，视为误触，忽略
                self._rb_origin = None
                event.accept()
                return

            self._select_curves_in_rect(rect)
            self._rb_origin = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _select_curves_in_rect(self, widget_rect):
        """
        判断哪些曲线的数据点落在 widget_rect 内，
        将其设为选中状态（支持 Ctrl/Shift 追加选择）。
        """
        modifiers = QApplication.keyboardModifiers()
        is_multi = bool(modifiers & (
            Qt.KeyboardModifier.ControlModifier |
            Qt.KeyboardModifier.ShiftModifier
        ))

        if not is_multi:
            # 非多选模式：先清空
            for curve in self.curves:
                curve.set_selected(False)

        vb = self.view_box
        # 将 widget 坐标先转场景坐标，再转 view 数据坐标
        scene_tl = self.plot_widget.mapToScene(widget_rect.topLeft())
        scene_br = self.plot_widget.mapToScene(widget_rect.bottomRight())
        top_left = vb.mapSceneToView(scene_tl)
        bottom_right = vb.mapSceneToView(scene_br)

        x_min, x_max = sorted([top_left.x(), bottom_right.x()])
        y_min, y_max = sorted([top_left.y(), bottom_right.y()])

        any_selected = False
        for curve in self.curves:
            x_data, y_data = curve.getData()
            if x_data is None or y_data is None:
                continue
            # 检查是否有数据点落在矩形内
            mask = (
                (x_data >= x_min) & (x_data <= x_max) &
                (y_data >= y_min) & (y_data <= y_max)
            )
            if np.any(mask):
                curve.set_selected(True)
                any_selected = True

        # 无论是否选中任何曲线，只要操作过就通知外部
        # （非多选模式下所有曲线已被清空，即使矩形内无任何点）
        self.selection_changed.emit(self.get_selected_curves())

    # ==================================================================
    # 视图控制
    # ==================================================================

    def toggle_legend(self):
        """切换图例的显示与隐藏"""
        self.legend_visible = not self.legend_visible
        if self.legend_visible:
            self.legend.show()
        else:
            self.legend.hide()

    def auto_scale_view(self):
        """自适应窗口大小，使所有曲线完整呈现"""
        self.plot_widget.enableAutoRange(axis=pg.ViewBox.XYAxes, enable=True)

    def zoom_in_api(self):
        """预留给工具栏的"放大"功能"""
        self.view_box.scaleBy((0.8, 0.8))

    def zoom_out_api(self):
        """预留给工具栏的"缩小"功能"""
        self.view_box.scaleBy((1.2, 1.2))

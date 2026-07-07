# -*- coding: utf-8 -*-
"""
文件路径: core/exporters/image_exporter.py
功能描述: 光谱画布图片导出工具。
          支持将 pyqtgraph PlotWidget 导出为 PNG / SVG / PDF 格式。
"""

import os
from PyQt6.QtWidgets import QFileDialog


def export_plot_to_image(plot_widget, output_path):
    """
    将 pyqtgraph PlotWidget 当前视图导出为图片文件。

    :param plot_widget: pyqtgraph.PlotWidget 实例
    :param output_path: 输出文件的完整路径（含扩展名，决定格式）
    :return: 实际写入的文件绝对路径，失败返回 None
    """
    try:
        exporter = _get_exporter_for_path(output_path)
        if exporter is None:
            return None

        exporter.export(output_path)
        return output_path
    except Exception as e:
        print(f"[导出错误] 图片导出失败: {e}")
        return None


def export_plot_dialog(plot_widget, parent=None, output_dir=None):
    """
    弹出保存文件对话框，让用户选择路径和格式，然后导出画布图片。

    :param plot_widget: pyqtgraph.PlotWidget 实例
    :param parent: 父级 QWidget（用于对话框模态）
    :param output_dir: 默认保存目录（可选）
    :return: 成功返回文件路径，取消或失败返回 None
    """
    default_dir = output_dir or os.path.expanduser("~")

    filepath, selected_filter = QFileDialog.getSaveFileName(
        parent,
        "导出画布图片",
        os.path.join(default_dir, "spectrum_plot"),
        "PNG 图片 (*.png);;SVG 矢量图 (*.svg);;PDF 文档 (*.pdf)"
    )

    if not filepath:
        return None

    return export_plot_to_image(plot_widget, filepath)


def _get_exporter_for_path(filepath):
    """
    根据文件扩展名返回对应的 pyqtgraph 导出器。
    """
    import pyqtgraph as pg

    ext = os.path.splitext(filepath)[1].lower()

    exporters = {
        '.png': pg.exporters.ImageExporter,
        '.svg': pg.exporters.SVGExporter,
        '.pdf': pg.exporters.MatplotlibExporter,
    }

    exporter_cls = exporters.get(ext)
    if exporter_cls is None:
        print(f"[导出错误] 不支持的图片格式: {ext}")
        return None

    # pg.exporters API: 创建 exporter 实例时需要传入要导出的 item
    scene = None
    try:
        # ImageExporter 和 SVGExporter 的构造函数接受 PlotItem
        if ext in ('.png', '.svg'):
            return exporter_cls(plot_widget.plotItem)
        else:
            return exporter_cls(plot_widget.plotItem)
    except TypeError:
        # 尝试旧版 API
        try:
            return exporter_cls(plot_widget.plotItem.scene())
        except Exception:
            return None

# -*- coding: utf-8 -*-
"""
文件路径: core/exporters/csv_exporter.py
功能描述: 光谱数据 CSV 导出工具。
          支持单曲线导出和批量多曲线导出。
"""

import os
import csv
import numpy as np


def export_curve_to_csv(x, y, filepath):
    """
    将单条光谱曲线导出为 CSV 文件（两列：wavelength, intensity）。

    :param x: 波长 X 轴，一维 NumPy 数组
    :param y: 强度 Y 轴，一维 NumPy 数组
    :param filepath: 输出文件的完整路径（含 .csv 扩展名）
    :return: 实际写入的文件绝对路径
    """
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)

    x_arr = np.asarray(x, dtype=float).flatten()
    y_arr = np.asarray(y, dtype=float).flatten()

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Wavelength', 'Intensity'])
        for i in range(len(x_arr)):
            writer.writerow([x_arr[i], y_arr[i]])

    return filepath


def export_batch_to_csv(curves_dict, filepath):
    """
    将多条曲线批量导出到一个 CSV 文件。
    第一列为波长，后续每列为一条曲线的强度数据。

    :param curves_dict: {name: (x, y), ...}
                        所有曲线的 X 轴必须对齐（长度一致）
    :param filepath: 输出文件的完整路径（含 .csv 扩展名）
    :return: 实际写入的文件绝对路径
    """
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)

    items = list(curves_dict.items())
    if not items:
        return None

    # 以第一条曲线的 X 轴为基准
    first_name, (first_x, _) = items[0]

    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # 表头：Wavelength, Curve1_Name, Curve2_Name, ...
        header = ['Wavelength'] + [_sanitize_filename(name) for name, _ in items]
        writer.writerow(header)

        # 数据行
        x_arr = np.asarray(first_x, dtype=float).flatten()
        n_points = len(x_arr)

        for i in range(n_points):
            row = [x_arr[i]]
            for _, (_, y) in items:
                y_arr = np.asarray(y, dtype=float).flatten()
                row.append(y_arr[i] if i < len(y_arr) else '')
            writer.writerow(row)

    return filepath


def _sanitize_filename(name):
    """
    清理文件名中的非法字符。
    """
    invalid_chars = '<>:"/\\|?*'
    for ch in invalid_chars:
        name = name.replace(ch, '_')
    return name.strip()

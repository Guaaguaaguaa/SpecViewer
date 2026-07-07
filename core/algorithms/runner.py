# -*- coding: utf-8 -*-
"""
文件路径: core/algorithms/runner.py
功能描述: 文件级别的算法运行桥接器。
          封装"从文件路径读取 → 提取所有 Y 列 → X 轴 PCHIP 插值对齐 → 调用算法"
          的完整流水线。
          支持混合数据智能检测：若文件曲线数不一致，自动预平均多曲线文件后统一计算；
          若所有文件曲线数相同，则按列对应平均（每列独立求均值）。
"""

import sys
import os
import warnings
import numpy as np

# ----------------------------------------------------
# 路径兼容性注入
# ----------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.algorithms.mean_engine import MeanAlgorithm
from core.parsers.base_parser import ParserFactory

# 触发解析器自注册
import core.parsers.vertical_multi    # noqa: F401
import core.parsers.horizontal_row    # noqa: F401
import core.parsers.iris_binary       # noqa: F401


def _pchip_interp(x_new, x, y, left=np.nan, right=np.nan):
    """
    PCHIP (Piecewise Cubic Hermite Interpolating Polynomial) 插值。
    优先使用 scipy 实现；若不可用则回退到 np.interp 线性插值。

    PCHIP 保持单调性，不会像三次样条那样产生过冲振荡，
    特别适合光谱数据这种平滑变化的物理量。
    """
    try:
        from scipy.interpolate import PchipInterpolator
        interpolator = PchipInterpolator(x, y, extrapolate=False)
        result = interpolator(x_new)
        # 手动处理外推：scipy 的 extrapolate=False 对超出范围的 x_new 返回 NaN
        below = x_new < x[0]
        above = x_new > x[-1]
        result[below] = left
        result[above] = right
        return result
    except (ImportError, ValueError):
        # scipy 不可用或数据不兼容（重复 X / 单点等）→ 回退线性插值
        return np.interp(x_new, x, y, left=left, right=right)


def _align_curves(all_curves, base_x):
    """
    将所有曲线的 X 轴对齐到 base_x（使用 PCHIP 插值）。
    all_curves: [(x, y, name), ...]
    返回: [(y_aligned, name), ...]
    """
    aligned = []
    for x, y, name in all_curves:
        if len(x) == len(base_x) and np.allclose(base_x, x, atol=1e-5):
            aligned.append((y, name))
        else:
            y_aligned = _pchip_interp(base_x, x, y, left=np.nan, right=np.nan)
            aligned.append((y_aligned, name))
    return aligned


def mean_from_files(file_paths):
    """
    从文件路径列表读取光谱数据，智能处理混合结构后计算平均值。

    智能策略：
    - 若所有文件曲线数全为 1：直接对所有曲线求平均 → 1 条结果。
    - 若所有文件曲线数相同（N > 1）：按列对应平均 → N 条结果（每条结果
      对应所有文件同列位置曲线的均值）。
    - 若文件曲线数不一致（混合数据）：先对每个多曲线文件内部预平均为
      1 条，再对所有文件求总平均 → 1 条结果，并产出警告信息。

    插值方法：PCHIP（保单调三次 Hermite），回退到 np.interp。

    :param file_paths: 文件绝对路径字符串列表
    :return: (base_x, results, warn_msgs)
             base_x:   公共 X 轴（取首个文件首条曲线的 X）
             results:  [{'y': ndarray, 'name': str}, ...] 可能有多条
             warn_msgs: 警告信息字符串列表
    """
    if not file_paths:
        return None, [], []

    # ================================================================
    # 1. 收集所有曲线数据（优先从 DataManager 内存获取，避免重读磁盘）
    # ================================================================
    from core.data_manager import DataManager
    dm = DataManager()

    file_curves = {}       # {filepath: [(x, y, col_name), ...]}
    all_curves_flat = []   # [(x, y, name), ...]
    warn_msgs = []
    cache_hits = 0

    for path in file_paths:
        # 快速路径：数据已在 DataManager 中 → 直接取内存副本
        spec = dm.get_spectrum(path)
        if spec is not None:
            cache_hits += 1
            curves = []
            for col_name in spec.column_names:
                x, y = spec.get_curve(col_name)
                curves.append((x, y, col_name))
                all_curves_flat.append((x, y, col_name))
            file_curves[path] = curves
            continue

        # 慢速路径：文件未载入 → 从磁盘解析
        parser = ParserFactory.get_parser_for_file(path)
        if parser is None:
            warn_msgs.append(f"跳过无法识别格式的文件: {os.path.basename(path)}")
            continue

        spec = parser.parse(path)
        curves = []
        for col_name in spec.column_names:
            x, y = spec.get_curve(col_name)
            curves.append((x, y, col_name))
            all_curves_flat.append((x, y, col_name))
        file_curves[path] = curves

    if not all_curves_flat:
        return None, [], warn_msgs

    # ================================================================
    # 2. 统计曲线数量，判断数据是否"混合"
    # ================================================================
    counts = [len(curves) for curves in file_curves.values()]
    unique_counts = set(counts)
    base_x = all_curves_flat[0][0].copy()  # 首条曲线的 X 轴副本（避免引用泄漏）
    total_curves = len(all_curves_flat)

    # 只有 1 条曲线 → 结果等于原数据，提示用户
    if total_curves == 1:
        warn_msgs.insert(0,
            f"只有一个文件且只包含 1 条曲线，"
            f"平均值等于原数据 ({os.path.basename(list(file_curves.keys())[0])})。"
        )

    # ================================================================
    # 3. 场景 A：全部单曲线，或多于 1 条但来自同 1 个文件 → 直接求总平均
    # ================================================================
    if unique_counts == {1} or len(file_curves) == 1:
        aligned = _align_curves(all_curves_flat, base_x)
        y_list = [ay for ay, _ in aligned]
        mean_y = MeanAlgorithm().execute(y_list)
        name = f"Mean_({len(y_list)}curves)"
        return base_x, [{'y': mean_y, 'name': name}], warn_msgs

    # ================================================================
    # 4. 场景 B：多个文件且所有文件曲线数相同（N > 1）→ 按列对应平均
    # ================================================================
    if len(file_curves) > 1 and len(unique_counts) == 1 and list(unique_counts)[0] > 1:
        n_cols = list(unique_counts)[0]
        results = []
        for col_idx in range(n_cols):
            col_curves = []
            for path in file_paths:
                if path not in file_curves:
                    continue
                curves = file_curves[path]
                if col_idx < len(curves):
                    col_curves.append(curves[col_idx])
            if not col_curves:
                continue
            aligned = _align_curves(col_curves, base_x)
            y_list = [ay for ay, _ in aligned]
            mean_y = MeanAlgorithm().execute(y_list)
            # 用第一条曲线名作为列名参考
            ref_name = col_curves[0][2]
            results.append({
                'y': mean_y,
                'name': f"Mean_Col{col_idx + 1}_({len(y_list)}files)"
            })
        return base_x, results, warn_msgs

    # ================================================================
    # 5. 场景 C：混合数据 → 警告 + 预平均多曲线文件 → 总平均
    # ================================================================
    multi_curve_files = []
    for path, curves in file_curves.items():
        if len(curves) > 1:
            multi_curve_files.append(
                f"  - {os.path.basename(path)} ({len(curves)} 条曲线)"
            )

    if multi_curve_files:
        warn_msgs.insert(0,
            f"检测到混合数据：部分文件包含多条曲线，"
            f"已对多曲线文件内部求平均后再参与总均值计算：\n"
            + "\n".join(multi_curve_files)
        )

    # 对每个文件：若多曲线则预平均，若单曲线则直接取
    per_file_y = []
    per_file_names = []
    for path, curves in file_curves.items():
        aligned = _align_curves(curves, base_x)
        y_list = [ay for ay, _ in aligned]
        if len(y_list) > 1:
            file_avg = MeanAlgorithm().execute(y_list)
        else:
            file_avg = y_list[0]
        per_file_y.append(file_avg)
        per_file_names.append(os.path.basename(path))

    mean_y = MeanAlgorithm().execute(per_file_y)
    name = f"Mean_({len(per_file_y)}files_mixed)"
    return base_x, [{'y': mean_y, 'name': name}], warn_msgs

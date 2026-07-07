# -*- coding: utf-8 -*-
"""
文件路径: core/algorithms/_validation.py
功能描述: 统计算法的共享输入校验工具。
          所有算法类通过调用此模块中的函数完成标准化的输入合法性检查，
          避免校验逻辑在多个算法中重复实现。
"""

import numpy as np


def validate_datasets_not_empty(datasets):
    """
    校验数据集非空且至少包含一条曲线。

    :param datasets: 一维 NumPy 数组的列表 [array_1, array_2, ...]
    :raises ValueError: 若数据集为空或无元素
    """
    if datasets is None:
        raise ValueError("计算输入不能为 None。")
    if not isinstance(datasets, (list, tuple)):
        raise ValueError(f"数据集必须是列表或元组，收到类型: {type(datasets).__name__}")
    if len(datasets) == 0:
        raise ValueError("计算输入数据集为空，至少需要 1 条曲线。")


def validate_datasets_alignment(datasets):
    """
    校验所有 1D 数组的长度完全一致。

    :param datasets: 一维 NumPy 数组的列表 [array_1, array_2, ...]
    :raises ValueError: 若存在长度不一致的数组
    """
    if len(datasets) < 1:
        return

    base_len = len(datasets[0])
    for i, ds in enumerate(datasets):
        if ds is None:
            raise ValueError(f"第 {i+1} 条曲线数据为 None。")
        arr = np.asarray(ds, dtype=float)
        if arr.ndim != 1:
            raise ValueError(
                f"第 {i+1} 条曲线必须是 1D 数组，当前维度: {arr.ndim}"
            )
        if len(arr) != base_len:
            raise ValueError(
                f"数据对齐错误：第 {i+1} 条曲线长度 ({len(arr)}) "
                f"与首条曲线长度 ({base_len}) 不一致。"
            )


def validate_ratio_inputs(num_x, num_y, den_x, den_y):
    """
    校验比值计算所需的四个输入参数均非 None，且各自长度匹配。

    :param num_x: 分子波长 X 轴
    :param num_y: 分子强度 Y 轴
    :param den_x: 分母波长 X 轴
    :param den_y: 分母强度 Y 轴
    :raises ValueError: 若任意参数为 None 或长度不匹配
    """
    if num_x is None or num_y is None or den_x is None or den_y is None:
        raise ValueError("比值计算输入数据不能为空。")

    num_x = np.asarray(num_x, dtype=float)
    num_y = np.asarray(num_y, dtype=float)
    den_x = np.asarray(den_x, dtype=float)
    den_y = np.asarray(den_y, dtype=float)

    if len(num_x) != len(num_y):
        raise ValueError(
            f"分子波长({len(num_x)})与强度({len(num_y)})长度不一致。"
        )
    if len(den_x) != len(den_y):
        raise ValueError(
            f"分母波长({len(den_x)})与强度({len(den_y)})长度不一致。"
        )

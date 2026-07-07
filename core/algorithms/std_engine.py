# -*- coding: utf-8 -*-
"""
文件路径: core/algorithms/std_engine.py
功能描述: 光谱通道多曲线标准差计算算法。
          继承自 BaseAlgorithm，外部唯一入口为 execute(datasets)。
          用于噪声与偏差水平评估。
"""

import numpy as np
from core.algorithms.base_algo import BaseAlgorithm
from core.algorithms._validation import validate_datasets_not_empty, validate_datasets_alignment


class StdAlgorithm(BaseAlgorithm):
    """
    光谱通道多曲线标准差计算算法。

    外部调用方式:
        result = StdAlgorithm().execute(datasets)
    其中 datasets 为一维 NumPy 数组的列表。
    """

    def __init__(self):
        super().__init__(name="Standard Deviation")

    # ==================================================================
    # 钩子实现
    # ==================================================================

    def _validate(self, datasets):
        """
        输入校验：非空 + 长度对齐。
        """
        validate_datasets_not_empty(datasets)
        validate_datasets_alignment(datasets)

    def _compute(self, datasets):
        """
        纯数学：沿多谱线维度（轴 0）求逐点标准差。
        """
        data_stack = np.array(datasets, dtype=float)
        return np.std(data_stack, axis=0)

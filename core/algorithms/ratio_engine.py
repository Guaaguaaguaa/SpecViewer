# -*- coding: utf-8 -*-
"""
文件路径: core/algorithms/ratio_engine.py
功能描述: Ratio（比值/反射率）深度衍算算法引擎。
          继承自 BaseAlgorithm，外部唯一入口为 execute(num_x, num_y, den_x, den_y)。
          支持：
          1. 智能大小判定 —— 始终以大值除以小值
          2. 高精度波长插值对齐 —— 两光谱波长不一致时自动线性插值
          3. 安全除法 —— 自动清洗 NaN/Inf
"""

import numpy as np
from core.algorithms.base_algo import BaseAlgorithm
from core.algorithms._validation import validate_ratio_inputs


class RatioAlgorithm(BaseAlgorithm):
    """
    高精度光谱比值（Ratio / Transmittance）算法。

    外部调用方式:
        aligned_x, ratio_y = RatioAlgorithm().execute(num_x, num_y, den_x, den_y)

    内部自动完成：
      1. 智能大小判定 —— 比较两组数据的平均强度，确保大 ÷ 小
      2. 波长对齐 —— 以分子波长轴为基准，对分母进行一维线性插值
      3. 安全除法 —— NaN/Inf 替换为 0.0
    """

    def __init__(self):
        super().__init__(name="Ratio")

    # ==================================================================
    # 钩子实现
    # ==================================================================

    def _validate(self, num_x, num_y, den_x, den_y):
        """
        输入校验：四参数均非 None 且各自长度匹配。
        """
        validate_ratio_inputs(num_x, num_y, den_x, den_y)

    def _compute(self, num_x, num_y, den_x, den_y):
        """
        核心比值运算流水线：智能大小判定 → 波长对齐插值 → 安全除法。
        """
        num_x = np.asarray(num_x, dtype=float)
        num_y = np.asarray(num_y, dtype=float)
        den_x = np.asarray(den_x, dtype=float)
        den_y = np.asarray(den_y, dtype=float)

        # ----------------------------------------------------------------
        # 1. 智能大小判定：始终用大值除以小值
        #    规格要求: "始终用大值除以小值"
        # ----------------------------------------------------------------
        if np.nanmean(num_y) < np.nanmean(den_y):
            # 分子平均值较小 → 交换，使 num ≥ den
            num_x, num_y, den_x, den_y = den_x, den_y, num_x, num_y

        # ----------------------------------------------------------------
        # 2. 波长对齐：若两 X 轴不一致，以分子波长轴为基准对分母插值
        # ----------------------------------------------------------------
        if len(num_x) == len(den_x) and np.allclose(num_x, den_x, atol=1e-5):
            aligned_den_y = den_y
        else:
            # 一维线性插值：将分母映射到分子的波长网格上
            aligned_den_y = np.interp(num_x, den_x, den_y, left=np.nan, right=np.nan)

        # ----------------------------------------------------------------
        # 3. 安全除法：规避除零，清洗 NaN/Inf
        # ----------------------------------------------------------------
        with np.errstate(divide='ignore', invalid='ignore'):
            ratio_y = num_y / aligned_den_y
            ratio_y[~np.isfinite(ratio_y)] = 0.0

        return num_x.copy(), ratio_y

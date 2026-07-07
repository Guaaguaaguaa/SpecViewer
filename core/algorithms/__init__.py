# -*- coding: utf-8 -*-
"""
core.algorithms 包 — 光谱统计算法引擎。
暴露算法基类、三个具体算法实现以及文件级桥接工具。
外部模块只需 import 此包即可使用全部统计算法功能。
"""

from core.algorithms.base_algo import BaseAlgorithm
from core.algorithms.mean_engine import MeanAlgorithm
from core.algorithms.std_engine import StdAlgorithm
from core.algorithms.ratio_engine import RatioAlgorithm
from core.algorithms.runner import mean_from_files

__all__ = [
    "BaseAlgorithm",
    "MeanAlgorithm",
    "StdAlgorithm",
    "RatioAlgorithm",
    "mean_from_files",
]

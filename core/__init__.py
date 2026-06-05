# -*- coding: utf-8 -*-
"""
core 包 — SpecViewer 核心数据层。
暴露 SpectrumData（光谱数据模型）和 DataManager（全局内存状态管理器）。
"""

from core.data_manager import SpectrumData, DataManager

__all__ = ["SpectrumData", "DataManager"]

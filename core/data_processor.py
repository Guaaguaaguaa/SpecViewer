# -*- coding: utf-8 -*-
"""
文件路径: core/data_processor.py
功能描述: 提供通用的数据处理接口。
          现已委托给 core.algorithms.runner.mean_from_files()，
          保留此类以维持向后兼容。
"""

from core.algorithms.runner import mean_from_files


class DataProcessor:
    @staticmethod
    def calculate_mean(file_paths):
        """
        接收文件绝对路径列表，批量读取并计算所有曲线的平均值。
        现已委托给统一算法桥接器 mean_from_files()。

        :return: (x, results, warnings)
                 x: 公共 X 轴
                 results: [{'y': ndarray, 'name': str}, ...]
                 warnings: 警告字符串列表
        """
        return mean_from_files(file_paths)

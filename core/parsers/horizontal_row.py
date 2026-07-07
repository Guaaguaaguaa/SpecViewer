# -*- coding: utf-8 -*-
"""
文件路径: core/parsers/horizontal_row.py
功能描述: 横向行存储光谱数据解析器（超强自适应版）。
          自适应解析格式 C 及其变体：
          - 标准模式：第一行为波长（横向），后续行为纯数值数据。
          - 标签变体模式（如 2025-01-16_13-49-50-967.csv）：第一行为索引（0,1,2...），
            第一列为各数据行对应的自定义名称，后续列为光谱数值。
"""

import sys
import os
import re
import numpy as np

# ----------------------------------------------------
# 路径兼容性注入：将项目根目录动态添加到 sys.path
# ----------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.parsers.base_parser import BaseParser, ParserFactory
from core.data_manager import SpectrumData


@ParserFactory.register
class HorizontalRowParser(BaseParser):
    """
    智能自适应横向行存储光谱解析器。
    继承自 BaseParser 并自动向工厂注册。
    """

    # 积分时间模糊匹配正则规则
    INT_TIME_PATTERNS = [
        r"integration[^0-9]*([0-9]+)",
        r"积分[^0-9]*([0-9]+)",
        r"upshutter[^0-9]*([0-9]+)",
    ]

    # 科学计数法数字判定正则
    NUM_PATTERN = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")

    @classmethod
    def can_parse(cls, filepath):
        """
        特征盲测函数：快速扫描文件前几行。
        判断是否为横向行存储格式。
        """
        if not os.path.exists(filepath):
            return False

        _, ext = os.path.splitext(filepath.lower())
        if ext not in ['.csv', '.txt']:
            return False

        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                # 读取前 5 行用于盲测
                probe_lines = [f.readline().strip() for _ in range(5)]

            probe_lines = [line for line in probe_lines if line]
            if not probe_lines:
                return False

            # 对第一行执行横向扫描测试
            first_line = probe_lines[0]
            parts = [p.strip() for p in re.split(r"[,\t ]+", first_line) if p.strip()]
            
            # 如果是 SpcName 这种开头，去掉第一个进行数字检测
            test_parts = parts[1:] if not cls.NUM_PATTERN.match(parts[0]) else parts
            
            if len(test_parts) < 10: 
                return False

            numeric_vals = [float(p) for p in test_parts if cls.NUM_PATTERN.match(p)]

            # 如果数值占比高，认为该文件可被解析
            if len(numeric_vals) / len(test_parts) >= 0.7:
                return True

        except Exception:
            return False

        return False

    def parse(self, filepath, display_name=None) -> SpectrumData:
        """
        自适应解析横向光谱文件，自动兼容首列带非数值文本标签的变体。
        """
        abs_path = os.path.abspath(filepath)
        filename = os.path.basename(abs_path)
        final_display_name = display_name if display_name else filename

        # 1. 载入所有文本行
        with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
            content_lines = [line.strip() for line in f.readlines() if line.strip()]

        if not content_lines:
            raise ValueError(f"文件内容为空: {filename}")

        # 2. 正则提取积分时间
        integration_time = self._extract_integration_time(content_lines)

        # 3. 筛选有效数值行
        # 如果第一行包含 SpcName 等字样，直接判定为标签模式
        first_line_parts = re.split(r"[,\t ]+", content_lines[0])
        has_first_col_names = not self.NUM_PATTERN.match(first_line_parts[0])
        
        # 将行数据转化为数值矩阵，如果 has_first_col_names 为 True，则跳过第一列
        wavelength_row = None
        intensity_rows = []
        custom_column_names = []
        authoritative_cols = None  # 以波长行长度为权威列数

        for i, line in enumerate(content_lines):
            parts = [p.strip() for p in re.split(r"[,\t ]+", line) if p.strip()]
            if len(parts) < 2:
                continue

            # 提取数值部分
            if has_first_col_names:
                row_label = parts[0]
                row_vals = [float(p) for p in parts[1:] if self.NUM_PATTERN.match(p)]
            else:
                row_label = f"行通道{i+1}"
                row_vals = [float(p) for p in parts if self.NUM_PATTERN.match(p)]

            if len(row_vals) < 5:
                continue

            if i == 0:
                wavelength_row = np.array(row_vals, dtype=float)
                authoritative_cols = len(wavelength_row)
            else:
                # 以波长行长度为权威列数截断对齐，排除尾部元数据干扰
                if authoritative_cols is not None and len(row_vals) > authoritative_cols:
                    row_vals = row_vals[:authoritative_cols]
                intensity_rows.append(row_vals)
                custom_column_names.append(row_label)

        if wavelength_row is None or not intensity_rows:
            raise ValueError(f"无法解析数据格式: {filename}")

        # 转置数据
        data_matrix = np.array(intensity_rows, dtype=float).T

        # 7. 元数据标注
        metadata = {"Wavelength Mode": "Pixel Index" if wavelength_row.max() < 10000 else "Physical Wavelength"}
        if integration_time: metadata['Integrate time'] = f"{integration_time}ms"

        return SpectrumData(
            filepath=abs_path,
            wavelengths=wavelength_row,
            data_matrix=data_matrix,
            column_names=custom_column_names,
            metadata=metadata,
            display_name=final_display_name
        )

    def _extract_integration_time(self, lines):
        for line in lines:
            match = re.search(r"integration[^0-9]*([0-9]+)", line.lower())
            if match: return int(match.group(1))
        return None


if __name__ == '__main__':
    print(">>> 正在启动自适应横向行存储解析器测试...")
    parser = HorizontalRowParser()
    print("✔ HorizontalRowParser 已成功加载并准备自适应读取。")
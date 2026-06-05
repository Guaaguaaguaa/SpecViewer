# -*- coding: utf-8 -*-
"""
文件路径: core/parsers/horizontal_row.py
功能描述: 横向行存储光谱数据解析器（超强鲁棒性版）。
          自适应解析格式 C：第一行为波长（横向），第二行及后续行为数据，
          文件尾部或不规则行作为仪器元数据进行提取和隔离。
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
    自适应横向行存储光谱解析器。
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
        如果文件属于“行存储”：首行或前几行的元素横向切分后，绝大部分都应该是连续递增的波长数值。
        """
        if not os.path.exists(filepath):
            return False

        _, ext = os.path.splitext(filepath.lower())
        if ext not in ['.csv', '.txt']:
            return False

        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                # 只读取前 3 行用于快速盲测
                probe_lines = [f.readline().strip() for _ in range(3)]

            probe_lines = [line for line in probe_lines if line]
            if not probe_lines:
                return False

            # 对第一行执行横向扫描测试
            first_line = probe_lines[0]
            parts = [p.strip() for p in re.split(r"[,\t ]+", first_line) if p.strip()]
            
            if len(parts) < 10:  # 横向光谱一般拥有上百个点，列数必然非常大
                return False

            # 提取其中能转化为浮点数的有效数值
            numeric_vals = []
            for p in parts:
                if cls.NUM_PATTERN.match(p):
                    numeric_vals.append(float(p))

            # 如果这一行有 80% 以上是数字，且整体上呈现典型的“波长递增”物理特征，即可确认为行存储格式
            if len(numeric_vals) / len(parts) >= 0.8:
                # 随机采样几个点检查是否严格递增（波长序列核心特征）
                increases = sum(1 for i in range(len(numeric_vals) - 1) if numeric_vals[i+1] > numeric_vals[i])
                if increases / (len(numeric_vals) - 1) >= 0.9:
                    return True

        except Exception:
            return False

        return False

    def parse(self, filepath, display_name=None) -> SpectrumData:
        """
        深度解析横向光谱文件。
        """
        abs_path = os.path.abspath(filepath)
        filename = os.path.basename(abs_path)
        final_display_name = display_name if display_name else filename

        # 1. 采用多编码策略载入所有文本行
        content_lines = []
        encodings = ['utf-8', 'gbk', 'gb2312', 'latin1']
        success = False

        for encoding in encodings:
            try:
                with open(abs_path, 'r', encoding=encoding) as f:
                    content_lines = [line.strip() for line in f.readlines()]
                success = True
                break
            except (UnicodeDecodeError, LookupError):
                continue

        if not success:
            raise ValueError(f"行存储解析器无法读取文件: {filename}")

        # 过滤空行
        content_lines = [line for line in content_lines if line]
        if not content_lines:
            raise ValueError(f"文件内容为空: {filename}")

        # 2. 正则提取可能的积分时间
        integration_time = self._extract_integration_time(content_lines)

        # 3. 扫描各行，提取数据行与非数据行（元数据）
        wavelength_row = None
        intensity_rows = []
        metadata = {}

        if integration_time is not None:
            metadata['Integrate time'] = f"{integration_time}ms"

        # 逐行清洗与判定
        for idx, line in enumerate(content_lines):
            parts = [p.strip() for p in re.split(r"[,\t ]+", line) if p.strip()]
            if not parts:
                continue

            # 统计这一行的数值占比
            numeric_count = 0
            row_numbers = []
            for p in parts:
                if self.NUM_PATTERN.match(p):
                    numeric_count += 1
                    row_numbers.append(float(p))

            # 判定阈值：若一行中超过 80% 为数值
            if len(parts) >= 10 and (numeric_count / len(parts) >= 0.8):
                # 如果还没有波长行，并且该行呈单调递增，则锁定为 X轴波长行
                if wavelength_row is None:
                    # 检查是否为递增序列（避免把数据强度行误当作波长）
                    increases = sum(1 for i in range(len(row_numbers) - 1) if row_numbers[i+1] > row_numbers[i])
                    if len(row_numbers) > 1 and (increases / (len(row_numbers) - 1) >= 0.8):
                        wavelength_row = np.array(row_numbers, dtype=float)
                    else:
                        # 否则，视为一条强度数据行 (即使没有波长，也有可能是第一条强度)
                        intensity_rows.append(row_numbers)
                else:
                    # 已有波长行，后续高比例数值行全部归入光谱强度矩阵
                    intensity_rows.append(row_numbers)
            else:
                # 属于非数值行，作为元数据/头文件暂存
                # 兼容 key: value, key, value 的解析
                meta_parts = [p.strip() for p in re.split(r"[:,]+", line) if p.strip()]
                if len(meta_parts) >= 2:
                    key = meta_parts[0]
                    # 避开已经被正则专门提取的积分时间
                    if not any(k in key.lower() for k in ["integration", "积分", "upshutter"]):
                        metadata[key] = meta_parts[1]

        # 4. 安全守护与数据对齐
        if wavelength_row is None:
            raise ValueError(f"行存储解析器未能在文件中检索到有效的单调波长行: {filename}")
        if not intensity_rows:
            raise ValueError(f"行存储解析器未能在文件中定位到任何有效的数据行: {filename}")

        # 将强度数据转化为标准的 2D numpy 矩阵
        # 注意：横向存储读取出来的是 (num_curves, num_wavelengths)，
        # 我们必须将其【转置】，变成中台统一规定的 (num_wavelengths, num_curves) 纵向矩阵！
        raw_matrix = np.array(intensity_rows, dtype=float)
        
        # 截断或对准，防止横向各行长度不一致引起的 numpy 报错
        min_len = min(len(wavelength_row), raw_matrix.shape[1])
        wavelength_row = wavelength_row[:min_len]
        data_matrix = raw_matrix[:, :min_len].T  # 执行关键转置！确保波长与强度矩阵的第 0 维度完全对齐

        # 5. 智能分配列名
        num_curves = data_matrix.shape[1]
        column_names = [f"行通道{i+1}" for i in range(num_curves)]

        # 6. 打包封装返回 SpectrumData
        return SpectrumData(
            filepath=abs_path,
            wavelengths=wavelength_row,
            data_matrix=data_matrix,
            column_names=column_names,
            metadata=metadata,
            display_name=final_display_name
        )

    def _extract_integration_time(self, lines):
        """
        利用多正则表达式模糊匹配，从文本行中快速捕捉积分时间 (ms)
        """
        for line in lines:
            line_low = line.lower()
            for pattern in self.INT_TIME_PATTERNS:
                match = re.search(pattern, line_low)
                if match:
                    try:
                        return int(match.group(1))
                    except Exception:
                        pass
        return None


# =================================------------------
# 独立单元测试
# =================================------------------
if __name__ == '__main__':
    print(">>> 正在启动横向行存储解析器测试...")
    parser = HorizontalRowParser()
    print("✔ HorizontalRowParser 已成功加载。")
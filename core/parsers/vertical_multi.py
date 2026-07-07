# -*- coding: utf-8 -*-
"""
文件路径: core/parsers/vertical_multi.py
功能描述: 纵向光谱数据解析器（超强鲁棒性版）。
          融合了自适应数值比例探测（智能寻找数据起点行）与多正则模糊元数据（如积分时间）提取技术。
          完美兼容格式 A（带文本头文件的多列纵向数据，如 ATP6500）与格式 B（带 SpcName 的单列纵向数据，如 JZh）。
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
class VerticalMultiParser(BaseParser):
    """
    超强鲁棒性的自适应纵向多列光谱解析器。
    继承自 BaseParser 并自动向工厂注册。
    """
    
    # 积分时间模糊匹配正则规则
    INT_TIME_PATTERNS = [
        r"integration[^0-9]*([0-9]+)",
        r"积分[^0-9]*([0-9]+)",
        r"upshutter[^0-9]*([0-9]+)",
    ]
    
    # 浮点数科学计数法通用校验正则
    NUM_PATTERN = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")

    @classmethod
    def can_parse(cls, filepath):
        """
        特征盲测函数：快速扫描文件前几行，判断是否属于纵向列排光谱格式。
        """
        if not os.path.exists(filepath):
            return False
            
        _, ext = os.path.splitext(filepath.lower())
        if ext not in ['.csv', '.txt']:
            return False

        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                # 读取前 20 行进行特征嗅探
                probe_lines = [f.readline().strip() for _ in range(20)]
                
            probe_lines = [line for line in probe_lines if line]
            if not probe_lines:
                return False

            # 特征 1：格式 B 特征（以 SpcName 开头）
            if probe_lines[0].startswith("SpcName,") or probe_lines[0].startswith("SpcName\t"):
                # 二次确认：排除横向格式。横向格式的第二行首列为文本标签
                # （如 "R", "T", "采集光谱"），而非数值波长。
                if len(probe_lines) >= 2:
                    second_line_first = re.split(r"[,\t ]+", probe_lines[1])[0].strip()
                    if not cls.NUM_PATTERN.match(second_line_first):
                        # 第二行首列非数值 → 这是横向格式，不归本解析器处理
                        return False
                return True

            # 特征 2：通过“数值比例探测法”盲测数据区
            # 扫描前 20 行，如果有任意一行满足列数 >= 2 且 80% 以上是数字，说明这含有列排光谱特征
            for line in probe_lines:
                # 兼容 逗号、制表符、空格 分隔
                parts = [p.strip() for p in re.split(r"[,\t ]+", line) if p.strip()]
                if len(parts) < 2:
                    continue
                
                numeric_count = sum(1 for p in parts if cls.NUM_PATTERN.match(p))
                if numeric_count / len(parts) >= 0.8:
                    return True
                    
        except Exception:
            return False
            
        return False

    def parse(self, filepath, display_name=None) -> SpectrumData:
        """
        利用智能起点探测和模糊正则深度解析文件。
        """
        abs_path = os.path.abspath(filepath)
        filename = os.path.basename(abs_path)
        final_display_name = display_name if display_name else filename

        # 1. 采用自适应编码载入所有文本行
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
            raise ValueError(f"无法使用任何已知编码读取文件: {filename}")

        # 过滤空行
        content_lines = [line for line in content_lines if line]
        if not content_lines:
            raise ValueError(f"光谱文件内容为空: {filename}")

        # 2. 智能提取积分时间（提取文本行中任意符合规则的信息）
        integration_time = self._extract_integration_time(content_lines)

        # 3. 智能寻找数据起点行 (Data Start Row)
        start_row_idx = -1
        max_scan_lines = min(30, len(content_lines))
        
        for idx in range(max_scan_lines):
            line = content_lines[idx]
            # 忽略含有典型表头信息的行，防止提前误判
            if re.search(r"(date|temperature|wavelength|wavelengths|w|position)", line, re.I):
                continue
                
            parts = [p.strip() for p in re.split(r"[,\t ]+", line) if p.strip()]
            if len(parts) < 2:
                continue

            # 计算当前行中数字的占比
            numeric_count = sum(1 for p in parts if self.NUM_PATTERN.match(p))
            if numeric_count / len(parts) >= 0.8:
                start_row_idx = idx
                break

        if start_row_idx == -1:
            raise ValueError(f"无法智能识别该光谱数据的数据起始行: {filename}")

        # 4. 提取元数据（数据起点行之前的文本均视为头文件/元数据）
        metadata = {}
        if integration_time is not None:
            metadata['Integrate time'] = f"{integration_time}ms"

        for idx in range(start_row_idx):
            line = content_lines[idx]
            # 兼容 key: value, key, value 等多种仪器头文件分隔形式
            parts = [p.strip() for p in re.split(r"[:,]+", line) if p.strip()]
            if len(parts) >= 2:
                key = parts[0]
                # 避开正则已经解析过的积分时间
                if not any(k in key.lower() for k in ["integration", "积分", "upshutter"]):
                    metadata[key] = parts[1]

        # 5. 提取数据列名（数据起点行紧邻的前一行，若含有英文字母则提取为原始列名）
        raw_column_headers = []
        if start_row_idx > 0:
            potential_header_line = content_lines[start_row_idx - 1]
            # 如果该行包含字母，则极有可能是数据表头 (如 position,value,value)
            if re.search(r"[a-zA-Z]", potential_header_line):
                raw_column_headers = [p.strip() for p in re.split(r"[,\t ]+", potential_header_line) if p.strip()]

        # 6. 读取光谱纯数值矩阵
        wavelengths = []
        intensity_rows = []

        for idx in range(start_row_idx, len(content_lines)):
            line = content_lines[idx]
            parts = [p.strip() for p in re.split(r"[,\t ]+", line) if p.strip()]
            try:
                # 第一列固定为 X 轴波长
                w_val = float(parts[0])
                # 后续所有列均为 Y 轴强度数据
                row_vals = [float(p) for p in parts[1:]]
                
                # 只有整行全解析成功，才存入容器中，避免脏数据崩溃
                wavelengths.append(w_val)
                intensity_rows.append(row_vals)
            except (ValueError, IndexError):
                # 鲁棒容错：非数值行自动忽略（如文件底部的备注行、噪声）
                continue

        if not wavelengths:
            raise ValueError(f"该光谱文件内未解析到任何有效的数值数据: {filename}")

        # 转换为 NumPy 数组
        wavelength_arr = np.array(wavelengths, dtype=float)
        data_matrix = np.array(intensity_rows, dtype=float)

        # 保护：如果是一维，强制升为二维列向量
        if data_matrix.ndim == 1:
            data_matrix = data_matrix.reshape(-1, 1)

        # 7. 智能生成各通道列名（并进行重复列名序列化清洗）
        num_data_cols = data_matrix.shape[1]
        column_names = []
        
        # 裁剪出属于 Y 数据列的原始表头
        raw_y_headers = raw_column_headers[1:] if len(raw_column_headers) > 1 else []

        for col_idx in range(num_data_cols):
            base_name = "通道"
            if col_idx < len(raw_y_headers) and raw_y_headers[col_idx]:
                header_str = raw_y_headers[col_idx]
                # 避开 wavelength / position 这种对 Y 轴无意义的名字
                if header_str.lower() not in ['value', 'position', 'wavelength', 'index']:
                    base_name = header_str
            
            column_names.append(f"{base_name}{col_idx + 1}")

        # 8. 统一组装并返回 SpectrumData 模型
        return SpectrumData(
            filepath=abs_path,
            wavelengths=wavelength_arr,
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


"""
# =================================------------------
# 独立单元测试
# =================================------------------
if __name__ == '__main__':
    print(">>> 正在启动纵向多列（超强鲁棒性版）自适应解析器测试...")
    parser = VerticalMultiParser()
    print("✔ 模块加载正常，特征盲测器与数值智能定位算法已就绪。")
"""
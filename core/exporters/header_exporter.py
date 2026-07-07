# -*- coding: utf-8 -*-
"""
文件路径: core/exporters/header_exporter.py
功能描述: 光谱头文件/元数据导出工具。
          从 SpectrumData 对象的 metadata 字典生成可读的 TXT 文件。
          支持单个导出和批量汇总导出。
"""

import os
from datetime import datetime


def export_single_header(spectrum_obj, filepath):
    """
    导出单个光谱文件的元数据为 TXT 文件。

    :param spectrum_obj: SpectrumData 实例
    :param filepath: 输出文件的完整路径（含 .txt 扩展名）
    :return: 实际写入的文件绝对路径，若无 metadata 返回 None
    """
    if not spectrum_obj.metadata:
        return None

    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
    _write_header_file(filepath, spectrum_obj)
    return filepath


def export_batch_headers(spectra_list, filepath):
    """
    批量导出所有已载入文件的元数据到一个汇总 TXT 文件。

    :param spectra_list: SpectrumData 实例列表
    :param filepath: 输出文件的完整路径（含 .txt 扩展名）
    :return: 实际写入的文件绝对路径
    """
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write(f"光谱头文件批量导出\n")
        f.write(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"文件总数: {len(spectra_list)}\n")
        f.write("=" * 60 + "\n\n")

        for i, spec in enumerate(spectra_list, 1):
            f.write(f"[{i}] 文件: {spec.filename}\n")
            f.write(f"    完整路径: {spec.filepath}\n")
            f.write(f"    曲线数量: {spec.num_curves}\n")
            f.write(f"    波长点数: {len(spec.wavelengths)}\n")
            f.write(f"    波长范围: {spec.wavelengths[0]:.2f} ~ "
                    f"{spec.wavelengths[-1]:.2f} nm\n")

            if spec.metadata:
                f.write(f"    元数据:\n")
                for key, value in spec.metadata.items():
                    f.write(f"      {key}: {value}\n")
            else:
                f.write(f"    元数据: (无)\n")
            f.write("\n")

    return filepath


def _write_header_file(filepath, spectrum_obj):
    """
    将单个 SpectrumData 的元数据写入文件。
    """
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"文件名: {spectrum_obj.filename}\n")
        f.write(f"完整路径: {spectrum_obj.filepath}\n")
        f.write(f"显示名称: {spectrum_obj.display_name}\n")
        f.write(f"曲线数量: {spectrum_obj.num_curves}\n")
        f.write(f"曲线名称: {', '.join(spectrum_obj.column_names)}\n")
        f.write(f"波长点数: {len(spectrum_obj.wavelengths)}\n")
        f.write(f"波长范围: {spectrum_obj.wavelengths[0]:.4f} ~ "
                f"{spectrum_obj.wavelengths[-1]:.4f} nm\n")
        f.write("-" * 40 + "\n")
        f.write("元数据:\n")
        if spectrum_obj.metadata:
            for key, value in spectrum_obj.metadata.items():
                f.write(f"  {key}: {value}\n")
        else:
            f.write("  (无)\n")

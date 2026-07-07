# -*- coding: utf-8 -*-
"""
文件路径: core/data_manager.py
功能描述: 整个光谱系统的【数据中台】。
          定义了标准光谱数据模型 SpectrumData，以及全局内存状态管理器 DataManager。
          支持自动分配唯一列名、防止重名列混淆、防止完全相同文件重复加载、自动处理同名不同路径文件。
"""

import sys
import os
import numpy as np
from PyQt6.QtCore import QSettings

# ----------------------------------------------------
# 路径兼容性注入：将项目根目录动态添加到 sys.path
# ----------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


class SpectrumData:
    """
    光谱数据模型类。
    用于在内存中封装单个光谱文件的解析结果，对外提供统一的数据属性。
    """
    def __init__(self, filepath, wavelengths, data_matrix, column_names=None, metadata=None, display_name=None):
        """
        :param filepath: 文件的绝对路径 (如 "D:/data/ATP6500_001.csv")
        :param wavelengths: NumPy 一维数组，代表波长 (X 轴)
        :param data_matrix: NumPy 二维矩阵，每一列代表一条光谱强度线 (Y 轴)
        :param column_names: 原始数据列名称的列表
        :param metadata: 字典类型，用于暂存头文件/元数据信息
        :param display_name: 唯一的显示名称（用于多文件同名时区分展示，若无则使用 filename）
        """
        self.filepath = os.path.abspath(filepath)
        self.filename = os.path.basename(self.filepath)
        self.display_name = display_name if display_name else self.filename
        
        self.wavelengths = np.asarray(wavelengths, dtype=float)
        self.data_matrix = np.asarray(data_matrix, dtype=float)
        self.metadata = metadata if isinstance(metadata, dict) else {}

        # 简单的参数校验，保证模型高内聚
        if self.data_matrix.ndim == 1:
            # 如果是单条数据，强制升维成二维列向量 (N, 1)
            self.data_matrix = self.data_matrix.reshape(-1, 1)

        # ----------------------------------------------------
        # 核心鲁棒性优化：自动赋值与全局唯一化列名
        # ----------------------------------------------------
        num_cols = self.data_matrix.shape[1]
        
        # 情况 A：如果处理数据时没有传入列名，或者数量对不上，自动接管并分配
        if column_names is None or len(column_names) != num_cols:
            self.column_names = [f"{self.display_name} - 数据列{i+1}" for i in range(num_cols)]
        else:
            # 情况 B：有原始列名（例如都是 'value'），为了防止多文件画图检索冲突，
            # 自动包装成带唯一文件标识的前缀： "display_name - column_name"
            self.column_names = []
            for name in column_names:
                name_str = str(name).strip()
                if name_str.startswith(self.display_name):
                    self.column_names.append(name_str)
                else:
                    self.column_names.append(f"{self.display_name} - {name_str}")

        # 终极安全守护校验
        assert len(self.wavelengths) == self.data_matrix.shape[0], \
            f"波长数量({len(self.wavelengths)})与数据行数({self.data_matrix.shape[0]})不一致！"
        assert len(self.column_names) == self.data_matrix.shape[1], \
            f"曲线标识数量({len(self.column_names)})与数据列数({self.data_matrix.shape[1]})不一致！"

    @property
    def num_curves(self):
        """获取当前数据包含的光谱曲线条数"""
        return self.data_matrix.shape[1]

    def get_curve(self, curve_name):
        """
        核心数据切片接口：
        UI 或统计计算引擎只持有 curve_name 字符串，通过该方法在中台内切出 NumPy 数组。
        """
        if curve_name in self.column_names:
            idx = self.column_names.index(curve_name)
            # 返回波长 (X) 和切片后的 1D 强度数据 (Y)
            return self.wavelengths, self.data_matrix[:, idx]
        
        # 鲁棒性退回：如果在极其特殊情况下，传入的是索引字符串，尝试转换为数字提取
        try:
            idx = int(curve_name)
            if 0 <= idx < self.num_curves:
                return self.wavelengths, self.data_matrix[:, idx]
        except ValueError:
            pass
            
        raise ValueError(f"光谱数据中找不到唯一的曲线标识: {curve_name}")


class DataManager:
    """
    数据管理器（单例模式）。
    统一以【绝对路径】作为存储键，彻底隔离多目录同名文件的覆盖风险。
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DataManager, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return

        # 核心改变：以绝对路径为存储键的字典 { absolute_filepath: SpectrumData_object }
        self._loaded_spectra = {}
        self._initialized = True

        # 从 QSettings 恢复上次的输出路径，实现跨会话持久化
        self._qsettings = QSettings("OptoAnalysisTech", "SpecViewer")
        self._output_path = self._qsettings.value("output_path", "", type=str)

    def check_file_status(self, filepath):
        """
        【文件状态检测网关】
        在 MainWindow 打开文件弹窗选好后，第一时间调用该函数。
        :param filepath: 文件路径
        :return: (status_code, message, suggested_display_name)
                 status_code: 
                   - 'ALREADY_LOADED': 绝对路径完全一致，应弹出提示并拒绝打开。
                   - 'NAME_CONFLICT': 文件名相同但属于不同路径。允许打开，但建议使用重命名后的显示名。
                   - 'NEW_FILE': 干净的全新文件，直接载入。
        """
        abs_path = os.path.abspath(filepath)
        filename = os.path.basename(abs_path)

        # 1. 完全相同路径的文件检测
        if abs_path in self._loaded_spectra:
            return 'ALREADY_LOADED', f"该文件已在软件中打开，请勿重复载入！\n路径: {abs_path}", filename

        # 2. 同名但不同物理路径的文件检测
        conflict_count = 0
        for spec in self._loaded_spectra.values():
            if spec.filename == filename:
                conflict_count += 1

        if conflict_count > 0:
            name_part, ext = os.path.splitext(filename)
            # 自动生成如 "data (1).csv" 的唯一显示别名
            unique_display_name = f"{name_part} ({conflict_count}){ext}"
            return 'NAME_CONFLICT', f"检测到同名文件，已自动重命名为 {unique_display_name}", unique_display_name

        return 'NEW_FILE', "全新文件加载", filename

    def add_spectrum(self, spectrum_obj):
        """将标准光谱对象注册进数据中台"""
        if not isinstance(spectrum_obj, SpectrumData):
            raise TypeError("添加的数据必须是 SpectrumData 类型实例")
        # 键值永远是唯一的绝对路径
        self._loaded_spectra[spectrum_obj.filepath] = spectrum_obj

    def remove_spectrum_by_filepath(self, filepath):
        """通过绝对路径注销内存光谱数据"""
        abs_path = os.path.abspath(filepath)
        if abs_path in self._loaded_spectra:
            del self._loaded_spectra[abs_path]

    def remove_spectrum_by_display_name(self, display_name):
        """辅助移除：通过界面显示的 display_name 寻找并移除对应数据"""
        target_path = None
        for path, spec in self._loaded_spectra.items():
            if spec.display_name == display_name:
                target_path = path
                break
        if target_path:
            del self._loaded_spectra[target_path]

    def clear_all(self):
        """清空中台中所有的载入数据"""
        self._loaded_spectra.clear()

    def get_spectrum(self, filepath):
        """获取指定绝对路径的光谱对象"""
        return self._loaded_spectra.get(os.path.abspath(filepath), None)

    def get_all_spectra(self):
        """获取中台里所有的光谱对象"""
        return list(self._loaded_spectra.values())

    def find_curve_source(self, curve_name):
        """
        通过唯一的曲线别名（如 "data.csv - value"），反查对应的 SpectrumData 数据对象
        """
        for spec in self._loaded_spectra.values():
            if curve_name in spec.column_names:
                return spec
        return None

    def get_curve_data(self, curve_name):
        """
        中台核心查询 API：
        右侧画布和计算层只要将选中的曲线别名（String）传过来，立刻返回物理 X (波长) 和 Y (强度) 数组。
        """
        spec = self.find_curve_source(curve_name)
        if spec:
            return spec.get_curve(curve_name)
        return None, None

    def register_computed_result(self, name, x, y):
        """
        将计算结果（Mean/Std/Ratio 等）注册为虚拟 SpectrumData。
        若同名结果已存在，自动追加序号（#2, #3...）确保不覆盖。
        使用合成路径 __calc__/<name> 避免与真实文件路径冲突。

        :param name: 结果曲线显示名（如 "Mean_(5files)"）
        :param x: X 轴波长数组
        :param y: Y 轴强度数组
        :return: 注册后的 SpectrumData 对象（name 可能已被修改为唯一值）
        """
        # 自动去重：若 display_name 已被占用，追加序号
        existing_names = {s.display_name for s in self._loaded_spectra.values()}
        unique_name = name
        counter = 2
        while unique_name in existing_names:
            unique_name = f"{name} (#{counter})"
            counter += 1

        synthetic_path = os.path.abspath(os.path.join("__calc__", unique_name))
        spec = SpectrumData(
            filepath=synthetic_path,
            wavelengths=x,
            data_matrix=np.atleast_2d(y).T if y.ndim == 1 else y,
            column_names=[unique_name],
            metadata={'type': 'computed'},
            display_name=unique_name
        )
        self._loaded_spectra[synthetic_path] = spec
        return spec

    def set_output_path(self, path):
        self._output_path = path
        # 持久化到 QSettings，下次启动自动恢复
        self._qsettings.setValue("output_path", path)

    def get_output_path(self):
        return self._output_path


"""
# =================================------------------
# 独立单元测试逻辑
# =================================------------------
if __name__ == '__main__':
    print(">>> 正在启动数据中台模块鲁棒性演进测试...")

    dm = DataManager()

    # 模拟路径 1 处的同名文件
    path_1 = "D:/Lab_A/test_data.csv"
    wave = np.array([500.0, 501.0, 502.0])
    intensity_1 = np.array([[1000], [1010], [1020]]) # 没有列名的情况

    # 检测路径 1
    status_1, msg_1, disp_1 = dm.check_file_status(path_1)
    assert status_1 == 'NEW_FILE', "全新路径文件检测失败！"

    spec_1 = SpectrumData(path_1, wave, intensity_1, column_names=None, display_name=disp_1)
    dm.add_spectrum(spec_1)
    print("✔ 全新无列名文件载入成功。自动生成的列名：", spec_1.column_names)

    # 检测完全相同的路径重复载入
    status_dup, msg_dup, _ = dm.check_file_status(path_1)
    assert status_dup == 'ALREADY_LOADED', "重复文件检测功能失效！"
    print("✔ 完全相同的路径过滤成功，拦截原因：", msg_dup)

    # 模拟路径 2 处的同名文件（模拟同名不同目录）
    path_2 = "D:/Lab_B/test_data.csv"
    intensity_2 = np.array([[2000], [2010], [2020]])

    # 检测路径 2
    status_2, msg_2, disp_2 = dm.check_file_status(path_2)
    assert status_2 == 'NAME_CONFLICT', "同名不同路径检测失败！"
    assert disp_2 == "test_data (1).csv", "自动重命名后缀分配有误！"

    spec_2 = SpectrumData(path_2, wave, intensity_2, column_names=["强度A"], display_name=disp_2)
    dm.add_spectrum(spec_2)
    print(f"✔ 同名冲突文件正常拉入，重命名为：{disp_2}，列名已自动保护绑定为：{spec_2.column_names}")

    # 验证 get_curve 数据获取
    x, y = dm.get_curve_data("test_data (1).csv - 强度A")
    assert y[0] == 2000, "跨文件数据精确匹配提取有误！"
    print("✔ 极速通过唯一的曲线别名反向索引获取对应切片数组成功！")
    print(">>> 所有的边界与鲁棒性验证全部通过！")
"""
# -*- coding: utf-8 -*-
"""
文件路径: core/parsers/iris_binary.py
功能描述: IRIS 仪器专属二进制光谱数据解析器。
          支持二进制数据块流式解析、多项式波长重构、自动计算扣除暗电流后的反射率与辐射亮度/辐照度。
          自注册到 ParserFactory 工厂，输出仅包含用户关心的核心通道（原始DN值及扣暗电流后的物理量）。
"""

import sys
import os
import struct
import json
import math
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
class IrisBinaryParser(BaseParser):
    """
    IRIS 二进制文件自适应解析器。
    """
    # ---------- 二进制块头常量定义 ----------
    SPECTRAL_DATA = 0x00ff00ff
    SPECTRAL_INFO = 0xff00ff00
    OTHER_BLOCK   = 0xf0f0f0f0
    IMAGE_BLOCK   = 0x0f0f0f0f

    # 地面数据类型字典映射
    GROUND_TYPE_MAP = {
        0: "Ground_DN",
        7: "Flat_DN",
        6: "Dark_DN",
        5: "Absfile",
        4: "Calfile",
    }

    @classmethod
    def can_parse(cls, filepath):
        """
        特征盲测函数：读取二进制文件前 4 字节，校验是否符合 IRIS 特征头定义
        """
        if not os.path.exists(filepath):
            return False

        try:
            with open(filepath, "rb") as f:
                header_bytes = f.read(4)
                if len(header_bytes) < 4:
                    return False
                # 以小端无符号整型解包首个 4 字节块头
                header_val, = struct.unpack("<I", header_bytes)
                
                # 校验是否属于 IRIS 的标准数据块
                if header_val in [cls.SPECTRAL_DATA, cls.SPECTRAL_INFO, cls.OTHER_BLOCK, cls.IMAGE_BLOCK]:
                    return True
        except Exception:
            return False
        return False

    def parse(self, filepath, display_name=None) -> SpectrumData:
        """
        流式解析二进制块，提取波长校准、曝光参数、多通道曲线，并自动进行物理学衍算。
        """
        abs_path = os.path.abspath(filepath)
        filename = os.path.basename(abs_path)
        final_display_name = display_name if display_name else filename

        wavelength_map = {}
        spectra_raw = {}
        json_blocks = []
        image_blocks = []
        it_sample = 1.0
        is_irradiance = False

        # 1. 二进制流式读取
        with open(abs_path, "rb") as f:
            file_size = os.path.getsize(abs_path)
            
            # IRIS 文件标准结构包含 4 个物理数据块
            for _ in range(4):
                if f.tell() >= file_size:
                    break
                try:
                    header, = self._read_struct("<I", f)
                    length, = self._read_struct("<Q", f)
                    block_start = f.tell()
                except (EOFError, struct.error):
                    break

                # -------------------- SpectralInfo 块 --------------------
                if header == self.SPECTRAL_INFO and length > 0:
                    try:
                        n, = self._read_struct("<H", f)
                        for _ in range(n):
                            info_len, = self._read_struct("<H", f)
                            info_type, = self._read_struct("<B", f)
                            buf = f.read(info_len)

                            if info_type == 0x00:
                                js = buf.decode(errors="ignore")
                                json_blocks.append(js)

                                # 提取波长校准系数
                                res = self._extract_wave_coeff(js)
                                if res:
                                    sid, bandnum, a1, a2, a3, a4 = res
                                    wavelength_map[sid] = [
                                        self._calc_wavelength_from_coeff(i, a1, a2, a3, a4)
                                        for i in range(bandnum)
                                    ]

                                # 提取曝光/积分时间
                                it = self._extract_it_from_json(js)
                                if it is not None:
                                    it_sample = it

                                # 判断是否处于 180d 辐照度工作模式
                                if not is_irradiance:
                                    is_irradiance = self._check_is_irradiance(js)
                    except Exception as e:
                        print(f"[IRIS解析警报] 信息块解析异常: {e}")

                # -------------------- SpectralData 块 --------------------
                elif header == self.SPECTRAL_DATA and length > 0:
                    try:
                        spec_num, = self._read_struct("<H", f)
                        for _ in range(spec_num):
                            # 跳过固定的描述字节
                            self._read_string(f, 100)
                            self._read_string(f, 50)

                            # 读取底层非数值传感器元数据
                            self._read_struct("<B", f)  # Fiber
                            f.read(10)                  # Time Struct
                            self._read_struct("<d", f)  # Exposure
                            self._read_struct("<f", f)  # Gain

                            # 数据类型特征读取
                            dtype, = self._read_struct("<B", f)
                            pixelsize, = self._read_struct("<B", f)
                            ground_type, = self._read_struct("<B", f)
                            bands, = self._read_struct("<H", f)
                            self._read_struct("<B", f)  # Valid flag

                            # 读取光谱点强度
                            values = []
                            for _ in range(bands):
                                if dtype == 0x12:
                                    v, = self._read_struct("<H", f)
                                elif dtype == 0x20:
                                    v, = self._read_struct("<f", f)
                                elif dtype == 0x21:
                                    v, = self._read_struct("<d", f)
                                else:
                                    f.read(pixelsize)
                                    v = math.nan
                                values.append(v)

                            col_key = self.GROUND_TYPE_MAP.get(ground_type)
                            if col_key:
                                # 截取前 512 个采样点以完成光谱对准
                                spectra_raw[col_key] = np.array(values[:512], dtype=float)
                    except Exception as e:
                        print(f"[IRIS解析警报] 数据块解析异常: {e}")

                # -------------------- Image 块 --------------------
                elif header == self.IMAGE_BLOCK and length > 0:
                    try:
                        n, = self._read_struct("<H", f)
                        for i in range(n):
                            img_len, = self._read_struct("<Q", f)
                            name = self._read_string(f, 100)
                            f.read(10)
                            img_type, = self._read_struct("<B", f)
                            img_data = f.read(img_len)
                            
                            image_blocks.append({
                                "index": i,
                                "name": name,
                                "type": img_type,
                                "length": img_len
                            })
                    except Exception as e:
                        print(f"[IRIS解析警报] 图像块解析异常: {e}")

                # 确保流指针对齐到下一块起点
                f.seek(block_start + length)

        # 2. 检查并校准重构出的波长
        if not wavelength_map:
            raise RuntimeError(f"IRIS二进制文件解析失败，未定位到任何有效波长校准信息: {filename}")
        
        # 截取前 512 点
        wavelengths_arr = np.array(next(iter(wavelength_map.values()))[:512], dtype=float)

        # 3. 核心算法层：衍生光谱物理模型计算
        derived_spectra = {}
        
        # 提取基础分量
        ground = spectra_raw.get("Ground_DN")
        flat = spectra_raw.get("Flat_DN")
        dark = spectra_raw.get("Dark_DN")
        abs_data = spectra_raw.get("Absfile")
        cal_data = spectra_raw.get("Calfile")

        # A. 计算扣暗电流的 Ground_DN 和 Flat_DN
        if ground is not None and dark is not None:
            derived_spectra["Ground_DN_扣暗电流"] = ground - dark
        if flat is not None and dark is not None:
            derived_spectra["Flat_DN_扣暗电流"] = flat - dark

        # B. 计算扣暗电流的高精反射率 Reflectance_DarkCorrected
        if all(v is not None for v in [ground, flat, dark, abs_data]):
            denom = flat - dark
            denom[denom == 0] = np.nan
            with np.errstate(divide='ignore', invalid='ignore'):
                ref_dark = (ground - dark) / denom * abs_data
                ref_dark[~np.isfinite(ref_dark)] = 0.0
                derived_spectra["Reflectance_扣暗电流"] = ref_dark

        # C. 计算扣暗电流的高精辐射亮度/辐照度
        if all(v is not None for v in [ground, dark, cal_data]):
            it_val = it_sample if it_sample > 0 else 1.0
            rad_base_dark = ((ground - dark) * cal_data) / it_val
            
            if is_irradiance:
                derived_spectra["Irradiance_辐照度_扣暗电流"] = rad_base_dark * np.pi
            else:
                derived_spectra["Radiance_辐射亮度_扣暗电流"] = rad_base_dark

        # 4. 组装多通道并存矩阵 (精准过滤：仅保留原始 DN 值与扣暗电流衍生量)
        column_names = []
        data_columns = []

        # 优先填入衍生高精光谱曲线
        for key in ["Reflectance_扣暗电流", "Radiance_辐射亮度_扣暗电流", "Irradiance_辐照度_扣暗电流", "Ground_DN_扣暗电流", "Flat_DN_扣暗电流"]:
            if key in derived_spectra:
                column_names.append(key)
                data_columns.append(derived_spectra[key])

        # 接着仅填入原始的三种物理 DN 值
        for key in ["Ground_DN", "Flat_DN", "Dark_DN"]:
            if key in spectra_raw:
                column_names.append(key)
                data_columns.append(spectra_raw[key])

        # 构建标准的 2D numpy 强度矩阵（对齐为 (num_wavelengths, num_curves)）
        data_matrix = np.column_stack(data_columns)

        # 5. 暂存元数据
        metadata = {
            "Instrument": "IRIS Binary Sensor",
            "Integration Time": f"{it_sample}ms",
            "Is Irradiance Mode": str(is_irradiance),
            "Metadata Blocks Count": f"{len(json_blocks)}"
        }
        # 尝试合并第一个配置 JSON 的部分可读键
        if json_blocks:
            try:
                js_dict = json.loads(json_blocks[0])
                for item in js_dict.get("info_list", []):
                    if item.get("info_type") == "devinfo":
                        metadata["Sensor ID"] = str(item.get("sensor_id", "Unknown"))
                        metadata["Bands Config"] = str(item.get("bandnum", "Unknown"))
            except Exception:
                pass

        # 6. 生成并返回 SpectrumData 对象
        return SpectrumData(
            filepath=abs_path,
            wavelengths=wavelengths_arr,
            data_matrix=data_matrix,
            column_names=column_names,
            metadata=metadata,
            display_name=final_display_name
        )

    # ---------- 内部二进制读取与结构解析辅助函数 ----------

    def _read_struct(self, fmt, f):
        size = struct.calcsize(fmt)
        buf = f.read(size)
        if len(buf) != size:
            raise EOFError("Unexpected EOF while reading binary structure")
        return struct.unpack(fmt, buf)

    def _read_string(self, f, n):
        buf = f.read(n)
        if len(buf) != n:
            raise EOFError("Unexpected EOF while reading binary string")
        # 清理 C 风格字符串末尾的空字节
        return buf.split(b'\x00', 1)[0].decode(errors="ignore")

    def _calc_wavelength_from_coeff(self, i, a1, a2, a3, a4):
        """三项式校准计算：a1*i^3 + a2*i^2 + a3*i + a4"""
        return a1 * i * i * i + a2 * i * i + a3 * i + a4

    def _extract_wave_coeff(self, js_str):
        try:
            j = json.loads(js_str)
        except Exception:
            return None

        if j.get("info_type") != "infolist":
            return None

        for info in j.get("info_list", []):
            if info.get("info_type") == "devinfo":
                wc = info.get("wave_coeff")
                if not wc:
                    continue
                return (
                    info["sensor_id"],
                    info["bandnum"],
                    wc["a1"], wc["a2"], wc["a3"], wc["a4"]
                )
        return None

    def _extract_it_from_json(self, js_str):
        try:
            j = json.loads(js_str)
        except Exception:
            return None

        if j.get("info_type") != "infolist":
            return None

        for info in j.get("info_list", []):
            if info.get("info_type") == "devinfo":
                if "IT" in info:
                    return info["IT"]
        return None

    def _check_is_irradiance(self, js_str):
        try:
            j = json.loads(js_str)
        except Exception:
            return False

        if j.get("info_type") != "infolist":
            return False

        for info in j.get("info_list", []):
            if info.get("info_type") == "environment":
                path = info.get("cailifilePath", "")
                if "180d" in path.lower():
                    return True
        return False


"""
# =================================------------------
# 单元测试
# =================================------------------
if __name__ == '__main__':
    print(">>> 正在启动 IRIS 二进制光谱解析器测试...")
    parser = IrisBinaryParser()
    print("✔ IrisBinaryParser 自注册与依赖校验成功。")
"""
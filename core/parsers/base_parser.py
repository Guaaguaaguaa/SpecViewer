# -*- coding: utf-8 -*-
"""
文件路径: core/parsers/base_parser.py
功能描述: 光谱解析器的抽象基类与工厂。
          定义了标准解析契约，提供自适应特征探测和自动识别路由器，
          支持解析器自动注册，为多异构数据格式的无缝扩展奠定坚实地基。
          修正：修复了错误的 SpectrumData 导入路径。
"""

import sys
import os
import abc

# ----------------------------------------------------
# 路径兼容性注入：将项目根目录动态添加到 sys.path
# ----------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 修正：将错误的 'core.parsers.data_manager' 修正为正确的项目级路径 'core.data_manager'
from core.data_manager import SpectrumData


class BaseParser(metaclass=abc.ABCMeta):
    """
    光谱解析器抽象基类 (Abstract Base Class)。
    定义了所有具体数据格式解析器必须遵循的接口规范。
    """

    @classmethod
    @abc.abstractmethod
    def can_parse(cls, filepath):
        """
        特征探测函数：通过轻量读取文件头部或分析文件名后缀，判断该解析器是否能够处理此文件。
        :param filepath: 文件的绝对路径
        :return: bool, True 代表能够解析，False 代表无法处理
        """
        pass

    @abc.abstractmethod
    def parse(self, filepath, display_name=None) -> SpectrumData:
        """
        深度解析函数：负责具体解析文件并打包返回标准的 SpectrumData 对象。
        :param filepath: 文件的绝对路径
        :param display_name: 在界面上显示的唯一重命名标识（若无则默认使用文件名）
        :return: SpectrumData 光谱模型实例
        """
        pass


class ParserFactory:
    """
    解析器工厂类 (Registry & Dispatcher)。
    维护着全局已注册解析器的注册表，并根据文件特征自适应匹配最佳解析器。
    """
    # 存储所有具体解析器类的列表: [ParserClass1, ParserClass2, ...]
    _parsers_registry = []

    @classmethod
    def register(cls, parser_class):
        """
        解析器自注册装饰器。
        允许具体的解析器子类通过 @ParserFactory.register 自动向工厂报到。
        """
        if parser_class not in cls._parsers_registry:
            cls._parsers_registry.append(parser_class)
        return parser_class

    @classmethod
    def get_parser_for_file(cls, filepath):
        """
        自适应匹配路由器：
        自动扫描注册表中的解析器，返回能够解析该文件的最佳解析器实例。
        :param filepath: 文件的绝对路径
        :return: BaseParser 的子类实例，若无匹配则返回 None
        """
        if not os.path.exists(filepath):
            return None

        # 遍历注册表中的所有解析器，执行特征盲测
        for parser_cls in cls._parsers_registry:
            try:
                # 询问解析器：“这个文件你能搞定吗？”
                if parser_cls.can_parse(filepath):
                    # 如果能，实例化该解析器并返回
                    return parser_cls()
            except Exception as e:
                # 容错处理：探测过程若报错，静默跳过，防止单个解析器逻辑漏洞导致整个工厂卡死
                print(f"[工厂警报] 解析器探测异常 {parser_cls.__name__}: {e}")
                continue
        
        return None

    @classmethod
    def clear_registry(cls):
        """清空注册表（主要用于单元测试和重载）"""
        cls._parsers_registry.clear()
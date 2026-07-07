# -*- coding: utf-8 -*-
"""
文件路径: core/algorithms/base_algo.py
功能描述: 整个光谱分析系统的【算法工厂契约】。
          定义了抽象基类 BaseAlgorithm，采用模板方法（Template Method）模式：
          - execute() 为外部唯一调用入口，依次执行 _validate() → _compute()
          - 子类只需实现 _validate()（输入校验）和 _compute()（纯数学逻辑）
          - 公共校验逻辑提取至 _validation.py，各算法共享，零重复。
"""

from abc import ABC, abstractmethod


class BaseAlgorithm(ABC):
    """
    光谱分析算法的抽象基类（模板方法模式）。

    外部统一调用 execute(*args, **kwargs)，内部自动完成：
      1. _validate(*args, **kwargs)   — 输入校验（可调用 _validation.py 共享工具）
      2. _compute(*args, **kwargs)    — 纯数学/物理计算

    子类必须覆写 _compute()，可选择性覆写 _validate()（默认无校验）。
    """

    def __init__(self, name: str):
        """
        :param name: 算法在系统注册和 UI 菜单中展示的唯一标识
        """
        self.name = name

    # ==================================================================
    # 模板方法：外部唯一入口
    # ==================================================================

    def execute(self, *args, **kwargs):
        """
        统一算法执行网关。
        所有外部调用者（UI 菜单、批量面板、数据处理模块）只需调用此方法。
        内部自动串联校验与计算流水线。

        :return: 算法计算结果（具体类型由子类 _compute 决定）
        """
        self._validate(*args, **kwargs)
        return self._compute(*args, **kwargs)

    # ==================================================================
    # 钩子方法：子类可重写
    # ==================================================================

    def _validate(self, *args, **kwargs):
        """
        输入校验钩子。默认无校验，子类应覆写以调用 _validation.py 共享工具。
        :raises ValueError: 若校验不通过
        """
        pass

    @abstractmethod
    def _compute(self, *args, **kwargs):
        """
        纯数学/物理计算逻辑。子类必须实现。
        此方法被 execute() 在 _validate() 之后自动调用，
        此时输入数据已通过校验，可直接进行计算。

        :return: 计算结果
        """
        pass

# -*- coding: utf-8 -*-
"""
文件路径: config/settings.py
功能描述: 光谱系统的全局配置管理中心。
          采用单例模式，集中管理配色方案、应用元数据、
          窗口默认参数、算法阈值、导出格式等全局常量。
          彻底消除魔术数字分散于各模块的混乱。
"""


class AppSettings:
    """
    全局配置管理单例。
    所有模块通过 AppSettings().COLOR_PALETTE / WINDOW_SIZE 等
    访问统一全局配置。
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return
        self._initialized = True
        self._load_defaults()

    def _load_defaults(self):
        # ==================== 应用元数据 ====================
        self.APP_NAME = "SpectralViewerPro"
        self.APP_DISPLAY_NAME = "光谱高性能通用分析与可视化系统 Pro"
        self.ORG_NAME = "OptoAnalysisTech"
        self.ORG_DOMAIN = "opto-tech.com"

        # ==================== 工业级高雅调色板 ====================
        self.COLOR_PALETTE = [
            '#1f77b4', '#2ca02c', '#d62728', '#9467bd',
            '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'
        ]

        # ==================== 窗口默认参数 ====================
        self.WINDOW_WIDTH = 1100
        self.WINDOW_HEIGHT = 750
        self.SPLITTER_LEFT_RATIO = 250
        self.SPLITTER_RIGHT_RATIO = 850

        # ==================== 算法参数 ====================
        self.RATIO_SAFE_GUARD = 0.0       # Ratio 计算中除零/NaN 的替换值

        # ==================== 文件解析 ====================
        self.PARSER_ENCODINGS = ['utf-8', 'gbk', 'gb2312', 'latin1']

        # ==================== 画布默认参数 ====================
        self.PLOT_NORMAL_LINE_WIDTH = 1.5
        self.PLOT_SELECTED_LINE_WIDTH = 3.0
        self.PLOT_SELECTED_COLOR = '#ff7f0e'
        self.PLOT_BACKGROUND = 'w'
        self.PLOT_FOREGROUND = 'k'
        self.PLOT_ANTIALIAS = True
        self.PLOT_GRID_ALPHA = 0.3

        # ==================== 导出默认参数 ====================
        self.EXPORT_IMAGE_DPI = 150
        self.EXPORT_IMAGE_FORMAT = 'PNG'
        self.EXPORT_CSV_DELIMITER = ','
        self.EXPORT_HEADER_EXT = '.txt'

# -*- coding: utf-8 -*-
"""
文件路径: main.py
功能描述: 光谱高性能通用分析与可视化系统的总启动入口。
          负责初始化 QApplication，加载并展现 MainWindow，提供应用级别的基础配置。
"""

import sys
import os

# ----------------------------------------------------
# 路径兼容性注入：将当前根目录加入 sys.path
# 确保在任意工作路径下运行 python main.py 都能无痛解析 'ui' 和 'core' 包
# ----------------------------------------------------
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow


def main():
    # 1. 初始化 Qt 应用程序对象
    app = QApplication(sys.argv)
    
    # 2. 设置应用全局元数据（便于日后窗口自适应图标、保存用户配置路径等宏大叙事拓展）
    app.setApplicationName("SpectralViewerPro")
    app.setApplicationDisplayName("光谱高性能通用分析与可视化系统 Pro")
    app.setOrganizationName("OptoAnalysisTech")
    app.setOrganizationDomain("opto-tech.com")

    # 3. 创建主窗口实例
    window = MainWindow()
    
    # 4. 展示主窗口
    window.show()
    
    # 5. 进入 Qt 主事件循环，并在安全退出时将状态码返回给系统
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
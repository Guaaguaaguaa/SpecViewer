# -*- coding: utf-8 -*-
"""
core.parsers 包 — 光谱解析器集合。
自动注册所有解析器到 ParserFactory，外部只需导入工厂与基类即可使用。
"""

from core.parsers.base_parser import BaseParser, ParserFactory

# 触发各解析器向 ParserFactory 自注册
from core.parsers import vertical_multi    # noqa: F401  (VerticalMultiParser)
from core.parsers import horizontal_row    # noqa: F401  (HorizontalRowParser)
from core.parsers import iris_binary       # noqa: F401  (IrisBinaryParser)

__all__ = ["BaseParser", "ParserFactory"]

# ============================================================
# EnJin Compiler - 包初始化文件
# ============================================================
# enjinc 是 EnJin 语言的编译器核心包。
# 职责：将 .ej 意图源码 -> I-AST -> 目标语言代码 (Python/Java)
#
# 包结构规划:
#   enjinc/
#   ├── __init__.py        # 本文件：版本号与公共导出
#   ├── grammar.lark       # Lark 语法定义文件
#   ├── ast_nodes.py       # I-AST 节点数据结构
#   ├── parser.py          # Lark Transformer -> I-AST
#   ├── analyzer.py        # 静态分析器（四层与导出约束）
#   └── cli.py             # CLI 入口 (enjinc build / enjinc analyze)
# ============================================================

__version__ = "0.1.0"

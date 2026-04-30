"""
Prompt 模板注册中心。
外部化 prompt_router.py 中的 f-string prompt，便于迭代和翻译。

新增目标栈的 prompt 只需在 prompts/ 下新建 <target>.py，
导出 MODEL_SYSTEM 和 METHOD_SYSTEM 常量。
"""

"""
EnJin Jinja2 环境管理。

支持三种模板目录解析：
1. 内置目标：enjinc/targets/<name>/templates/
2. 第三方插件：通过 register_template_dir() 注册
3. 共享宏目录：enjinc/targets/_shared/（所有目标可用）

模板继承/宏引用：
- 在模板中用 {% from "_shared/xxx.jinja" import xxx %} 引用共享宏
- 用 {% extends "_shared/base.xxx.jinja" %} 继承共享基模板
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, BaseLoader


def _snake_to_camel(value: str) -> str:
    """Convert snake_case to camelCase."""
    parts = value.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _snake_to_pascal(value: str) -> str:
    """Convert snake_case to PascalCase."""
    return "".join(p.capitalize() for p in value.split("_"))


def _pluralize_en(name: str) -> str:
    """Naive English pluralization for table names."""
    if name.endswith("y") and not name.endswith("ay") and not name.endswith("ey"):
        return name[:-1] + "ies"
    if name.endswith("s") or name.endswith("x") or name.endswith("ch") or name.endswith("sh"):
        return name + "es"
    return name + "s"


def _strip_lines(value: str) -> str:
    """Strip leading/trailing whitespace from each line."""
    return "\n".join(line.strip() for line in value.split("\n"))


# 全局 Jinja2 环境缓存
_jinja_envs: dict[str, Environment] = {}

# 第三方插件注册的模板目录（target_lang → template_dir）
_PLUGIN_TEMPLATE_DIRS: dict[str, Path] = {}

# 共享模板/宏目录
_SHARED_DIR = Path(__file__).parent / "targets" / "_shared"


def register_template_dir(target_lang: str, template_dir: Path | str) -> None:
    """第三方插件调用此函数注册自己的模板目录。

    在 renderer.py 的模块级别调用一次即可：

        from enjinc.jinja_utils import register_template_dir
        from pathlib import Path

        register_template_dir("go_gin", Path(__file__).parent / "templates")
    """
    _PLUGIN_TEMPLATE_DIRS[target_lang] = Path(template_dir)
    # 清除缓存，下次 get_jinja_env 时重建
    _jinja_envs.pop(target_lang, None)


def _resolve_template_dirs(target_lang: str, fallback_dir: Path | None = None) -> list[Path]:
    """解析模板目录列表（优先级从高到低）。

    返回的列表供 FileSystemLoader 使用，Jinja2 按顺序查找模板。
    """
    dirs: list[Path] = []

    # 优先级 1: 插件注册的模板目录
    if target_lang in _PLUGIN_TEMPLATE_DIRS:
        plugin_dir = _PLUGIN_TEMPLATE_DIRS[target_lang]
        if plugin_dir.exists():
            dirs.append(plugin_dir)

    # 优先级 2: 内置目标
    builtin_dir = Path(__file__).parent / "targets" / target_lang / "templates"
    if builtin_dir.exists():
        dirs.append(builtin_dir)

    # 优先级 3: fallback
    if fallback_dir is not None and fallback_dir.exists():
        dirs.append(fallback_dir)

    # 共享目录（总是追加，用于 {% from "_shared/..." import ... %}）
    if _SHARED_DIR.exists():
        dirs.append(_SHARED_DIR)

    return dirs


def get_jinja_env(target_lang: str, fallback_dir: Path | None = None) -> Environment:
    """获取目标语言的 Jinja2 环境（带缓存）。

    查找优先级：
    1. 第三方插件通过 register_template_dir 注册的目录
    2. 内置目标 enjinc/targets/<name>/templates/
    3. fallback_dir 参数
    4. 共享目录 enjinc/targets/_shared/（自动追加）
    """
    if target_lang not in _jinja_envs:
        dirs = _resolve_template_dirs(target_lang, fallback_dir)

        if not dirs or (len(dirs) == 1 and dirs[0] == _SHARED_DIR):
            raise FileNotFoundError(
                f"No templates found for target '{target_lang}'. "
                f"Checked: builtin targets and registered plugin directories."
            )

        loader = FileSystemLoader([str(d) for d in dirs])
        env = Environment(
            loader=loader,
            trim_blocks=True,
            lstrip_blocks=True,
            autoescape=False,
        )
        env.filters["snake_to_camel"] = _snake_to_camel
        env.filters["snake_to_pascal"] = _snake_to_pascal
        env.filters["pluralize_en"] = _pluralize_en
        env.filters["dedent"] = textwrap.dedent
        env.filters["strip_lines"] = _strip_lines
        _jinja_envs[target_lang] = env
    return _jinja_envs[target_lang]

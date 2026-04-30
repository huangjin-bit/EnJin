"""
============================================================
EnJin 注解工具函数 (annotations.py)
============================================================
提供注解查询和参数提取的统一接口，消除各模块重复的
any(a.name == "X" for a in ...) 和 kwargs.get → args[N] 回退模式。
============================================================
"""

from __future__ import annotations

from enjinc.ast_nodes import Annotation
from enjinc.constants import (
    ANNO_LOCKED,
    ANNO_HUMAN_MAINTAINED,
    ANNO_FOREIGN_KEY,
    ANNO_ENGINE,
    ANNO_API_CONTRACT,
    ANNO_DATA_PLANE,
    ANNO_TABLE,
    ANNO_PREFIX,
    ANNO_AUTH,
)


def has_annotation(annotations: list[Annotation], name: str) -> bool:
    """检查注解列表中是否包含指定名称的注解。"""
    return any(a.name == name for a in annotations)


def get_annotation(annotations: list[Annotation], name: str) -> Annotation | None:
    """获取指定名称的注解，不存在则返回 None。"""
    for a in annotations:
        if a.name == name:
            return a
    return None


def get_annotation_param(
    annotations: list[Annotation],
    name: str,
    kwarg: str = "",
    arg_index: int = 0,
    default: str = "",
) -> str:
    """统一提取注解参数：优先 kwargs[key]，回退 args[index]。

    解决了分布在 prompt_router, analyzer, dependency_graph 中的
    kwargs.get("x") or (anno.args[N] if ...) 重复模式。
    """
    anno = get_annotation(annotations, name)
    if anno is None:
        return default

    if kwarg and kwarg in anno.kwargs:
        return str(anno.kwargs[kwarg])

    if arg_index < len(anno.args):
        return str(anno.args[arg_index])

    return default


# ============================================================
# 便捷方法：常用注解的快速查询
# ============================================================

def is_locked(annotations: list[Annotation]) -> bool:
    return has_annotation(annotations, ANNO_LOCKED)


def is_human_maintained(annotations: list[Annotation]) -> bool:
    return has_annotation(annotations, ANNO_HUMAN_MAINTAINED)


def has_foreign_key(annotations: list[Annotation]) -> bool:
    return has_annotation(annotations, ANNO_FOREIGN_KEY)


def get_foreign_key_target(annotations: list[Annotation]) -> str:
    """从 @foreign_key 注解提取目标，如 "User.id" → "User.id"。"""
    return get_annotation_param(annotations, ANNO_FOREIGN_KEY, kwarg="target", arg_index=0)


def get_engine_config(annotations: list[Annotation]) -> tuple[str, str]:
    """从 @engine 注解提取 (type, framework)，缺失返回 ("", "")。"""
    engine_type = get_annotation_param(annotations, ANNO_ENGINE, kwarg="type", arg_index=0)
    framework = get_annotation_param(annotations, ANNO_ENGINE, kwarg="framework", arg_index=1)
    return engine_type, framework


def get_data_plane_config(annotations: list[Annotation]) -> tuple[str, str]:
    """从 @data_plane 注解提取 (protocol, engine)。"""
    protocol = get_annotation_param(annotations, ANNO_DATA_PLANE, kwarg="protocol", arg_index=0)
    engine = get_annotation_param(annotations, ANNO_DATA_PLANE, kwarg="engine", arg_index=1)
    return protocol, engine


def get_table_name(annotations: list[Annotation]) -> str:
    """从 @table 注解提取表名。"""
    return get_annotation_param(annotations, ANNO_TABLE, kwarg="name", arg_index=0)


def get_prefix_path(annotations: list[Annotation]) -> str:
    """从 @prefix 注解提取路径前缀。"""
    return get_annotation_param(annotations, ANNO_PREFIX, kwarg="path", arg_index=0, default="/")


def get_auth_strategy(annotations: list[Annotation]) -> str:
    """从 @auth 注解提取认证策略。"""
    return get_annotation_param(annotations, ANNO_AUTH, kwarg="strategy", arg_index=0, default="none")

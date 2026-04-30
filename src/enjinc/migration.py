"""
============================================================
EnJin 蓝绿迁移模块 (migration.py)
============================================================
ENJIN_CONSTITUTION.md §6 规定：当 AST 解析到 Model 层 (struct) 发生变更时，
严禁生成破坏性的 ALTER TABLE SQL。本模块生成"影子表双写 + 灰度切流"的迁移脚本。

核心策略:
    - 新增字段: ALTER TABLE ADD COLUMN (nullable first, backfill later)
    - 删除字段: 不 DROP COLUMN，仅标记为 @deprecated 并记录到注释
    - 类型变更: 新建 _v2 后缀列，保留旧列，双写过渡
    - 注解变更: 记录差异，生成对应的索引/约束变更 SQL

渲染输出:
    - SQL (PostgreSQL): 影子表、触发器、灰度切流步骤
    - Python (Alembic-style): SQLAlchemy/Alembic 迁移脚本
============================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from enjinc.ast_nodes import Annotation, FieldDef, StructDef, TypeRef


# ============================================================
# EnJin 类型 → SQL 类型映射
# ============================================================

_ENJIN_TYPE_TO_SQL: dict[str, str] = {
    "Int": "INTEGER",
    "Float": "DOUBLE PRECISION",
    "String": "TEXT",
    "Bool": "BOOLEAN",
    "DateTime": "TIMESTAMP",
    "List": "JSONB",
    "Map": "JSONB",
    "Enum": "TEXT",
}

_ENJIN_TYPE_TO_PYTHON: dict[str, str] = {
    "Int": "Integer()",
    "Float": "Float()",
    "String": "String()",
    "Bool": "Boolean()",
    "DateTime": "DateTime()",
    "List": "JSON()",
    "Map": "JSON()",
    "Enum": "String()",
}


# ============================================================
# StructDiff — 两个 struct 版本之间的差异
# ============================================================


@dataclass
class StructDiff:
    """两个 StructDef 版本之间的差异摘要。

    Attributes:
        added_fields: 新版本中新增的字段
        removed_fields: 新版本中被移除的字段
        type_changed: 类型发生变更的字段，每项为 (old_field, new_field)
        annotation_changed: 注解发生变更的字段，每项为 (old_field, new_field)
    """

    added_fields: list[FieldDef] = field(default_factory=list)
    removed_fields: list[FieldDef] = field(default_factory=list)
    type_changed: list[tuple[FieldDef, FieldDef]] = field(default_factory=list)
    annotation_changed: list[tuple[FieldDef, FieldDef]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """如果没有检测到任何变更，返回 True。"""
        return (
            not self.added_fields
            and not self.removed_fields
            and not self.type_changed
            and not self.annotation_changed
        )

    def to_dict(self) -> dict:
        return {
            "added_fields": [f.to_dict() for f in self.added_fields],
            "removed_fields": [f.to_dict() for f in self.removed_fields],
            "type_changed": [
                {"old": old.to_dict(), "new": new.to_dict()}
                for old, new in self.type_changed
            ],
            "annotation_changed": [
                {"old": old.to_dict(), "new": new.to_dict()}
                for old, new in self.annotation_changed
            ],
        }


# ============================================================
# 核心对比函数
# ============================================================


def _type_repr(t: TypeRef) -> str:
    """将 TypeRef 序列化为可比较的字符串表示。"""
    params_str = ""
    if t.params:
        parts = []
        for p in t.params:
            if isinstance(p, TypeRef):
                parts.append(_type_repr(p))
            else:
                parts.append(str(p))
        params_str = f"<{','.join(parts)}>"
    optional = "?" if t.is_optional else ""
    return f"{t.base}{params_str}{optional}"


def _annotation_repr(a: Annotation) -> str:
    """将 Annotation 序列化为可比较的字符串表示。"""
    args_str = ",".join(repr(arg) for arg in a.args)
    kwargs_str = ",".join(f"{k}={repr(v)}" for k, v in sorted(a.kwargs.items()))
    parts = []
    if args_str:
        parts.append(args_str)
    if kwargs_str:
        parts.append(kwargs_str)
    inner = ",".join(parts)
    return f"@{a.name}({inner})" if inner else f"@{a.name}"


def _annotations_match(old: FieldDef, new: FieldDef) -> bool:
    """比较两个字段的注解列表是否相同。"""
    old_set = {_annotation_repr(a) for a in old.annotations}
    new_set = {_annotation_repr(a) for a in new.annotations}
    return old_set == new_set


def diff_structs(old_struct: StructDef, new_struct: StructDef) -> StructDiff:
    """比较两个 struct 定义并生成差异摘要。

    Args:
        old_struct: 变更前的 struct 定义
        new_struct: 变更后的 struct 定义

    Returns:
        StructDiff 包含所有检测到的变更
    """
    old_fields = {f.name: f for f in old_struct.fields}
    new_fields = {f.name: f for f in new_struct.fields}

    old_names = set(old_fields.keys())
    new_names = set(new_fields.keys())

    added = [new_fields[name] for name in sorted(new_names - old_names)]
    removed = [old_fields[name] for name in sorted(old_names - new_names)]

    type_changed: list[tuple[FieldDef, FieldDef]] = []
    annotation_changed: list[tuple[FieldDef, FieldDef]] = []

    for name in sorted(old_names & new_names):
        old_f = old_fields[name]
        new_f = new_fields[name]

        old_type_str = _type_repr(old_f.type)
        new_type_str = _type_repr(new_f.type)
        if old_type_str != new_type_str:
            type_changed.append((old_f, new_f))
            continue

        if not _annotations_match(old_f, new_f):
            annotation_changed.append((old_f, new_f))

    return StructDiff(
        added_fields=added,
        removed_fields=removed,
        type_changed=type_changed,
        annotation_changed=annotation_changed,
    )


# ============================================================
# SQL 类型辅助
# ============================================================


def _to_sql_type(type_ref: TypeRef) -> str:
    """将 EnJin TypeRef 转换为 PostgreSQL 列类型。"""
    base = type_ref.base
    if base in _ENJIN_TYPE_TO_SQL:
        sql_type = _ENJIN_TYPE_TO_SQL[base]
        # String 如果有 @max_length 注解，可以用 VARCHAR(n)
        return sql_type
    # 自定义 struct 名 → INTEGER (作为 foreign key)
    return "INTEGER"


def _to_alembic_type(type_ref: TypeRef) -> str:
    """将 EnJin TypeRef 转换为 Alembic 列类型表达式。"""
    base = type_ref.base
    if base in _ENJIN_TYPE_TO_PYTHON:
        return f"sa.{_ENJIN_TYPE_TO_PYTHON[base]}"
    return "sa.Integer()"


def _table_name(struct_name: str) -> str:
    """将 PascalCase struct 名转换为 snake_case 表名。"""
    result = []
    for i, ch in enumerate(struct_name):
        if ch.isupper() and i > 0:
            result.append("_")
        result.append(ch.lower())
    return "".join(result)


def _timestamp_marker() -> str:
    """生成迁移脚本的 timestamp 标记。"""
    return datetime.now().strftime("%Y%m%d%H%M%S")


# ============================================================
# SQL 迁移生成 (PostgreSQL — 影子表双写 + 灰度切流)
# ============================================================


def generate_migration_sql(
    diff: StructDiff,
    struct_name: str,
    target_lang: str = "python_fastapi",
) -> str:
    """根据 StructDiff 生成非破坏性的 PostgreSQL 迁移 SQL。

    蓝绿迁移策略:
        Phase 1 — 扩展: 新增列 (nullable), 新建 _v2 列
        Phase 2 — 双写: 触发器同时写入新旧列
        Phase 3 — 回填: 数据迁移到新列 (需手动执行)
        Phase 4 — 切流: 验证完成后切换读取源 (需手动确认)
        Phase 5 — 清理: 删除旧列 (需人工审批后手动执行)

    Args:
        diff: struct 差异摘要
        struct_name: struct 名称 (PascalCase)
        target_lang: 目标语言栈（影响注释风格，不影响 SQL 语义）

    Returns:
        完整的迁移 SQL 脚本文本
    """
    if diff.is_empty:
        return f"-- [{struct_name}] 无结构变更，跳过迁移。\n"

    table = _table_name(struct_name)
    shadow_table = f"{table}_shadow"
    ts = _timestamp_marker()
    lines: list[str] = []

    lines.append(f"-- ============================================================")
    lines.append(f"-- EnJin 蓝绿迁移: {struct_name}")
    lines.append(f"-- 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"-- 迁移标记: mig_{ts}")
    lines.append(f"-- 目标表: {table}")
    lines.append(f"-- 策略: 影子表双写 + 灰度切流 (ENJIN_CONSTITUTION §6)")
    lines.append(f"-- ============================================================")
    lines.append("")

    # ── Phase 1: 扩展 (非破坏性) ─────────────────────────────
    lines.append("-- ─────────────────────────────────────────")
    lines.append("-- Phase 1: 扩展 — 新增列 (全部 nullable)")
    lines.append("-- ─────────────────────────────────────────")
    lines.append("")

    for f in diff.added_fields:
        col_type = _to_sql_type(f.type)
        lines.append(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {f.name} {col_type};"
        )
        lines.append(f"  -- [新增字段] {f.name}: {f.type.base}")
        lines.append("")

    for old_f, new_f in diff.type_changed:
        col_type = _to_sql_type(new_f.type)
        v2_name = f"{new_f.name}_v2"
        lines.append(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {v2_name} {col_type};"
        )
        lines.append(
            f"  -- [类型变更] {old_f.name}: {_type_repr(old_f.type)} "
            f"-> {_type_repr(new_f.type)}"
        )
        lines.append(f"  -- 旧列 {old_f.name} 保留，新列 {v2_name} 接替")
        lines.append("")

    # ── 删除字段: 仅标记，绝不 DROP COLUMN ────────────────────
    if diff.removed_fields:
        lines.append("-- ─────────────────────────────────────────")
        lines.append("-- Phase 1b: 标记废弃字段 (绝不执行 DROP COLUMN)")
        lines.append("-- ─────────────────────────────────────────")
        lines.append("")
        for f in diff.removed_fields:
            lines.append(f"-- [废弃字段] {f.name}: {_type_repr(f.type)}")
            lines.append(f"-- 警告: 字段 {f.name} 已从 struct 定义中移除，但数据库列保留。")
            lines.append(
                f"-- 请在应用层停止读取此字段后，经人工审批再执行 DROP COLUMN。"
            )
            lines.append(
                f"-- ALTER TABLE {table} DROP COLUMN {f.name};  -- 需人工审批"
            )
            lines.append("")

    # ── 注解变更 ──────────────────────────────────────────────
    if diff.annotation_changed:
        lines.append("-- ─────────────────────────────────────────")
        lines.append("-- Phase 1c: 注解变更 (索引/约束)")
        lines.append("-- ─────────────────────────────────────────")
        lines.append("")
        for old_f, new_f in diff.annotation_changed:
            old_annos = {_annotation_repr(a) for a in old_f.annotations}
            new_annos = {_annotation_repr(a) for a in new_f.annotations}

            added_annos = new_annos - old_annos
            removed_annos = old_annos - new_annos

            if added_annos:
                lines.append(
                    f"-- [注解新增] {new_f.name}: "
                    + ", ".join(sorted(added_annos))
                )
                # 检测是否有 @unique 或 @index 需要创建
                for anno in new_f.annotations:
                    if anno.name == "unique" and _annotation_repr(anno) in added_annos:
                        idx_name = f"ix_{table}_{new_f.name}"
                        lines.append(
                            f"CREATE UNIQUE INDEX IF NOT EXISTS {idx_name} "
                            f"ON {table} ({new_f.name});"
                        )
                    elif anno.name == "index" and _annotation_repr(anno) in added_annos:
                        idx_name = f"ix_{table}_{new_f.name}"
                        lines.append(
                            f"CREATE INDEX IF NOT EXISTS {idx_name} "
                            f"ON {table} ({new_f.name});"
                        )

            if removed_annos:
                lines.append(
                    f"-- [注解移除] {new_f.name}: "
                    + ", ".join(sorted(removed_annos))
                )
                lines.append(
                    f"-- 注意: 约束/索引的移除需人工确认后手动执行。"
                )

            lines.append("")

    # ── Phase 2: 影子表双写 ──────────────────────────────────
    has_dual_write = bool(diff.type_changed)
    if has_dual_write:
        lines.append("-- ─────────────────────────────────────────")
        lines.append("-- Phase 2: 影子表双写触发器 (PostgreSQL)")
        lines.append("-- ─────────────────────────────────────────")
        lines.append("")
        lines.append(f"-- 创建影子表用于灰度验证")
        lines.append(
            f"CREATE TABLE IF NOT EXISTS {shadow_table} "
            f"(LIKE {table} INCLUDING ALL);"
        )
        lines.append("")

        trigger_name = f"trg_{table}_dual_write"
        fn_name = f"fn_{table}_dual_write"

        lines.append(f"-- 双写触发器函数: 类型变更字段同时写入 _v2 列")
        lines.append(
            f"CREATE OR REPLACE FUNCTION {fn_name}()"
        )
        lines.append(f"RETURNS TRIGGER AS $$")
        lines.append("BEGIN")
        for _old_f, new_f in diff.type_changed:
            v2_name = f"{new_f.name}_v2"
            lines.append(f"    -- 双写: {new_f.name} -> {v2_name}")
            lines.append(
                f"    NEW.{v2_name} = CAST(NEW.{new_f.name} AS {_to_sql_type(new_f.type)});"
            )
        lines.append("    RETURN NEW;")
        lines.append("END;")
        lines.append("$$ LANGUAGE plpgsql;")
        lines.append("")
        lines.append(
            f"DROP TRIGGER IF EXISTS {trigger_name} ON {table};"
        )
        lines.append(
            f"CREATE TRIGGER {trigger_name}"
        )
        lines.append(
            f"    BEFORE INSERT OR UPDATE ON {table}"
        )
        lines.append(
            f"    FOR EACH ROW EXECUTE FUNCTION {fn_name}();"
        )
        lines.append("")

    # ── Phase 3: 回填 ────────────────────────────────────────
    if diff.type_changed:
        lines.append("-- ─────────────────────────────────────────")
        lines.append("-- Phase 3: 数据回填 (需在低峰期手动执行)")
        lines.append("-- ─────────────────────────────────────────")
        lines.append("")
        for _old_f, new_f in diff.type_changed:
            v2_name = f"{new_f.name}_v2"
            lines.append(
                f"-- 回填 {v2_name}: 从旧列 {new_f.name} 迁移数据"
            )
            lines.append(
                f"UPDATE {table} SET {v2_name} = CAST({new_f.name} AS {_to_sql_type(new_f.type)}) "
                f"WHERE {v2_name} IS NULL;"
            )
            lines.append("")

    # ── Phase 4: 灰度切流步骤 ────────────────────────────────
    lines.append("-- ─────────────────────────────────────────")
    lines.append("-- Phase 4: 灰度切流步骤 (手动确认)")
    lines.append("-- ─────────────────────────────────────────")
    lines.append("")
    lines.append("-- 切流清单:")
    if diff.added_fields:
        field_list = ", ".join(f.name for f in diff.added_fields)
        lines.append(
            f"--   1. 确认新增字段 ({field_list}) 已在应用层正确处理 NULL 值"
        )
    if diff.type_changed:
        for _old_f, new_f in diff.type_changed:
            v2_name = f"{new_f.name}_v2"
            lines.append(
                f"--   2. 确认 {v2_name} 回填完成且数据一致后，切换读取源"
            )
            lines.append(
                f"--      ALTER TABLE {table} RENAME COLUMN {new_f.name} TO {new_f.name}_legacy;"
            )
            lines.append(
                f"--      ALTER TABLE {table} RENAME COLUMN {v2_name} TO {new_f.name};"
            )
    if diff.removed_fields:
        field_list = ", ".join(f.name for f in diff.removed_fields)
        lines.append(
            f"--   3. 确认废弃字段 ({field_list}) 已无代码引用后，"
            f"经人工审批执行 DROP COLUMN"
        )
    lines.append("")

    # ── Phase 5: 清理 ────────────────────────────────────────
    lines.append("-- ─────────────────────────────────────────")
    lines.append("-- Phase 5: 清理 (人工审批后手动执行)")
    lines.append("-- ─────────────────────────────────────────")
    lines.append("")
    if has_dual_write:
        lines.append(f"-- DROP TRIGGER IF EXISTS {trigger_name} ON {table};")
        lines.append(f"-- DROP FUNCTION IF EXISTS {fn_name}();")
        lines.append(f"-- DROP TABLE IF EXISTS {shadow_table};")
        lines.append("")
    for _old_f, new_f in diff.type_changed:
        lines.append(
            f"-- ALTER TABLE {table} DROP COLUMN IF EXISTS {new_f.name}_legacy;"
        )
    lines.append("")
    lines.append(f"-- 迁移结束 mig_{ts}")

    return "\n".join(lines)


# ============================================================
# Python 迁移生成 (Alembic-style)
# ============================================================


def generate_migration_python(
    diff: StructDiff,
    struct_name: str,
) -> str:
    """根据 StructDiff 生成 Alembic-style Python 迁移脚本。

    Args:
        diff: struct 差异摘要
        struct_name: struct 名称 (PascalCase)

    Returns:
        Python 迁移脚本文本
    """
    if diff.is_empty:
        return f"# [{struct_name}] 无结构变更，跳过迁移。\n"

    table = _table_name(struct_name)
    ts = _timestamp_marker()
    revision = f"mig_{ts}"
    lines: list[str] = []

    # ── 文件头 ────────────────────────────────────────────────
    lines.append('"""')
    lines.append(f"EnJin 蓝绿迁移: {struct_name}")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"迁移标记: {revision}")
    lines.append(f"目标表: {table}")
    lines.append("策略: 影子表双写 + 灰度切流 (ENJIN_CONSTITUTION §6)")
    lines.append('"""')
    lines.append("")
    lines.append("import sqlalchemy as sa")
    lines.append("from alembic import op")
    lines.append("")
    lines.append(f"revision = '{revision}'")
    lines.append("down_revision = None  # 由 enjin.lock 自动填充")
    lines.append("branch_labels = None")
    lines.append("depends_on = None")
    lines.append("")
    lines.append("")

    # ── upgrade() ─────────────────────────────────────────────
    lines.append("def upgrade() -> None:")
    lines.append(f'    """蓝绿迁移 upgrade: {struct_name}"""')
    lines.append(f"    # 目标表: {table}")
    lines.append("")

    for f in diff.added_fields:
        col_type = _to_alembic_type(f.type)
        lines.append(f"    # [新增字段] {f.name}: {f.type.base}")
        lines.append(
            f"    op.add_column('{table}', sa.Column("
            f"'{f.name}', {col_type}, nullable=True))"
        )
        lines.append("")

    for old_f, new_f in diff.type_changed:
        col_type = _to_alembic_type(new_f.type)
        v2_name = f"{new_f.name}_v2"
        lines.append(
            f"    # [类型变更] {old_f.name}: "
            f"{_type_repr(old_f.type)} -> {_type_repr(new_f.type)}"
        )
        lines.append(
            f"    op.add_column('{table}', sa.Column("
            f"'{v2_name}', {col_type}, nullable=True))"
        )
        lines.append("")

    if diff.removed_fields:
        lines.append("    # [废弃字段] 绝不自动 DROP COLUMN")
        for f in diff.removed_fields:
            lines.append(
                f"    # 字段 '{f.name}' 已从 struct 定义中移除，"
                f"但数据库列保留。"
            )
            lines.append(
                f"    # 经人工审批后手动执行: "
                f"op.drop_column('{table}', '{f.name}')"
            )
        lines.append("")

    if diff.annotation_changed:
        lines.append("    # [注解变更]")
        for old_f, new_f in diff.annotation_changed:
            old_annos = {_annotation_repr(a) for a in old_f.annotations}
            new_annos = {_annotation_repr(a) for a in new_f.annotations}
            added_annos = new_annos - old_annos
            removed_annos = old_annos - new_annos
            if added_annos:
                lines.append(
                    f"    # {new_f.name}: 新增注解 "
                    + ", ".join(sorted(added_annos))
                )
                for anno in new_f.annotations:
                    if (
                        anno.name in ("unique", "index")
                        and _annotation_repr(anno) in added_annos
                    ):
                        idx_name = f"ix_{table}_{new_f.name}"
                        unique = "True" if anno.name == "unique" else "False"
                        lines.append(
                            f"    op.create_index('{idx_name}', '{table}', "
                            f"['{new_f.name}'], unique={unique})"
                        )
            if removed_annos:
                lines.append(
                    f"    # {new_f.name}: 移除注解 "
                    + ", ".join(sorted(removed_annos))
                )
                lines.append(
                    f"    # 约束移除需人工确认后手动执行"
                )
        lines.append("")

    # ── 数据回填 (type_changed) ──────────────────────────────
    if diff.type_changed:
        lines.append("    # ── Phase 3: 数据回填 (需在低峰期手动执行) ──")
        lines.append(f"    conn = op.get_bind()")
        for _old_f, new_f in diff.type_changed:
            v2_name = f"{new_f.name}_v2"
            lines.append(
                f"    conn.execute(sa.text("
            )
            lines.append(
                f'        "UPDATE {table} '
                f'SET {v2_name} = {new_f.name} WHERE {v2_name} IS NULL"'
            )
            lines.append(f"    ))")
        lines.append("")

    lines.append("")
    lines.append("")

    # ── downgrade() ──────────────────────────────────────────
    lines.append("def downgrade() -> None:")
    lines.append(f'    """蓝绿迁移 downgrade: {struct_name}"""')
    lines.append("    # 蓝绿迁移的 downgrade 仅移除新增列，不恢复已删除的列")
    lines.append("")

    for f in diff.added_fields:
        lines.append(f"    op.drop_column('{table}', '{f.name}')")

    for _old_f, new_f in diff.type_changed:
        v2_name = f"{new_f.name}_v2"
        lines.append(f"    op.drop_column('{table}', '{v2_name}')")

    if diff.annotation_changed:
        for old_f, new_f in diff.annotation_changed:
            old_annos = {_annotation_repr(a) for a in old_f.annotations}
            new_annos = {_annotation_repr(a) for a in new_f.annotations}
            added_annos = new_annos - old_annos
            for anno in new_f.annotations:
                if (
                    anno.name in ("unique", "index")
                    and _annotation_repr(anno) in added_annos
                ):
                    idx_name = f"ix_{table}_{new_f.name}"
                    lines.append(f"    op.drop_index('{idx_name}')")

    if not diff.added_fields and not diff.type_changed and not diff.annotation_changed:
        lines.append("    pass  # 无需回滚")

    lines.append("")

    return "\n".join(lines)


# ============================================================
# 顶层渲染入口: 比对两个 Program 输出，生成所有迁移文件
# ============================================================


def _struct_from_dict(struct_dict: dict) -> StructDef:
    """从 Program.to_dict() 中的 struct 字典重建 StructDef 对象。

    Args:
        struct_dict: 来自 Program.to_dict()["structs"][i] 的字典

    Returns:
        重建的 StructDef 实例
    """

    def _build_annotation(anno_dict: dict) -> Annotation:
        return Annotation(
            name=anno_dict["name"],
            args=list(anno_dict.get("args", [])),
            kwargs=dict(anno_dict.get("kwargs", {})),
        )

    def _build_type_ref(type_dict: dict) -> TypeRef:
        params = []
        for p in type_dict.get("params", []):
            if isinstance(p, dict):
                params.append(_build_type_ref(p))
            else:
                params.append(p)
        return TypeRef(
            base=type_dict["base"],
            params=params,
            is_optional=type_dict.get("is_optional", False),
        )

    fields = []
    for f_dict in struct_dict.get("fields", []):
        annotations = [
            _build_annotation(a) for a in f_dict.get("annotations", [])
        ]
        fields.append(
            FieldDef(
                name=f_dict["name"],
                type=_build_type_ref(f_dict["type"]),
                annotations=annotations,
            )
        )

    struct_annotations = [
        _build_annotation(a) for a in struct_dict.get("annotations", [])
    ]

    return StructDef(
        name=struct_dict["name"],
        annotations=struct_annotations,
        fields=fields,
    )


def render_migration(
    old_program: dict,
    new_program: dict,
    target_lang: str = "python_fastapi",
) -> list[dict]:
    """比较两个 Program.to_dict() 输出，为所有变更的 struct 生成迁移文件。

    Args:
        old_program: 变更前的 Program.to_dict() 结果
        new_program: 变更后的 Program.to_dict() 结果
        target_lang: 目标语言栈，决定生成 SQL 还是 Python 迁移脚本

    Returns:
        迁移文件列表，每项包含:
            - "name": 迁移文件名 (如 "mig_User_20260429120000.sql")
            - "content": 迁移脚本内容
    """
    old_structs = {
        s["name"]: s for s in old_program.get("structs", [])
    }
    new_structs = {
        s["name"]: s for s in new_program.get("structs", [])
    }

    all_struct_names = sorted(set(old_structs.keys()) | set(new_structs.keys()))
    migrations: list[dict] = []

    for name in all_struct_names:
        old_dict = old_structs.get(name)
        new_dict = new_structs.get(name)

        # 全新 struct: 不需要迁移，仅记录 DDL (建表由目标渲染器处理)
        if old_dict is None and new_dict is not None:
            continue

        # 被完全删除的 struct: 不生成 DROP TABLE (宪法禁止破坏性操作)
        if old_dict is not None and new_dict is None:
            table = _table_name(name)
            migrations.append({
                "name": f"mig_{name}_deprecated_{_timestamp_marker()}.sql",
                "content": (
                    f"-- [严重警告] struct {name} 已从源码中完全删除。\n"
                    f"-- 表 {table} 保留不删除 (ENJIN_CONSTITUTION §6)。\n"
                    f"-- 经人工审批后手动执行: DROP TABLE {table};\n"
                ),
            })
            continue

        old_struct = _struct_from_dict(old_dict)
        new_struct = _struct_from_dict(new_dict)
        struct_diff = diff_structs(old_struct, new_struct)

        if struct_diff.is_empty:
            continue

        ts = _timestamp_marker()

        # 生成 SQL 迁移
        sql_content = generate_migration_sql(struct_diff, name, target_lang)
        migrations.append({
            "name": f"mig_{name}_{ts}.sql",
            "content": sql_content,
        })

        # 生成 Python 迁移
        py_content = generate_migration_python(struct_diff, name)
        migrations.append({
            "name": f"mig_{name}_{ts}.py",
            "content": py_content,
        })

    return migrations

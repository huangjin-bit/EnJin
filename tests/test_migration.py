"""
============================================================
EnJin 蓝绿迁移模块测试 (test_migration.py)
============================================================
覆盖 migration.py 的 4 个公共函数:
  - diff_structs: struct 差异检测
  - generate_migration_sql: SQL 迁移脚本生成
  - generate_migration_python: Python Alembic 迁移脚本生成
  - render_migration: 顶层 Program 比对 + 迁移渲染
============================================================
"""

import pytest

from enjinc.migration import (
    StructDiff,
    diff_structs,
    generate_migration_python,
    generate_migration_sql,
    render_migration,
)
from enjinc.ast_nodes import Annotation, FieldDef, Program, StructDef, TypeRef


# ============================================================
# 辅助工厂函数
# ============================================================


def _make_struct(name: str, fields: list[FieldDef]) -> StructDef:
    """快速创建 StructDef 实例。"""
    return StructDef(name=name, fields=fields)


def _make_field(
    name: str,
    type_base: str = "String",
    annotations: list[Annotation] | None = None,
) -> FieldDef:
    """快速创建 FieldDef 实例。"""
    return FieldDef(
        name=name,
        type=TypeRef(base=type_base),
        annotations=annotations or [],
    )


def _make_program(structs: list[StructDef]) -> Program:
    """快速创建 Program 实例。"""
    return Program(structs=structs)


# ============================================================
# TestStructDiff — diff_structs 的 7 个测试用例
# ============================================================


class TestStructDiff:
    """测试 diff_structs 对各种变更类型的检测能力。"""

    def test_diff_added_fields(self):
        """新增字段应被正确检测。"""
        old = _make_struct("User", [
            _make_field("id", "Int"),
            _make_field("name", "String"),
        ])
        new = _make_struct("User", [
            _make_field("id", "Int"),
            _make_field("name", "String"),
            _make_field("email", "String"),
            _make_field("age", "Int"),
        ])

        diff = diff_structs(old, new)

        assert len(diff.added_fields) == 2
        added_names = {f.name for f in diff.added_fields}
        assert added_names == {"email", "age"}
        # 没有其他变更
        assert len(diff.removed_fields) == 0
        assert len(diff.type_changed) == 0
        assert len(diff.annotation_changed) == 0

    def test_diff_removed_fields(self):
        """被移除的字段应被正确检测。"""
        old = _make_struct("User", [
            _make_field("id", "Int"),
            _make_field("name", "String"),
            _make_field("nickname", "String"),
        ])
        new = _make_struct("User", [
            _make_field("id", "Int"),
            _make_field("name", "String"),
        ])

        diff = diff_structs(old, new)

        assert len(diff.removed_fields) == 1
        assert diff.removed_fields[0].name == "nickname"
        # 没有其他变更
        assert len(diff.added_fields) == 0
        assert len(diff.type_changed) == 0
        assert len(diff.annotation_changed) == 0

    def test_diff_type_changed(self):
        """类型变更应被检测为 type_changed，而非 added/removed。"""
        old = _make_struct("User", [
            _make_field("id", "Int"),
            _make_field("score", "String"),
        ])
        new = _make_struct("User", [
            _make_field("id", "Int"),
            _make_field("score", "Int"),
        ])

        diff = diff_structs(old, new)

        assert len(diff.type_changed) == 1
        old_field, new_field = diff.type_changed[0]
        assert old_field.name == "score"
        assert old_field.type.base == "String"
        assert new_field.type.base == "Int"
        # 类型变更不应出现在 added/removed 中
        assert len(diff.added_fields) == 0
        assert len(diff.removed_fields) == 0

    def test_diff_annotation_changed(self):
        """注解变更应被检测为 annotation_changed。"""
        old = _make_struct("User", [
            _make_field("id", "Int"),
            _make_field("email", "String"),
        ])
        new = _make_struct("User", [
            _make_field("id", "Int"),
            _make_field("email", "String", [Annotation(name="unique")]),
        ])

        diff = diff_structs(old, new)

        assert len(diff.annotation_changed) == 1
        old_field, new_field = diff.annotation_changed[0]
        assert old_field.name == "email"
        assert len(old_field.annotations) == 0
        assert len(new_field.annotations) == 1
        assert new_field.annotations[0].name == "unique"
        # 不应出现在其他变更类型中
        assert len(diff.added_fields) == 0
        assert len(diff.removed_fields) == 0
        assert len(diff.type_changed) == 0

    def test_diff_no_changes(self):
        """两个完全相同的 struct 应产生空差异。"""
        fields = [
            _make_field("id", "Int", [Annotation(name="primary")]),
            _make_field("name", "String"),
        ]
        old = _make_struct("User", fields)
        new = _make_struct("User", fields)

        diff = diff_structs(old, new)

        assert diff.is_empty is True
        assert len(diff.added_fields) == 0
        assert len(diff.removed_fields) == 0
        assert len(diff.type_changed) == 0
        assert len(diff.annotation_changed) == 0

    def test_struct_diff_is_empty(self):
        """验证 is_empty 属性在有变更时返回 False。"""
        # 有新增字段 → 非空
        old = _make_struct("User", [_make_field("id", "Int")])
        new = _make_struct("User", [
            _make_field("id", "Int"),
            _make_field("name", "String"),
        ])
        diff = diff_structs(old, new)
        assert diff.is_empty is False

        # 手动构造空 diff
        empty_diff = StructDiff()
        assert empty_diff.is_empty is True

        # 手动构造含 type_changed 的 diff
        typed_diff = StructDiff(
            type_changed=[(
                _make_field("age", "String"),
                _make_field("age", "Int"),
            )]
        )
        assert typed_diff.is_empty is False

    def test_struct_diff_to_dict(self):
        """验证 to_dict() 序列化结构正确。"""
        old = _make_struct("User", [_make_field("id", "Int")])
        new = _make_struct("User", [
            _make_field("id", "Int"),
            _make_field("email", "String", [Annotation(name="unique")]),
        ])
        diff = diff_structs(old, new)

        result = diff.to_dict()

        # 顶层应包含 4 个键
        assert set(result.keys()) == {
            "added_fields",
            "removed_fields",
            "type_changed",
            "annotation_changed",
        }
        # added_fields 应为列表，且元素是字典形式
        assert isinstance(result["added_fields"], list)
        assert len(result["added_fields"]) == 1
        assert result["added_fields"][0]["name"] == "email"
        # removed_fields / type_changed 应为空列表
        assert result["removed_fields"] == []
        assert result["type_changed"] == []


# ============================================================
# TestMigrationSQL — generate_migration_sql 的 3 个测试用例
# ============================================================


class TestMigrationSQL:
    """测试 SQL 迁移脚本生成。"""

    def test_sql_add_column(self):
        """新增字段应生成 ALTER TABLE ADD COLUMN，且默认 nullable。"""
        diff = StructDiff(
            added_fields=[_make_field("email", "String")],
        )
        sql = generate_migration_sql(diff, "User")

        # 应包含 ALTER TABLE ... ADD COLUMN 语句
        assert "ALTER TABLE user ADD COLUMN IF NOT EXISTS email TEXT" in sql
        # 应标记为新增字段
        assert "[新增字段]" in sql
        # 不应包含 DROP COLUMN
        assert "DROP COLUMN" not in sql.split("-- Phase 5")[0] if "-- Phase 5" in sql else "DROP COLUMN" not in sql

    def test_sql_removed_column_is_comment_only(self):
        """被移除的字段不应产生 DROP COLUMN，仅生成注释警告。"""
        diff = StructDiff(
            removed_fields=[_make_field("nickname", "String")],
        )
        sql = generate_migration_sql(diff, "User")

        # 应包含废弃字段标记
        assert "[废弃字段]" in sql
        assert "nickname" in sql
        # 绝不应有实际执行的 DROP COLUMN (只有注释中的)
        # 检查所有非注释行都不包含 DROP COLUMN
        for line in sql.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("--"):
                assert "DROP COLUMN" not in stripped, (
                    f"非注释行不应包含 DROP COLUMN: {stripped}"
                )
        # 应有人工审批提示
        assert "人工审批" in sql

    def test_sql_type_change_adds_v2_column(self):
        """类型变更应新增 _v2 后缀列，保留旧列。"""
        diff = StructDiff(
            type_changed=[
                (_make_field("score", "String"), _make_field("score", "Int")),
            ],
        )
        sql = generate_migration_sql(diff, "User")

        # 应新增 _v2 列
        assert "score_v2" in sql
        assert "ADD COLUMN IF NOT EXISTS score_v2" in sql
        # 应包含类型变更注释
        assert "[类型变更]" in sql
        assert "String" in sql
        assert "INTEGER" in sql
        # 应保留旧列（不出现 DROP 旧列的执行语句）
        assert "旧列 score 保留" in sql


# ============================================================
# TestMigrationPython — generate_migration_python 的 2 个测试用例
# ============================================================


class TestMigrationPython:
    """测试 Python Alembic 迁移脚本生成。"""

    def test_python_add_column(self):
        """新增字段应生成 op.add_column 调用。"""
        diff = StructDiff(
            added_fields=[_make_field("email", "String")],
        )
        py = generate_migration_python(diff, "User")

        # 应包含 Alembic op.add_column
        assert "op.add_column" in py
        assert "'user'" in py
        assert "'email'" in py
        assert "sa.String()" in py
        # 新增列应为 nullable=True
        assert "nullable=True" in py

    def test_python_has_upgrade_downgrade(self):
        """生成的脚本应同时包含 upgrade() 和 downgrade() 函数。"""
        diff = StructDiff(
            added_fields=[_make_field("age", "Int")],
        )
        py = generate_migration_python(diff, "User")

        assert "def upgrade()" in py
        assert "def downgrade()" in py
        # downgrade 中应有对应的 drop_column
        assert "op.drop_column" in py


# ============================================================
# TestRenderMigration — render_migration 的 2 个测试用例
# ============================================================


class TestRenderMigration:
    """测试顶层 render_migration 入口函数。"""

    def test_render_no_changes(self):
        """两个完全相同的 Program 不应产生任何迁移文件。"""
        struct = _make_struct("User", [
            _make_field("id", "Int"),
            _make_field("name", "String"),
        ])
        old_program = _make_program([struct])
        new_program = _make_program([struct])

        old_dict = old_program.to_dict()
        new_dict = new_program.to_dict()

        migrations = render_migration(old_dict, new_dict)

        assert migrations == []

    def test_render_with_changes(self):
        """有变更的 struct 应产生迁移文件（SQL + Python 各一份）。"""
        old_struct = _make_struct("User", [
            _make_field("id", "Int"),
            _make_field("name", "String"),
        ])
        new_struct = _make_struct("User", [
            _make_field("id", "Int"),
            _make_field("name", "String"),
            _make_field("email", "String"),
        ])

        old_program = _make_program([old_struct])
        new_program = _make_program([new_struct])

        old_dict = old_program.to_dict()
        new_dict = new_program.to_dict()

        migrations = render_migration(old_dict, new_dict)

        # 应生成至少 2 个迁移文件: .sql + .py
        assert len(migrations) >= 2
        file_names = [m["name"] for m in migrations]
        # 应包含 .sql 和 .py 文件
        assert any(n.endswith(".sql") for n in file_names)
        assert any(n.endswith(".py") for n in migrations[0]["name"] or n for n in file_names)
        # 文件名应包含 struct 名
        assert all("User" in m["name"] for m in migrations)
        # 内容应非空
        assert all(len(m["content"]) > 0 for m in migrations)

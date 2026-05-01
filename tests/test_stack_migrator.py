"""EnJin 技术栈迁移模块测试。"""

import pytest

from enjinc.ast_nodes import (
    Annotation,
    FieldDef,
    FnDef,
    NativeBlock,
    Param,
    ProcessIntent,
    Program,
    StructDef,
    TypeRef,
)
from enjinc.stack_migrator import (
    STACK_MAPPINGS,
    MigrationPlan,
    StackMapping,
    create_migration_plan,
)


def _make_struct(name: str, fields: list[FieldDef]) -> StructDef:
    return StructDef(name=name, fields=fields)


def _make_field(name: str, type_base: str = "String") -> FieldDef:
    return FieldDef(name=name, type=TypeRef(base=type_base))


def _make_program(
    structs=None, functions=None, routes=None, modules=None,
) -> Program:
    return Program(
        structs=structs or [],
        functions=functions or [],
        routes=routes or [],
        modules=modules or [],
    )


# ============================================================
# StackMapping 测试
# ============================================================


class TestStackMappings:
    """测试预定义的跨栈映射。"""

    def test_java_to_python_mapping_exists(self):
        mapping = STACK_MAPPINGS.get(("java_springboot", "python_fastapi"))
        assert mapping is not None
        assert mapping.from_target == "java_springboot"
        assert mapping.to_target == "python_fastapi"

    def test_python_to_java_mapping_exists(self):
        mapping = STACK_MAPPINGS.get(("python_fastapi", "java_springboot"))
        assert mapping is not None
        assert mapping.from_target == "python_fastapi"
        assert mapping.to_target == "java_springboot"

    def test_type_map_completeness(self):
        mapping = STACK_MAPPINGS[("java_springboot", "python_fastapi")]
        assert "String" in mapping.type_map
        assert mapping.type_map["String"] == "str"
        assert "Long" in mapping.type_map
        assert mapping.type_map["Long"] == "int"
        assert "Boolean" in mapping.type_map
        assert mapping.type_map["Boolean"] == "bool"

    def test_annotation_map(self):
        mapping = STACK_MAPPINGS[("java_springboot", "python_fastapi")]
        assert "@Entity" in mapping.annotation_map
        assert "@RestController" in mapping.annotation_map
        assert "@GetMapping" in mapping.annotation_map

    def test_file_map(self):
        mapping = STACK_MAPPINGS[("java_springboot", "python_fastapi")]
        assert "Entity.java" in mapping.file_map
        assert "Controller.java" in mapping.file_map

    def test_concepts_missing(self):
        mapping = STACK_MAPPINGS[("python_fastapi", "java_springboot")]
        assert len(mapping.concepts_missing) > 0
        concepts_text = " ".join(mapping.concepts_missing)
        assert "Alembic" in concepts_text or "Flyway" in concepts_text


# ============================================================
# MigrationPlan 测试
# ============================================================


class TestMigrationPlan:
    """测试迁移计划创建。"""

    def test_create_plan_with_known_mapping(self):
        program = _make_program(structs=[
            _make_struct("User", [
                _make_field("id", "Int"),
                _make_field("name", "String"),
            ])
        ])
        plan = create_migration_plan(program, "java_springboot", "python_fastapi")
        assert plan.source_target == "java_springboot"
        assert plan.target_target == "python_fastapi"
        assert plan.mapping is not None
        assert len(plan.warnings) == 0

    def test_create_plan_with_unknown_mapping(self):
        program = _make_program()
        plan = create_migration_plan(program, "go_gin", "rust_axum")
        assert plan.source_target == "go_gin"
        assert plan.target_target == "rust_axum"
        assert len(plan.warnings) > 0
        assert "无预定义映射" in plan.warnings[0]

    def test_native_block_warning(self):
        program = _make_program(functions=[
            FnDef(
                name="process_data",
                params=[Param(name="data", type=TypeRef(base="String"))],
                return_type=TypeRef(base="String"),
                annotations=[],
                guard=[],
                process=ProcessIntent(intent="process data"),
                expect=[],
                native_blocks=[
                    NativeBlock(target="python", code="return data.upper()"),
                ],
            ),
        ])
        plan = create_migration_plan(program, "java_springboot", "python_fastapi")
        assert len(plan.warnings) > 0
        assert any("native" in w for w in plan.warnings)

    def test_empty_program_plan(self):
        program = _make_program()
        plan = create_migration_plan(program, "python_fastapi", "java_springboot")
        assert plan.mapping is not None
        assert len(plan.warnings) == 0


# ============================================================
# 反向映射对称性测试
# ============================================================


class TestMappingSymmetry:
    """测试 Java↔Python 映射的对称性。"""

    def test_type_map_roundtrip_basic(self):
        java_to_py = STACK_MAPPINGS[("java_springboot", "python_fastapi")].type_map
        py_to_java = STACK_MAPPINGS[("python_fastapi", "java_springboot")].type_map

        # 检查常见类型可以双向映射
        for java_type, py_type in [("String", "str"), ("Boolean", "bool")]:
            assert java_to_py.get(java_type) == py_type
            assert py_to_java.get(py_type) == java_type

    def test_annotation_map_has_reversible_entries(self):
        java_to_py = STACK_MAPPINGS[("java_springboot", "python_fastapi")].annotation_map
        py_to_java = STACK_MAPPINGS[("python_fastapi", "java_springboot")].annotation_map

        assert "@GetMapping" in java_to_py
        assert java_to_py["@GetMapping"] == "@router.get"
        assert "@router.get" in py_to_java
        assert py_to_java["@router.get"] == "@GetMapping"

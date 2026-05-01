"""EnJin 重构模块测试。"""

import pytest

from enjinc.ast_nodes import (
    Annotation,
    ExpectAssertion,
    FieldDef,
    FnDef,
    GuardRule,
    ModuleDef,
    ModuleExport,
    Param,
    ProcessIntent,
    Program,
    RouteDef,
    StructDef,
    TypeRef,
)
from enjinc.refactor import (
    RefactorResult,
    extract_module,
    merge_structs,
    rename_struct,
    rename_struct_field,
    split_struct,
)


def _make_struct(name: str, fields: list[FieldDef], annotations=None) -> StructDef:
    return StructDef(name=name, fields=fields, annotations=annotations or [])


def _make_field(name: str, type_base: str = "String", annotations=None) -> FieldDef:
    return FieldDef(
        name=name, type=TypeRef(base=type_base), annotations=annotations or [],
    )


def _make_fn(
    name: str,
    params=None,
    return_type=None,
    guard_exprs=None,
    process_intent=None,
    expect_raw=None,
) -> FnDef:
    guard = [GuardRule(expr=e, message="") for e in (guard_exprs or [])]
    process = ProcessIntent(intent=process_intent) if process_intent else None
    expect = [ExpectAssertion(raw=r) for r in (expect_raw or [])] if expect_raw else []
    return FnDef(
        name=name,
        params=params or [],
        return_type=return_type,
        annotations=[],
        guard=guard,
        process=process,
        expect=expect,
    )


def _make_program(
    structs=None, functions=None, modules=None, routes=None,
) -> Program:
    return Program(
        structs=structs or [],
        functions=functions or [],
        modules=modules or [],
        routes=routes or [],
    )


# ============================================================
# rename_struct_field 测试
# ============================================================


class TestRenameStructField:
    """测试字段重命名及依赖传播。"""

    def test_basic_rename(self):
        program = _make_program(structs=[
            _make_struct("User", [_make_field("name"), _make_field("age", "Int")])
        ])
        result = rename_struct_field(program, "User", "name", "username")
        assert result.migration_needed is True
        assert "struct:User" in result.affected_nodes
        new_struct = result.new_program.structs[0]
        assert new_struct.fields[0].name == "username"
        assert new_struct.fields[1].name == "age"

    def test_propagate_to_guard(self):
        program = _make_program(
            structs=[_make_struct("User", [_make_field("age", "Int")])],
            functions=[_make_fn("check_age", params=[Param(name="u", type=TypeRef(base="User"))], guard_exprs=["age > 18"])],
        )
        result = rename_struct_field(program, "User", "age", "user_age")
        assert "fn:check_age" in result.affected_nodes
        fn = result.new_program.functions[0]
        assert "user_age > 18" == fn.guard[0].expr

    def test_propagate_to_process(self):
        program = _make_program(
            structs=[_make_struct("User", [_make_field("email")])],
            functions=[_make_fn("send_email", return_type=TypeRef(base="User"), process_intent="send to email")],
        )
        result = rename_struct_field(program, "User", "email", "email_address")
        assert "fn:send_email" in result.affected_nodes
        fn = result.new_program.functions[0]
        assert "email_address" in fn.process.intent

    def test_propagate_to_expect(self):
        program = _make_program(
            structs=[_make_struct("User", [_make_field("score", "Int")])],
            functions=[_make_fn("verify_score", params=[Param(name="u", type=TypeRef(base="User"))], expect_raw=["score > 0"])],
        )
        result = rename_struct_field(program, "User", "score", "total_score")
        fn = result.new_program.functions[0]
        assert "total_score > 0" == fn.expect[0].raw

    def test_no_match_struct(self):
        program = _make_program(structs=[_make_struct("User", [_make_field("id", "Int")])])
        result = rename_struct_field(program, "NotExist", "id", "new_id")
        assert result.affected_nodes == []

    def test_original_program_unchanged(self):
        program = _make_program(structs=[
            _make_struct("User", [_make_field("name")])
        ])
        rename_struct_field(program, "User", "name", "username")
        assert program.structs[0].fields[0].name == "name"

    def test_propagate_to_fn_param(self):
        program = _make_program(
            functions=[_make_fn("greet", params=[Param(name="name", type=TypeRef(base="String"))])],
        )
        result = rename_struct_field(program, "User", "name", "username")
        fn = result.new_program.functions[0]
        assert fn.params[0].name == "username"


# ============================================================
# rename_struct 测试
# ============================================================


class TestRenameStruct:
    """测试 struct 重命名及依赖传播。"""

    def test_basic_rename(self):
        program = _make_program(structs=[
            _make_struct("User", [_make_field("name")])
        ])
        result = rename_struct(program, "User", "Account")
        assert "struct:User" in result.affected_nodes
        assert result.new_program.structs[0].name == "Account"

    def test_propagate_to_fn_return_type(self):
        program = _make_program(
            structs=[_make_struct("User", [_make_field("name")])],
            functions=[_make_fn("get_user", return_type=TypeRef(base="User"))],
        )
        result = rename_struct(program, "User", "Account")
        fn = result.new_program.functions[0]
        assert fn.return_type.base == "Account"
        assert "fn:get_user" in result.affected_nodes

    def test_propagate_to_fn_param_type(self):
        program = _make_program(
            structs=[_make_struct("User", [_make_field("name")])],
            functions=[_make_fn("create", params=[Param(name="u", type=TypeRef(base="User"))])],
        )
        result = rename_struct(program, "User", "Account")
        fn = result.new_program.functions[0]
        assert fn.params[0].type.base == "Account"

    def test_propagate_to_module_deps(self):
        program = _make_program(
            structs=[_make_struct("User", [_make_field("name")])],
            modules=[ModuleDef(name="user_mod", dependencies=["User"], exports=[])],
        )
        result = rename_struct(program, "User", "Account")
        mod = result.new_program.modules[0]
        assert "Account" in mod.dependencies
        assert "User" not in mod.dependencies
        assert "module:user_mod" in result.affected_nodes

    def test_propagate_to_guard_text(self):
        program = _make_program(
            structs=[_make_struct("Order", [_make_field("amount", "Int")])],
            functions=[_make_fn("validate", guard_exprs=["Order.amount > 0"])],
        )
        result = rename_struct(program, "Order", "Purchase")
        fn = result.new_program.functions[0]
        assert "Purchase.amount > 0" == fn.guard[0].expr


# ============================================================
# extract_module 测试
# ============================================================


class TestExtractModule:
    """测试从源 module 提取 fn 到新 module。"""

    def test_basic_extract(self):
        program = _make_program(
            modules=[
                ModuleDef(
                    name="user_mod",
                    dependencies=["create_user", "delete_user"],
                    exports=[
                        ModuleExport(action="create_user", target="create_user"),
                        ModuleExport(action="delete_user", target="delete_user"),
                    ],
                ),
            ],
        )
        result = extract_module(program, "user_mod", ["delete_user"], "admin_mod")
        assert "module:user_mod" in result.affected_nodes
        assert "module:admin_mod" in result.affected_nodes

        source_mod = result.new_program.modules[0]
        assert "delete_user" not in source_mod.dependencies
        assert "create_user" in source_mod.dependencies

        new_mod = result.new_program.modules[1]
        assert new_mod.name == "admin_mod"
        assert "delete_user" in new_mod.dependencies

    def test_source_not_found(self):
        program = _make_program()
        result = extract_module(program, "nonexistent", ["fn1"], "new_mod")
        assert "not found" in result.change_description

    def test_route_dependency_updated(self):
        program = _make_program(
            modules=[
                ModuleDef(name="user_mod", dependencies=["create_user", "list_users"], exports=[]),
            ],
            routes=[
                RouteDef(name="user_api", dependencies=["user_mod"], annotations=[], endpoints=[]),
            ],
        )
        result = extract_module(program, "user_mod", ["list_users"], "query_mod")
        route = result.new_program.routes[0]
        assert "query_mod" in route.dependencies
        assert "route:user_api" in result.affected_nodes


# ============================================================
# merge_structs 测试
# ============================================================


class TestMergeStructs:
    """测试合并多个 struct。"""

    def test_basic_merge(self):
        program = _make_program(structs=[
            _make_struct("User", [_make_field("name"), _make_field("email")]),
            _make_struct("Profile", [_make_field("bio"), _make_field("avatar")]),
        ])
        result = merge_structs(program, ["User", "Profile"], "UserProfile")
        assert "struct:User" in result.affected_nodes
        assert "struct:Profile" in result.affected_nodes
        assert "struct:UserProfile" in result.affected_nodes

        merged = [s for s in result.new_program.structs if s.name == "UserProfile"][0]
        field_names = {f.name for f in merged.fields}
        assert field_names == {"name", "email", "bio", "avatar"}

    def test_field_conflict_latter_wins(self):
        program = _make_program(structs=[
            _make_struct("A", [_make_field("x", "Int"), _make_field("y", "Int")]),
            _make_struct("B", [_make_field("x", "String"), _make_field("z", "Int")]),
        ])
        result = merge_structs(program, ["A", "B"], "Merged")
        merged = [s for s in result.new_program.structs if s.name == "Merged"][0]
        x_field = [f for f in merged.fields if f.name == "x"][0]
        assert x_field.type.base == "Int"  # first one wins (existing_names check)

    def test_merge_updates_fn_type_refs(self):
        program = _make_program(
            structs=[
                _make_struct("A", [_make_field("id", "Int")]),
                _make_struct("B", [_make_field("id", "Int")]),
            ],
            functions=[
                _make_fn("get_a", return_type=TypeRef(base="A")),
                _make_fn("get_b", return_type=TypeRef(base="B")),
            ],
        )
        result = merge_structs(program, ["A", "B"], "Combined")
        for fn in result.new_program.functions:
            assert fn.return_type.base == "Combined"

    def test_merge_updates_module_deps(self):
        program = _make_program(
            structs=[
                _make_struct("A", [_make_field("id", "Int")]),
                _make_struct("B", [_make_field("id", "Int")]),
            ],
            modules=[
                ModuleDef(name="mod1", dependencies=["A", "B"], exports=[]),
            ],
        )
        result = merge_structs(program, ["A", "B"], "Combined")
        mod = result.new_program.modules[0]
        assert "Combined" in mod.dependencies
        assert "A" not in mod.dependencies
        assert "B" not in mod.dependencies


# ============================================================
# split_struct 测试
# ============================================================


class TestSplitStruct:
    """测试拆分 struct。"""

    def test_basic_split(self):
        program = _make_program(structs=[
            _make_struct("User", [
                _make_field("name"),
                _make_field("email"),
                _make_field("bio"),
                _make_field("avatar"),
            ]),
        ])
        result = split_struct(program, "User", {
            "UserProfile": ["bio", "avatar"],
        })
        assert "struct:UserProfile" in result.affected_nodes

        # Original should still have name and email
        original = [s for s in result.new_program.structs if s.name == "User"][0]
        assert {f.name for f in original.fields} == {"name", "email"}

        # New struct has bio and avatar
        profile = [s for s in result.new_program.structs if s.name == "UserProfile"][0]
        assert {f.name for f in profile.fields} == {"bio", "avatar"}

    def test_full_split_removes_original(self):
        program = _make_program(structs=[
            _make_struct("User", [_make_field("name"), _make_field("email")]),
        ])
        result = split_struct(program, "User", {
            "BasicInfo": ["name"],
            "ContactInfo": ["email"],
        })
        struct_names = {s.name for s in result.new_program.structs}
        assert "User" not in struct_names
        assert "BasicInfo" in struct_names
        assert "ContactInfo" in struct_names

    def test_struct_not_found(self):
        program = _make_program()
        result = split_struct(program, "NonExistent", {"New": ["field"]})
        assert "not found" in result.change_description

    def test_original_unchanged(self):
        program = _make_program(structs=[
            _make_struct("User", [_make_field("name"), _make_field("email")]),
        ])
        split_struct(program, "User", {"Profile": ["name"]})
        assert len(program.structs[0].fields) == 2

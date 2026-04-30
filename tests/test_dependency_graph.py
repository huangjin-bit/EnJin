"""Tests for dependency_graph.py"""

import pytest

from enjinc.ast_nodes import (
    Annotation,
    FieldDef,
    FnDef,
    GuardRule,
    ModuleDef,
    ModuleExport,
    Param,
    ProcessIntent,
    Program,
    RouteDef,
    EndpointDef,
    StructDef,
    TypeRef,
)
from enjinc.dependency_graph import DependencyGraph, PRIMITIVE_TYPES


def _make_user_program():
    """构造一个 user_management 风格的 Program。"""
    return Program(
        application=None,
        structs=[
            StructDef(
                name="User",
                fields=[
                    FieldDef(name="id", type=TypeRef(base="Int"), annotations=[Annotation(name="primary")]),
                    FieldDef(name="username", type=TypeRef(base="String")),
                    FieldDef(name="email", type=TypeRef(base="String"), annotations=[Annotation(name="unique")]),
                    FieldDef(name="status", type=TypeRef(base="String")),
                ],
            ),
            StructDef(
                name="UserProfile",
                fields=[
                    FieldDef(name="id", type=TypeRef(base="Int"), annotations=[Annotation(name="primary")]),
                    FieldDef(name="user_id", type=TypeRef(base="Int")),
                    FieldDef(name="bio", type=TypeRef(base="String")),
                ],
            ),
        ],
        functions=[
            FnDef(
                name="register_user",
                params=[
                    Param(name="username", type=TypeRef(base="String")),
                    Param(name="email", type=TypeRef(base="String")),
                    Param(name="password", type=TypeRef(base="String")),
                ],
                return_type=TypeRef(base="User"),
                process=ProcessIntent(intent="register a new user"),
                guard=[GuardRule(expr='exists(User, "email == email")', message="email already exists")],
            ),
            FnDef(
                name="get_user_by_id",
                params=[Param(name="id", type=TypeRef(base="Int"))],
                return_type=TypeRef(base="User"),
                process=ProcessIntent(intent="get user by id"),
            ),
            FnDef(
                name="delete_user",
                params=[Param(name="id", type=TypeRef(base="Int"))],
                return_type=TypeRef(base="Bool"),
                process=ProcessIntent(intent="delete a user"),
            ),
        ],
        modules=[
            ModuleDef(
                name="UserManager",
                dependencies=["User", "UserProfile", "register_user", "get_user_by_id", "delete_user"],
                exports=[
                    ModuleExport(action="register", target="register_user"),
                    ModuleExport(action="detail", target="get_user_by_id"),
                    ModuleExport(action="remove", target="delete_user"),
                ],
            ),
        ],
        routes=[
            RouteDef(
                name="UserService",
                annotations=[Annotation(name="prefix", args=["/api/v1/users"])],
                dependencies=["UserManager"],
                endpoints=[
                    EndpointDef(method="POST", path="/register", handler="register"),
                    EndpointDef(method="GET", path="/{id}", handler="detail"),
                    EndpointDef(method="DELETE", path="/{id}", handler="remove"),
                ],
            ),
        ],
    )


class TestDependencyGraphBuild:
    def test_build_empty_program(self):
        graph = DependencyGraph.build(Program())
        assert graph.structs == {}
        assert graph.functions == {}
        assert graph.modules == {}
        assert graph.routes == {}
        assert graph.fn_to_structs == {}

    def test_build_user_program(self):
        program = _make_user_program()
        graph = DependencyGraph.build(program)

        assert "User" in graph.structs
        assert "UserProfile" in graph.structs
        assert "register_user" in graph.functions
        assert "UserManager" in graph.modules
        assert "UserService" in graph.routes

    def test_fn_to_structs_return_type(self):
        program = _make_user_program()
        graph = DependencyGraph.build(program)

        assert "User" in graph.fn_to_structs["register_user"]
        assert "User" in graph.fn_to_structs["get_user_by_id"]

    def test_fn_to_structs_guard(self):
        program = _make_user_program()
        graph = DependencyGraph.build(program)

        assert "User" in graph.fn_to_structs["register_user"]

    def test_fn_to_structs_no_dep_for_primitive(self):
        program = _make_user_program()
        graph = DependencyGraph.build(program)

        assert graph.fn_to_structs["delete_user"] == set()

    def test_module_to_fns(self):
        program = _make_user_program()
        graph = DependencyGraph.build(program)

        fns = graph.module_to_fns["UserManager"]
        assert "register_user" in fns
        assert "get_user_by_id" in fns
        assert "delete_user" in fns

    def test_route_to_modules(self):
        program = _make_user_program()
        graph = DependencyGraph.build(program)

        assert "UserManager" in graph.route_to_modules["UserService"]


class TestRenderSummary:
    def test_empty_program(self):
        graph = DependencyGraph.build(Program())
        summary = graph.render_summary()
        assert "项目依赖图" in summary

    def test_user_program_summary(self):
        program = _make_user_program()
        graph = DependencyGraph.build(program)
        summary = graph.render_summary()

        assert "User" in summary
        assert "UserProfile" in summary
        assert "register_user" in summary
        assert "UserManager" in summary
        assert "UserService" in summary
        assert "调用关系" in summary

    def test_summary_contains_fields(self):
        program = _make_user_program()
        graph = DependencyGraph.build(program)
        summary = graph.render_summary()

        assert "username" in summary
        assert "email" in summary

    def test_summary_contains_endpoints(self):
        program = _make_user_program()
        graph = DependencyGraph.build(program)
        summary = graph.render_summary()

        assert "POST" in summary
        assert "GET" in summary


class TestRenderFnContext:
    def test_unknown_fn(self):
        program = _make_user_program()
        graph = DependencyGraph.build(program)
        ctx = graph.render_fn_context("nonexistent")
        assert ctx == ""

    def test_fn_with_dep(self):
        program = _make_user_program()
        graph = DependencyGraph.build(program)
        ctx = graph.render_fn_context("register_user")

        assert "register_user" in ctx
        assert "User" in ctx
        assert "username" in ctx

    def test_fn_without_dep(self):
        program = _make_user_program()
        graph = DependencyGraph.build(program)
        ctx = graph.render_fn_context("delete_user")

        assert "无外部 struct 依赖" in ctx


class TestRenderRouteContext:
    def test_unknown_route(self):
        program = _make_user_program()
        graph = DependencyGraph.build(program)
        ctx = graph.render_route_context("nonexistent")
        assert ctx == ""

    def test_route_with_module(self):
        program = _make_user_program()
        graph = DependencyGraph.build(program)
        ctx = graph.render_route_context("UserService")

        assert "UserService" in ctx
        assert "UserManager" in ctx
        assert "register" in ctx
        assert "register_user" in ctx

    def test_route_no_module_dep(self):
        program = Program(
            routes=[RouteDef(name="StandaloneRoute")],
        )
        graph = DependencyGraph.build(program)
        ctx = graph.render_route_context("StandaloneRoute")

        assert "无 module 依赖" in ctx


class TestPrimitiveTypes:
    def test_primitive_types_set(self):
        assert "Int" in PRIMITIVE_TYPES
        assert "String" in PRIMITIVE_TYPES
        assert "Bool" in PRIMITIVE_TYPES
        assert "Float" in PRIMITIVE_TYPES
        assert "DateTime" in PRIMITIVE_TYPES
        assert "List" in PRIMITIVE_TYPES


class TestStructToStructDependency:
    """验证 struct→struct 依赖追踪（foreign_key 和字段类型引用）。"""

    def _make_program(self):
        return Program(
            structs=[
                StructDef(name="User", fields=[
                    FieldDef(name="id", type=TypeRef(base="Int"), annotations=[Annotation(name="primary")]),
                    FieldDef(name="name", type=TypeRef(base="String")),
                ]),
                StructDef(name="Order", fields=[
                    FieldDef(name="id", type=TypeRef(base="Int"), annotations=[Annotation(name="primary")]),
                    FieldDef(name="user_id", type=TypeRef(base="Int"), annotations=[Annotation(name="foreign_key", args=["User.id"])]),
                    FieldDef(name="amount", type=TypeRef(base="Float")),
                ]),
                StructDef(name="Comment", fields=[
                    FieldDef(name="id", type=TypeRef(base="Int"), annotations=[Annotation(name="primary")]),
                    FieldDef(name="author", type=TypeRef(base="User")),
                ]),
            ],
            functions=[
                FnDef(name="get_order", params=[Param(name="id", type=TypeRef(base="Int"))],
                     return_type=TypeRef(base="Order"), process=ProcessIntent(intent="get order")),
            ],
        )

    def test_foreign_key_tracked(self):
        graph = DependencyGraph.build(self._make_program())
        assert "User" in graph.struct_to_structs["Order"]

    def test_field_type_ref_tracked(self):
        graph = DependencyGraph.build(self._make_program())
        assert "User" in graph.struct_to_structs["Comment"]

    def test_no_self_dependency(self):
        graph = DependencyGraph.build(self._make_program())
        assert "User" not in graph.struct_to_structs["User"]

    def test_render_struct_context_includes_related(self):
        graph = DependencyGraph.build(self._make_program())
        ctx = graph.render_struct_context("Order")
        assert "User" in ctx

    def test_render_fn_context_shows_secondary_deps(self):
        graph = DependencyGraph.build(self._make_program())
        ctx = graph.render_fn_context("get_order")
        assert "Order" in ctx
        assert "User" in ctx  # 二级依赖

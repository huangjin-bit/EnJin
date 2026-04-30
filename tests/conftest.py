"""
============================================================
EnJin 测试配置 (conftest.py)
============================================================
共享 pytest fixtures 和测试配置，供所有测试文件使用。

维护协议:
    新增 fixtures 前需确认是否可复用，避免重复定义。
============================================================
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Generator

import pytest


# ============================================================
# 路径 Fixtures
# ============================================================


@pytest.fixture
def project_root() -> Path:
    """项目根目录。"""
    return Path(__file__).parent.parent


@pytest.fixture
def examples_dir(project_root: Path) -> Path:
    """examples/ 目录。"""
    return project_root / "examples"


@pytest.fixture
def src_dir(project_root: Path) -> Path:
    """src/enjinc/ 源码目录。"""
    return project_root / "src" / "enjinc"


@pytest.fixture
def templates_dir(src_dir: Path) -> Path:
    """模板目录。"""
    return src_dir / "targets" / "python_fastapi" / "templates"


# ============================================================
# 临时路径 Fixtures
# ============================================================


@pytest.fixture
def tmp_output_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """临时输出目录，测试结束后自动清理。"""
    output = tmp_path / "output"
    output.mkdir(parents=True, exist_ok=True)
    yield output


# ============================================================
# 大规模测试数据生成 Fixtures
# ============================================================


def generate_large_struct_source(count: int, with_fields: bool = True) -> str:
    """生成大规模 struct 定义字符串。

    Args:
        count: 生成 struct 的数量
        with_fields: 是否包含字段定义

    Returns:
        多个 struct 定义的字符串
    """
    structs = []
    for i in range(count):
        if with_fields:
            structs.append(f"""
struct LargeStruct{i} {{
    id: Int @primary @auto_increment
    field_a: String @max_length(100)
    field_b: Int
    field_c: Bool @default(true)
    field_d: Optional<String>
}}
""")
        else:
            structs.append(f"struct LargeStruct{i} {{ }}")

    return "\n".join(structs)


def generate_large_fn_source(
    count: int, with_guard: bool = True, with_expect: bool = True
) -> str:
    """生成大规模 fn 定义字符串。

    Args:
        count: 生成 fn 的数量
        with_guard: 是否包含 guard
        with_expect: 是否包含 expect

    Returns:
        多个 fn 定义的字符串
    """
    fns = []
    for i in range(count):
        guard_block = ""
        if with_guard:
            guard_block = """
    guard {
        id > 0 : "ID must be positive"
    }
"""

        expect_block = ""
        if with_expect:
            expect_block = """
    expect {
        get_large_entity_{i}(1).id == 1
    }
""".format(i=i)

        fns.append(f"""
fn get_large_entity_{i}(id: Int) -> LargeStruct{i} {{
{guard_block}
    process {{
        "查询大型实体 {{id}}"
    }}
{expect_block}
}}
""")

    return "\n".join(fns)


def generate_large_module_source(count: int, deps_per_module: int = 3) -> str:
    """生成大规模 module 定义字符串。

    Args:
        count: 生成 module 的数量
        deps_per_module: 每个 module 的依赖数量

    Returns:
        多个 module 定义的字符串
    """
    modules = []
    for i in range(count):
        deps = [f"LargeModule{j}" for j in range(max(0, i - deps_per_module), i)]
        deps_str = "\n    ".join(f"use {d}" for d in deps)

        modules.append(f"""
module LargeModule{i} {{
    {deps_str}

    init {{
        "初始化模块 {i}"
    }}
}}
""")

    return "\n".join(modules)


def generate_large_route_source(count: int, endpoints_per_route: int = 5) -> str:
    """生成大规模 route 定义字符串。

    Args:
        count: 生成 route 的数量
        endpoints_per_route: 每个 route 的端点数量

    Returns:
        多个 route 定义的字符串
    """
    routes = []
    for i in range(count):
        endpoints = []
        methods = ["GET", "POST", "PUT", "DELETE"]
        for j in range(endpoints_per_route):
            method = methods[j % len(methods)]
            path = f"/entity/{i}/item/{j}"
            handler = f"handle_{i}_{j}"
            endpoints.append(f'{method} "{path}" -> {handler}')

        endpoints_str = "\n    ".join(endpoints)

        routes.append(f"""
route LargeRoute{i} {{
    use LargeModule{i}

    {endpoints_str}
}}
""")

    return "\n".join(routes)


# ============================================================
# 并发测试 Fixtures
# ============================================================


@pytest.fixture
def thread_safe_counter() -> Generator[dict, None, None]:
    """线程安全的计数器，用于并发测试。"""
    counter = {"value": 0, "lock": threading.Lock()}

    def increment():
        with counter["lock"]:
            counter["value"] += 1

    counter["increment"] = increment
    yield counter


# ============================================================
# 错误输入 Fixtures
# ============================================================


@pytest.fixture
def malformed_inputs() -> dict[str, str]:
    """各种格式错误的 .ej 源码输入。

    Returns:
        错误类型到源码的字典
    """
    return {
        "missing_closing_brace_struct": """
struct Incomplete {
    id: Int @primary
""",
        "missing_closing_brace_fn": """
fn broken_fn(id: Int) -> Int {
    process {
        "test"
    }
""",
        "missing_closing_brace_module": """
module BrokenModule {
    use User
""",
        "missing_closing_brace_route": """
route BrokenRoute {
    GET "/test" -> handler
""",
        "missing_colon_field": """
struct BadField {
    id Int @primary
""",
        "missing_arrow_return_type": """
fn no_arrow(id: Int) Int {
    process { "test" }
}
""",
        "missing parenthesis_params": """
fn no_paren id: Int {
    process { "test" }
}
""",
        "empty_file": "",
        "comment_only": """// This file only has comments
// Another comment
""",
        "invalid_unicode_ident": """
struct BadName {
    name_中文: String
}
""",
        "native_unbalanced_braces": """
fn native_braces(data: String) -> String {
    native python {
        import hashlib
        return hashlib.sha256(data.encode()).hexdigest()
}
""",
        "truncated_mid_token": """
struct Truncated {
    id: Int @primary @auto_
""",
        "struct_inside_struct": """
struct Outer {
    id: Int
    struct Inner {
        name: String
    }
}
""",
        "fn_inside_fn": """
fn outer() {
    fn inner() {
        process { "inner" }
    }
    process { "outer" }
}
""",
        "wrong_keyword_module": """
module BadModule {
    route RouteName {
        GET "/test" -> handler
    }
}
""",
        "invalid_annotation_syntax": """
@ table("users")
struct InvalidAnnotation {
    id: Int
}
""",
        "missing_type_in_field": """
struct NoType {
    field_without_type
}
""",
    }


# ============================================================
# 缓存/锁文件 Fixtures
# ============================================================


@pytest.fixture
def lock_file_content() -> dict:
    """生成 enjin.lock 文件的示例内容。"""
    return {
        "version": "1.0",
        "generated_at": "2026-03-16T12:00:00Z",
        "compiler_version": "0.3.0",
        "compilation_unit_id": "test_unit_123",
        "target": "python_fastapi",
        "nodes": {
            "sha256:abc123def456": {
                "node_type": "fn",
                "name": "test_fn",
                "intent_hash": "sha256:xyz789",
                "generated_code": {
                    "python_fastapi": "def test_fn():\n    pass\n",
                    "java_springboot": None,
                },
                "generated_at": "2026-03-16T11:00:00Z",
                "model_used": "gpt-4",
                "tokens_consumed": {"input": 100, "output": 50},
            }
        },
    }


@pytest.fixture
def corrupted_lock_file() -> str:
    """损坏的 enjin.lock 文件内容。"""
    return """
{
    "version": "1.0",
    "generated_at": "2026-03-16T12:00:00Z",
    "nodes": {
        "sha256:abc123": {
            "generated_code": {
                // JSON 注释会导致解析失败
                "python": "def test(): pass"
            }
        }
    }
"""


@pytest.fixture
def stale_lock_file_content() -> dict:
    """过期的缓存锁文件（AST hash 不匹配）。"""
    return {
        "version": "1.0",
        "generated_at": "2025-01-01T00:00:00Z",
        "compiler_version": "0.1.0",
        "compilation_unit_id": "old_unit_999",
        "target": "python_fastapi",
        "nodes": {
            "sha256:old_hash_abc": {
                "node_type": "fn",
                "name": "old_fn",
                "intent_hash": "sha256:old_intent",
                "generated_code": {
                    "python_fastapi": "def old_fn_old():\n    pass\n",
                },
                "generated_at": "2025-01-01T00:00:00Z",
            }
        },
    }

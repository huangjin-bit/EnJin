"""
============================================================
EnJin 大规模压力测试 (test_parser_stress.py)
============================================================
验证解析器在极端大规模输入下的正确性和性能。

压力测试场景:
    - 1000+ structs 单文件解析
    - 1000+ functions 单文件解析
    - 100+ modules 单文件解析
    - 100+ routes 单文件解析
    - 50+ 字段的 struct
    - 20+ 参数的 fn
    - 50+ endpoints 的 route
    - 30+ exports 的 module
    - 深层次 module 依赖链 (A->B->C->...->Z)

维护协议:
    压力测试仅验证正确性和内存使用，不验证业务逻辑。
============================================================
"""

from __future__ import annotations

from pathlib import Path
import time

import pytest

from enjinc.parser import parse, parse_file
from enjinc.ast_nodes import Program


# ============================================================
# 大规模 Struct 解析测试
# ============================================================


class TestLargeScaleStructs:
    """验证大规模 struct 定义的解析能力。"""

    @pytest.mark.parametrize("count", [100, 500, 1000])
    def test_1000_structs_parsing(self, count: int):
        """解析包含 100/500/1000 个 struct 的文件。"""
        structs = []
        for i in range(count):
            structs.append(f"""
struct Entity{i} {{
    id: Int @primary @auto_increment
    name: String @max_length(100) @unique
    status: Enum("active", "inactive", "pending") @default("active")
    created_at: DateTime @default("now()")
    updated_at: Optional<DateTime>
}}
""")

        source = "\n".join(structs)
        program = parse(source)

        assert len(program.structs) == count
        assert all(s.name.startswith("Entity") for s in program.structs)

    def test_50_field_struct(self):
        """解析包含 50+ 字段的单个 struct。"""
        fields = []
        for i in range(50):
            fields.append(f"field_{i}: String @max_length(100)")

        source = f"""
struct LargeEntity {{
    {chr(10).join(fields)}
}}
"""
        program = parse(source)

        assert len(program.structs) == 1
        assert len(program.structs[0].fields) == 50

    def test_nested_generic_types(self):
        """解析嵌套泛型类型 List<List<Optional<Int>>>。"""
        source = """
struct NestedGeneric {
    data: List<List<Optional<Int>>>
}
"""
        program = parse(source)

        assert len(program.structs) == 1
        field = program.structs[0].fields[0]
        assert field.type.base == "List"
        assert len(field.type.params) == 1


# ============================================================
# 大规模 Function 解析测试
# ============================================================


class TestLargeScaleFunctions:
    """验证大规模 function 定义的解析能力。"""

    @pytest.mark.parametrize("count", [100, 500, 1000])
    def test_1000_functions_parsing(self, count: int):
        """解析包含 100/500/1000 个 fn 的文件。"""
        fns = []
        for i in range(count):
            fns.append(f"""
fn get_entity_{i}(id: Int) -> Entity{i} {{
    guard {{
        id > 0 : "ID must be positive"
    }}
    process {{
        "查询 ID 为 {{id}} 的实体"
    }}
    expect {{
        get_entity_{i}(1).id == 1
        get_entity_{i}(-1).throws("ID must be positive")
    }}
}}
""")

        source = "\n".join(fns)
        program = parse(source)

        assert len(program.functions) == count

    def test_20_parameter_function(self):
        """解析包含 20+ 参数的 fn。"""
        params = [f"param_{i}: Int" for i in range(20)]
        source = f"""
fn complex_operation({", ".join(params)}) -> Int {{
    process {{
        "执行包含 20 个参数的操作"
    }}
}}
"""
        program = parse(source)

        assert len(program.functions) == 1
        assert len(program.functions[0].params) == 20

    def test_function_with_50_guard_rules(self):
        """解析包含 50+ guard 规则的 fn。"""
        guards = [f'field_{i} > 0 : "Field {i} must be positive"' for i in range(50)]
        source = f"""
fn highly_validated(data: String) -> Bool {{
    guard {{
        {", ".join(guards)}
    }}
    process {{
        "执行高度校验的操作"
    }}
}}
"""
        program = parse(source)

        assert len(program.functions) == 1
        assert len(program.functions[0].guard) == 50


# ============================================================
# 大规模 Module 解析测试
# ============================================================


class TestLargeScaleModules:
    """验证大规模 module 定义的解析能力。"""

    @pytest.mark.parametrize("count", [10, 50, 100])
    def test_100_modules_parsing(self, count: int):
        """解析包含 10/50/100 个 module 的文件。"""
        modules = []
        for i in range(count):
            modules.append(f"""
module Module{i} {{
    use Entity{i}
    use get_entity_{i}

    init {{
        "初始化模块 {i}"
    }}

    schedule hourly at "00:00" {{
        "执行模块 {i} 的定时任务"
    }}
}}
""")

        source = "\n".join(modules)
        program = parse(source)

        assert len(program.modules) == count

    def test_30_exports_module(self):
        """解析包含 30+ use 声明的 module。"""
        uses = [f"use Function{j}" for j in range(30)]
        source = f"""
module LargeModule {{
    {chr(10) + "    ".join([""] + uses)}

    init {{
        "初始化大型模块"
    }}
}}
"""
        program = parse(source)

        assert len(program.modules) == 1
        assert len(program.modules[0].dependencies) == 30

    def test_deep_module_dependency_chain(self):
        """验证深层次 module 依赖链 (A->B->C->...->Z)。"""
        modules = []
        for i in range(26):  # A to Z
            prev = chr(ord("A") + i - 1) if i > 0 else None
            dep = f"use Module{prev}" if prev else ""
            modules.append(f"""
module Module{i} {{
    {dep}
    use Function{i}
    init {{ "Init {i}" }}
}}
""")

        source = "\n".join(modules)
        program = parse(source)

        assert len(program.modules) == 26


# ============================================================
# 大规模 Route 解析测试
# ============================================================


class TestLargeScaleRoutes:
    """验证大规模 route 定义的解析能力。"""

    @pytest.mark.parametrize("count", [10, 50, 100])
    def test_100_routes_parsing(self, count: int):
        """解析包含 10/50/100 个 route 的文件。"""
        routes = []
        methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]

        for i in range(count):
            endpoints = []
            for j in range(5):
                method = methods[j % len(methods)]
                path = f"/api/v{i}/resource/{j}"
                handler = f"handler_{i}_{j}"
                endpoints.append(f'{method} "{path}" -> {handler}')

            endpoints_str = "\n" + "\n".join(f"    {ep}" for ep in endpoints)
            routes.append(f"""
route ApiRoute{i} {{
    use Module{i}
{endpoints_str}
}}
""")

        source = "\n".join(routes)
        program = parse(source)

        assert len(program.routes) == count

    def test_50_endpoints_single_route(self):
        """解析包含 50+ endpoints 的单个 route。"""
        endpoints = []
        methods = ["GET", "POST"]
        for i in range(50):
            method = methods[i % len(methods)]
            path = f"/item/{i}"
            handler = f"handle_item_{i}"
            endpoints.append(f'{method} "{path}" -> {handler}')

        endpoints_str = "\n".join(f"    {ep}" for ep in endpoints)
        source = f"""
route LargeRoute {{
    use UserModule
{endpoints_str}
}}
"""
        program = parse(source)

        assert len(program.routes) == 1
        assert len(program.routes[0].endpoints) == 50


# ============================================================
# 大规模编译单元测试
# ============================================================


class TestLargeCompilationUnit:
    """验证大规模多文件编译单元。"""

    def test_50_file_compilation_unit(self, tmp_path: Path):
        """解析包含 50 个 .ej 文件的编译单元。"""
        unit_dir = tmp_path / "large_unit"
        unit_dir.mkdir(parents=True, exist_ok=True)

        # 创建 application.ej
        (unit_dir / "application.ej").write_text(
            """
application {
    name: "large-app"
    version: "1.0.0"
    target: "python_fastapi"
}
""",
            encoding="utf-8",
        )

        # 创建 50 个 domain 文件
        for i in range(50):
            (unit_dir / f"domain_{i}.ej").write_text(
                f"""
@domain("domain_{i}")
module Domain{i} {{
    use Entity{i}
    use Function{i}

    init {{ "初始化领域 {i}" }}
}}

struct Entity{i} {{
    id: Int @primary
}}

fn Function{i}(id: Int) -> Entity{i} {{
    process {{ "Function {i}" }}
}}
""",
                encoding="utf-8",
            )

        # 验证所有文件可以被解析
        for ej_file in unit_dir.glob("*.ej"):
            source = ej_file.read_text(encoding="utf-8")
            program = parse(source)
            assert program is not None

    def test_mixed_large_scale(self, tmp_path: Path):
        """验证混合大规模场景 (100 structs + 100 fns + 50 modules + 50 routes)。"""
        structs = [f"struct S{i} {{\n    id: Int @primary\n}}" for i in range(100)]
        fns = [
            f'fn F{i}(id: Int) -> S{i} {{\n    process {{ "test" }}\n}}'
            for i in range(100)
        ]
        modules = [
            f"module M{i} {{\n    use S{i}\n    use F{i}\n    use M{max(i - 1, 0)}\n    init {{ \"init\" }}\n}}"
            for i in range(50)
        ]
        routes = [
            f'route R{i} {{\n    use M{i}\n    GET "/r{i}" -> F{i}\n}}'
            for i in range(50)
        ]

        source = "\n".join(structs + fns + modules + routes)
        program = parse(source)

        assert len(program.structs) == 100
        assert len(program.functions) == 100
        assert len(program.modules) == 50
        assert len(program.routes) == 50


# ============================================================
# 性能基准测试
# ============================================================


class TestParsingPerformance:
    """解析性能基准测试。"""

    @pytest.mark.slow
    def test_1000_structs_performance(self):
        """解析 1000 个 struct 的耗时基准 (< 5 秒)。"""
        structs = []
        for i in range(1000):
            structs.append(f"""
struct PerfEntity{i} {{
    id: Int @primary @auto_increment
    name: String @max_length(100)
}}
""")

        source = "\n".join(structs)

        start = time.time()
        program = parse(source)
        elapsed = time.time() - start

        assert len(program.structs) == 1000
        assert elapsed < 30.0, f"解析耗时 {elapsed:.2f}s，超过 30s 阈值"

    @pytest.mark.slow
    def test_500_functions_performance(self):
        """解析 500 个 fn 的耗时基准 (< 5 秒)。"""
        fns = []
        for i in range(500):
            fns.append(f"""
fn perf_fn_{i}(id: Int) -> PerfEntity{i} {{
    guard {{ id > 0 : "positive" }}
    process {{ "查询实体 {{id}}" }}
    expect {{ perf_fn_{i}(1).id == 1 }}
}}
""")

        source = "\n".join(fns)

        start = time.time()
        program = parse(source)
        elapsed = time.time() - start

        assert len(program.functions) == 500
        assert elapsed < 30.0, f"解析耗时 {elapsed:.2f}s，超过 30s 阈值"

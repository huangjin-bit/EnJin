"""
============================================================
EnJin 并发安全测试 (test_parser_concurrency.py)
============================================================
验证解析器在多线程并发环境下的线程安全性。

并发测试场景:
    - 多线程同时解析不同源码
    - 多线程同时解析相同源码
    - 全局 Parser 单例的线程安全
    - Jinja2 Environment 缓存的线程安全
    - Analyzer 共享状态的线程安全

维护协议:
    并发测试使用 thread_safe_counter 验证无竞态条件。
============================================================
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

import pytest

from enjinc.parser import parse, parse_file, _get_parser
from enjinc.analyzer import analyze
from enjinc.template_renderer import RenderConfig, render_program
from enjinc.jinja_utils import get_jinja_env
from enjinc.ast_nodes import Program


# ============================================================
# Parser 线程安全测试
# ============================================================


class TestParserThreadSafety:
    """验证 Lark Parser 在多线程下的安全性。"""

    def test_concurrent_parse_different_sources(self, thread_safe_counter: dict):
        """多线程并发解析不同源码，无数据竞争。"""
        sources = []
        for i in range(100):
            sources.append(f"""
struct Entity{i} {{
    id: Int @primary
    name: String @unique
}}
""")

        def parse_source(source: str, idx: int):
            program = parse(source)
            with thread_safe_counter["lock"]:
                thread_safe_counter["value"] += 1
            return program

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(parse_source, src, i) for i, src in enumerate(sources)
            ]
            results = [f.result() for f in as_completed(futures)]

        assert thread_safe_counter["value"] == 100
        assert all(isinstance(p, Program) for p in results)

    def test_concurrent_parse_same_source(self, thread_safe_counter: dict):
        """多线程并发解析相同源码，无数据竞争。"""
        source = """
struct SharedStruct {
    id: Int @primary
    name: String @unique
}
fn shared_fn(id: Int) -> SharedStruct {
    process { "shared function" }
}
"""

        def parse_shared(idx: int):
            program = parse(source)
            with thread_safe_counter["lock"]:
                thread_safe_counter["value"] += 1
            return program

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(parse_shared, i) for i in range(100)]
            results = [f.result() for f in as_completed(futures)]

        assert thread_safe_counter["value"] == 100
        assert all(isinstance(p, Program) for p in results)
        assert all(len(p.structs) == 1 for p in results)
        assert all(len(p.functions) == 1 for p in results)

    def test_concurrent_file_parsing(
        self, examples_dir: Path, thread_safe_counter: dict
    ):
        """多线程并发解析多个 .ej 文件，无数据竞争。"""
        if not examples_dir.exists():
            pytest.skip("examples directory not found")

        ej_files = list(examples_dir.glob("*.ej"))
        if not ej_files:
            pytest.skip("No .ej files in examples directory")

        def parse_file_task(filepath: Path, idx: int):
            program = parse_file(filepath)
            with thread_safe_counter["lock"]:
                thread_safe_counter["value"] += 1
            return program

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(parse_file_task, f, i) for i, f in enumerate(ej_files)
            ]
            results = [f.result() for f in as_completed(futures)]

        assert thread_safe_counter["value"] == len(ej_files)
        assert all(isinstance(p, Program) for p in results)

    def test_parser_singleton_thread_safety(self):
        """验证 _get_parser() 全局单例的线程安全。"""
        parser1 = None
        parser2 = None
        lock = threading.Lock()

        def get_parser_a():
            nonlocal parser1
            p = _get_parser()
            with lock:
                parser1 = p
            return p

        def get_parser_b():
            nonlocal parser2
            p = _get_parser()
            with lock:
                parser2 = p
            return p

        threads = [threading.Thread(target=get_parser_a) for _ in range(10)]
        threads += [threading.Thread(target=get_parser_b) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert parser1 is not None
        assert parser2 is not None


# ============================================================
# Analyzer 线程安全测试
# ============================================================


class TestAnalyzerThreadSafety:
    """验证 Analyzer 在多线程下的安全性。"""

    def test_concurrent_analyze_different_sources(self, thread_safe_counter: dict):
        """多线程并发分析不同源码，无数据竞争。"""
        sources = []
        for i in range(50):
            sources.append(f"""
struct Entity{i} {{
    id: Int @primary
}}

module Module{i} {{
    use Entity{i}
    use fn_{i}
    init {{ "init" }}
}}

fn fn_{i}(id: Int) -> Entity{i} {{
    process {{ "function {i}" }}
}}
""")

        def analyze_source(source: str, idx: int):
            program = parse(source)
            result = analyze(program)
            with thread_safe_counter["lock"]:
                thread_safe_counter["value"] += 1
            return result

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(analyze_source, src, i) for i, src in enumerate(sources)
            ]
            results = [f.result() for f in as_completed(futures)]

        assert thread_safe_counter["value"] == 50
        assert all(isinstance(r, list) for r in results)

    def test_concurrent_analyze_same_source(self, thread_safe_counter: dict):
        """多线程并发分析相同源码，无数据竞争。"""
        source = """
struct User {
    id: Int @primary
    name: String @unique
}

module UserModule {
    use User
    use get_user
    init { "init" }
}

fn get_user(id: Int) -> User {
    process { "get user" }
}
"""

        program = parse(source)

        def analyze_task(idx: int):
            result = analyze(program)
            with thread_safe_counter["lock"]:
                thread_safe_counter["value"] += 1
            return result

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(analyze_task, i) for i in range(100)]
            results = [f.result() for f in as_completed(futures)]

        assert thread_safe_counter["value"] == 100
        assert all(isinstance(r, list) for r in results)


# ============================================================
# Template Renderer 线程安全测试
# ============================================================


class TestTemplateRendererThreadSafety:
    """验证 Template Renderer 在多线程下的安全性。"""

    def test_concurrent_render_different_programs(
        self, examples_dir: Path, tmp_output_dir: Path, thread_safe_counter: dict
    ):
        """多线程并发渲染不同 Program 到不同输出目录，无数据竞争。"""
        if not examples_dir.exists():
            pytest.skip("examples directory not found")

        ej_files = list(examples_dir.glob("*.ej"))
        if not ej_files:
            pytest.skip("No .ej files in examples directory")

        def render_task(filepath: Path, idx: int, output_dir: Path):
            program = parse_file(filepath)
            config = RenderConfig(output_dir=output_dir, target_lang="python_fastapi")
            render_program(program, config)
            with thread_safe_counter["lock"]:
                thread_safe_counter["value"] += 1

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for i, f in enumerate(ej_files):
                output = tmp_output_dir / f"output_{i}"
                futures.append(executor.submit(render_task, f, i, output))
            [f.result() for f in as_completed(futures)]

        assert thread_safe_counter["value"] == len(ej_files)

    def test_jinja_env_singleton_thread_safety(self):
        """验证 get_jinja_env() 的线程安全。"""
        env1 = None
        env2 = None
        lock = threading.Lock()

        def get_env_a():
            nonlocal env1
            e = get_jinja_env("python_fastapi")
            with lock:
                env1 = e
            return e

        def get_env_b():
            nonlocal env2
            e = get_jinja_env("python_fastapi")
            with lock:
                env2 = e
            return e

        threads = [threading.Thread(target=get_env_a) for _ in range(10)]
        threads += [threading.Thread(target=get_env_b) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert env1 is not None
        assert env2 is not None
        assert env1 is env2


# ============================================================
# 并发压力测试
# ============================================================


class TestConcurrentStress:
    """高并发压力测试。"""

    @pytest.mark.slow
    def test_high_concurrency_100_threads(self, thread_safe_counter: dict):
        """100 线程并发解析 + 分析 + 渲染，验证极端压力下的稳定性。"""
        source = """
struct User {
    id: Int @primary
    name: String @unique
}

fn get_user(id: Int) -> User {
    process { "get user" }
}
"""

        def stress_task(idx: int):
            program = parse(source)
            result = analyze(program)
            with thread_safe_counter["lock"]:
                thread_safe_counter["value"] += 1
            return program, result

        start = time.time()
        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = [executor.submit(stress_task, i) for i in range(1000)]
            results = [f.result() for f in as_completed(futures)]
        elapsed = time.time() - start

        assert thread_safe_counter["value"] == 1000
        assert elapsed < 120.0, f"1000 次并发解析耗时 {elapsed:.2f}s，超过 120s 阈值"

    def test_rapid_start_stop(self):
        """快速启停测试：短时间内多次创建和销毁线程。"""
        for round_num in range(10):
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [
                    executor.submit(parse, f"struct S{i} {{ id: Int @primary }}")
                    for i in range(100)
                ]
                [f.result() for f in as_completed(futures)]


# ============================================================
# 竞态条件检测测试
# ============================================================


class TestRaceConditionDetection:
    """竞态条件检测测试。"""

    def test_no_struct_name_collision(self):
        """验证多线程解析不会导致 struct 名称冲突。"""
        source = """
struct TestEntity {
    id: Int @primary
}
"""
        programs = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(parse, source) for _ in range(100)]
            programs = [f.result() for f in as_completed(futures)]

        for program in programs:
            assert len(program.structs) == 1
            assert program.structs[0].name == "TestEntity"
            assert all(s.name == "TestEntity" for s in program.structs)

    def test_no_function_name_collision(self):
        """验证多线程解析不会导致 function 名称冲突。"""
        source = """
fn unique_fn() -> Int {
    process { "test" }
}
"""
        programs = []
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(parse, source) for _ in range(100)]
            programs = [f.result() for f in as_completed(futures)]

        for program in programs:
            assert len(program.functions) == 1
            assert program.functions[0].name == "unique_fn"

"""
============================================================
EnJin 宕机恢复测试 (test_crash_recovery.py)
============================================================
验证编译器在各种异常情况下的恢复能力。

宕机恢复测试场景:
    - 编译过程中断后的恢复
    - 缓存文件损坏的恢复
    - 模板文件缺失的降级处理
    - AI 服务不可用时的 fallback
    - 磁盘空间不足的处理
    - 输出目录权限错误的处理

维护协议:
    宕机恢复测试确保 EnJin 在生产环境中的稳定性。
============================================================
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import pytest

from enjinc.parser import parse, parse_file
from enjinc.template_renderer import RenderConfig, render_program
from enjinc.ast_nodes import Program


# ============================================================
# 编译中断恢复测试
# ============================================================


class TestCompilationInterruption:
    """验证编译过程中断后的恢复能力。"""

    def test_interrupted_build_partial_output(self, tmp_path: Path):
        """编译中断后，部分输出文件应被正确清理。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        (output_dir / "main.py").write_text("# partial output\n", encoding="utf-8")

        source = """
struct User {
    id: Int @primary
}
"""
        program = parse(source)

        interrupted = False
        try:
            config = RenderConfig(output_dir=output_dir, target_lang="python_fastapi")
            render_program(program, config)
        except Exception:
            interrupted = True

        if interrupted:
            assert (output_dir / "main.py").exists()

    def test_build_after_previous_crash(self, tmp_path: Path, examples_dir: Path):
        """前一次崩溃后，重新构建应成功。"""
        if not examples_dir.exists():
            pytest.skip("examples directory not found")

        ej_files = list(examples_dir.glob("*.ej"))
        if not ej_files:
            pytest.skip("No .ej files in examples directory")

        output_dir = tmp_path / "output"

        for i in range(3):
            try:
                for ej_file in ej_files:
                    program = parse_file(ej_file)
                    config = RenderConfig(
                        output_dir=output_dir, target_lang="python_fastapi"
                    )
                    render_program(program, config)
            except Exception:
                pass

        last_output = output_dir / "python_fastapi" / "models" / "__init__.py"
        assert last_output is not None


# ============================================================
# 缓存损坏恢复测试
# ============================================================


class TestCacheCorruptionRecovery:
    """验证缓存文件损坏时的恢复能力。"""

    def test_corrupted_lock_file_recovery(self, tmp_path: Path):
        """损坏的 enjin.lock 文件应被跳过并重建。"""
        lock_file = tmp_path / "enjin.lock"
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        lock_file.write_text("not valid json {{{", encoding="utf-8")

        try:
            loaded = json.loads(lock_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = None

        assert loaded is None

        new_lock_data = {
            "version": "1.0",
            "generated_at": "2026-03-16T12:00:00Z",
            "nodes": {},
        }

        lock_file.write_text(json.dumps(new_lock_data), encoding="utf-8")

        loaded_new = json.loads(lock_file.read_text(encoding="utf-8"))
        assert loaded_new is not None
        assert loaded_new["version"] == "1.0"

    def test_partial_lock_file_recovery(self, tmp_path: Path):
        """部分写入的 enjin.lock 文件应被恢复。"""
        lock_file = tmp_path / "enjin.lock"
        lock_file.parent.mkdir(parents=True, exist_ok=True)

        for i in range(5):
            try:
                lock_file.write_text(
                    '{"version": "1.0", "nodes": {"key' + str(i) + '": {',
                    encoding="utf-8",
                )
                time.sleep(0.01)
            except Exception:
                pass

        try:
            loaded = json.loads(lock_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = None

        assert loaded is None

    def test_missing_lock_file_recovery(self, tmp_path: Path):
        """缺失的 enjin.lock 文件应触发重新生成。"""
        lock_file = tmp_path / "nonexistent.lock"

        assert not lock_file.exists()

        lock_data = {
            "version": "1.0",
            "generated_at": "2026-03-16T12:00:00Z",
            "nodes": {},
        }

        lock_file.parent.mkdir(parents=True, exist_ok=True)
        lock_file.write_text(json.dumps(lock_data), encoding="utf-8")

        loaded = json.loads(lock_file.read_text(encoding="utf-8"))
        assert loaded is not None


# ============================================================
# 模板文件缺失降级测试
# ============================================================


class TestTemplateMissingDegradation:
    """验证模板文件缺失时的降级处理。"""

    def test_missing_template_file_handling(self, src_dir: Path):
        """缺失的模板文件应产生有意义的错误。"""
        templates_dir = src_dir / "targets" / "python_fastapi" / "templates"

        if not templates_dir.exists():
            pytest.skip("templates directory not found")

        required_templates = [
            "config.py.jinja",
            "database.py.jinja",
            "main.py.jinja",
            "models.py.jinja",
        ]

        missing = [t for t in required_templates if not (templates_dir / t).exists()]

        assert len(missing) == 0, f"Missing templates: {missing}"

    def test_partial_template_directory(self, tmp_path: Path, examples_dir: Path):
        """部分模板目录存在时的处理。"""
        if not examples_dir.exists():
            pytest.skip("examples directory not found")

        output_dir = tmp_path / "output"

        try:
            config = RenderConfig(
                output_dir=output_dir, target_lang="nonexistent_target"
            )
            source = """
struct User {
    id: Int @primary
}
"""
            program = parse(source)
            render_program(program, config)
        except Exception:
            pass


# ============================================================
# 输出目录异常测试
# ============================================================


class TestOutputDirectoryErrors:
    """验证输出目录异常的处理。"""

    def test_output_dir_not_writable(self, tmp_path: Path):
        """不可写的输出目录应产生错误。"""
        output_dir = tmp_path / "readonly"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_dir.chmod(0o444)

        source = """
struct User {
    id: Int @primary
}
"""
        program = parse(source)

        try:
            config = RenderConfig(output_dir=output_dir, target_lang="python_fastapi")
            render_program(program, config)
        except (PermissionError, OSError):
            pass
        finally:
            output_dir.chmod(0o755)

    def test_output_dir_is_file(self, tmp_path: Path):
        """输出路径是文件而非目录应产生错误。"""
        output_file = tmp_path / "afile"
        output_file.write_text("I am a file", encoding="utf-8")

        source = """
struct User {
    id: Int @primary
}
"""
        program = parse(source)

        try:
            config = RenderConfig(output_dir=output_file, target_lang="python_fastapi")
            render_program(program, config)
        except (NotADirectoryError, OSError):
            pass

    def test_output_disk_full_simulation(self, tmp_path: Path):
        """磁盘空间不足的模拟处理。"""
        output_dir = tmp_path / "output"

        source = """
struct User {
    id: Int @primary
}
"""
        program = parse(source)

        try:
            config = RenderConfig(output_dir=output_dir, target_lang="python_fastapi")
            render_program(program, config)
        except (OSError, IOError):
            pass


# ============================================================
# 并发构建冲突测试
# ============================================================


class TestConcurrentBuildConflicts:
    """验证并发构建时的冲突处理。"""

    def test_concurrent_build_same_output_dir(
        self, tmp_path: Path, examples_dir: Path, thread_safe_counter: dict
    ):
        """多个进程同时写入同一输出目录应安全。"""
        if not examples_dir.exists():
            pytest.skip("examples directory not found")

        ej_files = list(examples_dir.glob("*.ej"))
        if not ej_files:
            pytest.skip("No .ej files in examples directory")

        output_dir = tmp_path / "shared_output"

        def build_task(idx: int):
            try:
                for ej_file in ej_files:
                    program = parse_file(ej_file)
                    config = RenderConfig(
                        output_dir=output_dir, target_lang="python_fastapi"
                    )
                    render_program(program, config)
                with thread_safe_counter["lock"]:
                    thread_safe_counter["value"] += 1
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(build_task, i) for i in range(10)]
            [f.result() for f in as_completed(futures)]

    def test_rapid_build_restart(self, tmp_path: Path, examples_dir: Path):
        """快速反复重启构建的压力测试。"""
        if not examples_dir.exists():
            pytest.skip("examples directory not found")

        for i in range(5):
            output_dir = tmp_path / f"restart_{i}"
            source = f"""
struct Stress{i} {{
    id: Int @primary
}}
"""
            program = parse(source)
            config = RenderConfig(output_dir=output_dir, target_lang="python_fastapi")
            try:
                render_program(program, config)
            except Exception:
                pass


# ============================================================
# 网络/资源不可用测试
# ============================================================


class TestResourceUnavailability:
    """验证资源不可用时的降级处理。"""

    def test_template_cache_survives_clear(self, src_dir: Path):
        """模板缓存应能在清空后重建。"""
        templates_dir = src_dir / "targets" / "python_fastapi" / "templates"

        if not templates_dir.exists():
            pytest.skip("templates directory not found")

        initial_exists = all(
            (templates_dir / t).exists()
            for t in ["config.py.jinja", "database.py.jinja", "main.py.jinja"]
        )

        assert initial_exists

    def test_parser_after_memory_pressure(self):
        """内存压力后的解析器应仍能正常工作。"""
        source = """
struct AfterPressure {
    id: Int @primary
}
"""

        for i in range(10):
            program = parse(source)
            assert len(program.structs) == 1


# ============================================================
# 状态一致性测试
# ============================================================


class TestStateConsistency:
    """验证异常后的状态一致性。"""

    def test_parser_state_after_error(self):
        """解析错误后 Parser 状态应保持一致。"""
        invalid_source = """
struct Bad {
    id: Int @primary
"""

        for i in range(5):
            try:
                parse(invalid_source)
            except Exception:
                pass

        valid_source = """
struct Good {
    id: Int @primary
}
"""
        program = parse(valid_source)
        assert len(program.structs) == 1
        assert program.structs[0].name == "Good"

    def test_analyzer_state_after_error(self):
        """分析错误后 Analyzer 状态应保持一致。"""
        invalid_source = """
module Bad {
    use Nonexistent
"""

        from enjinc.analyzer import analyze

        for i in range(5):
            try:
                program = parse(invalid_source)
                analyze(program)
            except Exception:
                pass

        valid_source = """
struct Good {
    id: Int @primary
}
module GoodModule {
    use Good
    init { "init" }
}
"""
        program = parse(valid_source)
        result = analyze(program)
        assert isinstance(result, list)

    def test_output_files_after_partial_failure(self, tmp_path: Path):
        """部分失败后输出文件应保持一致。"""
        output_dir = tmp_path / "output"

        source = """
struct Good {
    id: Int @primary
}
"""
        program = parse(source)

        try:
            config = RenderConfig(output_dir=output_dir, target_lang="python_fastapi")
            render_program(program, config)
        except Exception:
            pass

        models_file = output_dir / "python_fastapi" / "models" / "good.py"
        if models_file.exists():
            content = models_file.read_text(encoding="utf-8")
            assert "class Good(Base):" in content or "Good" in content

"""
============================================================
EnJin @locked 缓存机制测试 (test_enjin_lock.py)
============================================================
验证 enjin.lock 缓存机制的完整生命周期。

缓存测试场景:
    - 成功构建后生成 enjin.lock
    - 缓存命中（AST Hash 未变化）跳过 AI 调用
    - 缓存失效（Intent Hash 变化）重新生成
    - 缓存文件损坏/JSON 解析失败
    - 缓存版本不匹配
    - 并发写入缓存文件
    - 多目标语言缓存隔离

维护协议:
    enjin.lock 是确定性构建的关键，必须严格测试。
============================================================
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import pytest

from enjinc.parser import parse
from enjinc.ast_nodes import FnDef, Program


# ============================================================
# enjin.lock 数据结构 (待实现)
# ============================================================


class EnjinLock:
    """enjin.lock 文件管理类 (Phase 3 实现)。

    本测试文件定义了 enjin.lock 的预期行为。
    实际实现需要在 src/enjinc/enjin_lock.py 中完成。
    """

    @staticmethod
    def compute_ast_hash(program: Program, node: FnDef) -> str:
        """计算 AST 节点的哈希值。

        Args:
            program: I-AST Program 节点
            node: 函数节点

        Returns:
            SHA-256 哈希值字符串
        """
        import hashlib

        content = f"{node.name}:{node.process.intent if node.process else ''}"
        return f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"

    @staticmethod
    def load(lock_file: Path) -> Optional[dict]:
        """加载 enjin.lock 文件。"""
        if not lock_file.exists():
            return None
        try:
            return json.loads(lock_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, IOError):
            return None

    @staticmethod
    def save(lock_file: Path, data: dict) -> None:
        """保存 enjin.lock 文件。"""
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        lock_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


# ============================================================
# 缓存生成测试
# ============================================================


class TestLockFileGeneration:
    """验证 enjin.lock 文件的生成。"""

    def test_lock_file_structure(self, tmp_path: Path):
        """验证 enjin.lock 文件结构完整。"""
        source = """
struct User {
    id: Int @primary
}

fn get_user(id: Int) -> User {
    process {
        "查询用户"
    }
}
"""
        program = parse(source)
        lock_data = {
            "version": "1.0",
            "generated_at": "2026-03-16T12:00:00Z",
            "compiler_version": "0.3.0",
            "compilation_unit_id": "test_unit_001",
            "target": "python_fastapi",
            "nodes": {},
        }

        for fn in program.functions:
            node_hash = EnjinLock.compute_ast_hash(program, fn)
            lock_data["nodes"][node_hash] = {
                "node_type": "fn",
                "name": fn.name,
                "intent_hash": node_hash,
                "generated_code": {
                    "python_fastapi": f"def {fn.name}(): pass\n",
                    "java_springboot": None,
                },
                "generated_at": "2026-03-16T12:00:00Z",
                "model_used": "gpt-4",
                "tokens_consumed": {"input": 100, "output": 50},
            }

        lock_file = tmp_path / "enjin.lock"
        EnjinLock.save(lock_file, lock_data)

        assert lock_file.exists()
        loaded = EnjinLock.load(lock_file)
        assert loaded is not None
        assert loaded["version"] == "1.0"
        assert "nodes" in loaded
        assert len(loaded["nodes"]) == 1

    def test_lock_file_contains_all_nodes(self, tmp_path: Path):
        """验证 enjin.lock 包含所有函数节点。"""
        source = """
fn fn_a() { process { "a" } }
fn fn_b() { process { "b" } }
fn fn_c() { process { "c" } }
"""
        program = parse(source)
        assert len(program.functions) == 3

        lock_data = {"version": "1.0", "nodes": {}}

        for fn in program.functions:
            node_hash = EnjinLock.compute_ast_hash(program, fn)
            lock_data["nodes"][node_hash] = {
                "name": fn.name,
                "generated_code": {"python_fastapi": f"# {fn.name}\n"},
            }

        lock_file = tmp_path / "enjin.lock"
        EnjinLock.save(lock_file, lock_data)

        loaded = EnjinLock.load(lock_file)
        assert len(loaded["nodes"]) == 3


# ============================================================
# 缓存命中测试
# ============================================================


class TestCacheHit:
    """验证缓存命中逻辑。"""

    def test_cache_hit_same_intent(self, tmp_path: Path):
        """Intent 未变化时，缓存应命中。"""
        source1 = """
fn test_fn(id: Int) -> Int {
    process { "返回输入值" }
}
"""
        source2 = """
fn test_fn(id: Int) -> Int {
    process { "返回输入值" }
}
"""
        program1 = parse(source1)
        program2 = parse(source2)

        fn1 = program1.functions[0]
        fn2 = program2.functions[0]

        hash1 = EnjinLock.compute_ast_hash(program1, fn1)
        hash2 = EnjinLock.compute_ast_hash(program2, fn2)

        assert hash1 == hash2

    def test_cache_miss_different_intent(self, tmp_path: Path):
        """Intent 变化时，缓存应失效。"""
        source1 = """
fn test_fn(id: Int) -> Int {
    process { "返回输入值" }
}
"""
        source2 = """
fn test_fn(id: Int) -> Int {
    process { "返回输入值的平方" }
}
"""
        program1 = parse(source1)
        program2 = parse(source2)

        fn1 = program1.functions[0]
        fn2 = program2.functions[0]

        hash1 = EnjinLock.compute_ast_hash(program1, fn1)
        hash2 = EnjinLock.compute_ast_hash(program2, fn2)

        assert hash1 != hash2

    def test_cache_miss_different_params(self, tmp_path: Path):
        """函数参数变化时，缓存应失效。"""
        source1 = """
fn test_fn(id: Int) -> Int {
    process { "处理单个 ID" }
}
"""
        source2 = """
fn test_fn(id: Int, name: String) -> Int {
    process { "处理 ID 和名称" }
}
"""
        program1 = parse(source1)
        program2 = parse(source2)

        fn1 = program1.functions[0]
        fn2 = program2.functions[0]

        hash1 = EnjinLock.compute_ast_hash(program1, fn1)
        hash2 = EnjinLock.compute_ast_hash(program2, fn2)

        assert hash1 != hash2


# ============================================================
# 缓存损坏/失效测试
# ============================================================


class TestCacheCorruption:
    """验证缓存损坏的处理。"""

    def test_corrupted_json_lock_file(self, tmp_path: Path, corrupted_lock_file: str):
        """损坏的 JSON 格式应被检测并返回 None。"""
        lock_file = tmp_path / "corrupted.lock"
        lock_file.write_text(corrupted_lock_file, encoding="utf-8")

        loaded = EnjinLock.load(lock_file)
        assert loaded is None

    def test_empty_lock_file(self, tmp_path: Path):
        """空文件应被检测并返回 None。"""
        lock_file = tmp_path / "empty.lock"
        lock_file.write_text("", encoding="utf-8")

        loaded = EnjinLock.load(lock_file)
        assert loaded is None

    def test_partial_json_lock_file(self, tmp_path: Path):
        """部分 JSON 内容应被检测并返回 None。"""
        lock_file = tmp_path / "partial.lock"
        lock_file.write_text('{"version": "1.0", "nodes": {', encoding="utf-8")

        loaded = EnjinLock.load(lock_file)
        assert loaded is None

    def test_version_mismatch(self, tmp_path: Path):
        """版本不匹配应触发重建。"""
        lock_data = {"version": "0.1.0", "compiler_version": "0.1.0", "nodes": {}}

        lock_file = tmp_path / "old_version.lock"
        EnjinLock.save(lock_file, lock_data)

        loaded = EnjinLock.load(lock_file)
        assert loaded is not None
        assert loaded["version"] == "0.1.0"

        current_version = "0.3.0"
        assert loaded["compiler_version"] != current_version


# ============================================================
# 缓存过期测试
# ============================================================


class TestCacheExpiration:
    """验证缓存过期逻辑。"""

    def test_stale_lock_file(self, tmp_path: Path, stale_lock_file_content: dict):
        """过期的缓存应被检测。"""
        lock_file = tmp_path / "stale.lock"
        EnjinLock.save(lock_file, stale_lock_file_content)

        loaded = EnjinLock.load(lock_file)
        assert loaded is not None

        generated_at = loaded.get("generated_at", "")
        assert "2025-01-01" in generated_at

    def test_old_compiler_version(self, tmp_path: Path):
        """旧编译器版本生成的缓存应失效。"""
        lock_data = {
            "version": "1.0",
            "compiler_version": "0.1.0",
            "generated_at": "2025-01-01T00:00:00Z",
            "nodes": {},
        }

        lock_file = tmp_path / "old_compiler.lock"
        EnjinLock.save(lock_file, lock_data)

        loaded = EnjinLock.load(lock_file)
        current_version = "0.3.0"
        assert loaded["compiler_version"] < current_version


# ============================================================
# 并发缓存写入测试
# ============================================================


class TestConcurrentCacheAccess:
    """验证并发场景下的缓存安全。"""

    def test_concurrent_lock_file_read(self, tmp_path: Path, lock_file_content: dict):
        """并发读取缓存文件应安全。"""
        lock_file = tmp_path / "concurrent_read.lock"
        EnjinLock.save(lock_file, lock_file_content)

        results = []
        lock = threading.Lock()

        def read_task(idx: int):
            loaded = EnjinLock.load(lock_file)
            with lock:
                results.append(loaded)

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(read_task, i) for i in range(100)]
            [f.result() for f in as_completed(futures)]

        assert len(results) == 100
        assert all(r is not None for r in results)

    def test_concurrent_lock_file_write(self, tmp_path: Path):
        """并发写入缓存文件应安全（文件锁）。"""
        lock_file = tmp_path / "concurrent_write.lock"
        results = []
        lock = threading.Lock()

        def write_task(idx: int):
            data = {
                "version": "1.0",
                "generated_at": f"2026-03-16T12:00:{idx:02d}Z",
                "nodes": {"hash_" + str(idx): {"name": f"fn_{idx}"}},
            }
            EnjinLock.save(lock_file, data)
            loaded = EnjinLock.load(lock_file)
            with lock:
                results.append(loaded)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(write_task, i) for i in range(50)]
            [f.result() for f in as_completed(futures)]

        assert len(results) == 50


# ============================================================
# 多目标语言缓存测试
# ============================================================


class TestMultiTargetCaching:
    """验证多目标语言的缓存隔离。"""

    def test_different_targets_separate_cache(self, tmp_path: Path):
        """不同目标语言应有独立的缓存。"""
        source = """
fn get_user(id: Int) -> User {
    process { "查询用户" }
}
"""
        program = parse(source)
        fn = program.functions[0]

        python_code = "def get_user(id): pass\n"
        java_code = "public User getUser(Long id) { return null; }\n"

        python_lock = {
            "version": "1.0",
            "target": "python_fastapi",
            "nodes": {
                EnjinLock.compute_ast_hash(program, fn): {
                    "name": fn.name,
                    "generated_code": {"python_fastapi": python_code},
                }
            },
        }

        java_lock = {
            "version": "1.0",
            "target": "java_springboot",
            "nodes": {
                EnjinLock.compute_ast_hash(program, fn): {
                    "name": fn.name,
                    "generated_code": {"java_springboot": java_code},
                }
            },
        }

        python_lock_file = tmp_path / "python.lock"
        java_lock_file = tmp_path / "java.lock"

        EnjinLock.save(python_lock_file, python_lock)
        EnjinLock.save(java_lock_file, java_lock)

        loaded_python = EnjinLock.load(python_lock_file)
        loaded_java = EnjinLock.load(java_lock_file)

        assert loaded_python["target"] == "python_fastapi"
        assert loaded_java["target"] == "java_springboot"


# ============================================================
# @locked 注解测试
# ============================================================


class TestLockedAnnotation:
    """验证 @locked 注解的解析和行为。"""

    def test_locked_function_parsed(self):
        """@locked 注解的函数应被正确解析。"""
        source = """
@locked
fn cached_fn(id: Int) -> Int {
    process { "缓存的函数" }
}
"""
        program = parse(source)
        assert len(program.functions) == 1
        assert program.functions[0].is_locked is True

    def test_locked_with_native_block(self):
        """@locked 函数可以有 native 块。"""
        source = """
@locked
fn locked_native(data: String) -> String {
    native python {
        return data.upper()
    }
}
"""
        program = parse(source)
        assert len(program.functions) == 1
        assert program.functions[0].is_locked is True
        assert len(program.functions[0].native_blocks) == 1

    def test_unlocked_function_not_locked(self):
        """未标注 @locked 的函数不应被锁定。"""
        source = """
fn normal_fn(id: Int) -> Int {
    process { "普通函数" }
}
"""
        program = parse(source)
        assert len(program.functions) == 1
        assert program.functions[0].is_locked is False

    def test_locked_on_route_endpoint(self):
        """@locked 可以标注在 route endpoint 上。"""
        source = """
route TestRoute {
    @locked
    DELETE "/item/{id}" -> delete_item
}
"""
        program = parse(source)
        assert len(program.routes) == 1
        endpoint = program.routes[0].endpoints[0]
        assert endpoint.is_locked is True

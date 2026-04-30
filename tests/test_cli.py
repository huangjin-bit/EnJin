"""
============================================================
EnJin CLI 单元测试 (test_cli.py)
============================================================
验证 cli.py 的 build/analyze 行为，重点覆盖：
1) build 默认执行静态分析并在违规时阻断
2) build 可处理目录级编译单元（合并多个 .ej）
3) --skip-analysis 可显式跳过静态分析
4) analyze/--strict 的退出码与输出行为
============================================================
"""

from __future__ import annotations

from pathlib import Path

from enjinc.cli import main


def _write(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_build_blocks_on_analysis_error(tmp_path: Path, capsys):
    """默认 build 应在静态分析失败时返回 2 并阻断渲染。"""
    source = tmp_path / "invalid.ej"
    out_dir = tmp_path / "out"

    _write(
        source,
        """
fn register_user(username: String, email: String, password: String) -> User {
    process {
        "创建用户"
    }
}

module UserManager {
    use register_user
    export register = register_user
}

route UserService {
    use UserManager
    POST "/register" -> register_user
}
""",
    )

    exit_code = main(["build", str(source), "--out", str(out_dir)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "ROUTE_BINDS_RAW_FN" in captured.err
    assert not (out_dir / "python_fastapi").exists()


def test_build_directory_compilation_unit_success(tmp_path: Path):
    """build 支持目录输入：合并多个 .ej 后通过分析并渲染产物。"""
    unit_dir = tmp_path / "trade-core"
    unit_dir.mkdir(parents=True, exist_ok=True)

    _write(
        unit_dir / "application.ej",
        """
application {
    name: "trade-core"
    version: "1.0.0"
    target: "python_fastapi"
}
""",
    )

    _write(
        unit_dir / "user.ej",
        """
struct User {
    id: Int
}

fn register_user(username: String, email: String, password: String) -> User {
    process {
        "创建用户"
    }
}

module UserManager {
    use User
    use register_user
    export register = register_user
}

@prefix("/api/v1/users")
route UserService {
    use UserManager
    POST "/register" -> register
}
""",
    )

    out_dir = tmp_path / "output"
    exit_code = main(["build", str(unit_dir), "--out", str(out_dir)])

    assert exit_code == 0
    artifact = out_dir / "python_fastapi"
    assert (artifact / "app" / "core" / "config.py").exists()
    assert (artifact / "app" / "core" / "database.py").exists()
    assert (artifact / "app" / "main.py").exists()
    assert (artifact / "app" / "models" / "__init__.py").exists()
    assert (artifact / "app" / "services" / "__init__.py").exists()
    assert (artifact / "app" / "modules" / "__init__.py").exists()
    assert (artifact / "app" / "api" / "v1" / "userservice.py").exists()


def test_build_skip_analysis_allows_rendering(tmp_path: Path):
    """当显式 --skip-analysis 时，build 可跳过静态校验。"""
    source = tmp_path / "invalid_skip.ej"
    out_dir = tmp_path / "out_skip"

    _write(
        source,
        """
fn register_user(username: String, email: String, password: String) -> User {
    process {
        "创建用户"
    }
}

module UserManager {
    use register_user
    export register = register_user
}

route UserService {
    use UserManager
    POST "/register" -> register_user
}
""",
    )

    exit_code = main(["build", str(source), "--out", str(out_dir), "--skip-analysis"])

    assert exit_code == 0
    assert (out_dir / "python_fastapi" / "app" / "api" / "v1" / "userservice.py").exists()


def test_analyze_strict_returns_non_zero_on_issues(tmp_path: Path, capsys):
    """analyze --strict 在发现问题时应返回非 0。"""
    source = tmp_path / "invalid_analyze.ej"

    _write(
        source,
        """
fn register_user(username: String, email: String, password: String) -> User {
    process {
        "创建用户"
    }
}

module UserManager {
    use register_user
    export register = register_user
}

route UserService {
    use UserManager
    POST "/register" -> register_user
}
""",
    )

    exit_code = main(["analyze", str(source), "--strict"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "ROUTE_BINDS_RAW_FN" in captured.out


def test_analyze_non_strict_returns_zero_on_issues(tmp_path: Path):
    """analyze 默认非 strict，即使有问题也返回 0（仅报告）。"""
    source = tmp_path / "invalid_analyze_non_strict.ej"

    _write(
        source,
        """
fn register_user(username: String, email: String, password: String) -> User {
    process {
        "创建用户"
    }
}

module UserManager {
    use register_user
    export register = register_user
}

route UserService {
    use UserManager
    POST "/register" -> register_user
}
""",
    )

    exit_code = main(["analyze", str(source)])
    assert exit_code == 0


def test_test_command_no_expect(tmp_path: Path, capsys):
    """test 命令在没有 expect 时应正常返回，不生成文件。"""
    source = tmp_path / "no_expect.ej"
    out_dir = tmp_path / "out"

    _write(
        source,
        """
struct User { id: Int @primary }

fn get_user(id: Int) -> User {
    process { "get user" }
}
""",
    )

    exit_code = main(["test", str(source), "--out", str(out_dir)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "no expect" in captured.out


def test_verify_command_no_lock(tmp_path: Path, capsys):
    """verify 命令在 lock 文件不存在时应返回 1。"""
    source = tmp_path / "simple.ej"
    lock_path = tmp_path / "nonexistent" / "enjin.lock"

    _write(
        source,
        """
struct User { id: Int @primary }

fn get_user(id: Int) -> User {
    process { "get user" }
}
""",
    )

    exit_code = main(["verify", str(source), "--lock", str(lock_path)])
    assert exit_code == 1


def test_migrate_command_no_changes(tmp_path: Path, capsys):
    """migrate 命令在两个版本相同时应报告无变更。"""
    old_source = tmp_path / "old.ej"
    new_source = tmp_path / "new.ej"
    out_dir = tmp_path / "migrations"

    content = """
struct User {
    id: Int @primary
    name: String
}
"""
    _write(old_source, content)
    _write(new_source, content)

    exit_code = main(["migrate", str(old_source), str(new_source), "--out", str(out_dir)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "no struct changes" in captured.out

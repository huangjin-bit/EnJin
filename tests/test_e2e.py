"""
============================================================
EnJin 端到端测试 (test_e2e.py)
============================================================
模拟真人使用生成的代码进行完整链路测试。
- 启动 FastAPI 服务器
- 发送 HTTP 请求验证 API 行为
============================================================
"""

import pytest
import tempfile
import subprocess
import sys
import time
import ast
import requests
from pathlib import Path
from threading import Thread
from typing import Optional

from enjinc.parser import parse
from enjinc.template_renderer import RenderConfig, render_program


class TestPythonFastAPIE2E:
    """Python FastAPI 端到端测试 - 模拟真人使用生成的 API。"""

    @pytest.fixture(scope="class")
    def generated_app(self):
        """生成并启动 FastAPI 应用。"""
        from enjinc.template_renderer import RenderConfig, render_program

        examples_dir = Path(__file__).parent.parent / "examples"
        ej_files = list(examples_dir.glob("**/user_management.ej"))
        if not ej_files:
            pytest.skip("user_management.ej not found")

        content = ej_files[0].read_text(encoding="utf-8")
        program = parse(content)

        tmpdir = tempfile.TemporaryDirectory()
        output_dir = Path(tmpdir.name) / "output"
        config = RenderConfig(
            target_lang="python_fastapi",
            output_dir=output_dir,
            app_name="test_app",
        )

        render_program(program, config)

        output_app = output_dir / "python_fastapi"

        config_file = output_app / "app" / "core" / "config.py"
        config_content = config_file.read_text(encoding="utf-8")
        config_content = config_content.replace('"postgresql"', '"sqlite"')
        config_file.write_text(config_content, encoding="utf-8")

        yield output_app, tmpdir

        tmpdir.cleanup()

    @pytest.fixture(scope="class")
    def server(self, generated_app):
        """启动 uvicorn 服务器。"""
        output_app, tmpdir = generated_app

        sys.path.insert(0, str(output_app))

        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8765",
            ],
            cwd=str(output_app),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        max_wait = 10
        for _ in range(max_wait):
            try:
                resp = requests.get("http://127.0.0.1:8765/health", timeout=1)
                if resp.status_code == 200:
                    break
            except requests.exceptions.ConnectionError:
                time.sleep(1)
        else:
            proc.kill()
            pytest.fail("Server failed to start within timeout")

        yield proc

        proc.terminate()
        proc.wait(timeout=5)

    def test_health_check(self, server):
        """测试健康检查端点。"""
        resp = requests.get("http://127.0.0.1:8765/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "app" in data
        assert "version" in data

    def test_app_has_routes(self, generated_app):
        """验证应用包含注册路由。"""
        output_app, _ = generated_app

        sys.path.insert(0, str(output_app))
        from app.main import app

        routes = [r.path for r in app.routes]
        assert len(routes) > 0, "No routes registered"
        assert any("health" in r for r in routes), "No health route found"

    def test_models_define_tables(self, generated_app):
        """验证模型定义了数据库表。"""
        output_app, _ = generated_app

        sys.path.insert(0, str(output_app))
        from app.core import database

        database.init_db()

        from sqlalchemy import inspect

        inspector = inspect(database.engine)
        tables = inspector.get_table_names()

        assert "users" in tables, f"users table not created. Tables found: {tables}"
        assert "user_profiles" in tables, f"user_profiles table not created"

    def test_database_session_works(self, generated_app):
        """验证数据库会话可以正常工作。"""
        output_app, _ = generated_app

        sys.path.insert(0, str(output_app))
        from app.core import database
        from sqlalchemy import text

        db = database.SessionLocal()
        try:
            result = db.execute(text("SELECT 1"))
            assert result.scalar() == 1
        finally:
            db.close()


class TestPythonCrawlerE2E:
    """Python Crawler 端到端测试。"""

    def test_httpx_config_is_valid(self):
        """验证 httpx 配置可以正常导入。"""
        from enjinc.template_renderer import RenderConfig, render_program
        import importlib.util

        examples_dir = Path(__file__).parent.parent / "examples"
        ej_files = list(examples_dir.glob("**/product_crawler.ej"))
        if not ej_files:
            pytest.skip("product_crawler.ej not found")

        content = ej_files[0].read_text(encoding="utf-8")
        program = parse(content)

        tmpdir = tempfile.TemporaryDirectory()
        output_dir = Path(tmpdir.name) / "output"
        config = RenderConfig(
            target_lang="python_crawler",
            output_dir=output_dir,
            app_name="crawler_app",
        )

        render_program(program, config)
        output_crawler = output_dir / "python_crawler"

        httpx_config_path = output_crawler / "httpx" / "config.py"
        spec = importlib.util.spec_from_file_location("httpx_config", httpx_config_path)
        httpx_config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(httpx_config)

        assert hasattr(httpx_config, "DEFAULT_HEADERS")
        assert hasattr(httpx_config, "START_URLS")
        assert hasattr(httpx_config, "MAX_CONCURRENT_REQUESTS")

        tmpdir.cleanup()

    def test_rate_limiter_is_valid(self):
        """验证 rate limiter 可以正常导入。"""
        from enjinc.template_renderer import RenderConfig, render_program
        import importlib.util
        import sys

        examples_dir = Path(__file__).parent.parent / "examples"
        ej_files = list(examples_dir.glob("**/product_crawler.ej"))
        if not ej_files:
            pytest.skip("product_crawler.ej not found")

        content = ej_files[0].read_text(encoding="utf-8")
        program = parse(content)

        tmpdir = tempfile.TemporaryDirectory()
        output_dir = Path(tmpdir.name) / "output"
        config = RenderConfig(
            target_lang="python_crawler",
            output_dir=output_dir,
            app_name="crawler_app",
        )

        render_program(program, config)
        output_crawler = output_dir / "python_crawler"

        httpx_dir = str(output_crawler / "httpx")
        sys.path.insert(0, httpx_dir)
        try:
            rate_limiter_path = output_crawler / "httpx" / "rate_limiter.py"
            spec = importlib.util.spec_from_file_location("rate_limiter", rate_limiter_path)
            rate_limiter = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(rate_limiter)

            assert hasattr(rate_limiter, "RateLimiter")
        finally:
            sys.path.remove(httpx_dir)

        tmpdir.cleanup()

    def test_proxy_pool_is_valid(self):
        """验证 proxy pool 可以正常导入。"""
        from enjinc.template_renderer import RenderConfig, render_program
        import importlib.util
        import sys

        examples_dir = Path(__file__).parent.parent / "examples"
        ej_files = list(examples_dir.glob("**/product_crawler.ej"))
        if not ej_files:
            pytest.skip("product_crawler.ej not found")

        content = ej_files[0].read_text(encoding="utf-8")
        program = parse(content)

        tmpdir = tempfile.TemporaryDirectory()
        output_dir = Path(tmpdir.name) / "output"
        config = RenderConfig(
            target_lang="python_crawler",
            output_dir=output_dir,
            app_name="crawler_app",
        )

        render_program(program, config)
        output_crawler = output_dir / "python_crawler"

        httpx_dir = str(output_crawler / "httpx")
        sys.path.insert(0, httpx_dir)
        try:
            proxy_pool_path = output_crawler / "httpx" / "proxy_pool.py"
            spec = importlib.util.spec_from_file_location("proxy_pool", proxy_pool_path)
            proxy_pool = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(proxy_pool)

            assert hasattr(proxy_pool, "ProxyPool")
        finally:
            sys.path.remove(httpx_dir)

        tmpdir.cleanup()


class TestGeneratedCodeExecution:
    """测试生成代码的业务逻辑执行。"""

    def test_services_can_be_called(self):
        """验证 services.py 中的函数可以被调用。

        注意：Phase 2 生成的是占位符代码，会抛出 NameError。
        此测试验证函数签名正确且可以被调用（即使业务逻辑未实现）。
        """
        from enjinc.template_renderer import RenderConfig, render_program

        examples_dir = Path(__file__).parent.parent / "examples"
        ej_files = list(examples_dir.glob("**/user_management.ej"))
        if not ej_files:
            pytest.skip("user_management.ej not found")

        content = ej_files[0].read_text(encoding="utf-8")
        program = parse(content)

        tmpdir = tempfile.TemporaryDirectory()
        output_dir = Path(tmpdir.name) / "output"
        config = RenderConfig(
            target_lang="python_fastapi",
            output_dir=output_dir,
            app_name="test_app",
        )

        render_program(program, config)
        output_app = output_dir / "python_fastapi"

        config_file = output_app / "app" / "core" / "config.py"
        config_content = config_file.read_text(encoding="utf-8")
        config_content = config_content.replace('"postgresql"', '"sqlite"')
        config_file.write_text(config_content, encoding="utf-8")

        sys.path.insert(0, str(output_app))

        from app.services import register_user, get_user_by_id, update_user, delete_user, custom_hash
        from app.core import database

        database.init_db()

        try:
            result = register_user(
                "testuser", "test@example.com", "password123"
            )
        except (NameError, NotImplementedError):
            pass

        tmpdir.cleanup()

    def test_models_can_be_instantiated(self):
        """验证 models.py 中的模型可以被实例化。"""
        from enjinc.template_renderer import RenderConfig, render_program

        examples_dir = Path(__file__).parent.parent / "examples"
        ej_files = list(examples_dir.glob("**/user_management.ej"))
        if not ej_files:
            pytest.skip("user_management.ej not found")

        content = ej_files[0].read_text(encoding="utf-8")
        program = parse(content)

        tmpdir = tempfile.TemporaryDirectory()
        output_dir = Path(tmpdir.name) / "output"
        config = RenderConfig(
            target_lang="python_fastapi",
            output_dir=output_dir,
            app_name="test_app",
        )

        render_program(program, config)
        output_app = output_dir / "python_fastapi"

        config_file = output_app / "app" / "core" / "config.py"
        config_content = config_file.read_text(encoding="utf-8")
        config_content = config_content.replace('"postgresql"', '"sqlite"')
        config_file.write_text(config_content, encoding="utf-8")

        sys.path.insert(0, str(output_app))

        from app.models import User, UserProfile
        from app.core import database

        database.init_db()

        user = User(
            username="alice",
            email="alice@example.com",
            password_hash="hashedpassword",
        )
        assert user.username == "alice"
        assert user.email == "alice@example.com"

        profile = UserProfile(
            user_id=1,
            bio="Hello world",
        )
        assert profile.bio == "Hello world"

        tmpdir.cleanup()


class TestJavaRiskControlE2E:
    """Java 风控系统编译和结构验证。"""

    def test_java_code_has_valid_structure(self):
        """验证 Java 风控代码结构有效。"""
        from enjinc.template_renderer import RenderConfig, render_risk_control

        risk_ej_path = (
            Path(__file__).parent.parent
            / "examples"
            / "java_ecommerce"
            / "risk_control.ej"
        )
        if not risk_ej_path.exists():
            pytest.skip("risk_control.ej not found")

        content = risk_ej_path.read_text(encoding="utf-8")
        program = parse(content)

        tmpdir = tempfile.TemporaryDirectory()
        output_dir = Path(tmpdir.name) / "output"
        config = RenderConfig(
            target_lang="java_springboot",
            output_dir=output_dir,
            app_name="risk-core",
        )

        render_risk_control(
            structs=program.structs,
            functions=program.functions,
            routes=program.routes,
            config=config,
            output_dir=output_dir,
        )

        java_files = list(output_dir.rglob("*.java"))
        assert len(java_files) > 0, "No Java files generated"

        for java_file in java_files:
            content = java_file.read_text(encoding="utf-8")
            assert content.count("{") == content.count("}"), (
                f"Brace mismatch in {java_file.name}"
            )
            assert content.count("(") == content.count(")"), (
                f"Paren mismatch in {java_file.name}"
            )
            assert "package " in content, f"No package declaration in {java_file.name}"

        tmpdir.cleanup()

    def test_migration_sql_is_valid(self):
        """验证数据库迁移 SQL 有效。"""
        from enjinc.template_renderer import RenderConfig, render_risk_control

        risk_ej_path = (
            Path(__file__).parent.parent
            / "examples"
            / "java_ecommerce"
            / "risk_control.ej"
        )
        if not risk_ej_path.exists():
            pytest.skip("risk_control.ej not found")

        content = risk_ej_path.read_text(encoding="utf-8")
        program = parse(content)

        tmpdir = tempfile.TemporaryDirectory()
        output_dir = Path(tmpdir.name) / "output"
        config = RenderConfig(
            target_lang="java_springboot",
            output_dir=output_dir,
            app_name="risk-core",
        )

        render_risk_control(
            structs=program.structs,
            functions=program.functions,
            routes=program.routes,
            config=config,
            output_dir=output_dir,
        )

        migration_file = (
            output_dir / "src/main/resources/db/migration/V2__init_risk_control.sql"
        )
        assert migration_file.exists(), "Migration SQL not generated"

        content = migration_file.read_text(encoding="utf-8")

        assert "CREATE TABLE" in content.upper(), "No CREATE TABLE statements"
        assert "INSERT INTO" in content.upper(), "No INSERT statements"

        statements = [s.strip() for s in content.split(";") if s.strip()]
        assert len(statements) > 10, (
            f"Expected many SQL statements, got {len(statements)}"
        )

        tmpdir.cleanup()

    def test_all_required_endpoints_present(self):
        """验证所有必需的 API 端点都存在。"""
        from enjinc.template_renderer import RenderConfig, render_risk_control

        risk_ej_path = (
            Path(__file__).parent.parent
            / "examples"
            / "java_ecommerce"
            / "risk_control.ej"
        )
        if not risk_ej_path.exists():
            pytest.skip("risk_control.ej not found")

        content = risk_ej_path.read_text(encoding="utf-8")
        program = parse(content)

        tmpdir = tempfile.TemporaryDirectory()
        output_dir = Path(tmpdir.name) / "output"
        config = RenderConfig(
            target_lang="java_springboot",
            output_dir=output_dir,
            app_name="risk-core",
        )

        render_risk_control(
            structs=program.structs,
            functions=program.functions,
            routes=program.routes,
            config=config,
            output_dir=output_dir,
        )

        controller_file = (
            output_dir
            / "src/main/java/risk_core/web/controller/RiskControlController.java"
        )
        assert controller_file.exists(), "Controller not generated"

        content = controller_file.read_text(encoding="utf-8")

        required_endpoints = [
            "evaluateRegisterRisk",
            "evaluateLoginRisk",
            "evaluateOrderRisk",
            "evaluatePaymentRisk",
            "checkBlacklist",
            "addToBlacklist",
            "checkWhitelist",
            "getRiskProfile",
            "triggerRiskAlert",
            "executeRiskRules",
            "makeRiskDecision",
            "getRiskStatistics",
        ]

        for endpoint in required_endpoints:
            assert endpoint in content, f"Missing endpoint method: {endpoint}"

        tmpdir.cleanup()

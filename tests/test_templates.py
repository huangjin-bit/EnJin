"""
============================================================
EnJin 模板渲染测试 (test_templates.py)
============================================================
验证 template_renderer.py 能否正确将 I-AST 渲染为目标语言代码。

测试覆盖:
    1. 基建层文件生成 (app/core/config.py, database.py, app/main.py)
    2. Model 层 ORM 类生成
    3. Schema 层 Pydantic 模型生成
    4. Repository 层数据访问生成
    5. Method 层服务函数生成
    6. Module 层初始化与调度生成
    7. Service 层路由生成 (app/api/v1/)
    8. requirements.txt 生成
============================================================
"""

from pathlib import Path

import pytest

from enjinc.parser import parse_file
from enjinc.template_renderer import RenderConfig, render_program
from enjinc.ast_nodes import Program


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """临时输出目录。"""
    output = tmp_path / "output"
    output.mkdir(parents=True, exist_ok=True)
    return output


class TestInfrastructureRendering:
    """验证基建层文件生成。"""

    def test_config_py_generated(self, examples_dir: Path, output_dir: Path):
        """config.py 文件应包含正确的应用配置。"""
        app_program = parse_file(examples_dir / "application.ej")
        config = RenderConfig(output_dir=output_dir)
        render_program(app_program, config)

        config_py = output_dir / "python_fastapi" / "app" / "core" / "config.py"
        assert config_py.exists()

        content = config_py.read_text(encoding="utf-8")
        assert 'APP_NAME = "user-service"' in content
        assert "DATABASE_CONFIG" in content
        assert "AI_CONFIG" in content

    def test_database_py_generated(self, examples_dir: Path, output_dir: Path):
        """database.py 文件应包含数据库连接逻辑。"""
        app_program = parse_file(examples_dir / "application.ej")
        config = RenderConfig(output_dir=output_dir)
        render_program(app_program, config)

        db_py = output_dir / "python_fastapi" / "app" / "core" / "database.py"
        assert db_py.exists()

        content = db_py.read_text(encoding="utf-8")
        assert "create_engine" in content
        assert "SessionLocal" in content
        assert "Base = declarative_base()" in content
        assert "def get_db():" in content

    def test_main_py_generated(self, examples_dir: Path, output_dir: Path):
        """main.py 文件应包含 FastAPI 应用启动逻辑。"""
        app_program = parse_file(examples_dir / "application.ej")
        config = RenderConfig(output_dir=output_dir)
        render_program(app_program, config)

        main_py = output_dir / "python_fastapi" / "app" / "main.py"
        assert main_py.exists()

        content = main_py.read_text(encoding="utf-8")
        assert "FastAPI(" in content
        assert "CORSMiddleware" in content
        assert "lifespan" in content
        assert 'title="user-service"' in content

    def test_requirements_txt_generated(self, examples_dir: Path, output_dir: Path):
        """requirements.txt 应包含必要依赖。"""
        app_program = parse_file(examples_dir / "application.ej")
        config = RenderConfig(output_dir=output_dir)
        render_program(app_program, config)

        req = output_dir / "python_fastapi" / "requirements.txt"
        assert req.exists()

        content = req.read_text(encoding="utf-8")
        assert "fastapi" in content
        assert "sqlalchemy" in content


class TestModelsRendering:
    """验证 Model 层 ORM 类生成。"""

    def test_models_py_contains_structs(self, examples_dir: Path, tmp_path: Path):
        """每个 struct 应生成独立的 ORM 模型文件。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "user_management.ej")
        config = RenderConfig(output_dir=output_dir)
        render_program(program, config)

        models_py = output_dir / "python_fastapi" / "app" / "models" / "user.py"
        assert models_py.exists()

        content = models_py.read_text(encoding="utf-8")
        assert "class User(Base):" in content

        user_profile_py = output_dir / "python_fastapi" / "app" / "models" / "userprofile.py"
        assert user_profile_py.exists()
        profile_content = user_profile_py.read_text(encoding="utf-8")
        assert "class UserProfile(Base):" in profile_content


class TestSchemasRendering:
    """验证 Schema 层 Pydantic 模型生成。"""

    def test_schemas_generated(self, examples_dir: Path, tmp_path: Path):
        """每个 struct 应生成 Create/Update/Response schema。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "user_management.ej")
        config = RenderConfig(output_dir=output_dir)
        render_program(program, config)

        schemas_dir = output_dir / "python_fastapi" / "app" / "schemas"
        assert schemas_dir.exists()
        assert (schemas_dir / "__init__.py").exists()
        assert (schemas_dir / "user.py").exists()

        content = (schemas_dir / "user.py").read_text(encoding="utf-8")
        assert "class UserCreate" in content
        assert "class UserUpdate" in content
        assert "class UserResponse" in content
        assert "BaseModel" in content


class TestRepositoriesRendering:
    """验证 Repository 层数据访问生成。"""

    def test_repositories_generated(self, examples_dir: Path, tmp_path: Path):
        """每个 struct 应生成 Repository 文件。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "user_management.ej")
        config = RenderConfig(output_dir=output_dir)
        render_program(program, config)

        repo_dir = output_dir / "python_fastapi" / "app" / "repositories"
        assert repo_dir.exists()
        assert (repo_dir / "__init__.py").exists()
        assert (repo_dir / "user_repository.py").exists()

        content = (repo_dir / "user_repository.py").read_text(encoding="utf-8")
        assert "class UserRepository" in content
        assert "def get_by_id" in content
        assert "def create" in content


class TestServicesRendering:
    """验证 Method 层服务函数生成。"""

    def test_services_py_contains_functions(self, examples_dir: Path, tmp_path: Path):
        """services 目录应包含所有 fn 定义的函数。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "user_management.ej")
        config = RenderConfig(output_dir=output_dir)
        render_program(program, config)

        services_dir = output_dir / "python_fastapi" / "app" / "services"
        assert services_dir.exists()
        assert (services_dir / "__init__.py").exists()

        register_user_py = services_dir / "register_user.py"
        assert register_user_py.exists()
        content = register_user_py.read_text(encoding="utf-8")
        assert "def register_user(" in content

        get_user_py = services_dir / "get_user_by_id.py"
        assert get_user_py.exists()
        assert "def get_user_by_id(" in get_user_py.read_text(encoding="utf-8")


class TestModulesRendering:
    """验证 Module 层初始化与调度生成。"""

    def test_modules_py_contains_modules(self, examples_dir: Path, tmp_path: Path):
        """modules 目录应包含模块初始化和调度。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "user_management.ej")
        config = RenderConfig(output_dir=output_dir)
        render_program(program, config)

        modules_py = output_dir / "python_fastapi" / "app" / "modules" / "usermanager.py"
        assert modules_py.exists()

        content = modules_py.read_text(encoding="utf-8")
        assert "def init_usermanager():" in content
        assert "MODULE_REGISTRY" in content


class TestRoutesRendering:
    """验证 Service 层路由生成。"""

    def test_api_directory_created(self, examples_dir: Path, tmp_path: Path):
        """app/api/v1/ 目录应被创建。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "user_management.ej")
        config = RenderConfig(output_dir=output_dir)
        render_program(program, config)

        api_dir = output_dir / "python_fastapi" / "app" / "api" / "v1"
        assert api_dir.exists()
        assert (api_dir / "__init__.py").exists()
        assert (api_dir / "userservice.py").exists()

    def test_route_file_content(self, examples_dir: Path, tmp_path: Path):
        """路由文件应包含 FastAPI 端点定义。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "user_management.ej")
        config = RenderConfig(output_dir=output_dir)
        render_program(program, config)

        route_py = output_dir / "python_fastapi" / "app" / "api" / "v1" / "userservice.py"
        assert route_py.exists()

        content = route_py.read_text(encoding="utf-8")
        assert "APIRouter()" in content
        assert "PREFIX" in content

    def test_api_init_contains_registration(self, examples_dir: Path, tmp_path: Path):
        """api/v1/__init__.py 应包含动态路由注册逻辑。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "user_management.ej")
        config = RenderConfig(output_dir=output_dir)
        render_program(program, config)

        init_py = output_dir / "python_fastapi" / "app" / "api" / "v1" / "__init__.py"
        assert init_py.exists()

        content = init_py.read_text(encoding="utf-8")
        assert "def register_all_routes" in content
        assert "app.include_router" in content


class TestIntegration:
    """集成测试: 端到端渲染。"""

    def test_full_rendering(self, examples_dir: Path, output_dir: Path):
        """完整渲染所有层，验证 app/ 包结构完整。"""
        program = parse_file(examples_dir / "user_management.ej")
        config = RenderConfig(output_dir=output_dir)
        render_program(program, config)

        target_dir = output_dir / "python_fastapi"

        expected_files = [
            "requirements.txt",
            "app/__init__.py",
            "app/main.py",
            "app/core/__init__.py",
            "app/core/config.py",
            "app/core/database.py",
            "app/core/exceptions.py",
            "app/models/__init__.py",
            "app/models/user.py",
            "app/schemas/__init__.py",
            "app/schemas/user.py",
            "app/repositories/__init__.py",
            "app/repositories/user_repository.py",
            "app/services/__init__.py",
            "app/services/register_user.py",
            "app/modules/__init__.py",
            "app/api/__init__.py",
            "app/api/v1/__init__.py",
            "app/api/v1/userservice.py",
        ]

        for file_path in expected_files:
            full_path = target_dir / file_path
            assert full_path.exists(), f"文件 {file_path} 不存在"

    def test_rendered_code_is_syntactically_valid(
        self, examples_dir: Path, output_dir: Path
    ):
        """渲染的代码应能被 Python 语法检查通过。"""
        program = parse_file(examples_dir / "user_management.ej")
        config = RenderConfig(output_dir=output_dir)
        render_program(program, config)

        target_dir = output_dir / "python_fastapi"

        import ast
        import os

        for root, dirs, files in os.walk(target_dir):
            for file in files:
                if file.endswith(".py"):
                    file_path = Path(root) / file
                    content = file_path.read_text(encoding="utf-8")
                    try:
                        ast.parse(content)
                    except SyntaxError as e:
                        pytest.fail(f"文件 {file_path} 存在语法错误: {e}")

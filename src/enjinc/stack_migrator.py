"""EnJin 技术栈迁移模块：将 .ej 项目从一个目标栈迁移到另一个。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from enjinc.ast_nodes import Program
from enjinc.template_renderer import RenderConfig, render_program


# ============================================================
# 跨栈类型映射
# ============================================================

@dataclass
class StackMapping:
    """两个技术栈之间的映射规则。"""
    from_target: str
    to_target: str
    type_map: dict[str, str]
    annotation_map: dict[str, str]
    file_map: dict[str, str]
    concepts_missing: list[str] = field(default_factory=list)


STACK_MAPPINGS: dict[tuple[str, str], StackMapping] = {
    ("java_springboot", "python_fastapi"): StackMapping(
        from_target="java_springboot",
        to_target="python_fastapi",
        type_map={
            "Long": "int", "Integer": "int", "Long": "int",
            "Double": "float", "Float": "float", "BigDecimal": "float",
            "Boolean": "bool",
            "String": "str",
            "LocalDateTime": "datetime", "LocalDate": "date",
            "List": "list", "Map": "dict", "Set": "set",
            "Object": "Any", "void": "None",
        },
        annotation_map={
            "@Entity": "SQLAlchemy Model",
            "@Table": "__tablename__",
            "@Id": "primary_key=True",
            "@GeneratedValue": "autoincrement=True",
            "@Column(unique=true)": "unique=True",
            "@Column(nullable=false)": "nullable=False",
            "@Transactional": "@transactional (业务逻辑层)",
            "@RestController": "FastAPI router",
            "@GetMapping": "@router.get",
            "@PostMapping": "@router.post",
            "@PutMapping": "@router.put",
            "@DeleteMapping": "@router.delete",
            "@Autowired": "dependency injection",
            "@Service": "business logic function",
            "@Repository": "data access layer",
        },
        file_map={
            "Entity.java": "models/{name}.py",
            "Mapper.java": "repositories/{name}_repository.py",
            "Service.java": "services/{name}.py",
            "ServiceImpl.java": "services/{name}.py",
            "Controller.java": "api/v1/{name}.py",
            "CreateRequest.java": "schemas/{name}.py",
            "UpdateRequest.java": "schemas/{name}.py",
            "Response.java": "schemas/{name}.py",
            "application.yml": "core/config.py",
            "pom.xml": "requirements.txt",
        },
        concepts_missing=[
            "MyBatis XML mapper → SQLAlchemy ORM",
            "Spring Security → FastAPI Depends + JWT",
            "Spring Kafka → asyncio + aiokafka",
            "Flyway → Alembic",
        ],
    ),
    ("python_fastapi", "java_springboot"): StackMapping(
        from_target="python_fastapi",
        to_target="java_springboot",
        type_map={
            "int": "Long", "float": "Double", "bool": "Boolean",
            "str": "String", "bytes": "byte[]",
            "datetime": "LocalDateTime", "date": "LocalDate",
            "dict": "Map<String, Object>", "list": "List",
            "set": "Set", "tuple": "List",
            "Optional": "Optional (via @Nullable)",
            "Any": "Object",
        },
        annotation_map={
            "@router.get": "@GetMapping",
            "@router.post": "@PostMapping",
            "@router.put": "@PutMapping",
            "@router.delete": "@DeleteMapping",
            "SQLAlchemy Column": "@Entity field",
            "Pydantic BaseModel": "DTO class",
            "Depends": "@Autowired",
        },
        file_map={
            "models/{name}.py": "domain/entity/{Name}.java",
            "schemas/{name}.py": "interface/dto/",
            "services/{name}.py": "application/service/",
            "api/v1/{name}.py": "interface/controller/{Name}Controller.java",
            "repositories/{name}_repository.py": "infrastructure/mapper/{Name}Mapper.java",
        },
        concepts_missing=[
            "Pydantic schema → DTO (Create/Update/Response)",
            "async def → sync method (Spring is thread-based)",
            "FastAPI dependency injection → Spring @Autowired",
            "Alembic → Flyway",
        ],
    ),
}


# ============================================================
# 迁移计划
# ============================================================

@dataclass
class MigrationPlan:
    """技术栈迁移计划。"""
    source_target: str
    target_target: str
    program: Program
    mapping: StackMapping
    adapter_files: list[dict] = field(default_factory=list)
    migration_scripts: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def create_migration_plan(
    program: Program,
    from_target: str,
    to_target: str,
) -> MigrationPlan:
    """分析 Program 并创建迁移计划。"""
    key = (from_target, to_target)
    mapping = STACK_MAPPINGS.get(key)

    warnings = []
    if not mapping:
        warnings.append(f"无预定义映射: {from_target} → {to_target}，将使用默认类型映射")
        mapping = StackMapping(
            from_target=from_target,
            to_target=to_target,
            type_map={}, annotation_map={}, file_map={},
        )

    # 检查 Program 中是否有目标栈不支持的概念
    for fn in program.functions:
        for nb in fn.native_blocks:
            if from_target.startswith("java") and nb.target == "python":
                warnings.append(f"fn '{fn.name}' 的 native python 块需手动迁移为 native java")
            elif from_target.startswith("python") and nb.target == "java":
                warnings.append(f"fn '{fn.name}' 的 native java 块需手动迁移为 native python")

    return MigrationPlan(
        source_target=from_target,
        target_target=to_target,
        program=program,
        mapping=mapping,
        warnings=warnings,
    )


def execute_migration(
    program: Program,
    from_target: str,
    to_target: str,
    output_dir: Path,
    use_ai: bool = False,
) -> Path:
    """执行完整的技术栈迁移流水线。

    1. 创建迁移计划
    2. 用新 target 编译 Program
    3. 生成适配层代码
    4. 生成迁移报告

    Returns:
        输出目录路径
    """
    plan = create_migration_plan(program, from_target, to_target)

    # Step 1: 用新 target 渲染
    config = RenderConfig(
        target_lang=to_target,
        output_dir=output_dir,
        use_ai=use_ai,
    )
    render_program(program, config)

    target_output = output_dir / to_target

    # Step 2: 生成适配层
    _generate_adapter_layer(plan, target_output)

    # Step 3: 生成迁移报告
    _generate_migration_report(plan, target_output)

    return target_output


def _generate_adapter_layer(plan: MigrationPlan, output_dir: Path) -> list[Path]:
    """生成适配/桥接代码，用于迁移期间的渐进式切换。"""
    files: list[Path] = []

    adapter_dir = output_dir / "migration_adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)

    app_name = "app"
    if plan.program.application:
        app_name = plan.program.application.config.get("name", "app")

    if plan.target_target == "python_fastapi":
        # Java → Python：生成一个 Python 代理，调用旧 Java 服务
        proxy_code = _generate_python_proxy(plan, app_name)
        proxy_path = adapter_dir / "java_service_proxy.py"
        proxy_path.write_text(proxy_code, encoding="utf-8")
        files.append(proxy_path)

    elif plan.target_target == "java_springboot":
        # Python → Java：生成一个 Java 代理，调用旧 Python 服务
        proxy_code = _generate_java_proxy(plan, app_name)
        proxy_path = adapter_dir / "PythonServiceProxy.java"
        proxy_path.write_text(proxy_code, encoding="utf-8")
        files.append(proxy_path)

    return files


def _generate_python_proxy(plan: MigrationPlan, app_name: str) -> str:
    """生成 Python 代理客户端，在迁移期间调用旧 Java 服务。"""
    routes = plan.program.routes
    endpoints = []
    for r in routes:
        prefix = "/"
        for a in r.annotations:
            if a.name == "prefix" and a.args:
                prefix = a.args[0]
        for ep in r.endpoints:
            endpoints.append(f"    # {ep.method} {prefix}{ep.path}")

    endpoint_lines = "\n".join(endpoints) if endpoints else "    # (从 .ej 自动提取)"

    return f'''"""
迁移适配层：代理调用旧 Java Spring Boot 服务。
迁移完成后删除此文件。
"""
import httpx

JAVA_SERVICE_URL = "http://localhost:8080"


class JavaServiceProxy:
    """在 Python 新服务就绪前，代理请求到旧 Java 服务。"""

    def __init__(self, base_url: str = JAVA_SERVICE_URL):
        self.base_url = base_url
        self.client = httpx.Client(base_url=base_url, timeout=30.0)

    async def proxy_request(self, method: str, path: str, **kwargs):
        response = self.client.request(method, path, **kwargs)
        return response.json()

    # 自动生成的端点映射
{endpoint_lines}
'''


def _generate_java_proxy(plan: MigrationPlan, pkg: str) -> str:
    """生成 Java 代理客户端，在迁移期间调用旧 Python 服务。"""
    routes = plan.program.routes
    endpoints = []
    for r in routes:
        prefix = "/"
        for a in r.annotations:
            if a.name == "prefix" and a.args:
                prefix = a.args[0]
        for ep in r.endpoints:
            endpoints.append(f"    // {ep.method} {prefix}{ep.path}")

    endpoint_lines = "\n".join(endpoints) if endpoints else "    // (从 .ej 自动提取)"

    return f'''package {pkg}.migration;

import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

/**
 * 迁移适配层：代理调用旧 Python FastAPI 服务。
 * 迁移完成后删除此文件。
 */
@Component
public class PythonServiceProxy {{

    private final RestTemplate restTemplate = new RestTemplate();
    private static final String PYTHON_SERVICE_URL = "http://localhost:8000";

    public Object proxyGet(String path) {{
        return restTemplate.getForObject(PYTHON_SERVICE_URL + path, Object.class);
    }}

    public Object proxyPost(String path, Object body) {{
        return restTemplate.postForObject(PYTHON_SERVICE_URL + path, body, Object.class);
    }}

    // 自动生成的端点映射
{endpoint_lines}
}}
'''


def _generate_migration_report(plan: MigrationPlan, output_dir: Path) -> Path:
    """生成迁移报告。"""
    report_dir = output_dir / "migration_report"
    report_dir.mkdir(parents=True, exist_ok=True)

    struct_names = [s.name for s in plan.program.structs]
    fn_names = [f.name for f in plan.program.functions]
    route_names = [r.name for r in plan.program.routes]

    report = f"""# 技术栈迁移报告

## 概述

- **源技术栈**: {plan.source_target}
- **目标技术栈**: {plan.target_target}

## 资源清单

| 类型 | 数量 | 列表 |
|------|------|------|
| 数据模型 (struct) | {len(struct_names)} | {', '.join(struct_names) or '(无)'} |
| 业务方法 (fn) | {len(fn_names)} | {', '.join(fn_names[:10])}{'...' if len(fn_names) > 10 else ''} |
| API 路由 (route) | {len(route_names)} | {', '.join(route_names) or '(无)'} |

## 类型映射

| 源类型 | 目标类型 |
|--------|---------|
"""
    for src, dst in sorted(plan.mapping.type_map.items()):
        report += f"| {src} | {dst} |\n"

    if plan.mapping.concepts_missing:
        report += "\n## 需要手动迁移的概念\n\n"
        for c in plan.mapping.concepts_missing:
            report += f"- {c}\n"

    if plan.warnings:
        report += "\n## 警告\n\n"
        for w in plan.warnings:
            report += f"- {w}\n"

    report += """
## 迁移步骤

1. **验证新服务**: 运行新 target 生成的项目，确认基本功能
2. **数据迁移**: 使用生成的 SQL/Alembic 迁移脚本
3. **流量切换**: 使用适配层逐步切换流量
4. **清理**: 删除适配层代码和旧项目

## 文件映射

| 源文件模式 | 目标文件模式 |
|-----------|-------------|
"""
    for src, dst in sorted(plan.mapping.file_map.items()):
        report += f"| `{src}` | `{dst}` |\n"

    report_path = report_dir / "MIGRATION_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    return report_path

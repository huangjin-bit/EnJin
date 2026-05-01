"""
============================================================
EnJin 模板渲染器 (template_renderer.py)
============================================================
将 I-AST 节点分发到已注册的 TargetRenderer 实例。
新增目标无需修改本文件——只需在 targets/<name>/renderer.py 中注册即可。
============================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from enjinc.annotations import has_annotation, get_annotation_param
from enjinc.constants import ANNO_TABLE

from enjinc.ast_nodes import Program
from enjinc.targets import get_renderer


@dataclass
class RenderConfig:
    """渲染配置。"""

    target_lang: str = "python_fastapi"
    output_dir: Path = Path("output")
    use_ai: bool = False
    app_name: str = "app"
    app_version: str = "0.1.0"
    ai_results: dict | None = None


def _get_ai_code(
    ai_results: dict | None, node_type: str, node_name: str
) -> str | None:
    """从 AI 结果字典中提取指定节点的生成代码，并清理 markdown 标记。"""
    if not ai_results:
        return None
    key = f"{node_type}:{node_name}"
    result = ai_results.get(key)
    if not result or not result.generated_code:
        return None
    code = result.generated_code.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        lines = [line for line in lines if not line.startswith("```")]
        code = "\n".join(lines).strip()
    return code if code else None


def _call_with_config(method, *args, app_config=None, **kwargs):
    """Call a renderer method, only passing kwargs the method accepts."""
    import inspect
    sig = inspect.signature(method)
    # Filter kwargs to only those the method accepts
    filtered = {}
    for k, v in kwargs.items():
        if k in sig.parameters:
            filtered[k] = v
    if "app_config" in sig.parameters:
        method(*args, **filtered, app_config=app_config)
    else:
        method(*args, **filtered)


def render_program(program: Program, config: RenderConfig) -> None:
    """渲染整个 Program 为目标语言代码。"""
    renderer = get_renderer(config.target_lang)
    if not renderer:
        raise ValueError(
            f"Unknown target: {config.target_lang}. "
            f"Available: {', '.join(_list_targets())}"
        )

    app_config = program.application.config if program.application else {}
    if program.application:
        config.app_name = app_config.get("name", config.app_name)
        config.app_version = app_config.get("version", config.app_version)

    output_dir = config.output_dir / config.target_lang
    output_dir.mkdir(parents=True, exist_ok=True)

    renderer.render_infrastructure(config.app_name, app_config, output_dir)

    # Pass app_config to renderers that accept it (backward compatible)
    _call_with_config(renderer.render_models, program.structs, config.app_name, output_dir, app_config=app_config)
    _call_with_config(
        renderer.render_methods,
        program.functions, program.structs, config.app_name,
        config.ai_results, output_dir, app_config=app_config,
    )
    renderer.render_modules(program.modules, output_dir)
    _call_with_config(
        renderer.render_routes,
        program.routes, config.app_name, config.ai_results, output_dir,
        functions=program.functions, structs=program.structs, app_config=app_config,
    )


def render_program_incremental(
    program: Program,
    config: RenderConfig,
    render_plan: list[str],
) -> None:
    """增量渲染：只重新渲染 render_plan 中指定的节点。

    Args:
        program: 完整 Program
        config: 渲染配置
        render_plan: 需要重新渲染的节点 key 列表（如 ["struct:User", "fn:create_order"]）
    """
    renderer = get_renderer(config.target_lang)
    if not renderer:
        raise ValueError(f"Unknown target: {config.target_lang}")

    app_config = program.application.config if program.application else {}
    if program.application:
        config.app_name = app_config.get("name", config.app_name)

    output_dir = config.output_dir / config.target_lang
    output_dir.mkdir(parents=True, exist_ok=True)

    plan_set = set(render_plan)

    # 基础设施层：如果有任何 struct 变更，重新渲染
    struct_changed = any(k.startswith("struct:") for k in plan_set)
    if struct_changed:
        renderer.render_infrastructure(config.app_name, app_config, output_dir)

    # 过滤出需要重新渲染的节点
    struct_names = {k.split(":")[1] for k in plan_set if k.startswith("struct:")}
    fn_names = {k.split(":")[1] for k in plan_set if k.startswith("fn:")}
    route_names = {k.split(":")[1] for k in plan_set if k.startswith("route:")}

    if struct_names:
        changed_structs = [s for s in program.structs if s.name in struct_names]
        _call_with_config(renderer.render_models, changed_structs, config.app_name, output_dir, app_config=app_config)

    if fn_names:
        changed_fns = [f for f in program.functions if f.name in fn_names]
        related_structs = [s for s in program.structs
                           if any(f.return_type and f.return_type.base == s.name or
                                  any(p.type.base == s.name for p in f.params)
                                  for f in changed_fns)]
        _call_with_config(
            renderer.render_methods, changed_fns, related_structs, config.app_name,
            config.ai_results, output_dir, app_config=app_config,
        )

    if route_names:
        changed_routes = [r for r in program.routes if r.name in route_names]
        _call_with_config(
            renderer.render_routes,
            changed_routes, config.app_name, config.ai_results, output_dir,
            functions=program.functions, structs=program.structs, app_config=app_config,
        )


def render_risk_control(
    structs, functions, routes, config: RenderConfig, output_dir: Path,
) -> None:
    """渲染风控模块（Java Spring Boot 专用）。"""
    if config.target_lang != "java_springboot":
        return

    from enjinc.targets import render_template
    from enjinc.ast_nodes import StructDef
    pkg_path = config.app_name.replace("-", "_")

    entity_dir = output_dir / "src/main/java" / pkg_path / "domain/entity"
    entity_dir.mkdir(parents=True, exist_ok=True)
    (entity_dir / "RiskEntity.java").write_text(
        render_template("java_springboot", "domain/RiskEntity.java.jinja", {
            "risk_structs": structs, "application": {"name": config.app_name},
        }),
        encoding="utf-8",
    )

    mapper_dir = output_dir / "src/main/java" / pkg_path / "infrastructure/mapper"
    mapper_dir.mkdir(parents=True, exist_ok=True)
    (mapper_dir / "RiskMapper.java").write_text(
        render_template("java_springboot", "infrastructure/mapper/RiskMapper.java.jinja", {
            "risk_entities": structs,
            "application": {"name": config.app_name},
            "has_risk_blacklist": any("blacklist" in m.name.lower() for m in structs),
            "has_risk_whitelist": any("whitelist" in m.name.lower() for m in structs),
            "has_risk_alert": any("alert" in m.name.lower() for m in structs),
            "has_device_fingerprint": any("device" in m.name.lower() or "fingerprint" in m.name.lower() for m in structs),
            "has_risk_rule": any("rule" in m.name.lower() and "risk" in m.name.lower() for m in structs),
            "has_risk_event": any("event" in m.name.lower() and "risk" in m.name.lower() for m in structs),
            "has_risk_profile": any("profile" in m.name.lower() and "risk" in m.name.lower() for m in structs),
        }),
        encoding="utf-8",
    )

    service_dir = output_dir / "src/main/java" / pkg_path / "application/service"
    service_dir.mkdir(parents=True, exist_ok=True)
    (service_dir / "RiskControlService.java").write_text(
        render_template("java_springboot", "application/RiskService.java.jinja", {
            "application": {"name": config.app_name},
        }),
        encoding="utf-8",
    )

    controller_dir = output_dir / "src/main/java" / pkg_path / "web/controller"
    controller_dir.mkdir(parents=True, exist_ok=True)
    (controller_dir / "RiskControlController.java").write_text(
        render_template("java_springboot", "interface/controller/RiskController.java.jinja", {
            "application": {"name": config.app_name},
        }),
        encoding="utf-8",
    )

    migration_dir = output_dir / "src/main/resources" / "db" / "migration"
    migration_dir.mkdir(parents=True, exist_ok=True)
    (migration_dir / "V2__init_risk_control.sql").write_text(
        render_template("java_springboot", "migration/V2__init_risk_control.sql.jinja", {
            "application": {"name": config.app_name},
        }),
        encoding="utf-8",
    )


def _list_targets():
    from enjinc.targets import list_targets
    return list_targets()

"""Python FastAPI 目标渲染器。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from enjinc.annotations import has_annotation
from enjinc.ast_nodes import (
    FnDef,
    ModuleDef,
    Param,
    RouteDef,
    StructDef,
    TypeRef,
)
from enjinc.constants import ANNO_AUTH, ENJIN_TO_PYTHON, MUTATING_HTTP_METHODS, PRIMITIVE_TYPES
from enjinc.guard_compiler import compile_guards_python
from enjinc.layout_config import PythonLayoutConfig, get_python_layout
from enjinc.targets import TargetRenderer, register_target, render_template, write_file


def _py_type_str(type_ref: TypeRef) -> str:
    """将 TypeRef 转为 Python 类型注解字符串。"""
    base = ENJIN_TO_PYTHON.get(type_ref.base)
    if base:
        if type_ref.is_optional:
            return f"Optional[{base}]"
        return base
    if type_ref.base == "List" and type_ref.params:
        inner = _py_type_str(type_ref.params[0]) if isinstance(type_ref.params[0], TypeRef) else "Any"
        return f"List[{inner}]"
    if type_ref.is_optional:
        return f"Optional[{type_ref.base}]"
    return type_ref.base


@register_target
class PythonFastAPIRenderer:
    target_lang = "python_fastapi"
    native_lang = "python"
    file_extension = ".py"

    def render_infrastructure(
        self, app_name: str, app_config: dict, output_dir: Path,
    ) -> None:
        t = self.target_lang
        layout = get_python_layout(app_config)
        pkg = layout.app_package_name
        base = output_dir / pkg

        # app/__init__.py
        write_file(base / "__init__.py", "")

        # app/core/
        core_dir = base / "core"
        write_file(core_dir / "__init__.py", "")
        write_file(core_dir / "config.py", render_template(t, "config.py.jinja", {"app_config": app_config}))
        write_file(core_dir / "database.py", render_template(t, "database.py.jinja", {"app_config": app_config}))
        write_file(core_dir / "exceptions.py", render_template(t, "exceptions.py.jinja", {}))

        # app/main.py
        write_file(base / "main.py", render_template(t, "main.py.jinja", {
            "app_name": app_config.get("name", app_name),
            "app_version": app_config.get("version", "0.1.0"),
            "api_version": layout.api_version,
        }))

        # requirements.txt at project root
        write_file(output_dir / "requirements.txt", render_template(t, "requirements.txt.jinja", {
            "app_config": app_config,
        }))

    def render_models(
        self, structs: list[StructDef], app_name: str, output_dir: Path,
        app_config: dict | None = None,
    ) -> None:
        t = self.target_lang
        layout = get_python_layout(app_config)
        pkg = layout.app_package_name
        models_dir = output_dir / pkg / "models"
        models_dir.mkdir(parents=True, exist_ok=True)

        write_file(models_dir / "__init__.py", "")

        for struct in structs:
            content = render_template(t, "models.py.jinja", {"structs": [struct]})
            write_file(models_dir / f"{struct.name.lower()}.py", content)

        imports = "\n".join(
            f"from {pkg}.models.{s.name.lower()} import {s.name}" for s in structs
        )
        write_file(models_dir / "__init__.py", imports + "\n")

    def render_schemas(
        self, structs: list[StructDef], output_dir: Path, app_config: dict | None = None,
    ) -> None:
        """渲染 Pydantic schemas 层。"""
        t = self.target_lang
        layout = get_python_layout(app_config)
        pkg = layout.app_package_name
        schemas_dir = output_dir / pkg / "schemas"
        schemas_dir.mkdir(parents=True, exist_ok=True)

        for struct in structs:
            content = render_template(t, "schemas.py.jinja", {
                "structs": [struct],
                "sensitive_fields": layout.sensitive_fields,
            })
            write_file(schemas_dir / f"{struct.name.lower()}.py", content)

        imports = "\n".join(
            f"from {pkg}.schemas.{s.name.lower()} import {s.name}Create, {s.name}Update, {s.name}Response"
            for s in structs
        )
        write_file(schemas_dir / "__init__.py", imports + "\n")

    def render_repositories(
        self, structs: list[StructDef], output_dir: Path, app_config: dict | None = None,
    ) -> None:
        """渲染 Repository 数据访问层。"""
        t = self.target_lang
        layout = get_python_layout(app_config)
        pkg = layout.app_package_name
        repo_dir = output_dir / pkg / "repositories"
        repo_dir.mkdir(parents=True, exist_ok=True)

        for struct in structs:
            content = render_template(t, "repository.py.jinja", {"struct": struct, "pkg": pkg})
            write_file(repo_dir / f"{struct.name.lower()}_repository.py", content)

        imports = "\n".join(
            f"from {pkg}.repositories.{s.name.lower()}_repository import {s.name}Repository"
            for s in structs
        )
        write_file(repo_dir / "__init__.py", imports + "\n")

    def render_methods(
        self,
        functions: list[FnDef],
        structs: list[StructDef],
        app_name: str,
        ai_results: dict | None,
        output_dir: Path,
        app_config: dict | None = None,
    ) -> None:
        from enjinc.template_renderer import _get_ai_code
        t = self.target_lang
        layout = get_python_layout(app_config)
        pkg = layout.app_package_name
        services_dir = output_dir / pkg / "services"
        services_dir.mkdir(parents=True, exist_ok=True)

        for fn in functions:
            context = {
                "functions": [{
                    "fn": fn,
                    "params_str": ", ".join(p.name for p in fn.params),
                    "ai_code": _get_ai_code(ai_results, "fn", fn.name),
                    "guard_code": compile_guards_python(fn.guard) if fn.guard else [],
                }]
            }
            content = render_template(t, "services.py.jinja", context)
            write_file(services_dir / f"{fn.name}.py", content)

        imports = "\n".join(
            f"from {pkg}.services.{fn.name} import {fn.name}" for fn in functions
        )
        write_file(services_dir / "__init__.py", imports + "\n")

    def render_modules(
        self, modules: list[ModuleDef], output_dir: Path,
    ) -> None:
        t = self.target_lang
        modules_dir = output_dir / "app" / "modules"
        modules_dir.mkdir(parents=True, exist_ok=True)

        for mod in modules:
            content = render_template(t, "modules.py.jinja", {"modules": [mod]})
            write_file(modules_dir / f"{mod.name.lower()}.py", content)

        write_file(modules_dir / "__init__.py", "")

    def render_routes(
        self,
        routes: list[RouteDef],
        app_name: str,
        ai_results: dict | None,
        output_dir: Path,
        functions: list | None = None,
        structs: list[StructDef] | None = None,
        app_config: dict | None = None,
    ) -> None:
        from enjinc.template_renderer import _get_ai_code
        t = self.target_lang
        layout = get_python_layout(app_config)
        pkg = layout.app_package_name
        api_version = layout.api_version
        api_dir = output_dir / pkg / "api" / api_version
        api_dir.mkdir(parents=True, exist_ok=True)

        # Auth detection
        has_auth = any(self._route_has_auth(r) for r in routes)
        if has_auth:
            core_dir = output_dir / pkg / "core"
            deps_content = render_template(t, "deps.py.jinja", {})
            write_file(core_dir / "security.py", deps_content)

        # Schemas and Repositories
        all_structs = structs or []
        if layout.use_schemas and all_structs:
            self.render_schemas(all_structs, output_dir, app_config)
        if layout.use_repository and all_structs:
            self.render_repositories(all_structs, output_dir, app_config)

        # Build request models for POST/PUT endpoints (for route template context)
        request_models = self._build_request_models(routes, functions or [])
        model_by_handler = {m["name"]: m for m in request_models}
        for route in routes:
            for ep in route.endpoints:
                ep.request_model = model_by_handler.get(ep.handler, {}).get("name")

        # API __init__.py
        init_content = render_template(t, "routes__init__.py.jinja", {
            "routes": routes,
            "api_version": api_version,
        })
        write_file(api_dir / "__init__.py", init_content)

        # Parent __init__.py files
        write_file(output_dir / pkg / "api" / "__init__.py", "")

        # Individual route files
        for route in routes:
            route_ai_code = _get_ai_code(ai_results, "route", route.name)
            route_has_auth = self._route_has_auth(route)
            route_content = render_template(t, "route.py.jinja", {
                "route": route,
                "ai_code": route_ai_code,
                "has_auth": route_has_auth,
                "has_request_models": False,  # schemas handle this now
            })
            write_file(api_dir / f"{route.name.lower()}.py", route_content)

    def _route_has_auth(self, route: RouteDef) -> bool:
        """检查 route 是否有 @auth 注解。"""
        return has_annotation(route.annotations, ANNO_AUTH)

    def _build_request_models(self, routes: list[RouteDef], functions: list) -> list[dict]:
        """为 POST/PUT/PATCH 端点构建 request model 定义。"""
        fn_map = {fn.name: fn for fn in functions}
        models = []
        seen = set()
        for route in routes:
            for ep in route.endpoints:
                if ep.method in MUTATING_HTTP_METHODS and ep.handler not in seen:
                    seen.add(ep.handler)
                    model_name = "".join(
                        w.capitalize() for w in ep.handler.split("_")
                    ) + "Request"
                    fn = fn_map.get(ep.handler)
                    if fn and fn.params:
                        fields = []
                        for p in fn.params:
                            if p.type.base not in PRIMITIVE_TYPES or p.name == "id":
                                continue
                            fields.append({
                                "name": p.name,
                                "py_type": _py_type_str(p.type),
                                "optional": p.type.is_optional,
                            })
                    else:
                        fields = [{"name": "data", "py_type": "dict", "optional": True}]
                    if fields:
                        models.append({
                            "name": model_name,
                            "handler": ep.handler,
                            "fields": fields,
                        })
        return models

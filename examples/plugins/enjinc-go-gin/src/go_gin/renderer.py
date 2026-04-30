"""Go Gin Web Framework target renderer for EnJin."""

from __future__ import annotations

from pathlib import Path

from enjinc.ast_nodes import FnDef, ModuleDef, RouteDef, StructDef
from enjinc.targets import register_target, render_template, write_file
from enjinc.jinja_utils import register_template_dir

register_template_dir("go_gin", Path(__file__).parent / "templates")


def _go_type(type_ref) -> str:
    """将 EnJin 类型转换为 Go 类型。"""
    mapping = {
        "Int": "int64",
        "Float": "float64",
        "Bool": "bool",
        "String": "string",
        "DateTime": "time.Time",
    }
    base = mapping.get(type_ref.base, type_ref.base)
    if type_ref.is_optional:
        return f"*{base}"
    if type_ref.base == "List" and type_ref.params:
        inner = _go_type(type_ref.params[0])
        return f"[]{inner}"
    return base


@register_target
class GoGinRenderer:
    """Go Gin Web Framework 目标渲染器。"""

    target_lang = "go_gin"
    native_lang = "go"
    file_extension = ".go"

    def render_infrastructure(
        self, app_name: str, app_config: dict, output_dir: Path,
    ) -> None:
        t = self.target_lang
        pkg = app_name.replace("-", "_")
        ctx = {"app_name": pkg, "app_config": app_config}

        write_file(output_dir / "main.go", render_template(t, "main.go.jinja", ctx))
        write_file(output_dir / "go.mod", render_template(t, "go.mod.jinja", ctx))
        write_file(output_dir / "config" / "config.go",
                   render_template(t, "config.go.jinja", ctx))
        write_file(output_dir / "router" / "router.go",
                   render_template(t, "router.go.jinja", ctx))

    def render_models(
        self, structs: list[StructDef], app_name: str, output_dir: Path,
        app_config: dict | None = None,
    ) -> None:
        t = self.target_lang
        pkg = app_name.replace("-", "_")
        models_dir = output_dir / "model"
        for struct in structs:
            ctx = {"struct": struct, "pkg": pkg}
            write_file(
                models_dir / f"{struct.name.lower()}.go",
                render_template(t, "model.go.jinja", ctx),
            )

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
        pkg = app_name.replace("-", "_")
        service_dir = output_dir / "service"
        for fn in functions:
            ctx = {
                "fn": fn,
                "pkg": pkg,
                "ai_code": _get_ai_code(ai_results, "fn", fn.name),
            }
            write_file(
                service_dir / f"{fn.name}.go",
                render_template(t, "service.go.jinja", ctx),
            )

    def render_modules(
        self, modules: list[ModuleDef], output_dir: Path,
    ) -> None:
        pass

    def render_routes(
        self,
        routes: list[RouteDef],
        app_name: str,
        ai_results: dict | None,
        output_dir: Path,
        functions: list | None = None,
        structs: list | None = None,
        app_config: dict | None = None,
    ) -> None:
        from enjinc.template_renderer import _get_ai_code
        t = self.target_lang
        pkg = app_name.replace("-", "_")
        handler_dir = output_dir / "handler"
        for route in routes:
            ctx = {
                "route": route,
                "pkg": pkg,
                "ai_code": _get_ai_code(ai_results, "route", route.name),
            }
            write_file(
                handler_dir / f"{route.name.lower()}.go",
                render_template(t, "handler.go.jinja", ctx),
            )

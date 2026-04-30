"""Python Crawler 目标渲染器。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from enjinc.ast_nodes import FnDef, ModuleDef, RouteDef, StructDef
from enjinc.targets import TargetRenderer, register_target, render_template, write_file


@register_target
class PythonCrawlerRenderer:
    target_lang = "python_crawler"
    native_lang = "python"
    file_extension = ".py"

    def render_infrastructure(
        self, app_name: str, app_config: dict, output_dir: Path,
    ) -> None:
        t = self.target_lang
        ctx = {"application": app_config}

        httpx_dir = output_dir / "httpx"
        write_file(httpx_dir / "config.py", render_template(t, "httpx/config.py.jinja", ctx))
        write_file(httpx_dir / "proxy_pool.py", render_template(t, "httpx/proxy_pool.py.jinja", ctx))
        write_file(httpx_dir / "rate_limiter.py", render_template(t, "httpx/rate_limiter.py.jinja", ctx))
        write_file(httpx_dir / "crawler.py", render_template(t, "httpx/crawler.py.jinja", ctx))

        scrapy_dir = output_dir / "scrapy"
        spider_name = app_config.get("name", "base_spider").replace("-", "_")
        start_urls = [app_config[k] for k in sorted(app_config) if k.startswith("start_url_") and app_config[k]]
        allowed_domain = app_config.get("allowed_domain", "")
        spider_ctx = {
            "application": app_config,
            "spider_name": spider_name,
            "allowed_domains": [allowed_domain] if allowed_domain else [],
            "start_urls": start_urls,
        }
        write_file(scrapy_dir / "spiders" / "base.py", render_template(t, "scrapy/spiders/base.py.jinja", spider_ctx))
        write_file(scrapy_dir / "pipelines.py", render_template(t, "scrapy/pipelines.py.jinja", ctx))

        pw_dir = output_dir / "playwright"
        write_file(pw_dir / "config.py", render_template(t, "playwright/config.py.jinja", ctx))
        write_file(pw_dir / "crawler.py", render_template(t, "playwright/crawler.py.jinja", ctx))

    def render_models(
        self, structs: list[StructDef], app_name: str, output_dir: Path,
    ) -> None:
        t = self.target_lang
        scrapy_dir = output_dir / "scrapy"
        write_file(scrapy_dir / "items.py", render_template(t, "scrapy/items.py.jinja", {"structs": structs}))

    def render_methods(
        self,
        functions: list[FnDef],
        structs: list[StructDef],
        app_name: str,
        ai_results: dict | None,
        output_dir: Path,
    ) -> None:
        from enjinc.template_renderer import _get_ai_code
        t = self.target_lang
        context = {
            "functions": [
                {
                    "fn": fn,
                    "params_str": ", ".join(p.name for p in fn.params),
                    "ai_code": _get_ai_code(ai_results, "fn", fn.name),
                }
                for fn in functions
            ]
        }
        httpx_dir = output_dir / "httpx"
        write_file(httpx_dir / "crawl_tasks.py", render_template(t, "httpx/crawl_tasks.py.jinja", context))

    def render_modules(
        self, modules: list[ModuleDef], output_dir: Path,
    ) -> None:
        t = self.target_lang
        httpx_dir = output_dir / "httpx"
        write_file(httpx_dir / "scheduler.py", render_template(t, "httpx/scheduler.py.jinja", {"modules": modules}))

    def render_routes(
        self,
        routes: list[RouteDef],
        app_name: str,
        ai_results: dict | None,
        output_dir: Path,
        functions: list | None = None,
    ) -> None:
        pass

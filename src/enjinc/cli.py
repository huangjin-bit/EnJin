"""
============================================================
EnJin CLI 入口 (cli.py)
============================================================
提供 `enjinc` 命令行入口：

- enjinc build <source>
- enjinc analyze <source>
- enjinc test <source>
- enjinc verify <source>
- enjinc migrate <old_source> <new_source>

当前 build 流程：
1) 解析 source（单文件或目录下所有 .ej 文件）
2) 执行静态分析（默认开启，可 --skip-analysis 关闭）
3) AI 代码生成（如果 --use-ai，在模板渲染之前执行）
4) 渲染目标代码（AI 结果作为模板变量注入）
5) 测试生成（从 expect 断言生成 pytest/JUnit 文件）
============================================================
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from enjinc.analyzer import EnJinAnalysisError, analyze, assert_valid
from enjinc.ast_nodes import Program
from enjinc.parser import parse_file
from enjinc.template_renderer import RenderConfig, render_program


def _merge_programs(programs: list[Program]) -> Program:
    """将多个 Program 合并为一个编译单元 Program。"""
    merged = Program()

    for program in programs:
        if program.application is not None:
            if merged.application is not None:
                raise ValueError(
                    "Multiple application blocks found in one compilation unit; "
                    "current CLI expects at most one application.ej"
                )
            merged.application = program.application

        merged.structs.extend(program.structs)
        merged.functions.extend(program.functions)
        merged.modules.extend(program.modules)
        merged.routes.extend(program.routes)

    return merged


def _load_program(source: str | Path) -> Program:
    """加载 source 对应的 Program。

    - 文件: 直接 parse_file
    - 目录: 扫描目录下所有 *.ej（非递归）并合并
    """
    source_path = Path(source)

    if source_path.is_file():
        return parse_file(source_path)

    if source_path.is_dir():
        ej_files = sorted(source_path.glob("*.ej"))
        if not ej_files:
            raise FileNotFoundError(f"No .ej files found under directory: {source_path}")

        programs = [parse_file(filepath) for filepath in ej_files]
        return _merge_programs(programs)

    raise FileNotFoundError(f"Source path not found: {source_path}")


def _resolve_target(program: Program, target_override: str | None) -> str:
    """解析目标栈：命令行参数优先，否则读取 application.target，否则默认 python_fastapi。"""
    if target_override:
        return target_override

    if program.application is not None:
        target = program.application.config.get("target")
        if isinstance(target, str) and target:
            return target

    return "python_fastapi"


def _run_ai_generation(
    program: Program,
    target_lang: str,
    provider: str,
    model: str,
    master_provider: str | None = None,
    master_model: str | None = None,
    fn_provider: str | None = None,
    fn_model: str | None = None,
    no_review: bool = False,
) -> dict | None:
    """AI 代码生成：返回 ai_results dict 或 None（失败时）。"""
    try:
        from enjinc.code_generator import create_generator

        generator = create_generator(
            target_lang=target_lang,
            provider=provider,
            model=model,
            use_ai=True,
            master_provider=master_provider,
            master_model=master_model,
            fn_provider=fn_provider,
            fn_model=fn_model,
            no_review=no_review,
        )
        results = generator.generate_program(program)

        if not results:
            return None

        print(f"[enjinc] AI generation: {len(results)} nodes processed")
        return results

    except Exception as exc:
        print(f"[enjinc] AI generation failed: {exc}", file=sys.stderr)
        print("[enjinc] Falling back to scaffold-only output.", file=sys.stderr)
        return None


def _write_ai_debug_file(
    ai_results: dict, output_dir: Path, target_lang: str
) -> None:
    """将 AI 生成结果写入调试用的 generated/ 目录。"""
    from enjinc.targets import get_renderer
    renderer = get_renderer(target_lang)
    ext = renderer.file_extension.lstrip(".") if renderer else "py"
    generated_dir = output_dir / target_lang / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)

    lines = []
    for key, result in ai_results.items():
        lines.append(f"# {'=' * 60}")
        lines.append(f"# Generated: {key}")
        lines.append(f"# {'=' * 60}")
        lines.append(result.generated_code)
        lines.append("")

    (generated_dir / f"generated_code.{ext}").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def build(
    source: str | Path,
    output_dir: str | Path = "output",
    target_override: str | None = None,
    skip_analysis: bool = False,
    use_ai: bool = False,
    provider: str = "openai",
    model: str = "gpt-4",
    master_provider: str | None = None,
    master_model: str | None = None,
    fn_provider: str | None = None,
    fn_model: str | None = None,
    no_review: bool = False,
) -> Path:
    """执行 build 流程并返回产物目录路径。"""
    program = _load_program(source)

    if not skip_analysis:
        assert_valid(program)

    target_lang = _resolve_target(program, target_override)

    # Step 1: AI generation (before template rendering)
    ai_results = None
    if use_ai:
        ai_results = _run_ai_generation(
            program, target_lang, provider, model,
            master_provider=master_provider,
            master_model=master_model,
            fn_provider=fn_provider,
            fn_model=fn_model,
            no_review=no_review,
        )
        if ai_results:
            _write_ai_debug_file(ai_results, Path(output_dir), target_lang)

    # Step 2: Template rendering (with AI results injected as context)
    config = RenderConfig(
        target_lang=target_lang,
        output_dir=Path(output_dir),
        ai_results=ai_results,
    )
    render_program(program, config)

    # Step 3: Test generation from expect assertions
    from enjinc.test_generator import render_tests
    test_output_dir = config.output_dir / target_lang
    fns_with_expect = [fn for fn in program.functions if fn.expect]
    if fns_with_expect:
        test_files = render_tests(fns_with_expect, target_lang, test_output_dir)
        if test_files:
            print(f"[enjinc] generated {len(test_files)} test file(s)")

    return config.output_dir / target_lang


def analyze_source(source: str | Path):
    """执行静态分析并返回 issues。"""
    program = _load_program(source)
    return analyze(program)


def _build_incremental(
    source: str | Path,
    output_dir: str | Path = "output",
    target_override: str | None = None,
    previous: str | None = None,
    skip_analysis: bool = False,
) -> Path:
    """增量构建：只重新渲染变更的节点。"""
    from enjinc.incremental import (
        BuildManifest,
        ChangeSet,
        compute_program_diff,
        compute_render_plan,
    )
    from enjinc.template_renderer import render_program_incremental

    new_program = _load_program(source)
    target_lang = _resolve_target(new_program, target_override)

    if not skip_analysis:
        assert_valid(new_program)

    output_path = Path(output_dir)

    # 获取旧 Program
    if previous:
        old_program = _load_program(previous)
    else:
        # 尝试从 manifest 恢复
        manifest = BuildManifest.load(output_path)
        if manifest and manifest.target_lang == target_lang:
            # 没有 .ej 源文件无法恢复 Program，退回全量构建
            print("[enjinc] --previous not specified, falling back to full build")
            config = RenderConfig(target_lang=target_lang, output_dir=output_path)
            render_program(new_program, config)
            BuildManifest.compute_for(new_program, target_lang, output_path / target_lang).save(output_path)
            return output_path / target_lang
        else:
            print("[enjinc] no previous version found, performing full build")
            config = RenderConfig(target_lang=target_lang, output_dir=output_path)
            render_program(new_program, config)
            BuildManifest.compute_for(new_program, target_lang, output_path / target_lang).save(output_path)
            return output_path / target_lang

    # 计算变更
    change_set = compute_program_diff(old_program, new_program)
    render_plan = compute_render_plan(change_set)

    if not render_plan:
        print("[enjinc] no changes detected, nothing to rebuild")
        return output_path / target_lang

    print(f"[enjinc] incremental build: {len(change_set.direct_changes)} direct change(s), "
          f"{len(render_plan)} node(s) to re-render")

    for c in change_set.direct_changes:
        print(f"  - {c.change_kind} {c.node_type} '{c.node_name}'")

    config = RenderConfig(target_lang=target_lang, output_dir=output_path)
    render_program_incremental(new_program, config, render_plan)

    # 更新 manifest
    BuildManifest.compute_for(new_program, target_lang, output_path / target_lang).save(output_path)

    return output_path / target_lang


def _scaffold_target(args) -> int:
    """生成目标栈扩展的脚手架代码。"""
    name = args.name
    # 从名称推断默认值
    native_lang = args.native_lang or name.split("_")[0]
    extension = args.extension or f".{native_lang}"
    is_plugin = args.plugin

    if is_plugin:
        # 第三方插件：独立 pip 包
        pkg_name = name.replace("-", "_")
        out_dir = Path(args.out) if args.out else Path(f"enjinc-{name}")
        _scaffold_plugin(name, pkg_name, native_lang, extension, out_dir)
    else:
        # 内置目标
        targets_dir = Path(__file__).parent / "targets"
        out_dir = Path(args.out) if args.out else targets_dir / name
        _scaffold_builtin(name, native_lang, extension, out_dir)

    print(f"[enjinc] scaffold created at {out_dir}")
    if is_plugin:
        print(f"[enjinc] next steps:")
        print(f"  cd {out_dir}")
        print(f"  pip install -e .")
        print(f"  enjinc targets   # verify '{name}' appears")
        print(f"  # edit renderer.py and templates/*.jinja")
    else:
        print(f"[enjinc] next steps:")
        print(f"  # edit {out_dir}/renderer.py and templates/*.jinja")
        print(f"  # add '{name}' to _BUILTIN_TARGETS in targets/__init__.py")
    return 0


def _write_file(path: Path, content: str) -> None:
    """写入文件，自动创建父目录。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _scaffold_builtin(name: str, native_lang: str, extension: str, out_dir: Path) -> None:
    """生成内置目标的脚手架。"""
    (out_dir / "templates").mkdir(parents=True, exist_ok=True)

    renderer_code = f'''"""Target renderer for {name}."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from enjinc.ast_nodes import FnDef, ModuleDef, RouteDef, StructDef
from enjinc.targets import register_target, render_template, write_file


@register_target
class _Renderer:
    target_lang = "{name}"
    native_lang = "{native_lang}"
    file_extension = "{extension}"

    def render_infrastructure(
        self, app_name: str, app_config: dict, output_dir: Path,
    ) -> None:
        t = self.target_lang
        ctx = {{"app_name": app_name, "app_config": app_config}}
        # TODO: generate entry point, config, etc.
        # write_file(output_dir / "main{extension}", render_template(t, "main{extension}.jinja", ctx))

    def render_models(
        self, structs: list[StructDef], app_name: str, output_dir: Path,
        app_config: dict | None = None,
    ) -> None:
        t = self.target_lang
        for struct in structs:
            ctx = {{"struct": struct}}
            # TODO: generate model files
            # write_file(output_dir / "models" / f"{{{{struct.name.lower()}}}}{extension}",
            #            render_template(t, "model{extension}.jinja", ctx))

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
        for fn in functions:
            ctx = {{
                "fn": fn,
                "ai_code": _get_ai_code(ai_results, "fn", fn.name),
            }}
            # TODO: generate service files
            # write_file(output_dir / "services" / f"{{{{fn.name}}}}{extension}",
            #            render_template(t, "service{extension}.jinja", ctx))

    def render_modules(
        self, modules: list[ModuleDef], output_dir: Path,
    ) -> None:
        pass  # Optional: implement if your target uses modules

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
        for route in routes:
            ctx = {{
                "route": route,
                "ai_code": _get_ai_code(ai_results, "route", route.name),
            }}
            # TODO: generate route files
            # write_file(output_dir / "routes" / f"{{{{route.name.lower()}}}}{extension}",
            #            render_template(t, "route{extension}.jinja", ctx))
'''
    _write_file(out_dir / "renderer.py", renderer_code)

    # 创建示例模板
    example_template = f"""# {name} template: main
# Context: {{{{ ctx | pprint }}}}

# TODO: implement {name} entry point template
# Available variables: app_name, app_config
"""
    _write_file(out_dir / "templates" / f"main{extension}.jinja", example_template)


def _scaffold_plugin(
    name: str, pkg_name: str, native_lang: str, extension: str, out_dir: Path,
) -> None:
    """生成第三方插件的完整 pip 包脚手架。"""
    src_dir = out_dir / "src" / pkg_name
    templates_dir = src_dir / "templates"

    # pyproject.toml
    pyproject = f'''[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "enjinc-{name}"
version = "0.1.0"
description = "{name} target for EnJin Compiler"
requires-python = ">=3.11"
dependencies = [
    "enjinc>=0.1.0",
]

[project.entry-points."enjinc.targets"]
{name} = "{pkg_name}.renderer"

[tool.setuptools.packages.find]
where = ["src"]
'''
    _write_file(out_dir / "pyproject.toml", pyproject)

    # src/<pkg>/__init__.py
    _write_file(src_dir / "__init__.py", f'"""EnJin target: {name}."""\n')

    # src/<pkg>/renderer.py
    renderer_code = f'''"""Target renderer for {name}."""

from __future__ import annotations

from pathlib import Path

from enjinc.ast_nodes import FnDef, ModuleDef, RouteDef, StructDef
from enjinc.targets import register_target, render_template, write_file
from enjinc.jinja_utils import register_template_dir

# 注册模板目录（让 render_template 能找到本包的模板）
register_template_dir("{name}", Path(__file__).parent / "templates")


@register_target
class Renderer:
    target_lang = "{name}"
    native_lang = "{native_lang}"
    file_extension = "{extension}"

    def render_infrastructure(
        self, app_name: str, app_config: dict, output_dir: Path,
    ) -> None:
        t = self.target_lang
        ctx = {{"app_name": app_name, "app_config": app_config}}
        # TODO: generate entry point, config, etc.
        # write_file(output_dir / "main{extension}",
        #            render_template(t, "main{extension}.jinja", ctx))

    def render_models(
        self, structs: list[StructDef], app_name: str, output_dir: Path,
        app_config: dict | None = None,
    ) -> None:
        t = self.target_lang
        for struct in structs:
            ctx = {{"struct": struct}}
            # TODO: generate model files
            # write_file(output_dir / "models" / f"{{{{struct.name.lower()}}}}{extension}",
            #            render_template(t, "model{extension}.jinja", ctx))

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
        for fn in functions:
            ctx = {{
                "fn": fn,
                "ai_code": _get_ai_code(ai_results, "fn", fn.name),
            }}
            # TODO: generate service files

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
        for route in routes:
            ctx = {{
                "route": route,
                "ai_code": _get_ai_code(ai_results, "route", route.name),
            }}
            # TODO: generate route files
'''
    _write_file(src_dir / "renderer.py", renderer_code)

    # 示例模板
    example = f"""# {name} template: main
# Available: app_name, app_config

# TODO: implement your template
"""
    _write_file(templates_dir / f"main{extension}.jinja", example)

    # README
    readme = f'''# enjinc-{name}

EnJin target for {name}.

## Install

```bash
pip install enjinc-{name}
```

## Usage

```bash
enjinc build app.ej --target {name}
```

## Development

```bash
pip install -e .
enjinc targets  # verify {name} appears
```
'''
    _write_file(out_dir / "README.md", readme)


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口，返回进程退出码。"""
    parser = argparse.ArgumentParser(prog="enjinc", description="EnJin Compiler CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="Parse, analyze, and render source")
    build_parser.add_argument("source", help="Path to .ej file or compilation-unit directory")
    build_parser.add_argument(
        "--out",
        default="output",
        help="Output directory root (default: output)",
    )
    build_parser.add_argument(
        "--target",
        default=None,
        help="Target language override (e.g. python_fastapi)",
    )
    build_parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Skip static analysis before rendering",
    )
    build_parser.add_argument(
        "--use-ai",
        action="store_true",
        help="Enable AI code generation for process intent blocks",
    )
    build_parser.add_argument(
        "--provider",
        default="openai",
        choices=["openai", "deepseek", "anthropic"],
        help="LLM provider (default: openai)",
    )
    build_parser.add_argument(
        "--model",
        default="gpt-4",
        help="LLM model name (default: gpt-4)",
    )
    build_parser.add_argument(
        "--master-provider",
        default=None,
        choices=["openai", "deepseek", "anthropic"],
        help="Master AI reviewer provider (enables review when set)",
    )
    build_parser.add_argument(
        "--master-model",
        default=None,
        help="Master AI reviewer model name",
    )
    build_parser.add_argument(
        "--fn-provider",
        default=None,
        choices=["openai", "deepseek", "anthropic"],
        help="fn layer LLM provider override",
    )
    build_parser.add_argument(
        "--fn-model",
        default=None,
        help="fn layer LLM model name override",
    )
    build_parser.add_argument(
        "--no-review",
        action="store_true",
        help="Disable Master AI review even when master model is configured",
    )
    build_parser.add_argument(
        "--incremental",
        action="store_true",
        help="Incremental build: only re-render changed nodes",
    )
    build_parser.add_argument(
        "--previous",
        default=None,
        help="Path to previous .ej version for incremental diff",
    )

    analyze_parser = subparsers.add_parser("analyze", help="Run static analysis only")
    analyze_parser.add_argument("source", help="Path to .ej file or compilation-unit directory")
    analyze_parser.add_argument(
        "--strict",
        action="store_true",
        help="Return non-zero exit code if analysis issues are found",
    )

    targets_parser = subparsers.add_parser("targets", help="List all available target stacks")

    scaffold_parser = subparsers.add_parser(
        "scaffold-target",
        help="Scaffold a new target extension (built-in or third-party plugin)",
    )
    scaffold_parser.add_argument("name", help="Target name (e.g. go_gin, node_express)")
    scaffold_parser.add_argument(
        "--native-lang",
        default=None,
        help="Native language for escape hatches (e.g. go, javascript)",
    )
    scaffold_parser.add_argument(
        "--extension",
        default=None,
        help="File extension (e.g. .go, .js)",
    )
    scaffold_parser.add_argument(
        "--plugin",
        action="store_true",
        help="Generate as a standalone third-party plugin (pip-installable package)",
    )
    scaffold_parser.add_argument(
        "--out",
        default=None,
        help="Output directory (default: ./<name> or targets/<name> for built-in)",
    )

    test_parser = subparsers.add_parser("test", help="Generate unit tests from expect assertions")
    test_parser.add_argument("source", help="Path to .ej file or compilation-unit directory")
    test_parser.add_argument(
        "--out",
        default="output",
        help="Output directory root (default: output)",
    )
    test_parser.add_argument(
        "--target",
        default=None,
        help="Target language override (e.g. python_fastapi)",
    )

    verify_parser = subparsers.add_parser("verify", help="Verify enjin.lock consistency for CI")
    verify_parser.add_argument("source", help="Path to .ej file or compilation-unit directory")
    verify_parser.add_argument(
        "--lock",
        default=".enjinc/enjin.lock",
        help="Path to enjin.lock file (default: .enjinc/enjin.lock)",
    )
    verify_parser.add_argument(
        "--target",
        default=None,
        help="Target language override",
    )

    migrate_parser = subparsers.add_parser("migrate", help="Generate blue-green migration scripts")
    migrate_parser.add_argument("old_source", help="Path to old .ej version")
    migrate_parser.add_argument("new_source", help="Path to new .ej version")
    migrate_parser.add_argument(
        "--out",
        default="migrations",
        help="Output directory for migration files (default: migrations)",
    )
    migrate_parser.add_argument(
        "--target",
        default="python_fastapi",
        help="Target language (default: python_fastapi)",
    )

    import_parser = subparsers.add_parser("import", help="Import existing project to .ej source")
    import_parser.add_argument("source", help="Path to existing project root directory")
    import_parser.add_argument(
        "--lang",
        choices=["python", "java"],
        required=True,
        help="Source language",
    )
    import_parser.add_argument(
        "--framework",
        default=None,
        help="Framework hint (fastapi, springboot)",
    )
    import_parser.add_argument(
        "--out",
        default="imported.ej",
        help="Output .ej file path (default: imported.ej)",
    )

    args = parser.parse_args(argv)

    # 确保 entry_points 插件被加载（支持 pip install 后立即可用）
    from enjinc.targets import rediscover_targets
    rediscover_targets()

    try:
        if args.command == "build":
            if getattr(args, 'incremental', False):
                artifact_dir = _build_incremental(
                    source=args.source,
                    output_dir=args.out,
                    target_override=args.target,
                    previous=args.previous,
                    skip_analysis=args.skip_analysis,
                )
            else:
                artifact_dir = build(
                    source=args.source,
                    output_dir=args.out,
                    target_override=args.target,
                    skip_analysis=args.skip_analysis,
                    use_ai=args.use_ai,
                    provider=args.provider,
                    model=args.model,
                    master_provider=args.master_provider,
                    master_model=args.master_model,
                    fn_provider=args.fn_provider,
                    fn_model=args.fn_model,
                    no_review=args.no_review,
                )
            print(f"[enjinc] build succeeded: {artifact_dir}")
            return 0

        if args.command == "analyze":
            issues = analyze_source(args.source)
            if not issues:
                print("[enjinc] static analysis passed")
                return 0

            print("[enjinc] static analysis found issues:")
            for issue in issues:
                print(f"- [{issue.code}] {issue.message} ({issue.context})")

            return 2 if args.strict else 0

        if args.command == "targets":
            from enjinc.targets import get_target_info
            targets = get_target_info()
            if not targets:
                print("[enjinc] No targets registered.")
                return 0
            print("Available targets:")
            for t in targets:
                marker = "built-in" if t["source"] == "built-in" else f"plugin: {t['source']}"
                print(f"  {t['name']:<25s} ({marker})")
            return 0

        if args.command == "scaffold-target":
            return _scaffold_target(args)

        if args.command == "test":
            program = _load_program(args.source)
            target_lang = _resolve_target(program, args.target)
            from enjinc.test_generator import render_tests
            test_output_dir = Path(args.out) / target_lang
            fns_with_expect = [fn for fn in program.functions if fn.expect]
            if not fns_with_expect:
                print("[enjinc] no expect assertions found, nothing to generate")
                return 0
            test_files = render_tests(fns_with_expect, target_lang, test_output_dir)
            if test_files:
                print(f"[enjinc] generated {len(test_files)} test file(s):")
                for tf in test_files:
                    print(f"  - {tf}")
            return 0

        if args.command == "verify":
            from enjinc.code_generator import EnjinLock
            program = _load_program(args.source)
            target_lang = _resolve_target(program, args.target)
            lock_path = Path(args.lock)

            if not lock_path.exists():
                print(f"[enjinc] lock file not found: {lock_path}", file=sys.stderr)
                print("[enjinc] CI verify failed: no lock file", file=sys.stderr)
                return 1

            lock = EnjinLock(lock_path)

            # 验证所有非 locked/native/human_maintained 节点都有缓存
            missing = []
            for fn in program.functions:
                is_special = (
                    fn.is_locked
                    or fn.native_blocks
                    or any(a.name == "human_maintained" for a in fn.annotations)
                )
                if is_special:
                    continue
                if fn.process and fn.process.intent:
                    from enjinc.code_generator import CodeGenerator
                    gen = CodeGenerator(target_lang=target_lang, use_ai=False)
                    fn_hash = gen._compute_fn_hash(fn)
                    cached = lock.get(fn_hash, target_lang)
                    if not cached:
                        missing.append(f"fn:{fn.name}")

            if missing:
                print(f"[enjinc] CI verify failed: {len(missing)} node(s) missing from lock:", file=sys.stderr)
                for m in missing:
                    print(f"  - {m}", file=sys.stderr)
                return 1

            print(f"[enjinc] CI verify passed: all {len(program.functions)} fn nodes covered by lock file")
            return 0

        if args.command == "migrate":
            from enjinc.migration import render_migration
            old_program = _load_program(args.old_source)
            new_program = _load_program(args.new_source)
            migrations = render_migration(
                old_program.to_dict(), new_program.to_dict(), args.target,
            )
            if not migrations:
                print("[enjinc] no struct changes detected, no migration needed")
                return 0

            out_dir = Path(args.out)
            out_dir.mkdir(parents=True, exist_ok=True)
            for mig in migrations:
                filepath = out_dir / mig["name"]
                filepath.write_text(mig["content"], encoding="utf-8")
                print(f"  - {filepath}")

            print(f"[enjinc] generated {len(migrations)} migration file(s)")
            return 0

        if args.command == "import":
            from enjinc.importer import import_python_source, import_java_source, program_to_ej
            source_path = Path(args.source)
            if not source_path.is_dir():
                print(f"[enjinc] source directory not found: {source_path}", file=sys.stderr)
                return 1

            if args.lang == "python":
                program = import_python_source(source_path)
            else:
                program = import_java_source(source_path)

            ej_text = program_to_ej(program)
            out_path = Path(args.out)
            out_path.write_text(ej_text, encoding="utf-8")

            print(f"[enjinc] imported {len(program.structs)} structs, "
                  f"{len(program.functions)} fns, {len(program.routes)} routes")
            print(f"[enjinc] output: {out_path}")
            return 0

        print(f"[enjinc] unknown command: {args.command}", file=sys.stderr)
        return 1

    except EnJinAnalysisError as exc:
        print("[enjinc] build blocked by static analysis:", file=sys.stderr)
        for issue in exc.issues:
            print(
                f"- [{issue.code}] {issue.message} ({issue.context})",
                file=sys.stderr,
            )
        return 2
    except Exception as exc:  # pragma: no cover - safety net for CLI UX
        print(f"[enjinc] error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

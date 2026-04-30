"""
============================================================
EnJin 静态分析器 (analyzer.py)
============================================================
本模块在 AST Transform 之后执行，负责核心架构约束校验。

当前已落地的最小规则:
1. route 只能依赖 module，不能依赖 struct/fn
2. route endpoint.handler 必须是所依赖 module 导出的 action
3. module 不能依赖 route（禁止越级）
4. module export 的 target 必须指向存在的 fn
5. module export 的 target 必须在 module.use 中显式声明
6. route 若依赖多个 module，action 名称不能冲突（避免歧义）
7. module-to-module 依赖必须是 DAG（禁止循环依赖）
8. 当 module 声明 @domain 时，禁止直接依赖其他 domain 的 module
9. 注解注册表校验（未知注解 / 作用域 / 参数）
10. @engine 语义校验（重复声明、type 合法性、framework/type 组合）
11. @api_contract 语义校验（禁止 native 实现块）
12. @data_plane 语义校验（禁止 native 实现块）
============================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from enjinc.ast_nodes import Program
from enjinc.parser import parse_file


@dataclass(frozen=True)
class AnalysisIssue:
    """单条静态分析问题。"""

    code: str
    message: str
    context: str

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "context": self.context,
        }


class EnJinAnalysisError(Exception):
    """静态分析失败异常，聚合多条 issue。"""

    def __init__(self, issues: list[AnalysisIssue]):
        self.issues = issues
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        lines = ["Static analysis failed with issues:"]
        for issue in self.issues:
            lines.append(f"- [{issue.code}] {issue.message} ({issue.context})")
        return "\n".join(lines)


_REGISTERED_ANNOTATIONS: set[str] = {
    # Model / field
    "table",
    "primary",
    "auto_increment",
    "unique",
    "max_length",
    "min_length",
    "default",
    "nullable",
    "index",
    "foreign_key",
    # Method
    "locked",
    "human_maintained",
    "transactional",
    "retry",
    "cached",
    "deprecated",
    "data_plane",
    "api_contract",
    # Module
    "engine",
    "domain",
    # Service
    "prefix",
    "auth",
    "rate_limit",
}


_ANNOTATION_ALLOWED_SCOPES: dict[str, set[str]] = {
    "table": {"struct"},
    "primary": {"field"},
    "auto_increment": {"field"},
    "unique": {"field"},
    "max_length": {"field"},
    "min_length": {"field"},
    "default": {"field"},
    "nullable": {"field"},
    "index": {"field"},
    "foreign_key": {"field"},
    "locked": {"fn", "endpoint"},
    "human_maintained": {"fn"},
    "transactional": {"fn"},
    "retry": {"fn"},
    "cached": {"fn"},
    "deprecated": {"fn"},
    "data_plane": {"fn"},
    "api_contract": {"fn"},
    "engine": {"module"},
    "domain": {"module"},
    "prefix": {"route"},
    "auth": {"route"},
    "rate_limit": {"route"},
}


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return _is_int(value) or isinstance(value, float)


def _is_type(value: object, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "int":
        return _is_int(value)
    if expected == "number":
        return _is_number(value)
    if expected == "any":
        return True
    return False


def _validate_no_args(annotation) -> bool:
    return not annotation.args and not annotation.kwargs


def _validate_single_arg(annotation, expected_type: str, kw_name: str) -> bool:
    if annotation.args and annotation.kwargs:
        return False
    if annotation.args:
        return len(annotation.args) == 1 and _is_type(annotation.args[0], expected_type)
    if annotation.kwargs:
        return (
            len(annotation.kwargs) == 1
            and kw_name in annotation.kwargs
            and _is_type(annotation.kwargs[kw_name], expected_type)
        )
    return False


def _validate_two_string_args(
    annotation,
    first_kw: str,
    second_kw: str,
) -> bool:
    if annotation.args and annotation.kwargs:
        return False
    if annotation.args:
        return (
            len(annotation.args) == 2
            and _is_type(annotation.args[0], "string")
            and _is_type(annotation.args[1], "string")
        )
    if annotation.kwargs:
        return (
            len(annotation.kwargs) == 2
            and first_kw in annotation.kwargs
            and second_kw in annotation.kwargs
            and _is_type(annotation.kwargs[first_kw], "string")
            and _is_type(annotation.kwargs[second_kw], "string")
        )
    return False


def _validate_annotation_args(annotation_name: str, annotation) -> bool:
    # domain 在 _extract_module_domain 中做专门校验，避免重复报错
    if annotation_name == "domain":
        return True

    if annotation_name in {
        "primary",
        "auto_increment",
        "unique",
        "nullable",
        "index",
        "locked",
        "human_maintained",
        "transactional",
        "api_contract",
    }:
        return _validate_no_args(annotation)

    if annotation_name == "default":
        return _validate_single_arg(annotation, "any", "value")

    if annotation_name in {"table", "foreign_key", "deprecated", "prefix", "auth"}:
        key_map = {
            "table": "name",
            "foreign_key": "ref",
            "deprecated": "msg",
            "prefix": "path",
            "auth": "strategy",
        }
        return _validate_single_arg(annotation, "string", key_map[annotation_name])

    if annotation_name in {"max_length", "min_length", "retry", "cached", "rate_limit"}:
        key_map = {
            "max_length": "n",
            "min_length": "n",
            "retry": "max",
            "cached": "ttl",
            "rate_limit": "rpm",
        }
        return _validate_single_arg(annotation, "int", key_map[annotation_name])

    if annotation_name == "engine":
        return _validate_two_string_args(annotation, "type", "framework")

    if annotation_name == "data_plane":
        return _validate_two_string_args(annotation, "protocol", "engine")

    return True


def _validate_single_annotation(annotation, scope: str, context: str) -> list[AnalysisIssue]:
    issues: list[AnalysisIssue] = []
    name = annotation.name

    if name not in _REGISTERED_ANNOTATIONS:
        issues.append(
            AnalysisIssue(
                code="ANNOTATION_UNKNOWN",
                message=f"unknown annotation '@{name}'",
                context=context,
            )
        )
        return issues

    allowed_scopes = _ANNOTATION_ALLOWED_SCOPES.get(name, set())
    if scope not in allowed_scopes:
        issues.append(
            AnalysisIssue(
                code="ANNOTATION_INVALID_SCOPE",
                message=(
                    f"annotation '@{name}' is not allowed on {scope}; "
                    f"allowed scopes: {sorted(allowed_scopes)}"
                ),
                context=context,
            )
        )
        return issues

    if not _validate_annotation_args(name, annotation):
        issues.append(
            AnalysisIssue(
                code="ANNOTATION_INVALID_ARGS",
                message=f"annotation '@{name}' has invalid args/kwargs",
                context=context,
            )
        )

    return issues


def _validate_program_annotations(program: Program) -> list[AnalysisIssue]:
    issues: list[AnalysisIssue] = []

    for struct in program.structs:
        for anno in struct.annotations:
            issues.extend(
                _validate_single_annotation(
                    anno,
                    scope="struct",
                    context=f"struct:{struct.name}",
                )
            )

        for field in struct.fields:
            for anno in field.annotations:
                issues.extend(
                    _validate_single_annotation(
                        anno,
                        scope="field",
                        context=f"field:{struct.name}.{field.name}",
                    )
                )

    for fn in program.functions:
        for anno in fn.annotations:
            issues.extend(
                _validate_single_annotation(
                    anno,
                    scope="fn",
                    context=f"fn:{fn.name}",
                )
            )

    for module in program.modules:
        for anno in module.annotations:
            issues.extend(
                _validate_single_annotation(
                    anno,
                    scope="module",
                    context=f"module:{module.name}",
                )
            )

    for route in program.routes:
        for anno in route.annotations:
            issues.extend(
                _validate_single_annotation(
                    anno,
                    scope="route",
                    context=f"route:{route.name}",
                )
            )

        for endpoint in route.endpoints:
            endpoint_ctx = f"endpoint:{route.name}:{endpoint.method} {endpoint.path}"
            for anno in endpoint.annotations:
                issues.extend(
                    _validate_single_annotation(
                        anno,
                        scope="endpoint",
                        context=endpoint_ctx,
                    )
                )

    return issues


def _extract_module_engine(module) -> tuple[tuple[str, str] | None, list[AnalysisIssue]]:
    """提取 module 的 engine 配置并校验重复声明。"""
    issues: list[AnalysisIssue] = []
    engine_annos = [anno for anno in module.annotations if anno.name == "engine"]

    if len(engine_annos) > 1:
        issues.append(
            AnalysisIssue(
                code="MODULE_DUPLICATE_ENGINE_ANNOTATION",
                message=(
                    f"module '{module.name}' has duplicate @engine annotations, "
                    "only one is allowed"
                ),
                context=f"module:{module.name}",
            )
        )

    if not engine_annos:
        return None, issues

    engine_anno = engine_annos[0]
    if not _validate_annotation_args("engine", engine_anno):
        # 参数合法性由 ANNOTATION_INVALID_ARGS 报告，避免重复报错
        return None, issues

    engine_type = engine_anno.kwargs.get("type")
    framework = engine_anno.kwargs.get("framework")

    if engine_type is None and len(engine_anno.args) >= 1:
        engine_type = engine_anno.args[0]
    if framework is None and len(engine_anno.args) >= 2:
        framework = engine_anno.args[1]

    if isinstance(engine_type, str) and isinstance(framework, str):
        return (engine_type, framework), issues

    return None, issues


def _validate_planned_annotation_semantics(
    program: Program,
    module_engines: dict[str, tuple[str, str]],
) -> list[AnalysisIssue]:
    """规划态注解语义级校验（超出参数/作用域）。"""
    issues: list[AnalysisIssue] = []
    supported_engine_types = {"workflow", "state_machine"}

    for module in program.modules:
        engine_cfg = module_engines.get(module.name)
        if not engine_cfg:
            continue

        engine_type, framework = engine_cfg
        if engine_type not in supported_engine_types:
            issues.append(
                AnalysisIssue(
                    code="MODULE_ENGINE_UNSUPPORTED_TYPE",
                    message=(
                        f"module '{module.name}' has unsupported @engine type '{engine_type}', "
                        f"expected one of {sorted(supported_engine_types)}"
                    ),
                    context=f"module:{module.name}",
                )
            )

        if framework == "temporal" and engine_type != "workflow":
            issues.append(
                AnalysisIssue(
                    code="MODULE_ENGINE_FRAMEWORK_TYPE_MISMATCH",
                    message=(
                        f"module '{module.name}' uses framework 'temporal' but @engine type "
                        f"is '{engine_type}', expected 'workflow'"
                    ),
                    context=f"module:{module.name}",
                )
            )

        if framework == "spring_statemachine" and engine_type != "state_machine":
            issues.append(
                AnalysisIssue(
                    code="MODULE_ENGINE_FRAMEWORK_TYPE_MISMATCH",
                    message=(
                        f"module '{module.name}' uses framework 'spring_statemachine' but "
                        f"@engine type is '{engine_type}', expected 'state_machine'"
                    ),
                    context=f"module:{module.name}",
                )
            )

    for fn in program.functions:
        annotation_names = {anno.name for anno in fn.annotations}

        if "api_contract" in annotation_names and fn.native_blocks:
            issues.append(
                AnalysisIssue(
                    code="API_CONTRACT_HAS_NATIVE_IMPL",
                    message=(
                        f"fn '{fn.name}' annotated with @api_contract must not contain native "
                        "implementation blocks"
                    ),
                    context=f"fn:{fn.name}",
                )
            )

        if "data_plane" in annotation_names and fn.native_blocks:
            issues.append(
                AnalysisIssue(
                    code="DATA_PLANE_HAS_NATIVE_IMPL",
                    message=(
                        f"fn '{fn.name}' annotated with @data_plane must not contain native "
                        "implementation blocks"
                    ),
                    context=f"fn:{fn.name}",
                )
            )

    return issues


def _extract_module_domain(module) -> tuple[str | None, list[AnalysisIssue]]:
    """提取 module 的 domain 名称并校验注解形态。"""
    issues: list[AnalysisIssue] = []
    domain_annos = [anno for anno in module.annotations if anno.name == "domain"]

    if len(domain_annos) > 1:
        issues.append(
            AnalysisIssue(
                code="MODULE_DUPLICATE_DOMAIN_ANNOTATION",
                message=(
                    f"module '{module.name}' has duplicate @domain annotations, "
                    "only one is allowed"
                ),
                context=f"module:{module.name}",
            )
        )

    if not domain_annos:
        return None, issues

    domain_anno = domain_annos[0]
    raw_name = domain_anno.kwargs.get("name")
    if raw_name is None and domain_anno.args:
        raw_name = domain_anno.args[0]

    if isinstance(raw_name, str) and raw_name.strip():
        return raw_name.strip(), issues

    issues.append(
        AnalysisIssue(
            code="MODULE_INVALID_DOMAIN_ANNOTATION",
            message=(
                f"module '{module.name}' has invalid @domain annotation, "
                "expected @domain(name=\"...\") or @domain(\"...\")"
            ),
            context=f"module:{module.name}",
        )
    )
    return None, issues


def _detect_module_dependency_cycles(module_map: dict) -> list[AnalysisIssue]:
    """检测 module-to-module 依赖循环。"""
    graph: dict[str, list[str]] = {
        name: [dep for dep in module.dependencies if dep in module_map]
        for name, module in module_map.items()
    }

    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []
    issues: list[AnalysisIssue] = []
    seen_cycles: set[tuple[str, ...]] = set()

    def _dfs(node: str) -> None:
        visiting.add(node)
        stack.append(node)

        for nxt in graph.get(node, []):
            if nxt in visiting:
                cycle_start = stack.index(nxt)
                cycle_path = stack[cycle_start:] + [nxt]
                cycle_key = tuple(cycle_path)
                if cycle_key not in seen_cycles:
                    seen_cycles.add(cycle_key)
                    issues.append(
                        AnalysisIssue(
                            code="MODULE_DEPENDENCY_CYCLE",
                            message=(
                                "module dependency cycle detected: "
                                + " -> ".join(cycle_path)
                            ),
                            context=f"module:{nxt}",
                        )
                    )
            elif nxt not in visited:
                _dfs(nxt)

        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for module_name in graph:
        if module_name not in visited:
            _dfs(module_name)

    return issues


def _validate_modules(
    program: Program,
    module_map: dict[str, "ModuleDef"],
    route_names: set[str],
    fn_names: set[str],
    allowed_module_dependencies: set[str],
    module_domains: dict[str, str],
) -> list[AnalysisIssue]:
    """校验 Module 层：依赖合法性、导出约束、跨域边界。"""
    issues: list[AnalysisIssue] = []

    for module in program.modules:
        for dep in module.dependencies:
            if dep in route_names:
                issues.append(
                    AnalysisIssue(
                        code="MODULE_CANNOT_USE_ROUTE",
                        message=f"module '{module.name}' cannot depend on route '{dep}'",
                        context=f"module:{module.name}",
                    )
                )
                continue

            if dep not in allowed_module_dependencies:
                issues.append(
                    AnalysisIssue(
                        code="MODULE_UNKNOWN_DEPENDENCY",
                        message=f"module '{module.name}' has unknown dependency '{dep}'",
                        context=f"module:{module.name}",
                    )
                )
                continue

            if dep in module_map:
                from_domain = module_domains.get(module.name)
                to_domain = module_domains.get(dep)
                if from_domain and to_domain and from_domain != to_domain:
                    issues.append(
                        AnalysisIssue(
                            code="MODULE_CROSS_DOMAIN_DEPENDENCY",
                            message=(
                                f"module '{module.name}' (domain={from_domain}) cannot directly "
                                f"depend on module '{dep}' (domain={to_domain})"
                            ),
                            context=f"module:{module.name}",
                        )
                    )

        action_names: set[str] = set()
        for export in module.exports:
            if export.action in action_names:
                issues.append(
                    AnalysisIssue(
                        code="MODULE_DUPLICATE_EXPORT_ACTION",
                        message=(
                            f"module '{module.name}' has duplicate export action '{export.action}'"
                        ),
                        context=f"module:{module.name}",
                    )
                )
            action_names.add(export.action)

            if export.target not in fn_names:
                issues.append(
                    AnalysisIssue(
                        code="MODULE_EXPORT_TARGET_NOT_FN",
                        message=(
                            f"module '{module.name}' export action '{export.action}' points to "
                            f"unknown fn '{export.target}'"
                        ),
                        context=f"module:{module.name}",
                    )
                )

            if export.target not in module.dependencies:
                issues.append(
                    AnalysisIssue(
                        code="MODULE_EXPORT_TARGET_NOT_IN_USE",
                        message=(
                            f"module '{module.name}' export action '{export.action}' target "
                            f"'{export.target}' must be declared in use list"
                        ),
                        context=f"module:{module.name}",
                    )
                )

    return issues


def _validate_routes(
    program: Program,
    module_map: dict[str, "ModuleDef"],
    struct_names: set[str],
    fn_names: set[str],
) -> list[AnalysisIssue]:
    """校验 Service (route) 层：依赖层级、action 绑定、导出映射。"""
    issues: list[AnalysisIssue] = []

    for route in program.routes:
        depended_modules = []
        for dep in route.dependencies:
            if dep in module_map:
                depended_modules.append(module_map[dep])
                continue

            if dep in struct_names:
                issues.append(
                    AnalysisIssue(
                        code="ROUTE_CANNOT_USE_MODEL",
                        message=f"route '{route.name}' cannot depend on struct '{dep}'",
                        context=f"route:{route.name}",
                    )
                )
            elif dep in fn_names:
                issues.append(
                    AnalysisIssue(
                        code="ROUTE_CANNOT_USE_METHOD",
                        message=f"route '{route.name}' cannot depend on fn '{dep}'",
                        context=f"route:{route.name}",
                    )
                )
            else:
                issues.append(
                    AnalysisIssue(
                        code="ROUTE_UNKNOWN_DEPENDENCY",
                        message=f"route '{route.name}' has unknown dependency '{dep}'",
                        context=f"route:{route.name}",
                    )
                )

        action_to_module: dict[str, str] = {}
        for module in depended_modules:
            for export in module.exports:
                if export.action in action_to_module and action_to_module[export.action] != module.name:
                    issues.append(
                        AnalysisIssue(
                            code="ROUTE_AMBIGUOUS_ACTION",
                            message=(
                                f"route '{route.name}' action '{export.action}' is exported by "
                                f"multiple modules: '{action_to_module[export.action]}' and '{module.name}'"
                            ),
                            context=f"route:{route.name}",
                        )
                    )
                else:
                    action_to_module[export.action] = module.name

        for endpoint in route.endpoints:
            if endpoint.handler in action_to_module:
                continue

            if endpoint.handler in fn_names:
                issues.append(
                    AnalysisIssue(
                        code="ROUTE_BINDS_RAW_FN",
                        message=(
                            f"route '{route.name}' endpoint '{endpoint.method} {endpoint.path}' "
                            f"binds raw fn '{endpoint.handler}', expected module export action"
                        ),
                        context=f"route:{route.name}",
                    )
                )
            else:
                issues.append(
                    AnalysisIssue(
                        code="ROUTE_ACTION_NOT_EXPORTED",
                        message=(
                            f"route '{route.name}' endpoint '{endpoint.method} {endpoint.path}' "
                            f"handler '{endpoint.handler}' is not exported by depended modules"
                        ),
                        context=f"route:{route.name}",
                    )
                )

    return issues


def analyze(program: Program) -> list[AnalysisIssue]:
    """执行静态分析，返回问题列表（为空表示通过）。"""

    issues: list[AnalysisIssue] = []

    struct_names = {s.name for s in program.structs}
    fn_names = {f.name for f in program.functions}
    module_map = {m.name: m for m in program.modules}
    route_names = {r.name for r in program.routes}

    allowed_module_dependencies = struct_names | fn_names | set(module_map.keys())
    module_domains: dict[str, str] = {}
    module_engines: dict[str, tuple[str, str]] = {}

    issues.extend(_validate_program_annotations(program))

    for module in program.modules:
        domain, domain_issues = _extract_module_domain(module)
        issues.extend(domain_issues)
        if domain is not None:
            module_domains[module.name] = domain

        engine_cfg, engine_issues = _extract_module_engine(module)
        issues.extend(engine_issues)
        if engine_cfg is not None:
            module_engines[module.name] = engine_cfg

    issues.extend(_validate_planned_annotation_semantics(program, module_engines))
    issues.extend(_validate_modules(program, module_map, route_names, fn_names, allowed_module_dependencies, module_domains))
    issues.extend(_detect_module_dependency_cycles(module_map))
    issues.extend(_validate_routes(program, module_map, struct_names, fn_names))

    return issues


def assert_valid(program: Program) -> None:
    """若存在静态分析问题则抛出 EnJinAnalysisError。"""

    issues = analyze(program)
    if issues:
        raise EnJinAnalysisError(issues)


def analyze_file(filepath: str | Path) -> list[AnalysisIssue]:
    """从 .ej 文件路径直接执行静态分析。"""

    program = parse_file(filepath)
    return analyze(program)

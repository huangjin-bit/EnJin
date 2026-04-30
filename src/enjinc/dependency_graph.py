"""
============================================================
EnJin Dependency Graph (dependency_graph.py)
============================================================
从 Program AST 提取轻量级依赖关系图，渲染为文本注入 AI system prompt。

依赖关系:
    - fn → struct (返回类型、参数类型、guard 表达式引用)
    - module → fn (use 声明、export 绑定)
    - route → module (use 声明)
============================================================
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from enjinc.ast_nodes import (
    FnDef,
    ModuleDef,
    Program,
    RouteDef,
    StructDef,
)
from enjinc.constants import ANNO_FOREIGN_KEY, PRIMITIVE_TYPES


@dataclass
class DependencyGraph:
    """从 Program AST 提取的轻量级依赖关系。"""

    structs: dict[str, StructDef]
    functions: dict[str, FnDef]
    modules: dict[str, ModuleDef]
    routes: dict[str, RouteDef]

    fn_to_structs: dict[str, set[str]]
    module_to_fns: dict[str, set[str]]
    route_to_modules: dict[str, set[str]]
    struct_to_structs: dict[str, set[str]]

    @classmethod
    def build(cls, program: Program) -> DependencyGraph:
        """从 Program AST 提取依赖关系。"""
        structs = {s.name: s for s in program.structs}
        functions = {f.name: f for f in program.functions}
        modules = {m.name: m for m in program.modules}
        routes = {r.name: r for r in program.routes}

        struct_names = set(structs.keys())

        fn_to_structs: dict[str, set[str]] = {}
        for fn in program.functions:
            deps: set[str] = set()

            if fn.return_type and fn.return_type.base not in PRIMITIVE_TYPES:
                if fn.return_type.base in struct_names:
                    deps.add(fn.return_type.base)

            for param in fn.params:
                base = param.type.base
                if base not in PRIMITIVE_TYPES and base in struct_names:
                    deps.add(base)
                for p in param.type.params:
                    if isinstance(p, str):
                        if p not in PRIMITIVE_TYPES and p in struct_names:
                            deps.add(p)

            for guard in fn.guard:
                for match in re.finditer(r"exists\((\w+)", guard.expr):
                    name = match.group(1)
                    if name in struct_names:
                        deps.add(name)
                for match in re.finditer(r"\b([A-Z]\w+)\b", guard.expr):
                    name = match.group(1)
                    if name in struct_names:
                        deps.add(name)

            fn_to_structs[fn.name] = deps

        module_to_fns: dict[str, set[str]] = {}
        for mod in program.modules:
            fn_deps: set[str] = set()
            for dep_name in mod.dependencies:
                if dep_name in functions:
                    fn_deps.add(dep_name)
                elif dep_name in structs:
                    pass
            for export in mod.exports:
                if export.target in functions:
                    fn_deps.add(export.target)
            module_to_fns[mod.name] = fn_deps

        route_to_modules: dict[str, set[str]] = {}
        for route in program.routes:
            mod_deps: set[str] = set()
            for dep_name in route.dependencies:
                if dep_name in modules:
                    mod_deps.add(dep_name)
            route_to_modules[route.name] = mod_deps

        # struct→struct: 追踪 foreign_key 关系和字段类型引用
        struct_to_structs: dict[str, set[str]] = {}
        for s in program.structs:
            deps: set[str] = set()
            for f in s.fields:
                if f.type.base in struct_names:
                    deps.add(f.type.base)
                for p in f.type.params:
                    pname = p if isinstance(p, str) else p.base if hasattr(p, "base") else ""
                    if pname in struct_names:
                        deps.add(pname)
                for anno in f.annotations:
                    if anno.name == ANNO_FOREIGN_KEY:
                        target = anno.args[0] if anno.args else anno.kwargs.get("target", "")
                        target_name = target.split(".")[0] if target else ""
                        if target_name in struct_names:
                            deps.add(target_name)
            struct_to_structs[s.name] = deps

        return cls(
            structs=structs,
            functions=functions,
            modules=modules,
            routes=routes,
            fn_to_structs=fn_to_structs,
            module_to_fns=module_to_fns,
            route_to_modules=route_to_modules,
            struct_to_structs=struct_to_structs,
        )

    def render_summary(self) -> str:
        """渲染完整依赖图文本，用于 AI system prompt 注入。"""
        lines = ["## 项目依赖图"]

        if self.structs:
            lines.append("\n### Model 层 (struct)")
            for name, s in self.structs.items():
                field_names = ", ".join(f.name for f in s.fields)
                lines.append(f"- {name}: {field_names}")

        if self.functions:
            lines.append("\n### Method 层 (fn)")
            for name, fn in self.functions.items():
                params_str = ", ".join(
                    f"{p.name}: {p.type.base}" for p in fn.params
                )
                ret = fn.return_type.base if fn.return_type else "void"
                lines.append(f"- {name}({params_str}) -> {ret}")

        if self.modules:
            lines.append("\n### Module 层 (module)")
            for name, mod in self.modules.items():
                use_str = ", ".join(mod.dependencies) if mod.dependencies else "无"
                export_str = ", ".join(
                    f"{e.action}={e.target}" for e in mod.exports
                ) if mod.exports else "无"
                lines.append(f"- {name}:")
                lines.append(f"    use: {use_str}")
                lines.append(f"    export: {export_str}")

        if self.routes:
            lines.append("\n### Service 层 (route)")
            for name, route in self.routes.items():
                annotations_str = ""
                for anno in route.annotations:
                    if anno.args:
                        annotations_str += f" @{anno.name} {anno.args[0]}"
                    elif anno.kwargs:
                        annotations_str += f" @{anno.name} {anno.kwargs}"
                lines.append(f"- {name} ({annotations_str.strip() or '无注解'}):")
                use_str = ", ".join(route.dependencies) if route.dependencies else "无"
                lines.append(f"    use: {use_str}")
                for ep in route.endpoints:
                    locked = " (@locked)" if ep.is_locked else ""
                    lines.append(f"    {ep.method} {ep.path} -> {ep.handler}{locked}")

        call_lines = self._render_call_relations()
        if call_lines:
            lines.append("\n### 调用关系")
            lines.extend(call_lines)

        return "\n".join(lines)

    def render_fn_context(self, fn_name: str) -> str:
        """渲染 fn 的精确依赖上下文（只包含它用到的 struct 字段定义）。"""
        fn = self.functions.get(fn_name)
        if not fn:
            return ""

        deps = self.fn_to_structs.get(fn_name, set())
        if not deps:
            return f"函数 {fn_name} 无外部 struct 依赖。"

        lines = [f"函数 {fn_name} 依赖的 struct:"]
        for struct_name in sorted(deps):
            s = self.structs.get(struct_name)
            if s:
                field_desc = ", ".join(
                    f"{f.name}: {f.type.base}" for f in s.fields
                )
                lines.append(f"- {struct_name}: {field_desc}")
                # 二级依赖：该 struct 引用的其他 struct（foreign_key 等）
                sub_deps = self.struct_to_structs.get(struct_name, set())
                if sub_deps:
                    lines.append(f"  (关联: {', '.join(sorted(sub_deps))})")
            else:
                lines.append(f"- {struct_name} (定义未找到)")

        return "\n".join(lines)

    def render_struct_context(self, struct_name: str) -> str:
        """渲染 struct 的精确上下文（只包含该 struct 自身的字段定义）。"""
        s = self.structs.get(struct_name)
        if not s:
            return ""

        lines = [f"Struct {struct_name} 的字段定义:"]
        for f in s.fields:
            type_name = f.type.base
            if f.type.is_optional:
                type_name = f"Optional[{type_name}]"
            annotations = ", ".join(f"@{a.name}" for a in f.annotations)
            lines.append(f"- {f.name}: {type_name}{'  ' + annotations if annotations else ''}")

        # 哪些 fn 依赖此 struct
        dependent_fns = [fn_name for fn_name, deps in self.fn_to_structs.items() if struct_name in deps]
        if dependent_fns:
            lines.append(f"\n被以下 fn 引用: {', '.join(sorted(dependent_fns))}")

        # struct→struct 依赖（foreign_key 和字段类型引用）
        struct_deps = self.struct_to_structs.get(struct_name, set())
        if struct_deps:
            lines.append(f"\n关联的 struct: {', '.join(sorted(struct_deps))}")

        return "\n".join(lines)

    def render_module_context(self, module_name: str) -> str:
        """渲染 module 的精确上下文（只包含该 module 自身的 fn 签名）。"""
        mod = self.modules.get(module_name)
        if not mod:
            return ""

        lines = [f"Module {module_name}:"]
        lines.append(f"  use: {', '.join(mod.dependencies) if mod.dependencies else '无'}")
        lines.append(f"  export: {', '.join(f'{e.action}={e.target}' for e in mod.exports) if mod.exports else '无'}")

        fn_names = self.module_to_fns.get(module_name, set())
        if fn_names:
            lines.append(f"\nModule {module_name} 管理的 fn 签名:")
            for fn_name in sorted(fn_names):
                fn = self.functions.get(fn_name)
                if fn:
                    params_str = ", ".join(f"{p.name}: {p.type.base}" for p in fn.params)
                    ret = fn.return_type.base if fn.return_type else "void"
                    lines.append(f"- {fn_name}({params_str}) -> {ret}")

        return "\n".join(lines)

    def render_route_context(self, route_name: str) -> str:
        """渲染 route 的精确上下文（module exports + fn 签名）。"""
        route = self.routes.get(route_name)
        if not route:
            return ""

        lines = [f"路由 {route_name} 的上下文:"]

        mod_names = self.route_to_modules.get(route_name, set())
        for mod_name in sorted(mod_names):
            mod = self.modules.get(mod_name)
            if not mod:
                continue
            lines.append(f"\nModule {mod_name} 导出:")
            for export in mod.exports:
                fn = self.functions.get(export.target)
                if fn:
                    params_str = ", ".join(
                        f"{p.name}: {p.type.base}" for p in fn.params
                    )
                    ret = fn.return_type.base if fn.return_type else "void"
                    lines.append(
                        f"  {export.action} => {fn.name}({params_str}) -> {ret}"
                    )
                else:
                    lines.append(f"  {export.action} => {export.target} (未找到)")

        if not mod_names:
            lines.append("无 module 依赖。")

        return "\n".join(lines)

    def _render_call_relations(self) -> list[str]:
        """渲染调用关系文本。"""
        lines = []
        for fn_name, struct_names in self.fn_to_structs.items():
            if struct_names:
                fn = self.functions.get(fn_name)
                reasons = []
                if fn:
                    if fn.return_type and fn.return_type.base in struct_names:
                        reasons.append("返回类型")
                    for p in fn.params:
                        if p.type.base in struct_names:
                            reasons.append("参数类型")
                            break
                    if fn.guard:
                        for g in fn.guard:
                            if any(s in g.expr for s in struct_names):
                                reasons.append("guard")
                                break
                reason_str = " + ".join(reasons) if reasons else "引用"
                struct_str = ", ".join(sorted(struct_names))
                lines.append(f"- {fn_name} 使用 {struct_str} ({reason_str})")

        for mod_name, fn_names in self.module_to_fns.items():
            if fn_names:
                fn_str = ", ".join(sorted(fn_names))
                lines.append(f"- {mod_name} -> [{fn_str}]")

        for route_name, mod_names in self.route_to_modules.items():
            if mod_names:
                route = self.routes.get(route_name)
                handler_str = ""
                if route:
                    handlers = [ep.handler for ep in route.endpoints]
                    if handlers:
                        handler_str = f" -> handlers: {', '.join(handlers)}"
                mod_str = ", ".join(sorted(mod_names))
                lines.append(f"- {route_name} -> [{mod_str}]{handler_str}")

        return lines

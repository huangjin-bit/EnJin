"""
============================================================
EnJin 解析器 (parser.py)
============================================================
本文件实现 .ej 源码的完整解析流程:
    .ej 文本 → Lark Parse Tree → I-AST (ast_nodes.py 数据结构)

核心组件:
    - EnJinTransformer: Lark Transformer 子类，将 Parse Tree 节点
      逐层转化为 ast_nodes.py 中定义的 I-AST 数据结构。
    - parse(): 顶层解析入口函数，接收 .ej 文本，返回 Program 节点。

维护协议:
    1. 本文件的 Transformer 方法名必须与 grammar.lark 中的规则名一一对应。
    2. 修改前需确认 docs/03_compiler_internals/ast_schema.md 已先行更新。

依赖:
    - lark: 解析器生成器
    - ast_nodes: I-AST 数据结构定义
============================================================
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lark import Lark, Transformer, Token

from enjinc.ast_nodes import (
    Annotation,
    ApplicationConfig,
    EndpointDef,
    ExpectAssertion,
    FieldDef,
    FnDef,
    GuardRule,
    HookDef,
    ImportDecl,
    ModuleDef,
    ModuleExport,
    NativeBlock,
    Param,
    ProcessIntent,
    Program,
    RouteDef,
    ScheduleDef,
    StructDef,
    TypeRef,
)

GRAMMAR_PATH = Path(__file__).parent / "grammar.lark"


class EnJinTransformer(Transformer):
    """Lark Transformer: 将 Parse Tree 转化为 I-AST 节点。"""

    def NAME(self, token: Token) -> str:
        return str(token)

    def ESCAPED_STRING(self, token: Token) -> str:
        s = str(token)[1:-1]
        s = s.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
        return s

    def PROCESS_STRING(self, token: Token) -> str:
        s = str(token)[1:-1]
        s = s.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
        return s

    def NUMBER(self, token: Token) -> int | float:
        s = str(token)
        if "." in s:
            return float(s)
        return int(s)

    def HTTP_METHOD(self, token: Token) -> str:
        return str(token)

    def NATIVE_CODE(self, token: Token) -> str:
        return str(token).strip()

    # ----------------------------------------------------------
    # 类型系统
    # ----------------------------------------------------------

    def base_type(self, items: list) -> TypeRef:
        return TypeRef(base=items[0])

    def generic_type(self, items: list) -> TypeRef:
        return TypeRef(base=items[0], params=[items[1]])

    def optional_type(self, items: list) -> TypeRef:
        inner = items[0]
        return TypeRef(base=inner.base, params=inner.params, is_optional=True)

    def enum_type(self, items: list) -> TypeRef:
        return TypeRef(base="Enum", params=items[0])

    def enum_value_list(self, items: list) -> list[str]:
        return list(items)

    # ----------------------------------------------------------
    # 注解系统
    # ----------------------------------------------------------

    def annotation_list(self, items: list) -> list[Annotation]:
        return [i for i in items if isinstance(i, Annotation)]

    def annotation(self, items: list) -> Annotation:
        name = items[0]
        args = []
        kwargs = {}
        if len(items) > 1 and items[1] is not None:
            args, kwargs = items[1]
        return Annotation(name=name, args=args, kwargs=kwargs)

    def annotation_arg_list(self, items: list) -> tuple[list, dict]:
        args = []
        kwargs = {}
        for item in items:
            if isinstance(item, tuple):
                kwargs[item[0]] = item[1]
            else:
                args.append(item)
        return (args, kwargs)

    def annotation_arg(self, items: list) -> Any:
        # 位置参数: "x" / 1
        if len(items) == 1:
            return items[0]
        # 具名参数: key="value" / key=1
        if len(items) == 2 and isinstance(items[0], str):
            return (items[0], items[1])
        return items[0] if items else None

    # ----------------------------------------------------------
    # [Model 层] struct 定义
    # ----------------------------------------------------------

    def struct_def(self, items: list) -> StructDef:
        annotations = []
        name = None
        extends = None
        fields = []
        hooks = []
        for item in items:
            if isinstance(item, list) and all(isinstance(f, FieldDef) for f in item):
                fields = item
            elif isinstance(item, list) and all(isinstance(h, HookDef) for h in item):
                hooks = item
            elif isinstance(item, list):
                # Could be mixed FieldDef + HookDef from struct_body
                fields.extend([x for x in item if isinstance(x, FieldDef)])
                hooks.extend([x for x in item if isinstance(x, HookDef)])
                annotations.extend([x for x in item if isinstance(x, Annotation)])
            elif isinstance(item, str) and name is None:
                name = item
            elif isinstance(item, str) and name is not None:
                extends = item
            elif isinstance(item, dict):
                # struct_body dict with fields and hooks
                fields.extend(item.get("fields", []))
                hooks.extend(item.get("hooks", []))
        return StructDef(name=name or "", annotations=annotations, fields=fields, extends=extends, hooks=hooks)

    def struct_body(self, items: list) -> dict:
        fields = [x for x in items if isinstance(x, FieldDef)]
        hooks = [x for x in items if isinstance(x, HookDef)]
        return {"fields": fields, "hooks": hooks}

    def hook_def(self, items: list) -> HookDef:
        name = items[0]
        intent = items[1].strip('"')
        return HookDef(name=name, intent=intent)

    def field_list(self, items: list) -> list[FieldDef]:
        return list(items)

    def field_def(self, items: list) -> FieldDef:
        name = items[0]
        type_ref = items[1]
        annotations = items[2] if len(items) > 2 and isinstance(items[2], list) else []
        return FieldDef(name=name, type=type_ref, annotations=annotations)

    # ----------------------------------------------------------
    # [Method 层] fn 定义
    # ----------------------------------------------------------

    def fn_def(self, items: list) -> FnDef:
        annotations = []
        name = None
        params = []
        return_type = None
        guard = []
        process = None
        expect = []
        native_blocks = []

        for item in items:
            if isinstance(item, list):
                if all(isinstance(a, Annotation) for a in item):
                    annotations = item
                elif all(isinstance(p, Param) for p in item):
                    params = item
                elif all(isinstance(f, FieldDef) for f in item):
                    pass  # field_list, skip
            elif isinstance(item, Annotation):
                annotations.append(item)
            elif isinstance(item, str) and name is None:
                name = item
            elif isinstance(item, TypeRef):
                return_type = item
            elif isinstance(item, dict):
                guard = item.get("guard", [])
                process = item.get("process")
                expect = item.get("expect", [])
                native_blocks = item.get("native_blocks", [])

        is_locked = any(a.name == "locked" for a in annotations)

        return FnDef(
            name=name or "",
            annotations=annotations,
            params=params,
            return_type=return_type,
            guard=guard,
            process=process,
            expect=expect,
            native_blocks=native_blocks,
            is_locked=is_locked,
        )

    def param_list(self, items: list) -> list[Param]:
        return [i for i in items if isinstance(i, Param)]

    def param(self, items: list) -> Param:
        return Param(name=items[0], type=items[1])

    def fn_body(self, items: list) -> dict:
        result = {"guard": [], "process": None, "expect": [], "native_blocks": []}
        for item in items:
            if isinstance(item, list):
                if item and isinstance(item[0], GuardRule):
                    result["guard"] = item
                elif item and isinstance(item[0], ExpectAssertion):
                    result["expect"] = item
                elif item and isinstance(item[0], NativeBlock):
                    result["native_blocks"] = item
            elif isinstance(item, ProcessIntent):
                result["process"] = item
            elif isinstance(item, NativeBlock):
                result["native_blocks"].append(item)
        return result

    def guard_block(self, items: list) -> list[GuardRule]:
        for item in items:
            if isinstance(item, list):
                return item
        return []

    def guard_rule_list(self, items: list) -> list[GuardRule]:
        return [i for i in items if isinstance(i, GuardRule)]

    def guard_rule(self, items: list) -> GuardRule:
        expr = str(items[0]).strip()
        message = items[1]
        return GuardRule(expr=expr, message=message)

    def guard_expr(self, items: list) -> str:
        return str(items[0]).strip()

    def process_or_native(self, items: list) -> Any:
        if len(items) == 1:
            return items[0]
        return items

    def process_block(self, items: list) -> ProcessIntent:
        return ProcessIntent(intent=items[0])

    def native_block(self, items: list) -> NativeBlock:
        target = items[0]
        code = str(items[1]).strip() if len(items) > 1 else ""
        return NativeBlock(target=target, code=code)

    def native_code_body(self, items: list) -> str:
        return str(items[0]).strip()

    def expect_block(self, items: list) -> list[ExpectAssertion]:
        for item in items:
            if isinstance(item, list):
                return item
        return []

    def expect_rule_list(self, items: list) -> list[ExpectAssertion]:
        return [i for i in items if isinstance(i, ExpectAssertion)]

    def expect_rule(self, items: list) -> ExpectAssertion:
        return ExpectAssertion(raw=str(items[0]).strip())

    # ----------------------------------------------------------
    # [Module 层] module 定义
    # ----------------------------------------------------------

    def module_def(self, items: list) -> ModuleDef:
        annotations = []
        name = None
        body = {"dependencies": [], "exports": [], "init": None, "schedules": []}
        for item in items:
            if isinstance(item, list):
                # annotation_list 可能为空，空列表也应视为合法注解列表
                if not item or isinstance(item[0], Annotation):
                    annotations = item
            elif isinstance(item, dict):
                body = item
            elif isinstance(item, str) and name is None:
                name = item
        return ModuleDef(
            name=name or "",
            annotations=annotations,
            dependencies=body.get("dependencies", []),
            exports=body.get("exports", []),
            init=body.get("init"),
            schedules=body.get("schedules", []),
        )

    def module_body(self, items: list) -> dict:
        result = {"dependencies": [], "exports": [], "init": None, "schedules": []}
        for item in items:
            if isinstance(item, str):
                result["dependencies"].append(item)
            elif isinstance(item, ModuleExport):
                result["exports"].append(item)
            elif isinstance(item, ProcessIntent):
                result["init"] = item
            elif isinstance(item, ScheduleDef):
                result["schedules"].append(item)
        return result

    def export_decl(self, items: list) -> ModuleExport:
        return ModuleExport(action=items[0], target=items[1])

    def use_decl(self, items: list) -> str:
        return items[0]

    def init_block(self, items: list) -> ProcessIntent:
        return ProcessIntent(intent=items[0])

    def schedule_block(self, items: list) -> ScheduleDef:
        return ScheduleDef(frequency=items[0], cron=items[1], intent=items[2])

    # ----------------------------------------------------------
    # [Service 层] route 定义
    # ----------------------------------------------------------

    def route_def(self, items: list) -> RouteDef:
        annotations = []
        name = None
        body = {"dependencies": [], "endpoints": []}
        for item in items:
            if isinstance(item, list):
                if item and isinstance(item[0], Annotation):
                    annotations = item
            elif isinstance(item, dict):
                body = item
            elif isinstance(item, str) and name is None:
                name = item
        return RouteDef(
            name=name or "",
            annotations=annotations,
            dependencies=body.get("dependencies", []),
            endpoints=body.get("endpoints", []),
        )

    def route_body(self, items: list) -> dict:
        result = {"dependencies": [], "endpoints": []}
        for item in items:
            if isinstance(item, str):
                result["dependencies"].append(item)
            elif isinstance(item, EndpointDef):
                result["endpoints"].append(item)
        return result

    def endpoint_def(self, items: list) -> EndpointDef:
        annotations = []
        method = None
        path = None
        handler = None
        for item in items:
            if isinstance(item, list):
                if all(isinstance(a, Annotation) for a in item):
                    annotations = item
            elif isinstance(item, Annotation):
                annotations.append(item)
            elif isinstance(item, str):
                if item in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                    method = item
                elif path is None:
                    path = item
                else:
                    handler = item
        is_locked = any(a.name == "locked" for a in annotations)
        return EndpointDef(
            method=method or "",
            path=path or "",
            handler=handler or "",
            annotations=annotations,
            is_locked=is_locked,
        )

    # ----------------------------------------------------------
    # [全局配置] application
    # ----------------------------------------------------------

    def application_def(self, items: list) -> ApplicationConfig:
        config = {}
        for item in items:
            if isinstance(item, list):
                for entry in item:
                    if isinstance(entry, tuple) and len(entry) == 2:
                        config[entry[0]] = entry[1]
            elif isinstance(item, tuple) and len(item) == 2:
                config[item[0]] = item[1]
        return ApplicationConfig(config=config)

    def config_entry_list(self, items: list) -> list:
        return list(items)

    def config_entry(self, items: list) -> tuple:
        key = items[0]
        if len(items) == 1:
            return (key, None)
        if len(items) == 2 and not isinstance(items[1], list):
            return (key, items[1])
        nested = {}
        for item in items[1:]:
            if isinstance(item, list):
                for entry in item:
                    if isinstance(entry, tuple) and len(entry) == 2:
                        nested[entry[0]] = entry[1]
            elif isinstance(item, tuple) and len(item) == 2:
                nested[item[0]] = item[1]
        return (key, nested)

    def env_call(self, items: list) -> str:
        return f'env("{items[0]}")'

    # ----------------------------------------------------------
    # 顶层规则
    # ----------------------------------------------------------

    def import_decl(self, items: list) -> ImportDecl:
        path = items[0].strip('"')
        return ImportDecl(path=path)

    def start(self, items: list) -> Program:
        program = Program()
        for item in items:
            if item is None:
                continue
            if isinstance(item, StructDef):
                program.structs.append(item)
            elif isinstance(item, FnDef):
                program.functions.append(item)
            elif isinstance(item, ModuleDef):
                program.modules.append(item)
            elif isinstance(item, RouteDef):
                program.routes.append(item)
            elif isinstance(item, ApplicationConfig):
                program.application = item
            elif isinstance(item, ImportDecl):
                program.imports.append(item)
        return program


_parser: Lark | None = None


def _get_parser() -> Lark:
    global _parser
    if _parser is None:
        grammar_text = GRAMMAR_PATH.read_text(encoding="utf-8")
        _parser = Lark(grammar_text, parser="earley", propagate_positions=True)
    return _parser


def parse(source: str) -> Program:
    parser = _get_parser()
    tree = parser.parse(source)
    transformer = EnJinTransformer()
    return transformer.transform(tree)


def parse_file(filepath: str | Path) -> Program:
    path = Path(filepath)
    source = path.read_text(encoding="utf-8")
    return parse(source)

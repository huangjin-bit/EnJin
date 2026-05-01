"""
============================================================
EnJin I-AST 节点定义 (ast_nodes.py)
============================================================
本文件定义了 Intent-AST（意图抽象语法树）的所有数据结构。
这些数据类与 docs/03_compiler_internals/ast_schema.md 严格对应。

维护协议:
    修改任何节点结构前，必须先更新 ast_schema.md，
    经人类审核后方可修改本文件。

使用方式:
    parser.py 中的 Lark Transformer 将 Parse Tree 转化为这些节点。
    后续阶段（模板渲染、Prompt 路由）均以这些节点为输入。
============================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# 公共子结构
# ============================================================


@dataclass
class Annotation:
    """注解节点。

    对应语法: @name 或 @name("arg") 或 @name(key="value")

    Attributes:
        name: 注解名称（不含 @ 前缀）
        args: 位置参数列表
        kwargs: 具名参数字典
    """

    name: str
    args: list = field(default_factory=list)
    kwargs: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "args": self.args,
            "kwargs": self.kwargs,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Annotation:
        return cls(
            name=data["name"],
            args=data.get("args", []),
            kwargs=data.get("kwargs", {}),
        )


@dataclass
class TypeRef:
    """类型引用节点。

    对应语法: Int, String, List<String>, Optional<String>, Enum("a","b")

    Attributes:
        base: 基础类型名 (Int/Float/String/Bool/DateTime/Enum/List/自定义struct名)
        params: 泛型参数列表。List<String> → [TypeRef("String")]，Enum("a","b") → ["a","b"]
        is_optional: 是否为 Optional<T> 包装
    """

    base: str
    params: list = field(default_factory=list)
    is_optional: bool = False

    def to_dict(self) -> dict:
        return {
            "base": self.base,
            "params": [
                p.to_dict() if isinstance(p, TypeRef) else p for p in self.params
            ],
            "is_optional": self.is_optional,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TypeRef:
        params = []
        for p in data.get("params", []):
            if isinstance(p, dict):
                params.append(cls.from_dict(p))
            else:
                params.append(p)
        return cls(base=data["base"], params=params, is_optional=data.get("is_optional", False))


@dataclass
class Param:
    """函数参数节点。

    对应语法: name: Type

    Attributes:
        name: 参数名
        type: 参数类型引用
    """

    name: str
    type: TypeRef

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> Param:
        return cls(name=data["name"], type=TypeRef.from_dict(data["type"]))


# ============================================================
# Model 层 — struct
# ============================================================


@dataclass
class FieldDef:
    """struct 字段定义。

    对应语法: field_name: Type @annotation1 @annotation2(arg)

    Attributes:
        name: 字段名 (snake_case)
        type: 字段类型
        annotations: 字段级注解列表
    """

    name: str
    type: TypeRef
    annotations: list[Annotation] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type.to_dict(),
            "annotations": [a.to_dict() for a in self.annotations],
        }

    @classmethod
    def from_dict(cls, data: dict) -> FieldDef:
        return cls(
            name=data["name"],
            type=TypeRef.from_dict(data["type"]),
            annotations=[Annotation.from_dict(a) for a in data.get("annotations", [])],
        )


@dataclass
class StructDef:
    """Model 层节点: struct 定义。

    对应语法: @table("name") struct Name { fields... }

    Attributes:
        name: struct 名称 (PascalCase)
        annotations: struct 级注解列表
        fields: 字段定义列表
    """

    name: str
    annotations: list[Annotation] = field(default_factory=list)
    fields: list[FieldDef] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "node_type": "struct",
            "name": self.name,
            "annotations": [a.to_dict() for a in self.annotations],
            "fields": [f.to_dict() for f in self.fields],
        }

    @classmethod
    def from_dict(cls, data: dict) -> StructDef:
        return cls(
            name=data["name"],
            annotations=[Annotation.from_dict(a) for a in data.get("annotations", [])],
            fields=[FieldDef.from_dict(f) for f in data.get("fields", [])],
        )


# ============================================================
# Method 层 — fn (三段意图体)
# ============================================================


@dataclass
class GuardRule:
    """guard 块中的单条校验规则。

    对应语法: 表达式 : "错误信息"

    Attributes:
        expr: 布尔表达式原始文本
        message: 校验失败的错误信息
    """

    expr: str
    message: str

    def to_dict(self) -> dict:
        return {
            "expr": self.expr,
            "message": self.message,
        }


@dataclass
class ProcessIntent:
    """process 块: AI 生成入口的意图描述。

    对应语法: process { "自然语言描述" }

    Attributes:
        intent: 自然语言意图文本
        hash: 意图文本的 SHA-256 哈希值（由编译器后续阶段填充）
    """

    intent: str
    hash: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "hash": self.hash,
        }


@dataclass
class ExpectAssertion:
    """expect 块中的单条测试断言。

    对应语法: 函数调用.属性 == 值 或 函数调用.throws("msg")
    注意: Phase 1 中 expect 规则以原始文本捕获，后续阶段再结构化解析。

    Attributes:
        raw: 断言的原始文本
    """

    raw: str

    def to_dict(self) -> dict:
        return {
            "raw": self.raw,
        }


@dataclass
class NativeBlock:
    """native 逃生舱: 原生目标语言代码注入。

    对应语法: native python { ... } 或 native java { ... }

    Attributes:
        target: 目标语言名 ("python", "java")
        code: 原生代码文本（原封不动保留）
    """

    target: str
    code: str

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "code": self.code,
        }


@dataclass
class FnDef:
    """Method 层节点: fn 函数定义。

    包含完整的三段意图体 (guard/process/expect) 或 native 逃生舱。

    Attributes:
        name: 函数名 (snake_case)
        annotations: 函数级注解列表
        params: 参数列表
        return_type: 返回类型（无返回值时为 None）
        guard: guard 校验规则列表（可为空）
        process: process 意图（与 native_blocks 互斥）
        expect: expect 断言列表（可为空）
        native_blocks: native 逃生舱列表（与 process 互斥）
        is_locked: 是否被 @locked 注解锁定
    """

    name: str
    annotations: list[Annotation] = field(default_factory=list)
    params: list[Param] = field(default_factory=list)
    return_type: Optional[TypeRef] = None
    guard: list[GuardRule] = field(default_factory=list)
    process: Optional[ProcessIntent] = None
    expect: list[ExpectAssertion] = field(default_factory=list)
    native_blocks: list[NativeBlock] = field(default_factory=list)
    is_locked: bool = False

    def to_dict(self) -> dict:
        return {
            "node_type": "fn",
            "name": self.name,
            "annotations": [a.to_dict() for a in self.annotations],
            "params": [p.to_dict() for p in self.params],
            "return_type": self.return_type.to_dict() if self.return_type else None,
            "guard": [g.to_dict() for g in self.guard],
            "process": self.process.to_dict() if self.process else None,
            "expect": [e.to_dict() for e in self.expect],
            "native_blocks": [n.to_dict() for n in self.native_blocks],
            "is_locked": self.is_locked,
        }

    @classmethod
    def from_dict(cls, data: dict) -> FnDef:
        return cls(
            name=data["name"],
            annotations=[Annotation.from_dict(a) for a in data.get("annotations", [])],
            params=[Param.from_dict(p) for p in data.get("params", [])],
            return_type=TypeRef.from_dict(data["return_type"]) if data.get("return_type") else None,
            guard=[GuardRule(expr=g["expr"], message=g["message"]) for g in data.get("guard", [])],
            process=ProcessIntent(**data["process"]) if data.get("process") else None,
            expect=[ExpectAssertion(raw=e["raw"]) for e in data.get("expect", [])],
            native_blocks=[NativeBlock(**n) for n in data.get("native_blocks", [])],
            is_locked=data.get("is_locked", False),
        )


# ============================================================
# Module 层 — module
# ============================================================


@dataclass
class ScheduleDef:
    """module 内的调度任务定义。

    对应语法: schedule daily at "02:00" { "意图描述" }

    Attributes:
        frequency: 频率关键字 (daily/hourly/weekly/cron)
        cron: 时间表达式
        intent: 任务意图描述
    """

    frequency: str
    cron: str
    intent: str

    def to_dict(self) -> dict:
        return {
            "frequency": self.frequency,
            "cron": self.cron,
            "intent": self.intent,
        }


@dataclass
class ModuleExport:
    """module 的导出 action 声明。

    对应语法: export action_name = fn_name

    Attributes:
        action: 对外暴露给 route 层的 action 名称
        target: 绑定的内部 fn 名称
    """

    action: str
    target: str

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "target": self.target,
        }


@dataclass
class ModuleDef:
    """Module 层节点: module 定义。

    对应语法: @anno module Name { use ...; export x = fn_y; init { ... }; schedule ... }

    Attributes:
        name: 模块名 (PascalCase)
        annotations: 模块级注解列表
        dependencies: use 声明的依赖名称列表
        exports: 对外导出的 action 列表
        init: 初始化意图（可选）
        schedules: 调度任务列表
    """

    name: str
    annotations: list[Annotation] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    exports: list[ModuleExport] = field(default_factory=list)
    init: Optional[ProcessIntent] = None
    schedules: list[ScheduleDef] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "node_type": "module",
            "name": self.name,
            "annotations": [a.to_dict() for a in self.annotations],
            "dependencies": self.dependencies,
            "exports": [e.to_dict() for e in self.exports],
            "init": self.init.to_dict() if self.init else None,
            "schedules": [s.to_dict() for s in self.schedules],
        }

    @classmethod
    def from_dict(cls, data: dict) -> ModuleDef:
        return cls(
            name=data["name"],
            annotations=[Annotation.from_dict(a) for a in data.get("annotations", [])],
            dependencies=data.get("dependencies", []),
            exports=[ModuleExport(**e) for e in data.get("exports", [])],
            init=ProcessIntent(**data["init"]) if data.get("init") else None,
            schedules=[ScheduleDef(**s) for s in data.get("schedules", [])],
        )


# ============================================================
# Service 层 — route
# ============================================================


@dataclass
class EndpointDef:
    """route 内的单个 HTTP 端点定义。

    对应语法: GET "/path" -> handler_fn

    Attributes:
        method: HTTP 方法 (GET/POST/PUT/DELETE/PATCH)
        path: 路由路径
        handler: 映射的目标函数名
        annotations: 端点级注解
        is_locked: 是否被 @locked 锁定
    """

    method: str
    path: str
    handler: str
    annotations: list[Annotation] = field(default_factory=list)
    is_locked: bool = False

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "path": self.path,
            "handler": self.handler,
            "annotations": [a.to_dict() for a in self.annotations],
            "is_locked": self.is_locked,
        }


@dataclass
class RouteDef:
    """Service 层节点: route 定义。

    对应语法: @prefix("/api") route Name { use ...; endpoints... }

    Attributes:
        name: 服务名 (PascalCase)
        annotations: 服务级注解列表 (如 @prefix, @auth)
        dependencies: use 声明的依赖
        endpoints: HTTP 端点列表
    """

    name: str
    annotations: list[Annotation] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    endpoints: list[EndpointDef] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "node_type": "route",
            "name": self.name,
            "annotations": [a.to_dict() for a in self.annotations],
            "dependencies": self.dependencies,
            "endpoints": [e.to_dict() for e in self.endpoints],
        }

    @classmethod
    def from_dict(cls, data: dict) -> RouteDef:
        return cls(
            name=data["name"],
            annotations=[Annotation.from_dict(a) for a in data.get("annotations", [])],
            dependencies=data.get("dependencies", []),
            endpoints=[
                EndpointDef(
                    method=e["method"], path=e["path"], handler=e["handler"],
                    annotations=[Annotation.from_dict(a) for a in e.get("annotations", [])],
                    is_locked=e.get("is_locked", False),
                ) for e in data.get("endpoints", [])
            ],
        )


# ============================================================
# 全局配置 — application
# ============================================================


@dataclass
class ApplicationConfig:
    """全局配置节点。

    对应语法: application { name: "x"; target: "python_fastapi"; database { ... }; ai { ... } }
    以嵌套字典形式存储所有配置键值对。

    Attributes:
        config: 扁平化/嵌套的配置字典
    """

    config: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "node_type": "application",
            **self.config,
        }


# ============================================================
# 顶层节点 — Program (整个 .ej 文件的解析结果)
# ============================================================


@dataclass
class Program:
    """I-AST 根节点: 一个 .ej 文件的完整解析结果。

    Attributes:
        application: 全局配置（可选，只有 application.ej 中有）
        structs: 所有 struct 定义
        functions: 所有 fn 定义
        modules: 所有 module 定义
        routes: 所有 route 定义
    """

    application: Optional[ApplicationConfig] = None
    structs: list[StructDef] = field(default_factory=list)
    functions: list[FnDef] = field(default_factory=list)
    modules: list[ModuleDef] = field(default_factory=list)
    routes: list[RouteDef] = field(default_factory=list)

    def to_dict(self) -> dict:
        """将整个 I-AST 导出为标准 JSON 字典。

        Returns:
            符合 ast_schema.md 规范的完整字典结构
        """
        return {
            "node_type": "program",
            "application": self.application.to_dict() if self.application else None,
            "structs": [s.to_dict() for s in self.structs],
            "functions": [f.to_dict() for f in self.functions],
            "modules": [m.to_dict() for m in self.modules],
            "routes": [r.to_dict() for r in self.routes],
        }

    @classmethod
    def from_dict(cls, data: dict) -> Program:
        """从 to_dict() 输出重建 Program AST。"""
        app = None
        if data.get("application"):
            cfg = {k: v for k, v in data["application"].items() if k != "node_type"}
            app = ApplicationConfig(config=cfg)

        return cls(
            application=app,
            structs=[StructDef.from_dict(s) for s in data.get("structs", [])],
            functions=[FnDef.from_dict(f) for f in data.get("functions", [])],
            modules=[ModuleDef.from_dict(m) for m in data.get("modules", [])],
            routes=[RouteDef.from_dict(r) for r in data.get("routes", [])],
        )

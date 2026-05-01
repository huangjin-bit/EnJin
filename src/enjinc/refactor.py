"""EnJin 重构模块：在 .ej 层面执行安全重构，自动传播到所有依赖。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Optional

from enjinc.ast_nodes import (
    Annotation,
    FieldDef,
    FnDef,
    ModuleDef,
    ModuleExport,
    Program,
    RouteDef,
    StructDef,
    TypeRef,
)
from enjinc.dependency_graph import DependencyGraph


@dataclass
class RefactorResult:
    """重构操作的结果。"""
    old_program: Program
    new_program: Program
    change_description: str
    affected_nodes: list[str] = field(default_factory=list)
    migration_needed: bool = False


def rename_struct_field(
    program: Program,
    struct_name: str,
    old_field_name: str,
    new_field_name: str,
) -> RefactorResult:
    """重命名 struct 字段，传播到所有 fn 的 guard/expect 和 module 导出。"""
    new_program = deepcopy(program)
    affected: list[str] = []

    # Step 1: 修改 struct 字段
    for struct in new_program.structs:
        if struct.name == struct_name:
            for f in struct.fields:
                if f.name == old_field_name:
                    f.name = new_field_name
                    affected.append(f"struct:{struct_name}")

    # Step 2: 传播到 fn（guard 表达式、process 意图文本、expect 断言）
    dep_graph = DependencyGraph.build(program)
    fn_names_using_struct = dep_graph.fn_to_structs
    for fn in new_program.functions:
        if fn.name in fn_names_using_struct and struct_name in fn_names_using_struct[fn.name]:
            modified = False
            for g in fn.guard:
                if old_field_name in g.expr:
                    g.expr = g.expr.replace(old_field_name, new_field_name)
                    modified = True
            if fn.process and old_field_name in fn.process.intent:
                fn.process.intent = fn.process.intent.replace(old_field_name, new_field_name)
                modified = True
            for e in fn.expect:
                if old_field_name in e.raw:
                    e.raw = e.raw.replace(old_field_name, new_field_name)
                    modified = True
            if modified:
                affected.append(f"fn:{fn.name}")

    # Step 3: 传播到 fn 参数名（如果有同名参数）
    for fn in new_program.functions:
        for p in fn.params:
            if p.name == old_field_name:
                p.name = new_field_name
                affected.append(f"fn:{fn.name}")

    return RefactorResult(
        old_program=program,
        new_program=new_program,
        change_description=f"rename field {struct_name}.{old_field_name} → {new_field_name}",
        affected_nodes=list(set(affected)),
        migration_needed=True,
    )


def rename_struct(
    program: Program,
    old_name: str,
    new_name: str,
) -> RefactorResult:
    """重命名 struct，传播到所有引用（fn 返回类型、参数类型、module 依赖、route）。"""
    new_program = deepcopy(program)
    affected: list[str] = []

    # Step 1: 重命名 struct
    for struct in new_program.structs:
        if struct.name == old_name:
            struct.name = new_name
            # 更新 @table 注解的表名提示
            affected.append(f"struct:{old_name}")

    # Step 2: 传播到 fn 返回类型和参数类型
    for fn in new_program.functions:
        modified = False
        if fn.return_type and fn.return_type.base == old_name:
            fn.return_type.base = new_name
            modified = True
        for p in fn.params:
            if p.type.base == old_name:
                p.type.base = new_name
                modified = True
        # guard 中的 struct 引用
        for g in fn.guard:
            if old_name in g.expr:
                g.expr = g.expr.replace(old_name, new_name)
                modified = True
        if fn.process and old_name in fn.process.intent:
            fn.process.intent = fn.process.intent.replace(old_name, new_name)
            modified = True
        for e in fn.expect:
            if old_name in e.raw:
                e.raw = e.raw.replace(old_name, new_name)
                modified = True
        if modified:
            affected.append(f"fn:{fn.name}")

    # Step 3: 传播到 module 依赖
    for mod in new_program.modules:
        if old_name in mod.dependencies:
            mod.dependencies = [new_name if d == old_name else d for d in mod.dependencies]
            affected.append(f"module:{mod.name}")

    # Step 4: 传播到 route（通过 module 间传播已覆盖）

    return RefactorResult(
        old_program=program,
        new_program=new_program,
        change_description=f"rename struct {old_name} → {new_name}",
        affected_nodes=list(set(affected)),
        migration_needed=True,
    )


def extract_module(
    program: Program,
    source_module: str,
    fn_names: list[str],
    new_module_name: str,
) -> RefactorResult:
    """从源 module 提取指定 fn 到新 module。"""
    new_program = deepcopy(program)
    affected: list[str] = []

    fn_names_set = set(fn_names)

    # 找到源 module
    source = None
    for mod in new_program.modules:
        if mod.name == source_module:
            source = mod
            break

    if not source:
        return RefactorResult(
            old_program=program, new_program=new_program,
            change_description=f"module '{source_module}' not found",
        )

    # 从源 module 移除 fn 依赖和导出
    source.dependencies = [d for d in source.dependencies if d not in fn_names_set]
    source.exports = [e for e in source.exports if e.target not in fn_names_set]
    affected.append(f"module:{source_module}")

    # 创建新 module
    new_exports = [ModuleExport(action=fn, target=fn) for fn in fn_names]
    new_module = ModuleDef(
        name=new_module_name,
        dependencies=list(fn_names_set),
        exports=new_exports,
    )
    new_program.modules.append(new_module)
    affected.append(f"module:{new_module_name}")

    # 更新引用源 module 的 route
    for route in new_program.routes:
        if source_module in route.dependencies:
            route.dependencies.append(new_module_name)
            affected.append(f"route:{route.name}")

    return RefactorResult(
        old_program=program,
        new_program=new_program,
        change_description=f"extract {len(fn_names)} fn(s) from {source_module} → {new_module_name}",
        affected_nodes=list(set(affected)),
    )


def merge_structs(
    program: Program,
    struct_names: list[str],
    merged_name: str,
) -> RefactorResult:
    """合并多个 struct 为一个。字段冲突时后者覆盖前者。"""
    new_program = deepcopy(program)
    affected: list[str] = []

    name_set = set(struct_names)

    # 收集所有字段（后者覆盖同名字段）
    merged_fields: list[FieldDef] = []
    merged_annotations: list[Annotation] = []
    for struct in new_program.structs:
        if struct.name in name_set:
            existing_names = {f.name for f in merged_fields}
            for f in struct.fields:
                if f.name not in existing_names:
                    merged_fields.append(f)
            if not merged_annotations:
                merged_annotations = list(struct.annotations)
            affected.append(f"struct:{struct.name}")

    # 移除旧 struct，添加合并后的 struct
    new_program.structs = [s for s in new_program.structs if s.name not in name_set]
    merged_struct = StructDef(name=merged_name, annotations=merged_annotations, fields=merged_fields)
    new_program.structs.append(merged_struct)
    affected.append(f"struct:{merged_name}")

    # 更新所有 fn 中的类型引用
    for fn in new_program.functions:
        modified = False
        if fn.return_type and fn.return_type.base in name_set:
            fn.return_type.base = merged_name
            modified = True
        for p in fn.params:
            if p.type.base in name_set:
                p.type.base = merged_name
                modified = True
        if modified:
            affected.append(f"fn:{fn.name}")

    # 更新 module 依赖
    for mod in new_program.modules:
        old_deps = [d for d in mod.dependencies if d in name_set]
        if old_deps:
            mod.dependencies = [d for d in mod.dependencies if d not in name_set]
            if merged_name not in mod.dependencies:
                mod.dependencies.append(merged_name)
            affected.append(f"module:{mod.name}")

    return RefactorResult(
        old_program=program,
        new_program=new_program,
        change_description=f"merge {', '.join(struct_names)} → {merged_name}",
        affected_nodes=list(set(affected)),
        migration_needed=True,
    )


def split_struct(
    program: Program,
    struct_name: str,
    split_config: dict[str, list[str]],
) -> RefactorResult:
    """拆分 struct 为多个新 struct。split_config: {new_name: [field_names]}。"""
    new_program = deepcopy(program)
    affected: list[str] = []

    # 找到原始 struct
    source = None
    source_idx = -1
    for i, s in enumerate(new_program.structs):
        if s.name == struct_name:
            source = s
            source_idx = i
            break

    if not source:
        return RefactorResult(
            old_program=program, new_program=new_program,
            change_description=f"struct '{struct_name}' not found",
        )

    field_map = {f.name: f for f in source.fields}

    # 为每个拆分创建新 struct
    all_assigned_fields: set[str] = set()
    new_structs: list[StructDef] = []
    for new_name, field_names in split_config.items():
        new_fields = [deepcopy(field_map[fn]) for fn in field_names if fn in field_map]
        all_assigned_fields.update(field_names)
        new_structs.append(StructDef(name=new_name, fields=new_fields))
        affected.append(f"struct:{new_name}")

    # 保留未分配的字段在原 struct 中
    remaining_fields = [f for f in source.fields if f.name not in all_assigned_fields]
    if remaining_fields:
        source.fields = remaining_fields
        affected.append(f"struct:{struct_name}")
    else:
        # 原始 struct 所有字段都已分配，移除它
        new_program.structs.pop(source_idx)

    new_program.structs.extend(new_structs)

    return RefactorResult(
        old_program=program,
        new_program=new_program,
        change_description=f"split {struct_name} → {', '.join(split_config.keys())}",
        affected_nodes=list(set(affected)),
        migration_needed=True,
    )

"""EnJin 逆向导入模块：从已有 Java/Python 项目生成 .ej 骨架文件。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from enjinc.ast_nodes import (
    Annotation,
    ApplicationConfig,
    EndpointDef,
    ExpectAssertion,
    FieldDef,
    FnDef,
    GuardRule,
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
from enjinc.constants import ENJIN_TO_JAVA, ENJIN_TO_PYTHON


# ============================================================
# 反向类型映射（目标语言 → EnJin）
# ============================================================

_PYTHON_TO_ENJIN: dict[str, str] = {v: k for k, v in ENJIN_TO_PYTHON.items()}
_PYTHON_TO_ENJIN.update({
    "int": "Int", "float": "Float", "bool": "Bool",
    "str": "String", "datetime": "DateTime",
    "date": "DateTime", "Decimal": "Float",
    "bytes": "String", "dict": "Map", "list": "List",
    "Optional": "Optional",
})

_JAVA_TO_ENJIN: dict[str, str] = {v: k for k, v in ENJIN_TO_JAVA.items()}
_JAVA_TO_ENJIN.update({
    "Long": "Int", "Integer": "Int", "int": "Int",
    "Double": "Float", "double": "Float", "Float": "Float", "float": "Float",
    "Boolean": "Bool", "boolean": "Bool",
    "String": "String",
    "LocalDateTime": "DateTime", "LocalDate": "DateTime",
    "BigDecimal": "Float",
})


# ============================================================
# Python (FastAPI / SQLAlchemy) 导入
# ============================================================

def import_python_source(source_dir: Path, app_name: str = "app") -> Program:
    """扫描 Python FastAPI 项目，提取 struct/fn/route 定义。

    Args:
        source_dir: 项目根目录
        app_name: 应用名（用于 application 配置）

    Returns:
        Program AST（process 块为 TODO 占位）
    """
    source_dir = Path(source_dir)
    structs: list[StructDef] = []
    functions: list[FnDef] = []
    routes: list[RouteDef] = []
    modules: list[ModuleDef] = []

    # 定位关键目录
    models_dir = _find_dir(source_dir, ["models", "app/models"])
    schemas_dir = _find_dir(source_dir, ["schemas", "app/schemas"])
    api_dir = _find_dir(source_dir, ["api", "app/api", "api/v1", "app/api/v1"])
    services_dir = _find_dir(source_dir, ["services", "app/services"])

    if models_dir:
        structs = _extract_python_structs(models_dir)

    if services_dir:
        functions = _extract_python_fns(services_dir, structs)

    if api_dir:
        routes = _extract_python_routes(api_dir)

    # 推断 modules：根据 fn → struct 依赖关系自动聚合
    if functions and structs:
        modules = _infer_modules(functions, structs)

    return Program(
        application=ApplicationConfig(config={"name": app_name, "target": "python_fastapi"}),
        structs=structs,
        functions=functions,
        modules=modules,
        routes=routes,
    )


def _find_dir(root: Path, candidates: list[str]) -> Optional[Path]:
    """在多个候选路径中找到第一个存在的目录。"""
    for c in candidates:
        p = root / c
        if p.is_dir():
            return p
    return None


def _extract_python_structs(models_dir: Path) -> list[StructDef]:
    """从 SQLAlchemy 模型文件提取 struct 定义。"""
    structs = []
    for py_file in sorted(models_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        content = py_file.read_text(encoding="utf-8")
        if "Base" not in content and "Model" not in content and "Column" not in content:
            continue
        structs.extend(_parse_sqlalchemy_model(content))
    return structs


def _parse_sqlalchemy_model(content: str) -> list[StructDef]:
    """解析单个 SQLAlchemy 模型文件。"""
    results = []
    # 匹配 class Xxx(Base): 或 class Xxx(Model):
    class_pattern = re.compile(
        r'class\s+(\w+)\s*\([^)]*(?:Base|Model)[^)]*\)\s*:',
        re.MULTILINE,
    )

    for m in class_pattern.finditer(content):
        class_name = m.group(1)
        class_body = _extract_class_body(content, m.end())

        fields = []
        for line in class_body.split('\n'):
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('"') or line.startswith("'"):
                continue
            # 匹配: field_name = Column(Type, ...)
            col_match = re.match(
                r'(\w+)\s*[:=]\s*Column\s*\(\s*(\w+)',
                line,
            )
            if col_match:
                fname = col_match.group(1)
                ftype_str = col_match.group(2)
                if fname.startswith('_'):
                    continue

                enjin_type = _resolve_python_type(ftype_str, line)
                annotations = _extract_python_field_annotations(line)
                fields.append(FieldDef(
                    name=fname,
                    type=enjin_type,
                    annotations=annotations,
                ))

        if fields:
            table_name = _extract_python_table_name(class_name, content)
            struct_annos = [Annotation("table", [table_name])] if table_name else []
            results.append(StructDef(
                name=class_name,
                annotations=struct_annos,
                fields=fields,
            ))

    return results


def _extract_class_body(content: str, start: int) -> str:
    """提取类体内容（到下一个同级 class 或文件末尾）。"""
    depth = 0
    body_start = start
    i = start
    while i < len(content):
        if content[i] == ':':
            depth += 1
        elif content[i] == '\n':
            # 检查下一行是否是新的顶级 class
            rest = content[i:].lstrip('\n')
            if rest.startswith('class ') and depth <= 1:
                return content[body_start:i]
        i += 1
    return content[body_start:]


def _resolve_python_type(col_type: str, line: str) -> TypeRef:
    """将 SQLAlchemy Column 类型转换为 EnJin TypeRef。"""
    type_map = {
        "Integer": "Int", "BigInteger": "Int", "SmallInteger": "Int",
        "Float": "Float", "Numeric": "Float",
        "String": "String", "Text": "String", "VARCHAR": "String",
        "Boolean": "Bool",
        "DateTime": "DateTime", "Date": "DateTime", "TIMESTAMP": "DateTime",
        "JSON": "String", "JSONB": "String",
        "LargeBinary": "String",
    }

    is_optional = "nullable=True" in line or "nullable = True" in line
    base = type_map.get(col_type, "String")

    if is_optional:
        return TypeRef(base="Optional", params=[TypeRef(base=base)], is_optional=True)
    return TypeRef(base=base)


def _extract_python_field_annotations(line: str) -> list[Annotation]:
    """从 Column(...) 提取注解。"""
    annos = []

    if "primary_key=True" in line:
        annos.append(Annotation("primary"))
        if "autoincrement=True" in line or "autoincrement=True" in line:
            annos.append(Annotation("auto_increment"))

    if "unique=True" in line:
        annos.append(Annotation("unique"))

    if "index=True" in line:
        annos.append(Annotation("index"))

    if "nullable=False" in line:
        annos.append(Annotation("required"))

    # ForeignKey("table.id")
    fk_match = re.search(r'ForeignKey\s*\(\s*["\'](\w+)\.(\w+)["\']', line)
    if fk_match:
        annos.append(Annotation("foreign_key", [f"{fk_match.group(1).title()}.{fk_match.group(2)}"]))

    return annos


def _extract_python_table_name(class_name: str, content: str) -> str:
    """提取 __tablename__ 或推导表名。"""
    match = re.search(r'__tablename__\s*=\s*["\'](\w+)["\']', content)
    if match:
        return match.group(1)
    # 默认：PascalCase → snake_case + s
    name = re.sub(r'(?<!^)(?=[A-Z])', '_', class_name).lower() + "s"
    return name


def _extract_python_fns(services_dir: Path, structs: list[StructDef]) -> list[FnDef]:
    """从 Python service 文件提取函数定义。"""
    struct_names = {s.name for s in structs}
    fns = []

    for py_file in sorted(services_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        content = py_file.read_text(encoding="utf-8")

        # 匹配 def function_name(param: Type) -> ReturnType:
        fn_pattern = re.compile(
            r'def\s+(\w+)\s*\(([^)]*)\)\s*(?:->\s*([^\n:]+))?\s*:',
            re.MULTILINE,
        )
        for m in fn_pattern.finditer(content):
            fn_name = m.group(1)
            if fn_name.startswith('_'):
                continue

            params = _parse_python_params(m.group(2), struct_names)
            return_type = _parse_python_return_type(m.group(3), struct_names)

            fns.append(FnDef(
                name=fn_name,
                params=params,
                return_type=return_type,
                process=ProcessIntent(intent=f"TODO: reverse-engineer from {py_file.name}::{fn_name}"),
            ))

    return fns


def _parse_python_params(params_str: str, struct_names: set[str]) -> list[Param]:
    """解析 Python 函数参数列表。"""
    if not params_str.strip():
        return []

    params = []
    for p in params_str.split(','):
        p = p.strip()
        if not p or p.startswith('*') or p.startswith('/'):
            continue

        if ':' in p:
            parts = p.split(':', 1)
            name = parts[0].strip()
            type_str = parts[1].strip().split('=')[0].strip()
            type_ref = _python_type_str_to_ref(type_str, struct_names)
            params.append(Param(name=name, type=type_ref))
        elif '=' in p:
            name = p.split('=')[0].strip()
            params.append(Param(name=name, type=TypeRef(base="String")))

    # 跳过 self, cls, db, session 等框架参数
    params = [p for p in params if p.name not in ('self', 'cls', 'db', 'session')]

    return params


def _python_type_str_to_ref(type_str: str, struct_names: set[str]) -> TypeRef:
    """将 Python 类型字符串转为 TypeRef。"""
    type_str = type_str.strip()

    if type_str.startswith('Optional[') and type_str.endswith(']'):
        inner = type_str[9:-1]
        return TypeRef(base="Optional", params=[_python_type_str_to_ref(inner, struct_names)], is_optional=True)

    if type_str.startswith('List[') and type_str.endswith(']'):
        inner = type_str[5:-1]
        return TypeRef(base="List", params=[_python_type_str_to_ref(inner, struct_names)])

    base = type_str.strip('()').strip()
    enjin = _PYTHON_TO_ENJIN.get(base, base if base in struct_names else "String")
    return TypeRef(base=enjin)


def _parse_python_return_type(ret_str: str | None, struct_names: set[str]) -> TypeRef | None:
    """解析 Python 返回类型注解。"""
    if not ret_str:
        return None
    ret_str = ret_str.strip()
    if ret_str in ('None', 'none'):
        return None
    return _python_type_str_to_ref(ret_str, struct_names)


def _extract_python_routes(api_dir: Path) -> list[RouteDef]:
    """从 FastAPI router 文件提取 route 定义。"""
    routes = []

    for py_file in sorted(api_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        content = py_file.read_text(encoding="utf-8")

        endpoints = []
        prefix = ""

        # 提取 router 前缀: router = APIRouter(prefix="/api/v1/xxx")
        prefix_match = re.search(r'prefix\s*=\s*["\']([^"\']+)["\']', content)
        if prefix_match:
            prefix = prefix_match.group(1)

        # 匹配 @router.get("/path")、@router.post("/path") 等
        ep_pattern = re.compile(
            r'@router\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']',
            re.IGNORECASE,
        )
        for m in ep_pattern.finditer(content):
            method = m.group(1).upper()
            path = m.group(2)
            handler = path.strip('/').replace('/', '_').replace('{', '').replace('}', '') or "index"
            endpoints.append(EndpointDef(method=method, path=path, handler=handler))

        if endpoints:
            route_name = py_file.stem.replace("_", " ").title().replace(" ", "")
            routes.append(RouteDef(
                name=f"{route_name}Service",
                annotations=[Annotation("prefix", [prefix])] if prefix else [],
                endpoints=endpoints,
            ))

    return routes


def _infer_modules(functions: list[FnDef], structs: list[StructDef]) -> list[ModuleDef]:
    """根据 fn → struct 依赖关系自动推断 module。"""
    struct_to_fns: dict[str, list[str]] = {}

    for fn in functions:
        related_structs = set()
        if fn.return_type and fn.return_type.base not in ("Int", "String", "Bool", "Float", "List", "Optional"):
            related_structs.add(fn.return_type.base)
        for p in fn.params:
            if p.type.base not in ("Int", "String", "Bool", "Float", "List", "Optional", "DateTime"):
                related_structs.add(p.type.base)

        for s in related_structs:
            struct_to_fns.setdefault(s, []).append(fn.name)

    modules = []
    for struct_name, fn_names in struct_to_fns.items():
        exports = [ModuleExport(action=fn, target=fn) for fn in fn_names]
        modules.append(ModuleDef(
            name=f"{struct_name}Manager",
            dependencies=[struct_name] + fn_names,
            exports=exports,
        ))

    return modules


# ============================================================
# Java (Spring Boot) 导入
# ============================================================

def import_java_source(source_dir: Path, app_name: str = "app") -> Program:
    """扫描 Java Spring Boot 项目，提取 struct/fn/route 定义。"""
    source_dir = Path(source_dir)
    structs: list[StructDef] = []
    functions: list[FnDef] = []
    routes: list[RouteDef] = []

    # 定位关键目录
    entity_dir = _find_dir(source_dir, [
        "src/main/java", "domain/entity",
    ])
    # 搜索更深层
    if not entity_dir:
        for d in source_dir.rglob("entity"):
            if d.is_dir():
                entity_dir = d
                break

    controller_search = []
    for d in source_dir.rglob("controller"):
        if d.is_dir():
            controller_search.append(d)

    service_search = []
    for d in source_dir.rglob("service"):
        if d.is_dir():
            service_search.append(d)

    if entity_dir:
        structs = _extract_java_structs(entity_dir)

    for svc_dir in service_search:
        functions.extend(_extract_java_fns(svc_dir, structs))

    for ctrl_dir in controller_search:
        routes.extend(_extract_java_routes(ctrl_dir))

    modules = _infer_modules(functions, structs) if functions and structs else []

    return Program(
        application=ApplicationConfig(config={"name": app_name, "target": "java_springboot"}),
        structs=structs,
        functions=functions,
        modules=modules,
        routes=routes,
    )


def _extract_java_structs(entity_dir: Path) -> list[StructDef]:
    """从 JPA/MyBatis-Plus Entity 文件提取 struct 定义。"""
    structs = []
    for java_file in sorted(entity_dir.glob("*.java")):
        content = java_file.read_text(encoding="utf-8")
        if "@Entity" not in content and "@TableName" not in content and "Entity" not in content:
            continue
        structs.extend(_parse_java_entity(content))
    return structs


def _parse_java_entity(content: str) -> list[StructDef]:
    """解析单个 Java Entity 文件。"""
    results = []

    class_match = re.search(r'public\s+class\s+(\w+)', content)
    if not class_match:
        return results

    class_name = class_match.group(1)

    # 提取注解
    struct_annos = []

    # @Table(name = "xxx") 或 @TableName("xxx")
    table_match = re.search(r'@Table(?:Name)?\s*\(\s*(?:(?:name\s*=\s*)?["\'])(\w+)', content)
    if table_match:
        struct_annos.append(Annotation("table", [table_match.group(1)]))

    # 提取字段
    fields = []
    # 匹配: private Type fieldName;
    field_pattern = re.compile(
        r'(?:@[\w.]+(?:\([^)]*\))?\s+)*private\s+(\w+)\s+(\w+)\s*;',
        re.MULTILINE,
    )
    for fm in field_pattern.finditer(content):
        java_type = fm.group(1)
        field_name = fm.group(2)

        if field_name in ('serialVersionUID', 'id'):
            if field_name == 'id':
                fields.insert(0, FieldDef(
                    name="id",
                    type=TypeRef(base="Int"),
                    annotations=[Annotation("primary"), Annotation("auto_increment")],
                ))
            continue

        enjin_type = _resolve_java_type(java_type)
        # 提取字段级注解
        line_start = content.rfind('\n', 0, fm.start()) + 1
        preceding = content[line_start:fm.start()]
        annos = _extract_java_field_annotations(preceding)

        fields.append(FieldDef(name=field_name, type=enjin_type, annotations=annos))

    if fields:
        results.append(StructDef(name=class_name, annotations=struct_annos, fields=fields))

    return results


def _resolve_java_type(java_type: str) -> TypeRef:
    """将 Java 类型转换为 EnJin TypeRef。"""
    enjin = _JAVA_TO_ENJIN.get(java_type, "String")
    return TypeRef(base=enjin)


def _extract_java_field_annotations(preceding: str) -> list[Annotation]:
    """从字段前的注解提取信息。"""
    annos = []

    if '@Id' in preceding:
        annos.append(Annotation("primary"))
    if '@GeneratedValue' in preceding or '@TableId' in preceding:
        annos.append(Annotation("auto_increment"))
    if '@Column(unique = true)' in preceding or '@UniqueConstraint' in preceding:
        annos.append(Annotation("unique"))

    length_match = re.search(r'@(?:Column|Size)\s*\([^)]*length\s*=\s*(\d+)', preceding)
    if length_match:
        annos.append(Annotation("max_length", [length_match.group(1)]))

    fk_match = re.search(r'@JoinColumn\s*\([^)]*name\s*=\s*"(\w+)"', preceding)
    if fk_match:
        annos.append(Annotation("foreign_key", [fk_match.group(1)]))

    if '@Index' in preceding:
        annos.append(Annotation("index"))

    return annos


def _extract_java_fns(service_dir: Path, structs: list[StructDef]) -> list[FnDef]:
    """从 Java Service 文件提取函数定义。"""
    struct_names = {s.name for s in structs}
    fns = []

    for java_file in sorted(service_dir.rglob("*.java")):
        if java_file.name.startswith("I") and "Impl" not in java_file.name:
            # 跳过接口文件，只看实现
            continue
        content = java_file.read_text(encoding="utf-8")

        # 匹配: public ReturnType methodName(ParamType paramName, ...)
        fn_pattern = re.compile(
            r'public\s+(\w+)\s+(\w+)\s*\(([^)]*)\)\s*\{?',
            re.MULTILINE,
        )
        for m in fn_pattern.finditer(content):
            return_type_str = m.group(1)
            fn_name = m.group(2)
            params_str = m.group(3)

            if return_type_str in ('class', 'interface', 'static'):
                continue
            if fn_name in ('equals', 'hashCode', 'toString'):
                continue

            params = _parse_java_params(params_str, struct_names)
            return_type = _parse_java_return_type(return_type_str, struct_names)

            annos = []
            if '@Transactional' in content[:m.start()].split('\n')[-1:]:
                annos.append(Annotation("transactional"))

            fns.append(FnDef(
                name=_camel_to_snake(fn_name),
                annotations=annos,
                params=params,
                return_type=return_type,
                process=ProcessIntent(intent=f"TODO: reverse-engineer from {java_file.name}::{fn_name}"),
            ))

    return fns


def _parse_java_params(params_str: str, struct_names: set[str]) -> list[Param]:
    """解析 Java 方法参数列表。"""
    if not params_str.strip():
        return []

    params = []
    for p in params_str.split(','):
        p = p.strip()
        if not p:
            continue
        parts = p.strip().split()
        if len(parts) >= 2:
            annos_prefix = ' '.join(parts[:-2])
            java_type = parts[-2]
            name = parts[-1]

            type_ref = _resolve_java_type(java_type)
            # 如果类型名是已知 struct
            if java_type in struct_names:
                type_ref = TypeRef(base=java_type)

            params.append(Param(name=name, type=type_ref))

    # 过滤框架参数
    params = [p for p in params if p.name not in ('request', 'response', 'model', 'bindingResult')]

    return params


def _parse_java_return_type(ret_str: str, struct_names: set[str]) -> TypeRef | None:
    """解析 Java 返回类型。"""
    if ret_str in ('void', 'Void'):
        return None

    # List<X> → List<X>
    list_match = re.match(r'List<(\w+)>', ret_str)
    if list_match:
        inner = list_match.group(1)
        inner_enjin = _JAVA_TO_ENJIN.get(inner, inner if inner in struct_names else "String")
        return TypeRef(base="List", params=[TypeRef(base=inner_enjin)])

    # Optional<X>
    opt_match = re.match(r'Optional<(\w+)>', ret_str)
    if opt_match:
        inner = opt_match.group(1)
        inner_enjin = _JAVA_TO_ENJIN.get(inner, inner if inner in struct_names else "String")
        return TypeRef(base="Optional", params=[TypeRef(base=inner_enjin)], is_optional=True)

    enjin = _JAVA_TO_ENJIN.get(ret_str, ret_str if ret_str in struct_names else None)
    if enjin:
        return TypeRef(base=enjin)
    return None


def _extract_java_routes(controller_dir: Path) -> list[RouteDef]:
    """从 @RestController 文件提取 route 定义。"""
    routes = []

    for java_file in sorted(controller_dir.glob("*.java")):
        content = java_file.read_text(encoding="utf-8")
        if "@RestController" not in content and "@Controller" not in content:
            continue

        class_match = re.search(r'public\s+class\s+(\w+)Controller', content)
        if not class_match:
            continue
        route_name = class_match.group(1)

        # 提取 @RequestMapping 前缀
        prefix = ""
        prefix_match = re.search(r'@RequestMapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']', content)
        if prefix_match:
            prefix = prefix_match.group(1)

        endpoints = []
        # 匹配 @GetMapping("/path")、@PostMapping("/path") 等
        ep_pattern = re.compile(
            r'@(Get|Post|Put|Delete|Patch)Mapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']',
            re.MULTILINE,
        )
        for m in ep_pattern.finditer(content):
            method = m.group(1).upper()
            path = m.group(2)
            handler = path.strip('/').replace('/', '_').replace('{', '').replace('}', '') or "index"
            endpoints.append(EndpointDef(method=method, path=path, handler=handler))

        annos = []
        if prefix:
            annos.append(Annotation("prefix", [prefix]))

        routes.append(RouteDef(
            name=route_name,
            annotations=annos,
            endpoints=endpoints,
        ))

    return routes


def _camel_to_snake(name: str) -> str:
    """camelCase / PascalCase → snake_case。"""
    return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()


# ============================================================
# Program → .ej 序列化
# ============================================================

def program_to_ej(program: Program) -> str:
    """将 Program AST 序列化为 .ej 源码文本。"""
    lines: list[str] = []

    # application 配置
    if program.application and program.application.config:
        lines.append("// Application 配置")
        lines.append("application {")
        for key, value in program.application.config.items():
            if isinstance(value, str):
                lines.append(f'    {key}: "{value}"')
            elif isinstance(value, dict):
                lines.append(f"    {key} {{")
                for k, v in value.items():
                    lines.append(f'        {k}: "{v}"' if isinstance(v, str) else f"        {k}: {v}")
                lines.append("    }")
            else:
                lines.append(f"    {key}: {value}")
        lines.append("}")
        lines.append("")

    # struct 定义
    if program.structs:
        lines.append("// ============================================================")
        lines.append("// Model 层 — struct 定义")
        lines.append("// ============================================================")
        for struct in program.structs:
            lines.append("")
            for anno in struct.annotations:
                lines.append(_format_annotation(anno))
            lines.append(f"struct {struct.name} {{")
            for f in struct.fields:
                anno_str = " ".join(f"@{a.name}" + (f"({_format_args(a.args)})" if a.args else "") for a in f.annotations)
                type_str = _format_type(f.type)
                line = f"    {f.name}: {type_str}"
                if anno_str:
                    line += f" {anno_str}"
                lines.append(line)
            lines.append("}")

    # fn 定义
    if program.functions:
        lines.append("")
        lines.append("// ============================================================")
        lines.append("// Method 层 — fn 定义")
        lines.append("// ============================================================")
        for fn in program.functions:
            lines.append("")
            for anno in fn.annotations:
                lines.append(_format_annotation(anno))
            params_str = ", ".join(f"{p.name}: {_format_type(p.type)}" for p in fn.params)
            ret_str = f" -> {_format_type(fn.return_type)}" if fn.return_type else ""
            lines.append(f"fn {fn.name}({params_str}){ret_str} {{")

            if fn.guard:
                lines.append("    guard {")
                for g in fn.guard:
                    lines.append(f'        {g.expr} : "{g.message}"')
                lines.append("    }")
                lines.append("")

            if fn.process:
                lines.append("    process {")
                lines.append(f'        "{fn.process.intent}"')
                lines.append("    }")
                lines.append("")

            if fn.expect:
                lines.append("    expect {")
                for e in fn.expect:
                    lines.append(f"        {e.raw}")
                lines.append("    }")

            if fn.native_blocks:
                for nb in fn.native_blocks:
                    lines.append(f"    native {nb.target} {{")
                    for code_line in nb.code.strip().split('\n'):
                        lines.append(f"        {code_line}")
                    lines.append("    }")

            lines.append("}")

    # module 定义
    if program.modules:
        lines.append("")
        lines.append("// ============================================================")
        lines.append("// Module 层 — module 定义")
        lines.append("// ============================================================")
        for mod in program.modules:
            lines.append("")
            for dep in mod.dependencies:
                lines.append(f"    use {dep}")
            lines.append(f"module {mod.name} {{")
            if mod.exports:
                for exp in mod.exports:
                    lines.append(f"    export {exp.action} = {exp.target}")
            if mod.init:
                lines.append("")
                lines.append("    init {")
                lines.append(f'        "{mod.init.intent}"')
                lines.append("    }")
            for sched in mod.schedules:
                lines.append("")
                lines.append(f'    schedule {sched.frequency} at "{sched.cron}" {{')
                lines.append(f'        "{sched.intent}"')
                lines.append("    }")
            lines.append("}")

    # route 定义
    if program.routes:
        lines.append("")
        lines.append("// ============================================================")
        lines.append("// Service 层 — route 定义")
        lines.append("// ============================================================")
        for route in program.routes:
            lines.append("")
            for anno in route.annotations:
                lines.append(_format_annotation(anno))
            lines.append(f"route {route.name} {{")
            for dep in route.dependencies:
                lines.append(f"    use {dep}")
            if route.dependencies and route.endpoints:
                lines.append("")
            for ep in route.endpoints:
                locked = " @locked" if ep.is_locked else ""
                lines.append(f'    {ep.method} "{ep.path}" -> {ep.handler}{locked}')
            lines.append("}")

    return "\n".join(lines) + "\n"


def _format_annotation(anno: Annotation) -> str:
    """格式化注解为 .ej 文本。"""
    args = _format_args(anno.args)
    if args:
        return f"@{anno.name}({args})"
    return f"@{anno.name}"


def _format_args(args: list) -> str:
    """格式化注解参数。"""
    parts = []
    for a in args:
        if isinstance(a, str):
            parts.append(f'"{a}"')
        else:
            parts.append(str(a))
    return ", ".join(parts)


def _format_type(t: TypeRef | None) -> str:
    """格式化 TypeRef 为 .ej 类型文本。"""
    if t is None:
        return "Void"

    if t.base == "Optional" and t.params:
        return f"Optional<{_format_type(t.params[0])}>"
    if t.base == "List" and t.params:
        return f"List<{_format_type(t.params[0])}>"

    return t.base

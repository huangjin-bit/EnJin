"""
============================================================
EnJin Guard Compiler (guard_compiler.py)
============================================================
将 GuardRule.expr 文本编译为 Python/Java 验证代码。

所有 guard 表达式都是确定性的，无需 AI 参与。

支持的模式:
    - num_cmp:      id > 0, count >= 1
    - str_length:   username.length > 0, name.length < 50
    - str_contains:  email.contains("@")
    - enum_or:      status == "active" or status == "inactive"
    - not_exists:   not exists(User, email=email)
    - exists:       exists(Category, id=category_id)
============================================================
"""

from __future__ import annotations

import re
from typing import Optional

from enjinc.ast_nodes import GuardRule
from enjinc.constants import GUARD_EXCEPTIONS


def _get_exception_class(guard_type: str, lang: str) -> str:
    """根据 guard 类型与目标语言查表获取异常类名。

    未注册的 guard_type 回退到 GUARD_EXCEPTIONS["default"]。
    """
    return GUARD_EXCEPTIONS.get(guard_type, GUARD_EXCEPTIONS["default"]).get(
        lang, GUARD_EXCEPTIONS["default"][lang]
    )


def _parse_guard_expr(expr: str) -> dict:
    """解析单条 guard 表达式为结构化 dict。"""
    expr = expr.strip()

    # 1. not exists(Entity, field=value, ...)
    m = re.match(
        r"not\s+exists\(\s*(\w+)\s*,\s*(.+)\s*\)", expr
    )
    if m:
        entity = m.group(1)
        conditions = _parse_exists_conditions(m.group(2))
        return {"type": "not_exists", "entity": entity, "conditions": conditions}

    # 2. exists(Entity, field=value, ...)
    m = re.match(r"exists\(\s*(\w+)\s*,\s*(.+)\s*\)", expr)
    if m:
        entity = m.group(1)
        conditions = _parse_exists_conditions(m.group(2))
        return {"type": "exists", "entity": entity, "conditions": conditions}

    # 3. x.length <op> N
    m = re.match(r"(\w+)\.length\s*(>=|<=|>|<|==|!=)\s*(\d+)", expr)
    if m:
        return {
            "type": "str_length",
            "var": m.group(1),
            "op": m.group(2),
            "value": int(m.group(3)),
        }

    # 4. x.contains("s")
    m = re.match(r'(\w+)\.contains\("([^"]*)"\)', expr)
    if m:
        return {"type": "str_contains", "var": m.group(1), "substr": m.group(2)}

    # 5. x == "a" or x == "b" or ...
    or_match = re.match(r'^(\w+)\s*==\s*"[^"]*"(?:\s+or\s+\1\s*==\s*"[^"]*")+$', expr)
    if or_match:
        var = or_match.group(1)
        values = re.findall(r'"([^"]*)"', expr)
        return {"type": "enum_or", "var": var, "values": values}

    # 6. 兜底: 简单比较表达式
    m = re.match(r"(\w+)\s*(>=|<=|>|<|==|!=)\s*(.+)", expr)
    if m:
        return {
            "type": "num_cmp",
            "var": m.group(1),
            "op": m.group(2),
            "value": m.group(3).strip(),
        }

    return {"type": "unknown", "expr": expr}


def _parse_exists_conditions(text: str) -> list[tuple[str, str]]:
    """解析 exists 条件: 'email=email, status="active"' → [('email', 'email'), ...]"""
    conditions = []
    for part in text.split(","):
        part = part.strip()
        m = re.match(r"(\w+)\s*=\s*(.+)", part)
        if m:
            conditions.append((m.group(1), m.group(2).strip().strip('"')))
    return conditions


def compile_guards_python(
    guard_rules: list[GuardRule], db_param: str = "db"
) -> list[str]:
    """将 guard 规则列表编译为 Python 验证代码行。"""
    lines = []
    for rule in guard_rules:
        parsed = _parse_guard_expr(rule.expr)
        code = _to_python(parsed, rule.message, db_param)
        lines.extend(code)
    return lines


def compile_guards_java(guard_rules: list[GuardRule]) -> list[str]:
    """将 guard 规则列表编译为 Java 验证代码行。"""
    lines = []
    for rule in guard_rules:
        parsed = _parse_guard_expr(rule.expr)
        code = _to_java(parsed, rule.message)
        lines.extend(code)
    return lines


def _to_python(parsed: dict, message: str, db_param: str) -> list[str]:
    """将解析后的 guard 编译为 Python 代码行。"""
    t = parsed["type"]

    exc = _get_exception_class(t, "python")

    if t == "num_cmp":
        cond = f"{parsed['var']} {parsed['op']} {parsed['value']}"
        return [f"# Guard: {cond}", f"if not ({cond}):", f'    raise {exc}("{message}")']

    if t == "str_length":
        var, op, val = parsed["var"], parsed["op"], parsed["value"]
        if op == ">" and val == 0:
            return [f"# Guard: {var}.length > 0", f"if not {var}:", f'    raise {exc}("{message}")']
        cond = f"len({var}) {op} {val}"
        return [f"# Guard: {var}.length {op} {val}", f"if not ({cond}):", f'    raise {exc}("{message}")']

    if t == "str_contains":
        var, substr = parsed["var"], parsed["substr"]
        return [f'# Guard: {var}.contains("{substr}")', f'if "{substr}" not in {var}:', f'    raise {exc}("{message}")']

    if t == "enum_or":
        var, values = parsed["var"], parsed["values"]
        vals_str = ", ".join(f'"{v}"' for v in values)
        set_literal = "{" + vals_str + "}"
        return [f"# Guard: {var} enum check", f"if {var} not in {set_literal}:", f'    raise {exc}("{message}")']

    if t == "not_exists":
        entity = parsed["entity"]
        conditions = parsed["conditions"]
        filters = ", ".join(f"{f}={v}" for f, v in conditions)
        return [
            f"# Guard: not exists({entity}, {filters})",
            f"if {db_param}.query({entity}).filter_by({filters}).first():",
            f'    raise {exc}("{message}")',
        ]

    if t == "exists":
        entity = parsed["entity"]
        conditions = parsed["conditions"]
        filters = ", ".join(f"{f}={v}" for f, v in conditions)
        return [
            f"# Guard: exists({entity}, {filters})",
            f"if not {db_param}.query({entity}).filter_by({filters}).first():",
            f'    raise {exc}("{message}")',
        ]

    # unknown
    return [f"# Guard: {parsed.get('expr', '???')}", f'raise {exc}("{message}")']


def _to_java(parsed: dict, message: str) -> list[str]:
    """将解析后的 guard 编译为 Java 代码行。"""
    t = parsed["type"]

    exc = _get_exception_class(t, "java")

    if t == "num_cmp":
        cond = f"{parsed['var']} {parsed['op']} {parsed['value']}"
        return [f"if (!({cond})) throw new {exc}(\"{message}\");"]

    if t == "str_length":
        var, op, val = parsed["var"], parsed["op"], parsed["value"]
        if op == ">" and val == 0:
            return [f'if ({var} == null || {var}.isEmpty()) throw new {exc}("{message}");']
        if op == "<=":
            return [f'if ({var} != null && {var}.length() > {val}) throw new {exc}("{message}");']
        cond = f"{var}.length() {op} {val}"
        return [f"if (!({cond})) throw new {exc}(\"{message}\");"]

    if t == "str_contains":
        var, substr = parsed["var"], parsed["substr"]
        return [f'if (!{var}.contains("{substr}")) throw new {exc}("{message}");']

    if t == "enum_or":
        var, values = parsed["var"], parsed["values"]
        checks = " || ".join(f'"{v}".equals({var})' for v in values)
        return [f"if (!({checks})) throw new {exc}(\"{message}\");"]

    if t == "not_exists":
        entity = parsed["entity"]
        conditions = parsed["conditions"]
        repo_var = _entity_to_repo_var(entity)
        checks = _build_java_repo_check(entity, conditions, negate=True)
        return [f'{checks} throw new {exc}("{message}");']

    if t == "exists":
        entity = parsed["entity"]
        conditions = parsed["conditions"]
        checks = _build_java_repo_check(entity, conditions, negate=False)
        return [f'{checks} throw new {exc}("{message}");']

    return [f'// Guard: {parsed.get("expr", "???")} - {message}']


def _entity_to_repo_var(entity: str) -> str:
    """Entity name → repository variable: User → userRepository."""
    return entity[0].lower() + entity[1:] + "Repository"


def _build_java_repo_check(
    entity: str, conditions: list[tuple[str, str]], negate: bool
) -> str:
    """构建 Java repository 查询条件。"""
    repo_var = _entity_to_repo_var(entity)
    if len(conditions) == 1:
        field, value = conditions[0]
        method = f"findBy{_capitalize(field)}"
        check = f"{repo_var}.{method}({value}).isPresent()" if not negate else f"!{repo_var}.{method}({value}).isEmpty()"
        if negate:
            check = f"{repo_var}.{method}({value}) != null"
        else:
            check = f"{repo_var}.{method}({value}) == null"
        prefix = "if (" if not negate else "if ("
        if negate:
            return f'{prefix}{repo_var}.findBy{_capitalize(field)}({value}) != null)'
        return f'{prefix}{repo_var}.findBy{_capitalize(field)}({value}) == null)'
    # Multi-condition: use findBy...And...
    method_parts = [_capitalize(f) for f, _ in conditions]
    method = "findBy" + "And".join(method_parts)
    args = ", ".join(v for _, v in conditions)
    if negate:
        return f'if ({repo_var}.{method}({args}) != null)'
    return f'if ({repo_var}.{method}({args}) == null)'


def _capitalize(s: str) -> str:
    return s[0].upper() + s[1:]

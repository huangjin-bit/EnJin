"""
============================================================
EnJin AST Edit Distance Audit (ast_audit.py)
============================================================
ENJIN_CONSTITUTION §6 — 逻辑守恒审计

大模型升级或漂移时，新生成的代码必须通过基于 AST 编辑距离的结构化审计，
并且 100% 跑通由 expect 自动生成的单元测试。

本模块对比两版 AI 生成代码的结构差异：
  1. 将源码解析为归一化的 ASTNode 树
  2. 按节点名匹配，用 Jaccard 系数计算 token 重叠度
  3. 输出 EditDistance（增/删/改）与 AuditResult（通过/阻断）

仅依赖 stdlib（ast, re, dataclasses, typing），无外部依赖。
============================================================
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# 数据结构
# ============================================================


@dataclass
class ASTNode:
    """归一化的代码块 AST 节点。

    不是 EnJin 的 I-AST 节点，而是目标语言（Python/Java）生成代码的
    结构化摘要，用于跨版本比较。

    Attributes:
        node_type: 节点类型 (function, class, method, import 等)
        name: 节点名称（函数名、类名等）
        children: 子节点列表（如类中的方法）
        tokens: 关键标识符/字面量集合，用于相似度计算
    """

    node_type: str
    name: str
    children: list[ASTNode] = field(default_factory=list)
    tokens: set[str] = field(default_factory=set)

    @property
    def qualified_name(self) -> str:
        """返回 'node_type:name' 格式的唯一标识。"""
        return f"{self.node_type}:{self.name}"


@dataclass
class EditDistance:
    """两版代码的结构编辑距离。

    Attributes:
        added_nodes: 新代码中新增的节点（旧代码中不存在）
        removed_nodes: 新代码中缺失的节点（旧代码中有）
        modified_nodes: 结构发生变化的节点，附带相似度分数 (< 1.0)
        total_distance: 聚合距离 (0.0 = 完全相同, 1.0 = 完全不同)
    """

    added_nodes: list[str] = field(default_factory=list)
    removed_nodes: list[str] = field(default_factory=list)
    modified_nodes: list[tuple[str, float]] = field(default_factory=list)
    total_distance: float = 0.0


@dataclass
class AuditResult:
    """审计结果：通过或阻断。

    Attributes:
        passed: 是否通过审计（所有节点相似度 >= 阈值）
        distance: 详细的编辑距离
        warnings: 警告信息列表（如新增/删除节点）
        blocked_nodes: 变化过大被阻断的节点列表
    """

    passed: bool
    distance: EditDistance
    warnings: list[str] = field(default_factory=list)
    blocked_nodes: list[str] = field(default_factory=list)


# ============================================================
# Python AST 解析
# ============================================================


def _extract_identifiers(node: ast.AST) -> set[str]:
    """从 AST 节点中提取所有标识符和字面量作为 token 集合。

    提取范围：Name id、Constant 值、函数参数名。过滤掉短于 2 字符的
    token（如 'x', 'i'）以降低噪音。

    Args:
        node: Python ast 节点

    Returns:
        标识符/字面量的集合
    """
    tokens: set[str] = set()

    for child in ast.walk(node):
        if isinstance(child, ast.Name) and len(child.id) >= 2:
            tokens.add(child.id)
        elif isinstance(child, ast.Constant):
            # 只收集字符串和数值型常量，跳过 None/True/False
            val = child.value
            if isinstance(val, str) and len(val) >= 2:
                tokens.add(val)
            elif isinstance(val, (int, float)):
                tokens.add(str(val))
        elif isinstance(child, ast.arg):
            if len(child.arg) >= 2:
                tokens.add(child.arg)

    return tokens


def _build_param_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """提取函数参数类型注解中的类型名作为 token。

    仅提取类型注解而非参数名本身，因为参数名改变不影响逻辑签名。

    Args:
        node: 函数定义节点

    Returns:
        类型注解标识符集合
    """
    tokens: set[str] = set()

    for arg in node.args.args:
        if arg.annotation is not None:
            tokens.update(_extract_identifiers(arg.annotation))

    if node.args.vararg and node.args.vararg.annotation:
        tokens.update(_extract_identifiers(node.args.vararg.annotation))

    if node.args.kwarg and node.args.kwarg.annotation:
        tokens.update(_extract_identifiers(node.args.kwarg.annotation))

    for arg in node.args.kwonlyargs:
        if arg.annotation is not None:
            tokens.update(_extract_identifiers(arg.annotation))

    if node.returns is not None:
        tokens.update(_extract_identifiers(node.returns))

    # 装饰器标识符
    for decorator in node.decorator_list:
        tokens.update(_extract_identifiers(decorator))

    return tokens


def _parse_function_node(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> ASTNode:
    """将 Python 函数定义转为 ASTNode。

    Args:
        node: 函数/异步函数定义

    Returns:
        归一化的 ASTNode
    """
    body_tokens = _extract_identifiers(node)
    param_tokens = _build_param_signature(node)
    all_tokens = body_tokens | param_tokens

    return ASTNode(
        node_type="function",
        name=node.name,
        children=[],
        tokens=all_tokens,
    )


def _parse_class_node(node: ast.ClassDef) -> ASTNode:
    """将 Python 类定义转为 ASTNode，包含方法子节点。

    Args:
        node: 类定义

    Returns:
        归一化的 ASTNode，children 为类内方法
    """
    tokens: set[str] = set()

    # 基类标识符
    for base in node.bases:
        tokens.update(_extract_identifiers(base))

    # 装饰器
    for decorator in node.decorator_list:
        tokens.update(_extract_identifiers(decorator))

    # 类体中非方法级标识符（类属性赋值等）
    for stmt in node.body:
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            tokens.update(_extract_identifiers(stmt))

    children: list[ASTNode] = []
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            children.append(_parse_function_node(item))

    return ASTNode(
        node_type="class",
        name=node.name,
        children=children,
        tokens=tokens,
    )


def parse_python_ast(code: str) -> list[ASTNode]:
    """将 Python 源码解析为归一化的 ASTNode 列表。

    提取顶层函数定义、类定义（含内部方法），以及 import 语句。
    语法错误的代码会返回空列表而非抛出异常。

    Args:
        code: Python 源码字符串

    Returns:
        顶层 ASTNode 列表
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    nodes: list[ASTNode] = []

    for item in ast.iter_child_nodes(tree):
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fn_node = _parse_function_node(item)
            fn_node.node_type = "function"
            nodes.append(fn_node)

        elif isinstance(item, ast.ClassDef):
            cls_node = _parse_class_node(item)
            nodes.append(cls_node)

        elif isinstance(item, (ast.Import, ast.ImportFrom)):
            # import 语句作为独立节点
            import_tokens: set[str] = set()
            if isinstance(item, ast.Import):
                for alias in item.names:
                    import_tokens.add(alias.name)
                    if alias.asname:
                        import_tokens.add(alias.asname)
            else:  # ImportFrom
                if item.module:
                    import_tokens.add(item.module)
                for alias in item.names:
                    import_tokens.add(alias.name)
                    if alias.asname:
                        import_tokens.add(alias.asname)

            # 将同名模块的 import 合并到一个节点（取模块名做标识）
            if isinstance(item, ast.ImportFrom) and item.module:
                name = item.module
            elif isinstance(item, ast.Import) and item.names:
                name = item.names[0].name
            else:
                name = "unknown_import"

            nodes.append(ASTNode(
                node_type="import",
                name=name,
                tokens=import_tokens,
            ))

    return nodes


# ============================================================
# Java AST 解析（基于正则的结构化提取）
# ============================================================

# Java 方法签名正则：
#   可见性修饰? static? 返回类型 方法名(参数列表) throws?
#   注意：不匹配 main 方法签名中的 String[] args 的方括号问题已处理
_JAVA_METHOD_RE = re.compile(
    r"(?:public|private|protected)\s+"
    r"(?:static\s+)?"
    r"(?:final\s+)?"
    r"(?:synchronized\s+)?"
    r"([\w<>\[\],\s\?]+?)\s+"   # return type
    r"(\w+)\s*"                  # method name
    r"\(([^)]*)\)"               # parameters
    r"(?:\s*throws\s+[\w,\s]+)?",
    re.MULTILINE,
)

# Java 类/接口/枚举声明
_JAVA_CLASS_RE = re.compile(
    r"(?:public\s+|private\s+|protected\s+)?"
    r"(?:abstract\s+|final\s+)?"
    r"(?:class|interface|enum)\s+"
    r"(\w+)"                     # class name
    r"(?:\s+extends\s+(\w+))?"   # parent class
    r"(?:\s+implements\s+([\w,\s]+))?",
    re.MULTILINE,
)

# Java import 语句
_JAVA_IMPORT_RE = re.compile(
    r"import\s+(?:static\s+)?([\w.\*]+)\s*;",
    re.MULTILINE,
)

# Java 标识符提取
_JAVA_IDENT_RE = re.compile(r"\b([a-zA-Z_]\w{1,})\b")


def parse_java_ast(code: str) -> list[ASTNode]:
    """将 Java 源码解析为归一化的 ASTNode 列表。

    使用正则进行结构化提取：类声明、方法签名、import 语句。
    精确度低于 Python AST 解析，但足以支撑编辑距离比较。

    Args:
        code: Java 源码字符串

    Returns:
        顶层 ASTNode 列表
    """
    nodes: list[ASTNode] = []

    # --- import 节点 ---
    import_tokens: set[str] = set()
    for match in _JAVA_IMPORT_RE.finditer(code):
        import_tokens.add(match.group(1).strip())

    if import_tokens:
        nodes.append(ASTNode(
            node_type="import",
            name="imports",
            tokens=import_tokens,
        ))

    # --- 类/接口/枚举 ---
    class_matches = list(_JAVA_CLASS_RE.finditer(code))
    for cls_match in class_matches:
        cls_name = cls_match.group(1)
        cls_tokens: set[str] = set()

        # 继承的父类
        if cls_match.group(2):
            cls_tokens.add(cls_match.group(2))

        # 实现的接口
        if cls_match.group(3):
            for iface in cls_match.group(3).split(","):
                iface = iface.strip()
                if iface:
                    cls_tokens.add(iface)

        # 提取类体内的方法作为子节点
        children: list[ASTNode] = []

        # 确定类体的范围：从 { 到匹配的 }
        cls_body_start = code.find("{", cls_match.end())
        if cls_body_start != -1:
            cls_body = _extract_balanced_brace_block(code, cls_body_start)

            for method_match in _JAVA_METHOD_RE.finditer(cls_body):
                method_name = method_match.group(2)
                return_type = method_match.group(1).strip()
                params_str = method_match.group(3).strip()

                method_tokens: set[str] = set()
                method_tokens.add(return_type.split()[-1] if return_type else "void")

                # 参数类型
                if params_str:
                    for param in params_str.split(","):
                        param = param.strip()
                        if param:
                            parts = param.split()
                            if len(parts) >= 1:
                                method_tokens.add(parts[0].strip("[]<>"))

                # 方法体标识符
                method_body_start = cls_body.find("{", method_match.end())
                if method_body_start != -1:
                    method_body = _extract_balanced_brace_block(
                        cls_body, method_body_start,
                    )
                    # 提取方法体内的标识符，排除 Java 关键字
                    raw_idents = _JAVA_IDENT_RE.findall(method_body)
                    method_tokens.update(
                        ident for ident in raw_idents
                        if ident not in _JAVA_KEYWORDS
                    )

                children.append(ASTNode(
                    node_type="method",
                    name=method_name,
                    tokens=method_tokens,
                ))

        nodes.append(ASTNode(
            node_type="class",
            name=cls_name,
            children=children,
            tokens=cls_tokens,
        ))

    # 如果没有类匹配（如顶层方法/脚本式代码），尝试直接提取方法
    if not class_matches:
        for method_match in _JAVA_METHOD_RE.finditer(code):
            method_name = method_match.group(2)
            return_type = method_match.group(1).strip()
            params_str = method_match.group(3).strip()

            method_tokens: set[str] = set()
            method_tokens.add(return_type.split()[-1] if return_type else "void")

            if params_str:
                for param in params_str.split(","):
                    param = param.strip()
                    if param:
                        parts = param.split()
                        if len(parts) >= 1:
                            method_tokens.add(parts[0].strip("[]<>"))

            nodes.append(ASTNode(
                node_type="method",
                name=method_name,
                tokens=method_tokens,
            ))

    return nodes


def _extract_balanced_brace_block(code: str, start: int) -> str:
    """从 start 位置（应指向 '{'）提取大括号平衡的代码块。

    Args:
        code: 完整源码
        start: 左大括号的位置

    Returns:
        从 '{' 到对应 '}' 的子字符串
    """
    if start >= len(code) or code[start] != "{":
        return ""

    depth = 0
    i = start
    while i < len(code):
        if code[i] == "{":
            depth += 1
        elif code[i] == "}":
            depth -= 1
            if depth == 0:
                return code[start : i + 1]
        i += 1

    # 未找到匹配的右大括号，返回从 start 到末尾
    return code[start:]


# Java 关键字集合，用于过滤标识符提取时的噪音
_JAVA_KEYWORDS = frozenset({
    "abstract", "assert", "boolean", "break", "byte", "case", "catch",
    "char", "class", "const", "continue", "default", "do", "double",
    "else", "enum", "extends", "final", "finally", "float", "for",
    "goto", "if", "implements", "import", "instanceof", "int",
    "interface", "long", "native", "new", "package", "private",
    "protected", "public", "return", "short", "static", "strictfp",
    "super", "switch", "synchronized", "this", "throw", "throws",
    "transient", "try", "void", "volatile", "while", "true", "false",
    "null", "String",
})


# ============================================================
# 编辑距离计算
# ============================================================


def _jaccard_similarity(tokens_a: set[str], tokens_b: set[str]) -> float:
    """计算两个 token 集合之间的 Jaccard 相似系数。

    Jaccard(A, B) = |A ∩ B| / |A ∪ B|

    Args:
        tokens_a: 集合 A
        tokens_b: 集合 B

    Returns:
        相似度 [0.0, 1.0]，两个空集返回 1.0（视为相同）
    """
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _compare_child_lists(
    old_children: list[ASTNode],
    new_children: list[ASTNode],
) -> tuple[float, list[tuple[str, float]]]:
    """递归比较子节点列表，返回平均相似度和修改详情。

    Args:
        old_children: 旧版子节点
        new_children: 新版子节点

    Returns:
        (平均相似度, 修改节点详情列表)
    """
    if not old_children and not new_children:
        return 1.0, []

    old_by_name = {c.name: c for c in old_children}
    new_by_name = {c.name: c for c in new_children}

    all_names = set(old_by_name.keys()) | set(new_by_name.keys())
    if not all_names:
        return 1.0, []

    total_sim = 0.0
    modified: list[tuple[str, float]] = []

    for name in all_names:
        old_child = old_by_name.get(name)
        new_child = new_by_name.get(name)

        if old_child is None or new_child is None:
            # 新增或删除的子节点
            total_sim += 0.0
            modified.append((name, 0.0))
            continue

        # 同名子节点的 token 相似度
        token_sim = _jaccard_similarity(old_child.tokens, new_child.tokens)

        # 递归比较下一层子节点
        child_sim, _ = _compare_child_lists(old_child.children, new_child.children)

        # 综合相似度 = token 权重 70% + 结构权重 30%
        combined = 0.7 * token_sim + 0.3 * child_sim
        total_sim += combined

        if combined < 1.0:
            modified.append((name, combined))

    avg_sim = total_sim / len(all_names)
    return avg_sim, modified


def compute_edit_distance(
    old_nodes: list[ASTNode],
    new_nodes: list[ASTNode],
) -> EditDistance:
    """比较两份 ASTNode 列表，计算结构编辑距离。

    按节点名匹配（同名视为同一节点），对匹配节点计算 Jaccard token
    相似度并递归比较子节点。未匹配节点记为新增或删除。

    Args:
        old_nodes: 旧版代码的 AST 节点列表
        new_nodes: 新版代码的 AST 节点列表

    Returns:
        EditDistance 包含增/删/改详情与聚合距离
    """
    old_by_name: dict[str, ASTNode] = {n.name: n for n in old_nodes}
    new_by_name: dict[str, ASTNode] = {n.name: n for n in new_nodes}

    old_names = set(old_by_name.keys())
    new_names = set(new_by_name.keys())

    added = sorted(new_names - old_names)
    removed = sorted(old_names - new_names)
    modified: list[tuple[str, float]] = []

    # 共同名节点逐个比较
    common_names = old_names & new_names
    similarity_scores: list[float] = []

    for name in common_names:
        old_node = old_by_name[name]
        new_node = new_by_name[name]

        # token 级 Jaccard 相似度
        token_sim = _jaccard_similarity(old_node.tokens, new_node.tokens)

        # 递归比较子节点
        child_sim, child_mods = _compare_child_lists(
            old_node.children, new_node.children,
        )

        # 综合相似度
        combined = 0.7 * token_sim + 0.3 * child_sim
        similarity_scores.append(combined)

        if combined < 1.0:
            qualified = f"{old_node.node_type}:{name}"
            modified.append((qualified, round(combined, 4)))

            # 子节点的修改也记录下来
            for child_name, child_score in child_mods:
                child_qualified = f"{qualified}/{child_name}"
                modified.append((child_qualified, round(child_score, 4)))

    # 聚合 total_distance
    total_names = len(old_names | new_names)
    if total_names == 0:
        total_distance = 0.0
    else:
        # 修改节点的平均距离 + 新增/删除节点的惩罚
        unchanged_count = sum(1 for s in similarity_scores if s == 1.0)
        changed_penalty = len(added) + len(removed)
        # 每个修改节点的距离贡献 = 1 - similarity
        change_magnitude = sum(1.0 - s for s in similarity_scores)

        total_distance = min(
            1.0,
            (changed_penalty + change_magnitude) / total_names,
        )
        total_distance = round(total_distance, 4)

    return EditDistance(
        added_nodes=added,
        removed_nodes=removed,
        modified_nodes=modified,
        total_distance=total_distance,
    )


# ============================================================
# 审计入口
# ============================================================


def audit_code(
    old_code: str,
    new_code: str,
    lang: str,
    threshold: float = 0.7,
) -> AuditResult:
    """AST 编辑距离审计的主入口（ENJIN_CONSTITUTION §6 逻辑守恒审计）。

    解析两份代码为 AST 节点，计算编辑距离，对相似度低于阈值的节点
    进行阻断。新增/删除的节点产生警告但不阻断。

    Args:
        old_code: 旧版 AI 生成代码
        new_code: 新版 AI 生成代码
        lang: 目标语言，"python" 或 "java"
        threshold: 最低相似度阈值，低于此值的节点将被阻断 (默认 0.7)

    Returns:
        AuditResult 包含通过/阻断状态、编辑距离和警告
    """
    # 1. 解析
    if lang.lower() in ("python", "python_fastapi"):
        old_nodes = parse_python_ast(old_code)
        new_nodes = parse_python_ast(new_code)
    elif lang.lower() in ("java", "java_spring"):
        old_nodes = parse_java_ast(old_code)
        new_nodes = parse_java_ast(new_code)
    else:
        return AuditResult(
            passed=False,
            distance=EditDistance(total_distance=1.0),
            warnings=[f"Unsupported language: {lang}"],
            blocked_nodes=[],
        )

    # 2. 计算编辑距离
    distance = compute_edit_distance(old_nodes, new_nodes)

    # 3. 识别阻断节点（相似度低于阈值）
    blocked_nodes: list[str] = []
    warnings: list[str] = []

    for node_name, score in distance.modified_nodes:
        if score < threshold:
            blocked_nodes.append(f"{node_name} (similarity={score:.2f})")

    # 新增节点警告
    for added in distance.added_nodes:
        warnings.append(f"Node added in new code: {added}")

    # 删除节点警告（更严重，因为可能丢失逻辑）
    for removed in distance.removed_nodes:
        warnings.append(f"Node removed in new code: {removed}")

    # 整体距离过高时追加警告
    if distance.total_distance > 0.5:
        warnings.append(
            f"High overall edit distance ({distance.total_distance:.2f}): "
            "new code differs significantly from old version"
        )

    # 4. 判定通过
    passed = len(blocked_nodes) == 0 and len(distance.removed_nodes) == 0

    return AuditResult(
        passed=passed,
        distance=distance,
        warnings=warnings,
        blocked_nodes=blocked_nodes,
    )

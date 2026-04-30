"""
============================================================
EnJin 测试生成器 (test_generator.py)
============================================================
本模块负责从 `expect` 断言生成目标语言的单元测试代码。

核心流程:
1. 解析 ExpectAssertion.raw 文本为结构化断言
2. 使用 Jinja2 模板渲染为目标语言测试代码
3. 支持 pytest (Python) 和 JUnit (Java)

断言语法:
- fn_call().property == value    # 属性相等断言
- fn_call().throws("message")     # 异常抛出断言
- fn_call().status == 200         # HTTP 状态断言
============================================================
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, TemplateError, TemplateNotFound

from enjinc.ast_nodes import ExpectAssertion, FnDef
from enjinc.jinja_utils import get_jinja_env


class AssertionType(Enum):
    PROPERTY_EQ = "property_eq"
    THROWS = "throws"
    STATUS_EQ = "status_eq"
    CONTAINS = "contains"


@dataclass
class ParsedAssertion:
    """解析后的断言结构。"""

    assertion_type: AssertionType
    raw: str
    fn_call: str
    fn_name: str
    fn_args: list[str]
    property_path: Optional[str]
    expected_value: Optional[str]
    expected_exception: Optional[str]


@dataclass
class TestContext:
    """测试生成的上下文。"""

    fn_def: FnDef
    parsed_assertions: list[ParsedAssertion]
    target_lang: str
    module_name: Optional[str] = None


def _get_jinja_env(target_lang: str) -> Environment:
    """获取目标语言的 Jinja2 环境。"""
    fallback = Path(__file__).parent / "templates"
    return get_jinja_env(target_lang, fallback_dir=fallback)


def parse_expect_assertion(raw: str) -> ParsedAssertion:
    """解析 expect 断言文本为结构化断言。

    支持的格式:
    - fn_call().property == value
    - fn_call().throws("message")
    - fn_call().status == 200
    - fn_call().contains("substring")

    Args:
        raw: 原始断言文本，如 `register_user("alice").username == "alice"`

    Returns:
        ParsedAssertion 对象
    """
    raw = raw.strip()

    throws_match = re.match(r'^(.+?)\.throws\("([^"]*)"\)$', raw)
    if throws_match:
        fn_call = throws_match.group(1)
        expected_exception = throws_match.group(2)
        fn_name, fn_args = _parse_fn_call(fn_call)
        return ParsedAssertion(
            assertion_type=AssertionType.THROWS,
            raw=raw,
            fn_call=fn_call,
            fn_name=fn_name,
            fn_args=fn_args,
            property_path=None,
            expected_value=None,
            expected_exception=expected_exception,
        )

    status_eq_match = re.match(r"^(.+?)\.status\s*==\s*(\d+)$", raw)
    if status_eq_match:
        fn_call = status_eq_match.group(1)
        expected_value = status_eq_match.group(2)
        fn_name, fn_args = _parse_fn_call(fn_call)
        return ParsedAssertion(
            assertion_type=AssertionType.STATUS_EQ,
            raw=raw,
            fn_call=fn_call,
            fn_name=fn_name,
            fn_args=fn_args,
            property_path="status",
            expected_value=expected_value,
            expected_exception=None,
        )

    property_eq_match = re.match(r"^(.+?)\.(\w+)\s*==\s*(.+)$", raw)
    if property_eq_match:
        fn_call = property_eq_match.group(1)
        property_path = property_eq_match.group(2)
        expected_value = property_eq_match.group(3)
        fn_name, fn_args = _parse_fn_call(fn_call)
        return ParsedAssertion(
            assertion_type=AssertionType.PROPERTY_EQ,
            raw=raw,
            fn_call=fn_call,
            fn_name=fn_name,
            fn_args=fn_args,
            property_path=property_path,
            expected_value=expected_value,
            expected_exception=None,
        )

    contains_match = re.match(r'^(.+?)\.contains\("([^"]*)"\)$', raw)
    if contains_match:
        fn_call = contains_match.group(1)
        expected_value = contains_match.group(2)
        fn_name, fn_args = _parse_fn_call(fn_call)
        return ParsedAssertion(
            assertion_type=AssertionType.CONTAINS,
            raw=raw,
            fn_call=fn_call,
            fn_name=fn_name,
            fn_args=fn_args,
            property_path=None,
            expected_value=f'"{expected_value}"',
            expected_exception=None,
        )

    simple_eq_match = re.match(r"^(.+?)\s*==\s*(.+)$", raw)
    if simple_eq_match:
        fn_call = simple_eq_match.group(1)
        expected_value = simple_eq_match.group(2)
        fn_name, fn_args = _parse_fn_call(fn_call)
        return ParsedAssertion(
            assertion_type=AssertionType.PROPERTY_EQ,
            raw=raw,
            fn_call=fn_call,
            fn_name=fn_name,
            fn_args=fn_args,
            property_path=None,
            expected_value=expected_value,
            expected_exception=None,
        )

    fn_name, fn_args = _parse_fn_call(raw)
    return ParsedAssertion(
        assertion_type=AssertionType.PROPERTY_EQ,
        raw=raw,
        fn_call=raw,
        fn_name=fn_name,
        fn_args=fn_args,
        property_path=None,
        expected_value=None,
        expected_exception=None,
    )


def _parse_fn_call(fn_call: str) -> tuple[str, list[str]]:
    """解析函数调用字符串。

    Args:
        fn_call: 函数调用字符串，如 `register_user("alice", "alice@test.com")`

    Returns:
        (函数名, 参数列表)
    """
    match = re.match(r"^(\w+)\((.*)\)$", fn_call.strip())
    if not match:
        return fn_call, []

    fn_name = match.group(1)
    args_str = match.group(2).strip()

    if not args_str:
        return fn_name, []

    args = _split_args(args_str)
    return fn_name, args


def _split_args(args_str: str) -> list[str]:
    """智能分割参数字符串，处理嵌套括号和引号。"""
    args = []
    current = []
    depth = 0
    in_string = False
    string_char = None

    i = 0
    while i < len(args_str):
        c = args_str[i]

        if not in_string:
            if c in '("':
                in_string = True
                string_char = c
                current.append(c)
            elif c == "(":
                depth += 1
                current.append(c)
            elif c == ")":
                depth -= 1
                current.append(c)
            elif c == "," and depth == 0:
                arg = "".join(current).strip()
                if arg:
                    args.append(arg)
                current = []
            else:
                current.append(c)
        else:
            if c == "\\" and i + 1 < len(args_str):
                current.append(c)
                current.append(args_str[i + 1])
                i += 1
            elif c == string_char:
                in_string = False
                string_char = None
                current.append(c)
            else:
                current.append(c)
        i += 1

    arg = "".join(current).strip()
    if arg:
        args.append(arg)

    return args


def generate_pytest_for_fn(fn_def: FnDef) -> str:
    """为单个函数生成 pytest 测试代码。

    Args:
        fn_def: 函数定义节点

    Returns:
        pytest 测试代码字符串
    """
    if not fn_def.expect:
        return ""

    parsed = [parse_expect_assertion(a.raw) for a in fn_def.expect]

    context = {
        "fn": fn_def,
        "assertions": parsed,
        "test_name": f"test_{fn_def.name}",
    }

    env = _get_jinja_env("python_fastapi")
    try:
        template = env.get_template("test_fn.py.jinja")
        return template.render(**context)
    except (TemplateError, TemplateNotFound):
        return _generate_pytest_fallback(context)


def _generate_pytest_fallback(context: dict[str, Any]) -> str:
    """生成 pytest 的后备实现（不使用模板）。"""
    fn = context["fn"]
    lines = [
        f"import pytest",
        f"",
        f"",
        f"class Test{fn.name.title()}:",
    ]

    for i, assertion in enumerate(context["assertions"]):
        test_method = f"    def test_{fn.name}_{i + 1}(self):"
        lines.append(test_method)

        if assertion.assertion_type == AssertionType.THROWS:
            lines.append(f'        """验证异常: {assertion.expected_exception}"""')
            lines.append(f"        with pytest.raises(Exception) as exc_info:")
            lines.append(f"            {assertion.fn_call}")
            lines.append(
                f'        assert "{assertion.expected_exception}" in str(exc_info.value)'
            )
        elif assertion.assertion_type == AssertionType.PROPERTY_EQ:
            lines.append(f'        """验证: {assertion.raw}"""')
            lines.append(f"        result = {assertion.fn_call}")
            if assertion.property_path:
                lines.append(
                    f"        assert result.{assertion.property_path} == {assertion.expected_value}"
                )
            else:
                lines.append(f"        assert result == {assertion.expected_value}")
        elif assertion.assertion_type == AssertionType.CONTAINS:
            lines.append(f'        """验证包含: {assertion.expected_value}"""')
            lines.append(f"        result = {assertion.fn_call}")
            lines.append(f"        assert {assertion.expected_value} in result")

        lines.append("")

    return "\n".join(lines)


def generate_junit_for_fn(fn_def: FnDef) -> str:
    """为单个函数生成 JUnit 测试代码。

    Args:
        fn_def: 函数定义节点

    Returns:
        JUnit 测试代码字符串
    """
    if not fn_def.expect:
        return ""

    parsed = [parse_expect_assertion(a.raw) for a in fn_def.expect]

    context = {
        "fn": fn_def,
        "assertions": parsed,
        "test_name": f"test{fn_def.name.title()}",
    }

    env = _get_jinja_env("java_springboot")
    try:
        template = env.get_template("test/Test.java.jinja")
        return template.render(**context)
    except (TemplateError, TemplateNotFound):
        return _generate_junit_fallback(context)


def _generate_junit_fallback(context: dict[str, Any]) -> str:
    """生成 JUnit 的后备实现（不使用模板）。"""
    fn = context["fn"]
    class_name = f"Test{fn.name.title()}"

    lines = [
        f"package {fn.name};",
        "",
        f"import org.junit.jupiter.api.Test;",
        f"import static org.junit.jupiter.api.Assertions.*;",
        "",
        f"class {class_name} {{",
    ]

    for i, assertion in enumerate(context["assertions"]):
        test_method = f"    @Test"
        lines.append(test_method)

        method_name = f"    void test{fn.name.title()}_{i + 1}() {{"
        lines.append(method_name)

        if assertion.assertion_type == AssertionType.THROWS:
            lines.append(
                f"        assertThrows(Exception.class, () -> {{ {assertion.fn_call}; }});"
            )
        elif assertion.assertion_type == AssertionType.PROPERTY_EQ:
            lines.append(f"        var result = {assertion.fn_call};")
            if assertion.property_path:
                lines.append(
                    f"        assertEquals({assertion.expected_value}, result.{assertion.property_path});"
                )
            else:
                lines.append(
                    f"        assertEquals({assertion.expected_value}, result);"
                )
        elif assertion.assertion_type == AssertionType.CONTAINS:
            lines.append(f"        var result = {assertion.fn_call};")
            lines.append(
                f"        assertTrue(result.contains({assertion.expected_value}));"
            )

        lines.append("    }")
        lines.append("")

    lines.append("}")

    return "\n".join(lines)


def generate_test_module(
    fn_defs: list[FnDef], target_lang: str, module_name: Optional[str] = None
) -> str:
    """为多个函数生成完整的测试模块。

    Args:
        fn_defs: 函数定义列表
        target_lang: 目标语言
        module_name: 可选的模块名

    Returns:
        完整的测试模块代码
    """
    if target_lang == "python_fastapi":
        all_tests = []
        for fn in fn_defs:
            if fn.expect:
                test_code = generate_pytest_for_fn(fn)
                if test_code:
                    all_tests.append(test_code)
        return "\n\n".join(all_tests) if all_tests else ""

    elif target_lang == "java_springboot":
        all_tests = []
        for fn in fn_defs:
            if fn.expect:
                test_code = generate_junit_for_fn(fn)
                if test_code:
                    all_tests.append(test_code)
        return "\n\n".join(all_tests) if all_tests else ""

    return ""


def render_tests(
    fn_defs: list[FnDef], target_lang: str, output_dir: Path
) -> list[Path]:
    """将测试代码渲染到指定目录。

    Args:
        fn_defs: 函数定义列表
        target_lang: 目标语言
        output_dir: 输出目录

    Returns:
        生成的测试文件路径列表
    """
    output_dir = Path(output_dir)
    generated_files = []

    if target_lang == "python_fastapi":
        test_dir = output_dir / "tests"
        test_dir.mkdir(parents=True, exist_ok=True)

        init_content = '"""Auto-generated tests."""\n'
        (test_dir / "__init__.py").write_text(init_content, encoding="utf-8")

        for fn in fn_defs:
            if fn.expect:
                test_code = generate_pytest_for_fn(fn)
                if test_code:
                    test_file = test_dir / f"test_{fn.name}.py"
                    test_file.write_text(test_code, encoding="utf-8")
                    generated_files.append(test_file)

    elif target_lang == "java_springboot":
        for fn in fn_defs:
            if fn.expect:
                test_code = generate_junit_for_fn(fn)
                if test_code:
                    test_dir = (
                        output_dir / "src" / "test" / "java" / fn.name.replace("-", "_")
                    )
                    test_dir.mkdir(parents=True, exist_ok=True)
                    test_file = test_dir / f"Test{fn.name.title()}.java"
                    test_file.write_text(test_code, encoding="utf-8")
                    generated_files.append(test_file)

    return generated_files

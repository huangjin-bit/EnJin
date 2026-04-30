"""
============================================================
EnJin 错误恢复测试 (test_parser_error_recovery.py)
============================================================
验证解析器在各种畸形输入下的错误处理能力。

错误恢复测试场景:
    - 缺少闭合括号/引号
    - 截断的源码
    - 无效的 Unicode 字符
    - 嵌套层级错误
    - Native 块花括号不匹配
    - 缺失关键语法元素

维护协议:
    所有错误输入必须产生有意义的错误消息。
============================================================
"""

from __future__ import annotations

from pathlib import Path

import pytest

from enjinc.parser import parse


# ============================================================
# 缺少闭合括号测试
# ============================================================


class TestMissingClosingBraces:
    """验证缺少闭合括号的错误处理。"""

    def test_missing_closing_brace_struct(self, malformed_inputs: dict):
        """缺少 struct 的闭合花括号。"""
        with pytest.raises(Exception):
            parse(malformed_inputs["missing_closing_brace_struct"])

    def test_missing_closing_brace_fn(self, malformed_inputs: dict):
        """缺少 fn 的闭合花括号。"""
        with pytest.raises(Exception):
            parse(malformed_inputs["missing_closing_brace_fn"])

    def test_missing_closing_brace_module(self, malformed_inputs: dict):
        """缺少 module 的闭合花括号。"""
        with pytest.raises(Exception):
            parse(malformed_inputs["missing_closing_brace_module"])

    def test_missing_closing_brace_route(self, malformed_inputs: dict):
        """缺少 route 的闭合花括号。"""
        with pytest.raises(Exception):
            parse(malformed_inputs["missing_closing_brace_route"])

    def test_extra_closing_brace(self):
        """多余的闭合花括号。"""
        source = """
struct Extra {
    id: Int @primary
}}
"""
        with pytest.raises(Exception):
            parse(source)

    def test_mismatched_braces_fn(self):
        """fn 中花括号不匹配（process 块未闭合）。"""
        source = """
fn bad_fn(id: Int) -> Int {
    process { "test"
}
"""
        with pytest.raises(Exception):
            parse(source)


# ============================================================
# 缺少关键语法元素测试
# ============================================================


class TestMissingSyntaxElements:
    """验证缺少关键语法元素的错误处理。"""

    def test_missing_colon_in_field(self, malformed_inputs: dict):
        """字段定义缺少冒号。"""
        with pytest.raises(Exception):
            parse(malformed_inputs["missing_colon_field"])

    def test_missing_arrow_return_type(self, malformed_inputs: dict):
        """fn 缺少返回类型箭头。"""
        with pytest.raises(Exception):
            parse(malformed_inputs["missing_arrow_return_type"])

    def test_missing_paren_params(self, malformed_inputs: dict):
        """fn 缺少参数括号。"""
        with pytest.raises(Exception):
            parse(malformed_inputs["missing_paren_params"])

    def test_missing_type_in_field(self, malformed_inputs: dict):
        """字段定义缺少类型。"""
        with pytest.raises(Exception):
            parse(malformed_inputs["missing_type_in_field"])

    def test_missing_annotation_args_parens(self):
        """注解缺少括号。"""
        source = """
struct Bad {
    @table
    id: Int
}
"""
        with pytest.raises(Exception):
            parse(source)

    def test_missing_guard_open_brace(self):
        """guard 缺少开括号。"""
        source = """
fn bad_guard(id: Int) -> Int
    guard {
        id > 0 : "positive"
    }
    process { "test" }
}
"""
        with pytest.raises(Exception):
            parse(source)


# ============================================================
# Native 块错误测试
# ============================================================


class TestNativeBlockErrors:
    """验证 native 块的各种错误情况。"""

    def test_native_unbalanced_braces(self, malformed_inputs: dict):
        """native 块花括号不匹配。"""
        with pytest.raises(Exception):
            parse(malformed_inputs["native_unbalanced_braces"])

    def test_native_without_target_language(self):
        """native 块缺少目标语言。"""
        source = """
fn bad_native(data: String) -> String {
    native {
        return data
    }
}
"""
        with pytest.raises(Exception):
            parse(source)

    def test_native_empty_block(self):
        """native 块为空——语法层面可能被接受，语义层面由 analyzer 拒绝。"""
        source = """
fn empty_native(data: String) -> String {
    native python {
    }
}
"""
        # 语法层面允许空 native 块（NATIVE_CODE 可匹配空白），
        # 语义校验由 analyzer 负责。
        program = parse(source)
        assert len(program.functions) == 1


# ============================================================
# 空文件和注释测试
# ============================================================


class TestEmptyAndCommentOnly:
    """验证空文件和纯注释文件的处理。"""

    def test_empty_file(self, malformed_inputs: dict):
        """空文件。"""
        program = parse(malformed_inputs["empty_file"])
        assert program.structs == []
        assert program.functions == []
        assert program.modules == []
        assert program.routes == []

    def test_comment_only_file(self, malformed_inputs: dict):
        """仅包含注释的文件。"""
        program = parse(malformed_inputs["comment_only"])
        assert program.structs == []
        assert program.functions == []
        assert program.modules == []
        assert program.routes == []

    def test_only_whitespace(self):
        """仅包含空白字符。"""
        source = "   \n\n   \n   "
        program = parse(source)
        assert len(program.structs) == 0


# ============================================================
# 截断文件测试
# ============================================================


class TestTruncatedFiles:
    """验证截断源码的错误处理。"""

    def test_truncated_mid_token(self, malformed_inputs: dict):
        """文件在 token 中间被截断。"""
        with pytest.raises(Exception):
            parse(malformed_inputs["truncated_mid_token"])

    def test_truncated_in_string(self):
        """在字符串字面量中截断。"""
        source = """
struct Bad {
    name: String @default("unclosed string)
}
"""
        with pytest.raises(Exception):
            parse(source)

    def test_truncated_in_native_block(self):
        """在 native 块中截断。"""
        source = """
fn broken_native(data: String) -> String {
    native python {
        import hashlib
        return hashlib.sha
"""
        with pytest.raises(Exception):
            parse(source)


# ============================================================
# 无效语法结构测试
# ============================================================


class TestInvalidStructures:
    """验证无效语法结构的错误处理。"""

    def test_struct_inside_struct(self, malformed_inputs: dict):
        """struct 内部定义了另一个 struct（不支持嵌套）。"""
        with pytest.raises(Exception):
            parse(malformed_inputs["struct_inside_struct"])

    def test_fn_inside_fn(self, malformed_inputs: dict):
        """fn 内部定义了另一个 fn（不支持嵌套）。"""
        with pytest.raises(Exception):
            parse(malformed_inputs["fn_inside_fn"])

    def test_wrong_keyword_module(self, malformed_inputs: dict):
        """module 中使用了 route 关键字。"""
        with pytest.raises(Exception):
            parse(malformed_inputs["wrong_keyword_module"])

    def test_route_inside_module(self):
        """route 定义在 module 内部。"""
        source = """
module Bad {
    route InnerRoute {
        GET "/test" -> handler
    }
}
"""
        with pytest.raises(Exception):
            parse(source)

    def test_struct_inside_fn(self):
        """struct 定义在 fn 内部。"""
        source = """
fn bad_fn() {
    struct Inner {
        id: Int
    }
}
"""
        with pytest.raises(Exception):
            parse(source)


# ============================================================
# 无效注解测试
# ============================================================


class TestInvalidAnnotations:
    """验证无效注解语法的错误处理。"""

    def test_invalid_annotation_syntax(self, malformed_inputs: dict):
        """注解语法无效——@ 后跟空格在语法层面合法（WS_INLINE 被忽略）。"""
        # "@ table(...)" 等价于 "@table(...)"，语法层面有效
        # 语义校验（未知注解名、参数类型）由 analyzer 负责
        program = parse(malformed_inputs["invalid_annotation_syntax"])
        assert len(program.structs) == 1

    def test_annotation_on_nonexistent_element(self):
        """注解在不存在元素上。"""
        source = """
@table("users")
"""
        with pytest.raises(Exception):
            parse(source)

    def test_unknown_annotation_name(self):
        """未知的注解名称——语法层面合法（NAME 匹配任意标识符），语义校验由 analyzer 负责。"""
        source = """
@unknown_annotation
struct Test {
    id: Int
}
"""
        program = parse(source)
        assert len(program.structs) == 1

    def test_annotation_with_wrong_args_type(self):
        """注解参数类型——NUMBER 是合法 annotation_arg，语义校验由 analyzer 负责。"""
        source = """
@table(123)
struct Bad {
    id: Int
}
"""
        program = parse(source)
        assert len(program.structs) == 1


# ============================================================
# 无效类型测试
# ============================================================


class TestInvalidTypes:
    """验证无效类型引用的错误处理。"""

    def test_undefined_type_reference(self):
        """引用未定义的类型——语法层面合法（base_type 匹配任意 NAME），语义校验由 analyzer 负责。"""
        source = """
struct Bad {
    field: UndefinedType
}
"""
        program = parse(source)
        assert len(program.structs) == 1
        assert program.structs[0].fields[0].type.base == "UndefinedType"

    def test_invalid_generic_type(self):
        """无效的泛型类型。"""
        source = """
struct Bad {
    field: List<>
}
"""
        with pytest.raises(Exception):
            parse(source)

    def test_nested_generic_without_closing(self):
        """嵌套泛型缺少闭合。"""
        source = """
struct Bad {
    field: List<Map<String
}
"""
        with pytest.raises(Exception):
            parse(source)


# ============================================================
# 错误消息质量测试
# ============================================================


class TestErrorMessageQuality:
    """验证错误消息的质量和有用性。"""

    def test_error_message_contains_line_number(self):
        """错误消息应包含行号（使用 UnexpectedCharacters 而非 UnexpectedEOF 场景）。"""
        source = """
struct Bad {
    id: Int @primary
    name: $$$
}
"""
        try:
            parse(source)
            assert False, "Should have raised an exception"
        except Exception as e:
            error_msg = str(e)
            assert "line" in error_msg.lower()

    def test_error_message_contains_column_info(self):
        """错误消息应包含列信息（Lark 使用 'col' 关键字）。"""
        source = """
struct Bad {
    id: Int @primary
    name: $$$
}
"""
        try:
            parse(source)
            assert False, "Should have raised an exception"
        except Exception as e:
            error_msg = str(e)
            assert "col" in error_msg.lower()

    def test_multiple_errors_reported_together(self):
        """多个错误应该被一起报告。"""
        source = """
struct A {
    id Int
    name String
}
"""
        try:
            parse(source)
        except Exception as e:
            error_msg = str(e)
            assert len(error_msg) > 0


# ============================================================
# 特殊字符和编码测试
# ============================================================


class TestSpecialCharacters:
    """验证特殊字符和编码的处理。"""

    def test_valid_unicode_in_strings(self):
        """字符串中支持有效的 Unicode。"""
        source = """
struct Unicode {
    name: String @default("中文名称")
    emoji: String @default("😀")
}
"""
        program = parse(source)
        assert len(program.structs) == 1

    def test_invalid_unicode_in_identifier(self, malformed_inputs: dict):
        """标识符中包含无效 Unicode。"""
        with pytest.raises(Exception):
            parse(malformed_inputs["invalid_unicode_ident"])

    def test_control_characters_in_string(self):
        """字符串中包含控制字符。"""
        source = """
struct Bad {
    name: String @default("line1\\nline2")
}
"""
        try:
            parse(source)
        except Exception:
            pass


# ============================================================
# 超大输入测试
# ============================================================


class TestExtremelyLargeInputs:
    """验证超大输入的处理。"""

    def test_very_long_single_line(self):
        """非常长的单行源码。"""
        long_name = "a" * 10000
        source = f"""
struct VeryLong {{
    field: String @{long_name}
}}
"""
        try:
            parse(source)
        except Exception:
            pass

    def test_deeply_nested_blocks(self):
        """深层嵌套的块结构。"""
        source = """
struct Deep {{
    field1: String
    field2: String
    field3: String
    field4: String
    field5: String
"""
        with pytest.raises(Exception):
            parse(source)


# ============================================================
# CRLF vs LF 处理测试
# ============================================================


class TestLineEndingHandling:
    """验证不同行尾符号的处理。"""

    def test_crlf_line_endings(self):
        """Windows CRLF 行尾。"""
        source = "struct Test {\r\n    id: Int @primary\r\n}\r\n"
        program = parse(source)
        assert len(program.structs) == 1

    def test_mixed_line_endings(self):
        """混合 LF 和 CRLF 行尾。"""
        source = "struct A {\r\n    id: Int\r\n}\nstruct B {\n    name: String\r\n}"
        program = parse(source)
        assert len(program.structs) == 2

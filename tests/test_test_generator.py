"""
============================================================
EnJin 测试生成器测试 (test_test_generator.py)
============================================================
验证 expect 断言解析和测试代码生成功能。
============================================================
"""

import pytest

from enjinc.ast_nodes import (
    Annotation,
    ExpectAssertion,
    FnDef,
    Param,
    ProcessIntent,
    TypeRef,
)
from enjinc.test_generator import (
    AssertionType,
    ParsedAssertion,
    parse_expect_assertion,
    generate_pytest_for_fn,
    generate_junit_for_fn,
    generate_test_module,
)


class TestParseExpectAssertion:
    """测试 expect 断言解析。"""

    def test_property_eq_assertion(self):
        """测试属性相等断言解析。"""
        raw = 'register_user("alice", "alice@test.com").username == "alice"'
        result = parse_expect_assertion(raw)

        assert result.assertion_type == AssertionType.PROPERTY_EQ
        assert result.fn_name == "register_user"
        assert result.fn_args == ['"alice"', '"alice@test.com"']
        assert result.property_path == "username"
        assert result.expected_value == '"alice"'

    def test_throws_assertion(self):
        """测试异常抛出断言解析。"""
        raw = 'register_user("", "bad").throws("用户名不能为空")'
        result = parse_expect_assertion(raw)

        assert result.assertion_type == AssertionType.THROWS
        assert result.fn_name == "register_user"
        assert result.fn_args == ['""', '"bad"']
        assert result.expected_exception == "用户名不能为空"

    def test_status_eq_assertion(self):
        """测试 HTTP 状态断言解析。"""
        raw = "get_user(1).status == 200"
        result = parse_expect_assertion(raw)

        assert result.assertion_type == AssertionType.STATUS_EQ
        assert result.fn_name == "get_user"
        assert result.fn_args == ["1"]
        assert result.property_path == "status"
        assert result.expected_value == "200"

    def test_contains_assertion(self):
        """测试包含断言解析。"""
        raw = 'search_products("laptop").contains("results")'
        result = parse_expect_assertion(raw)

        assert result.assertion_type == AssertionType.CONTAINS
        assert result.fn_name == "search_products"
        assert result.fn_args == ['"laptop"']
        assert result.expected_value == '"results"'

    def test_simple_eq_assertion(self):
        """测试简单相等断言（无属性访问）。"""
        raw = "is_valid(1) == true"
        result = parse_expect_assertion(raw)

        assert result.assertion_type == AssertionType.PROPERTY_EQ
        assert result.fn_name == "is_valid"
        assert result.fn_args == ["1"]
        assert result.expected_value == "true"

    def test_no_args_fn_call(self):
        """测试无参函数调用。"""
        raw = "get_current_user()"
        result = parse_expect_assertion(raw)

        assert result.fn_name == "get_current_user"
        assert result.fn_args == []


class TestGeneratePytestForFn:
    """测试 pytest 测试代码生成。"""

    def _make_fn(self, name: str, expect_raws: list[str]) -> FnDef:
        """创建带有 expect 断言的 FnDef。"""
        return FnDef(
            name=name,
            params=[
                Param(name="id", type=TypeRef(base="Int")),
            ],
            return_type=TypeRef(base="User"),
            expect=[ExpectAssertion(raw=raw) for raw in expect_raws],
        )

    def test_generate_property_eq_test(self):
        """测试属性相等测试生成。"""
        fn = self._make_fn("get_user", ['get_user(1).username == "admin"'])
        result = generate_pytest_for_fn(fn)

        assert "class TestGetuser:" in result
        assert "test_get_user_1" in result
        assert "get_user(1)" in result
        assert "result.username" in result
        assert '=="admin"' in result or '== "admin"' in result

    def test_generate_throws_test(self):
        """测试异常抛出测试生成。"""
        fn = self._make_fn(
            "register_user", ['register_user("", "bad").throws("用户名不能为空")']
        )
        result = generate_pytest_for_fn(fn)

        assert "pytest.raises" in result
        assert 'register_user("", "bad")' in result
        assert "用户名不能为空" in result

    def test_generate_empty_expect(self):
        """测试空 expect 列表返回空字符串。"""
        fn = self._make_fn("get_user", [])
        result = generate_pytest_for_fn(fn)

        assert result == ""


class TestGenerateJUnitForFn:
    """测试 JUnit 测试代码生成。"""

    def _make_fn(self, name: str, expect_raws: list[str]) -> FnDef:
        """创建带有 expect 断言的 FnDef。"""
        return FnDef(
            name=name,
            params=[
                Param(name="id", type=TypeRef(base="Int")),
            ],
            return_type=TypeRef(base="User"),
            expect=[ExpectAssertion(raw=raw) for raw in expect_raws],
        )

    def test_generate_property_eq_test(self):
        """测试属性相等测试生成。"""
        fn = self._make_fn("get_user", ['get_user(1).username == "admin"'])
        result = generate_junit_for_fn(fn)

        assert "class TestGetuser" in result
        assert "testGetuser_1" in result
        assert "var result = get_user(1);" in result
        assert "result.username()" in result

    def test_generate_throws_test(self):
        """测试异常抛出测试生成。"""
        fn = self._make_fn(
            "register_user", ['register_user("", "bad").throws("用户名不能为空")']
        )
        result = generate_junit_for_fn(fn)

        assert "assertThrows" in result
        assert "Exception.class" in result


class TestGenerateTestModule:
    """测试测试模块生成。"""

    def test_generate_python_test_module(self):
        """测试 Python 测试模块生成。"""
        fns = [
            FnDef(
                name="get_user",
                params=[],
                return_type=TypeRef(base="User"),
                expect=[ExpectAssertion(raw='get_user(1).username == "admin"')],
            ),
            FnDef(
                name="create_user",
                params=[],
                return_type=TypeRef(base="User"),
                expect=[ExpectAssertion(raw='create_user("bob").throws("invalid")')],
            ),
        ]

        result = generate_test_module(fns, "python_fastapi")

        assert "TestGetuser" in result
        assert "TestCreateuser" in result
        assert "get_user(1)" in result
        assert "pytest.raises" in result

    def test_generate_java_test_module(self):
        """测试 Java 测试模块生成。"""
        fns = [
            FnDef(
                name="get_user",
                params=[],
                return_type=TypeRef(base="User"),
                expect=[ExpectAssertion(raw='get_user(1).username == "admin"')],
            ),
        ]

        result = generate_test_module(fns, "java_springboot")

        assert "class TestGetuser" in result
        assert "var result = get_user(1);" in result

    def test_unsupported_target_lang(self):
        """测试不支持的目标语言。"""
        fns = [
            FnDef(
                name="get_user",
                params=[],
                return_type=TypeRef(base="User"),
                expect=[ExpectAssertion(raw="get_user(1).id == 1")],
            ),
        ]

        result = generate_test_module(fns, "unsupported_lang")
        assert result == ""


class TestEdgeCases:
    """边界情况测试。"""

    def test_nested_parentheses_in_args(self):
        """测试参数中嵌套括号。"""
        raw = 'create_order({"items": [1, 2, 3]}).id == 1'
        result = parse_expect_assertion(raw)

        assert result.fn_name == "create_order"
        assert result.property_path == "id"
        assert result.expected_value == "1"

    def test_quoted_string_with_escaped_quote(self):
        """测试带转义引号的字符串。"""
        raw = r'message("say \"hello\"").content == "ok"'
        result = parse_expect_assertion(raw)

        assert result.fn_name == "message"
        assert 'say \\"hello\\"' in result.fn_args[0]

    def test_complex_property_path(self):
        """测试复杂属性路径（嵌套属性）。"""
        raw = 'get_user(1).profile.address.city == "Beijing"'
        result = parse_expect_assertion(raw)

        assert (
            result.fn_name == "get_user" or "get_user(1).profile.address" in result.raw
        )
        assert result.expected_value == '"Beijing"'


class TestGeneratedPytestExecution:
    """测试生成的 pytest 代码实际运行。"""

    def test_generated_pytest_runs_successfully(self):
        """验证生成的 pytest 代码能成功运行。"""
        import tempfile
        import subprocess
        import sys
        from pathlib import Path

        service_code = """
class User:
    def __init__(self, username, email):
        self.username = username
        self.email = email

def register_user(username, email):
    if not username or len(username) == 0:
        raise ValueError('invalid input')
    return User(username, email)

def get_user(id):
    return User('admin', 'admin@test.com')
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            service_path = Path(tmpdir) / "service.py"
            service_path.write_text(service_code, encoding="utf-8")

            fn = FnDef(
                name="register_user",
                params=[
                    Param(name="username", type=TypeRef(base="String")),
                    Param(name="email", type=TypeRef(base="String")),
                ],
                return_type=TypeRef(base="User"),
                expect=[
                    ExpectAssertion(
                        raw='register_user("alice", "alice@test.com").username == "alice"'
                    ),
                    ExpectAssertion(
                        raw='register_user("", "bad").throws("invalid input")'
                    ),
                ],
            )

            test_code = generate_pytest_for_fn(fn)
            test_code = "from service import *\n\n" + test_code

            test_path = Path(tmpdir) / "test_register_user.py"
            test_path.write_text(test_code, encoding="utf-8")

            sys.path.insert(0, tmpdir)

            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_path), "-v", "--tb=short"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            assert result.returncode == 0, (
                f"pytest failed: {result.stdout}\n{result.stderr}"
            )
            assert "test_register_user_1 PASSED" in result.stdout
            assert "test_register_user_2 PASSED" in result.stdout

    def test_generated_pytest_with_status_assertion(self):
        """验证生成的 HTTP 状态断言测试能成功运行。"""
        import tempfile
        import subprocess
        import sys
        from pathlib import Path

        service_code = """
class ApiResponse:
    def __init__(self, status, data):
        self.status = status
        self.data = data

def get_user(id):
    return ApiResponse(200, {"username": "admin"})
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            service_path = Path(tmpdir) / "service.py"
            service_path.write_text(service_code, encoding="utf-8")

            fn = FnDef(
                name="get_user",
                params=[Param(name="id", type=TypeRef(base="Int"))],
                return_type=TypeRef(base="ApiResponse"),
                expect=[
                    ExpectAssertion(raw="get_user(1).status == 200"),
                ],
            )

            test_code = generate_pytest_for_fn(fn)
            test_code = "from service import *\n\n" + test_code

            test_path = Path(tmpdir) / "test_get_user.py"
            test_path.write_text(test_code, encoding="utf-8")

            sys.path.insert(0, tmpdir)

            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_path), "-v", "--tb=short"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            assert result.returncode == 0, (
                f"pytest failed: {result.stdout}\n{result.stderr}"
            )
            assert "test_get_user_1 PASSED" in result.stdout

    def test_generated_pytest_with_contains_assertion(self):
        """验证生成的 contains 断言测试能成功运行。"""
        import tempfile
        import subprocess
        import sys
        from pathlib import Path

        service_code = """
def search_products(query):
    return {"laptop": {"name": "Laptop Pro"}, "total": 1}
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            service_path = Path(tmpdir) / "service.py"
            service_path.write_text(service_code, encoding="utf-8")

            fn = FnDef(
                name="search_products",
                params=[Param(name="query", type=TypeRef(base="String"))],
                return_type=TypeRef(base="Dict"),
                expect=[
                    ExpectAssertion(raw='search_products("laptop").contains("laptop")'),
                ],
            )

            test_code = generate_pytest_for_fn(fn)
            test_code = "from service import *\n\n" + test_code

            test_path = Path(tmpdir) / "test_search.py"
            test_path.write_text(test_code, encoding="utf-8")

            sys.path.insert(0, tmpdir)

            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_path), "-v", "--tb=short"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            assert result.returncode == 0, (
                f"pytest failed: {result.stdout}\n{result.stderr}"
            )
            assert "test_search_products_1 PASSED" in result.stdout

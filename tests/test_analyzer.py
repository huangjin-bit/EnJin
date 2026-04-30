"""
============================================================
EnJin 静态分析器单元测试 (test_analyzer.py)
============================================================
验证 analyzer.py 对四层架构与 route->module action 约束的校验能力。

测试覆盖:
    1. 合法示例通过
    2. route 直绑裸 fn
    3. route 非法依赖 fn
    4. route handler 非导出 action
    5. module 依赖 route
    6. module export target 不是 fn
    7. module export target 未在 use 中声明
    8. route action 在多 module 下歧义
    9. module-to-module 依赖循环检测
    10. @domain 跨域依赖与注解形态校验
    11. 注解注册表校验（未知注解/作用域/参数）
    12. 规划态注解语义校验（@engine/@api_contract/@data_plane）
============================================================
"""

from __future__ import annotations

from pathlib import Path

import pytest

from enjinc.analyzer import EnJinAnalysisError, analyze, assert_valid
from enjinc.parser import parse, parse_file


def _issue_codes(issues) -> set[str]:
    return {issue.code for issue in issues}


class TestAnalyzer:
    """静态分析器行为测试。"""

    def test_user_management_example_passes(self, examples_dir: Path):
        """官方四层示例应通过最小静态分析。"""
        filepath = examples_dir / "user_management.ej"
        if not filepath.exists():
            pytest.skip("examples/user_management.ej not found")

        program = parse_file(filepath)
        issues = analyze(program)
        assert issues == []

    def test_route_binds_raw_fn(self):
        """route 不能直接绑定裸 fn。"""
        source = """
fn register_user(username: String, email: String, password: String) -> User {
    process {
        "创建用户"
    }
}

module UserManager {
    use register_user
    export register = register_user
}

route UserService {
    use UserManager
    POST "/register" -> register_user
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "ROUTE_BINDS_RAW_FN" in codes

    def test_route_cannot_use_method_dependency(self):
        """route 只能 use module，不能 use fn。"""
        source = """
fn register_user(username: String, email: String, password: String) -> User {
    process {
        "创建用户"
    }
}

route UserService {
    use register_user
    POST "/register" -> register
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "ROUTE_CANNOT_USE_METHOD" in codes

    def test_route_action_not_exported(self):
        """route handler 必须来自依赖 module 的 export。"""
        source = """
fn register_user(username: String, email: String, password: String) -> User {
    process {
        "创建用户"
    }
}

module UserManager {
    use register_user
    export register = register_user
}

route UserService {
    use UserManager
    POST "/register" -> create
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "ROUTE_ACTION_NOT_EXPORTED" in codes

    def test_module_cannot_use_route(self):
        """module 不能依赖 route（禁止越级）。"""
        source = """
route UserService {
}

module UserManager {
    use UserService
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "MODULE_CANNOT_USE_ROUTE" in codes

    def test_module_export_target_not_fn(self):
        """module export target 必须是 fn。"""
        source = """
struct User {
    id: Int
}

module UserManager {
    use User
    export register = User
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "MODULE_EXPORT_TARGET_NOT_FN" in codes

    def test_module_export_target_must_be_in_use(self):
        """module export target 必须在 use 中显式声明。"""
        source = """
fn register_user(username: String, email: String, password: String) -> User {
    process {
        "创建用户"
    }
}

module UserManager {
    export register = register_user
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "MODULE_EXPORT_TARGET_NOT_IN_USE" in codes

    def test_route_ambiguous_action(self):
        """route 依赖多个 module 时，action 不允许重名。"""
        source = """
fn register_user(username: String, email: String, password: String) -> User {
    process {
        "创建用户"
    }
}

fn register_user_v2(username: String, email: String, password: String) -> User {
    process {
        "创建用户 v2"
    }
}

module UserManagerA {
    use register_user
    export register = register_user
}

module UserManagerB {
    use register_user_v2
    export register = register_user_v2
}

route UserService {
    use UserManagerA
    use UserManagerB
    POST "/register" -> register
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "ROUTE_AMBIGUOUS_ACTION" in codes

    def test_module_dependency_cycle(self):
        """module-to-module 依赖必须是 DAG，禁止循环。"""
        source = """
module A {
    use B
}

module B {
    use C
}

module C {
    use A
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "MODULE_DEPENDENCY_CYCLE" in codes

    def test_module_cross_domain_dependency(self):
        """当双方都声明 @domain 时，禁止直接跨域 module 依赖。"""
        source = """
@domain(name="payment")
module PaymentApp {
}

@domain(name="order")
module OrderApp {
    use PaymentApp
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "MODULE_CROSS_DOMAIN_DEPENDENCY" in codes

    def test_module_invalid_domain_annotation(self):
        """@domain 注解参数非法时应报错。"""
        source = """
@domain(name=123)
module UserApp {
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "MODULE_INVALID_DOMAIN_ANNOTATION" in codes

    def test_module_domain_positional_arg_is_valid(self):
        """@domain("...") 位置参数形式应被识别为合法。"""
        source = """
@domain("user")
module UserApp {
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "MODULE_INVALID_DOMAIN_ANNOTATION" not in codes

    def test_module_cross_domain_requires_both_sides_labeled(self):
        """仅一侧声明 @domain 时，不触发跨域依赖阻断。"""
        source = """
module SharedLib {
}

@domain(name="order")
module OrderApp {
    use SharedLib
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "MODULE_CROSS_DOMAIN_DEPENDENCY" not in codes

    def test_module_duplicate_domain_annotation(self):
        """同一 module 上重复 @domain 应报错。"""
        source = """
@domain(name="user")
@domain(name="member")
module UserApp {
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "MODULE_DUPLICATE_DOMAIN_ANNOTATION" in codes

    def test_annotation_unknown(self):
        """未注册注解应报 ANNOTATION_UNKNOWN。"""
        source = """
@foobar
fn ping() {
    process {
        "打点"
    }
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "ANNOTATION_UNKNOWN" in codes

    def test_annotation_invalid_scope(self):
        """注解作用域错误应报 ANNOTATION_INVALID_SCOPE。"""
        source = """
@prefix("/api")
fn ping() {
    process {
        "打点"
    }
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "ANNOTATION_INVALID_SCOPE" in codes

    def test_annotation_invalid_args(self):
        """注解参数类型/个数错误应报 ANNOTATION_INVALID_ARGS。"""
        source = """
@retry("three")
fn ping() {
    process {
        "打点"
    }
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "ANNOTATION_INVALID_ARGS" in codes

    def test_annotation_endpoint_scope_valid(self):
        """@locked 在 endpoint 作用域应合法。"""
        source = """
fn remove_user(id: Int) {
    process {
        "删除用户"
    }
}

module UserManager {
    use remove_user
    export remove = remove_user
}

route UserService {
    use UserManager

    @locked
    DELETE "/{id}" -> remove
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "ANNOTATION_INVALID_SCOPE" not in codes
        assert "ANNOTATION_UNKNOWN" not in codes

    def test_engine_duplicate_annotation(self):
        """同一 module 上重复 @engine 应报错。"""
        source = """
@engine(type="workflow", framework="temporal")
@engine(type="workflow", framework="temporal")
module AgentWorkflow {
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "MODULE_DUPLICATE_ENGINE_ANNOTATION" in codes

    def test_engine_unsupported_type(self):
        """@engine type 超出支持集合应报错。"""
        source = """
@engine(type="batch", framework="custom")
module AgentWorkflow {
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "MODULE_ENGINE_UNSUPPORTED_TYPE" in codes

    def test_engine_framework_type_mismatch(self):
        """framework 与 type 组合不匹配应报错。"""
        source = """
@engine(type="state_machine", framework="temporal")
module AgentWorkflow {
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "MODULE_ENGINE_FRAMEWORK_TYPE_MISMATCH" in codes

    def test_api_contract_cannot_have_native_impl(self):
        """@api_contract 不允许 native 实现块。"""
        source = """
@api_contract
fn call_tool(name: String, payload: String) -> String {
    native python {
        return "done"
    }
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "API_CONTRACT_HAS_NATIVE_IMPL" in codes

    def test_data_plane_cannot_have_native_impl(self):
        """@data_plane 不允许 native 实现块。"""
        source = """
@data_plane(protocol="grpc", engine="flink")
fn calculate_ctr(user_id: Int, product_id: Int) -> Float {
    native python {
        return 0.1
    }
}
"""
        program = parse(source)
        issues = analyze(program)
        codes = _issue_codes(issues)
        assert "DATA_PLANE_HAS_NATIVE_IMPL" in codes

    def test_assert_valid_raises(self):
        """assert_valid 在存在问题时应抛出聚合异常。"""
        source = """
fn register_user(username: String, email: String, password: String) -> User {
    process {
        "创建用户"
    }
}

module UserManager {
    use register_user
    export register = register_user
}

route UserService {
    use UserManager
    POST "/register" -> register_user
}
"""
        program = parse(source)

        with pytest.raises(EnJinAnalysisError) as exc_info:
            assert_valid(program)

        assert any(issue.code == "ROUTE_BINDS_RAW_FN" for issue in exc_info.value.issues)


class TestHumanMaintainedScope:
    """验证 @human_maintained 注解的作用域规则。"""

    def test_human_maintained_allowed_on_fn(self):
        """@human_maintained 在 fn 上合法。"""
        source = """
struct User { id: Int @primary }

@human_maintained
fn legacy_fn(id: Int) -> User {
    process { "get user" }
}
"""
        program = parse(source)
        issues = analyze(program)
        assert not any(i.code == "ANNOTATION_INVALID_SCOPE" for i in issues)

    def test_human_maintained_rejected_on_struct(self):
        """@human_maintained 不允许用在 struct 上。"""
        source = """
@human_maintained
struct LegacyEntity {
    id: Int @primary
}
"""
        program = parse(source)
        issues = analyze(program)
        assert any(
            i.code == "ANNOTATION_INVALID_SCOPE" and "human_maintained" in i.message
            for i in issues
        )

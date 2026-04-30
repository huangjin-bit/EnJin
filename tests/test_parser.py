"""
============================================================
EnJin 解析器单元测试 (test_parser.py)
============================================================
验证 parser.py 能否将 .ej 源码正确解析为 I-AST 节点。

测试覆盖:
    1. struct 定义（含注解、字段、类型系统）
    2. fn 定义（三段意图体: guard/process/expect）
    3. fn 的 native 逃生舱
    4. module 定义（annotation/use/export/init/schedule）
    5. route 定义（HTTP 端点映射）
    6. application 全局配置
    7. @locked 注解的 is_locked 标志检测
    8. 完整的 user_management.ej 示例文件解析
============================================================
"""

import json
from pathlib import Path

import pytest

from enjinc.parser import parse, parse_file
from enjinc.ast_nodes import (
    Program,
    StructDef,
    FnDef,
    ModuleDef,
    RouteDef,
    ApplicationConfig,
)


# ============================================================
# 1. struct 定义测试
# ============================================================


class TestStructParsing:
    """验证 Model 层 (struct) 的解析能力。"""

    def test_simple_struct(self):
        """最简单的 struct: 无注解、单字段。"""
        source = """
struct User {
    id: Int
}
"""
        program = parse(source)
        assert len(program.structs) == 1

        user = program.structs[0]
        assert user.name == "User"
        assert len(user.fields) == 1
        assert user.fields[0].name == "id"
        assert user.fields[0].type.base == "Int"

    def test_struct_with_table_annotation(self):
        """struct 带 @table 注解。"""
        source = """
@table("users")
struct User {
    id: Int @primary @auto_increment
    username: String @unique @max_length(50)
}
"""
        program = parse(source)
        user = program.structs[0]

        # struct 级注解
        assert len(user.annotations) == 1
        assert user.annotations[0].name == "table"
        assert user.annotations[0].args == ["users"]

        # 字段级注解
        id_field = user.fields[0]
        assert id_field.name == "id"
        anno_names = [a.name for a in id_field.annotations]
        assert "primary" in anno_names
        assert "auto_increment" in anno_names

        username_field = user.fields[1]
        assert username_field.name == "username"
        assert username_field.type.base == "String"
        max_len = [a for a in username_field.annotations if a.name == "max_length"]
        assert len(max_len) == 1
        assert max_len[0].args == [50]

    def test_struct_with_enum_type(self):
        """struct 字段使用 Enum 类型。"""
        source = """
struct User {
    status: Enum("active", "banned") @default("active")
}
"""
        program = parse(source)
        field = program.structs[0].fields[0]
        assert field.type.base == "Enum"
        assert field.type.params == ["active", "banned"]

    def test_struct_with_optional_type(self):
        """struct 字段使用 Optional<T> 类型。"""
        source = """
struct Profile {
    bio: Optional<String>
}
"""
        program = parse(source)
        field = program.structs[0].fields[0]
        assert field.type.base == "String"
        assert field.type.is_optional is True

    def test_struct_with_generic_type(self):
        """struct 字段使用 List<T> 泛型类型。"""
        source = """
struct Post {
    tags: List<String>
}
"""
        program = parse(source)
        field = program.structs[0].fields[0]
        assert field.type.base == "List"
        assert len(field.type.params) == 1
        assert field.type.params[0].base == "String"

    def test_multiple_structs(self):
        """同一文件中定义多个 struct。"""
        source = """
struct User {
    id: Int
}

struct Post {
    title: String
}
"""
        program = parse(source)
        assert len(program.structs) == 2
        assert program.structs[0].name == "User"
        assert program.structs[1].name == "Post"


# ============================================================
# 2. fn 定义测试 (三段意图体)
# ============================================================


class TestFnParsing:
    """验证 Method 层 (fn) 的解析能力，含 guard/process/expect。"""

    def test_fn_with_process_only(self):
        """最简 fn: 只有 process 块。"""
        source = """
fn hello() -> String {
    process {
        "返回 Hello World 字符串"
    }
}
"""
        program = parse(source)
        assert len(program.functions) == 1

        fn = program.functions[0]
        assert fn.name == "hello"
        assert fn.return_type.base == "String"
        assert fn.process is not None
        assert "Hello World" in fn.process.intent

    def test_fn_with_full_triplet(self):
        """完整三段体: guard + process + expect。"""
        source = """
fn register_user(username: String, email: String) -> User {
    guard {
        username.length > 0 : "用户名不能为空"
        email.contains("@") : "邮箱格式不合法"
    }

    process {
        "创建新用户并写入数据库"
    }

    expect {
        register_user("alice", "alice@test.com").username == "alice"
        register_user("", "bad").throws("用户名不能为空")
    }
}
"""
        program = parse(source)
        fn = program.functions[0]

        # 参数
        assert len(fn.params) == 2
        assert fn.params[0].name == "username"
        assert fn.params[0].type.base == "String"
        assert fn.params[1].name == "email"

        # 返回类型
        assert fn.return_type.base == "User"

        # guard
        assert len(fn.guard) == 2
        assert "username.length > 0" in fn.guard[0].expr
        assert fn.guard[0].message == "用户名不能为空"
        assert fn.guard[1].message == "邮箱格式不合法"

        # process
        assert fn.process is not None
        assert "创建新用户" in fn.process.intent

        # expect
        assert len(fn.expect) == 2
        assert "alice" in fn.expect[0].raw

    def test_fn_with_annotations(self):
        """fn 带注解: @transactional。"""
        source = """
@transactional
fn transfer(from_id: Int, to_id: Int, amount: Float) -> Bool {
    process {
        "执行转账操作"
    }
}
"""
        program = parse(source)
        fn = program.functions[0]
        assert len(fn.annotations) == 1
        assert fn.annotations[0].name == "transactional"
        assert fn.params[2].name == "amount"
        assert fn.params[2].type.base == "Float"

    def test_fn_locked(self):
        """@locked 标注的 fn，is_locked 应为 True。"""
        source = """
@locked
fn cached_query(id: Int) -> User {
    process {
        "查询并缓存用户"
    }
}
"""
        program = parse(source)
        fn = program.functions[0]
        assert fn.is_locked is True
        assert any(a.name == "locked" for a in fn.annotations)

    def test_fn_with_native_block(self):
        """fn 使用 native 逃生舱替代 process。"""
        source = """
fn custom_hash(data: String) -> String {
    native python {
        import hashlib
        return hashlib.sha256(data.encode()).hexdigest()
    }
}
"""
        program = parse(source)
        fn = program.functions[0]
        assert fn.process is None
        assert len(fn.native_blocks) == 1
        assert fn.native_blocks[0].target == "python"
        assert "hashlib" in fn.native_blocks[0].code

    def test_fn_with_native_java_braces(self):
        """native java 代码支持一层花括号嵌套。"""
        source = """
fn pick_level(score: Int) -> String {
    native java {
        if (score > 60) {
            return "pass";
        }
        return "fail";
    }
}
"""
        program = parse(source)
        fn = program.functions[0]
        assert fn.process is None
        assert len(fn.native_blocks) == 1
        assert fn.native_blocks[0].target == "java"
        assert "if (score > 60)" in fn.native_blocks[0].code
        assert 'return "pass";' in fn.native_blocks[0].code

    def test_fn_no_return_type(self):
        """fn 没有返回类型（void 函数）。"""
        source = """
fn log_event(message: String) {
    process {
        "将事件信息写入日志"
    }
}
"""
        program = parse(source)
        fn = program.functions[0]
        assert fn.name == "log_event"
        assert fn.return_type is None


# ============================================================
# 3. module 定义测试
# ============================================================


class TestModuleParsing:
    """验证 Module 层 (module) 的解析能力。"""

    def test_simple_module(self):
        """module 含 use、export、init 和 schedule。"""
        source = """
module UserManager {
    use User
    use register_user
    export register = register_user

    init {
        "初始化用户服务连接池"
    }

    schedule daily at "02:00" {
        "清理过期用户账号"
    }
}
"""
        program = parse(source)
        assert len(program.modules) == 1

        mod = program.modules[0]
        assert mod.name == "UserManager"

        # 依赖
        assert "User" in mod.dependencies
        assert "register_user" in mod.dependencies

        # 导出 action
        assert len(mod.exports) == 1
        assert mod.exports[0].action == "register"
        assert mod.exports[0].target == "register_user"

        # init
        assert mod.init is not None
        assert "连接池" in mod.init.intent

        # schedule
        assert len(mod.schedules) == 1
        assert mod.schedules[0].frequency == "daily"
        assert mod.schedules[0].cron == "02:00"
        assert "清理" in mod.schedules[0].intent

    def test_module_with_annotations_and_multiple_exports(self):
        """module 支持注解与多个 export 声明。"""
        source = """
@domain(name="user")
@engine(type="workflow", framework="temporal")
module UserManager {
    use register_user
    use get_user_by_id

    export register = register_user
    export detail = get_user_by_id
}
"""
        program = parse(source)
        mod = program.modules[0]
        assert mod.name == "UserManager"
        assert len(mod.annotations) == 2
        assert mod.annotations[0].name == "domain"
        assert mod.annotations[0].kwargs.get("name") == "user"
        assert mod.annotations[1].name == "engine"
        assert mod.annotations[1].kwargs.get("type") == "workflow"
        assert mod.annotations[1].kwargs.get("framework") == "temporal"
        assert len(mod.exports) == 2
        assert mod.exports[0].action == "register"
        assert mod.exports[0].target == "register_user"
        assert mod.exports[1].action == "detail"
        assert mod.exports[1].target == "get_user_by_id"


# ============================================================
# 4. route 定义测试
# ============================================================


class TestRouteParsing:
    """验证 Service 层 (route) 的解析能力。"""

    def test_simple_route(self):
        """route 含注解、use 和端点映射。"""
        source = """
@prefix("/api/v1/users")
route UserService {
    use UserManager

    POST "/register" -> register
    GET "/{id}" -> detail
}
"""
        program = parse(source)
        assert len(program.routes) == 1

        route = program.routes[0]
        assert route.name == "UserService"

        # 注解
        assert len(route.annotations) == 1
        assert route.annotations[0].name == "prefix"
        assert route.annotations[0].args == ["/api/v1/users"]

        # 依赖
        assert "UserManager" in route.dependencies

        # 端点
        assert len(route.endpoints) == 2
        assert route.endpoints[0].method == "POST"
        assert route.endpoints[0].path == "/register"
        assert route.endpoints[0].handler == "register"
        assert route.endpoints[1].method == "GET"
        assert route.endpoints[1].handler == "detail"

    def test_route_with_locked_endpoint(self):
        """route 中带 @locked 的端点。"""
        source = """
route TestService {
    @locked
    DELETE "/item" -> delete_item
}
"""
        program = parse(source)
        endpoint = program.routes[0].endpoints[0]
        assert endpoint.method == "DELETE"
        assert endpoint.is_locked is True


# ============================================================
# 5. application 全局配置测试
# ============================================================


class TestApplicationParsing:
    """验证全局配置 (application) 的解析能力。"""

    def test_application_config(self):
        """解析完整的 application 配置块。"""
        source = """
application {
    name: "test-app"
    version: "1.0.0"
    target: "python_fastapi"

    database {
        driver: "postgresql"
        host: env("DB_HOST")
        port: 5432
    }

    ai {
        provider: "openai"
        model: "gpt-4"
    }
}
"""
        program = parse(source)
        assert program.application is not None

        config = program.application.config
        assert config["name"] == "test-app"
        assert config["version"] == "1.0.0"
        assert config["target"] == "python_fastapi"
        assert config["database"]["driver"] == "postgresql"
        assert config["database"]["port"] == 5432
        assert "env(" in config["database"]["host"]
        assert config["ai"]["provider"] == "openai"


# ============================================================
# 6. to_dict() 序列化测试
# ============================================================


class TestSerialization:
    """验证 I-AST 节点的 to_dict() JSON 序列化。"""

    def test_struct_to_dict(self):
        """struct 序列化为 JSON 后包含正确的 node_type。"""
        source = """
struct User {
    id: Int @primary
}
"""
        program = parse(source)
        d = program.to_dict()

        assert d["node_type"] == "program"
        assert len(d["structs"]) == 1
        assert d["structs"][0]["node_type"] == "struct"
        assert d["structs"][0]["name"] == "User"
        assert d["structs"][0]["fields"][0]["name"] == "id"

    def test_full_program_serializable(self):
        """完整 Program 可被 json.dumps 序列化（无异常）。"""
        source = """
struct Item {
    name: String
}

fn get_item(id: Int) -> Item {
    process {
        "查询商品"
    }
}
"""
        program = parse(source)
        # 不应抛出异常
        json_str = json.dumps(program.to_dict(), ensure_ascii=False, indent=2)
        assert "Item" in json_str
        assert "get_item" in json_str


# ============================================================
# 7. 集成测试: 解析完整示例文件
# ============================================================


class TestIntegration:
    """集成测试: 验证示例 .ej 文件的端到端解析。"""

    def test_parse_application_ej(self, examples_dir: Path):
        """解析 examples/application.ej 全局配置文件。"""
        filepath = examples_dir / "application.ej"
        if not filepath.exists():
            pytest.skip("examples/application.ej not found")

        program = parse_file(filepath)
        assert program.application is not None
        assert program.application.config["name"] == "user-service"
        assert program.application.config["target"] == "python_fastapi"

    def test_parse_user_management_ej(self, examples_dir: Path):
        """解析 examples/user_management.ej 完整四层示例。

        验证所有四个层级 (struct/fn/module/route) 均被正确解析。
        """
        filepath = examples_dir / "user_management.ej"
        if not filepath.exists():
            pytest.skip("examples/user_management.ej not found")

        program = parse_file(filepath)

        # Model 层: 应该有 2 个 struct (User, UserProfile)
        assert len(program.structs) == 2
        struct_names = [s.name for s in program.structs]
        assert "User" in struct_names
        assert "UserProfile" in struct_names

        # Method 层: 应该有 5 个 fn
        assert len(program.functions) >= 4
        fn_names = [f.name for f in program.functions]
        assert "register_user" in fn_names
        assert "get_user_by_id" in fn_names
        assert "custom_hash" in fn_names

        # 验证 register_user 的三段体
        reg_fn = next(f for f in program.functions if f.name == "register_user")
        assert len(reg_fn.guard) >= 3
        assert reg_fn.process is not None
        assert len(reg_fn.expect) >= 2

        # 验证 custom_hash 的 native 块
        hash_fn = next(f for f in program.functions if f.name == "custom_hash")
        assert len(hash_fn.native_blocks) >= 1
        assert hash_fn.process is None

        # 验证 @locked fn
        locked_fns = [f for f in program.functions if f.is_locked]
        assert len(locked_fns) >= 1

        # Module 层: 应该有 1 个 module
        assert len(program.modules) == 1
        mod = program.modules[0]
        assert mod.name == "UserManager"
        assert len(mod.exports) == 4
        export_actions = [e.action for e in mod.exports]
        assert "register" in export_actions
        assert "detail" in export_actions
        assert "update" in export_actions
        assert "remove" in export_actions

        # Service 层: 应该有 1 个 route
        assert len(program.routes) == 1
        assert program.routes[0].name == "UserService"
        assert len(program.routes[0].endpoints) >= 3
        endpoint_handlers = [e.handler for e in program.routes[0].endpoints]
        assert "register" in endpoint_handlers
        assert "detail" in endpoint_handlers
        assert "update" in endpoint_handlers
        assert "remove" in endpoint_handlers

    def test_full_roundtrip_json(self, examples_dir: Path):
        """端到端测试: .ej → I-AST → JSON → 验证结构完整性。"""
        filepath = examples_dir / "user_management.ej"
        if not filepath.exists():
            pytest.skip("examples/user_management.ej not found")

        program = parse_file(filepath)
        result = program.to_dict()

        # JSON 序列化不应失败
        json_str = json.dumps(result, ensure_ascii=False, indent=2)

        # 反序列化后结构完整
        loaded = json.loads(json_str)
        assert loaded["node_type"] == "program"
        assert len(loaded["structs"]) == 2
        assert len(loaded["functions"]) >= 4
        assert len(loaded["modules"]) == 1
        assert len(loaded["routes"]) == 1
        assert "exports" in loaded["modules"][0]


# ============================================================
# 8. @human_maintained 注解测试
# ============================================================


class TestHumanMaintainedParsing:
    """验证 @human_maintained 注解的解析。"""

    def test_fn_with_human_maintained(self):
        """fn 上的 @human_maintained 注解应被正确解析。"""
        source = """
@human_maintained
fn legacy_auth(token: String) -> Bool {
    process {
        "遗留认证逻辑，由人类维护"
    }
}
"""
        program = parse(source)
        fn = program.functions[0]
        assert len(fn.annotations) == 1
        assert fn.annotations[0].name == "human_maintained"

    def test_fn_human_maintained_with_guard(self):
        """@human_maintained fn 可以同时有 guard 和 process。"""
        source = """
@human_maintained
fn legacy_check(id: Int) -> String {
    guard { id > 0: "ID must be positive" }
    process {
        "遗留检查逻辑"
    }
}
"""
        program = parse(source)
        fn = program.functions[0]
        assert fn.annotations[0].name == "human_maintained"
        assert fn.guard is not None
        assert fn.process is not None

    def test_fn_human_maintained_with_native(self):
        """@human_maintained fn 可以同时有 native 块。"""
        source = """
@human_maintained
fn legacy_hash(data: String) -> String {
    native python {
        import hashlib
        return hashlib.sha256(data.encode()).hexdigest()
    }
}
"""
        program = parse(source)
        fn = program.functions[0]
        assert fn.annotations[0].name == "human_maintained"
        assert len(fn.native_blocks) == 1

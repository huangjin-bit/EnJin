"""EnJin 逆向导入模块测试。"""

from pathlib import Path

import pytest

from enjinc.ast_nodes import (
    Annotation,
    FieldDef,
    FnDef,
    Param,
    ProcessIntent,
    Program,
    StructDef,
    TypeRef,
)
from enjinc.importer import (
    _parse_java_entity,
    _parse_sqlalchemy_model,
    import_java_source,
    import_python_source,
    program_to_ej,
)


# ============================================================
# SQLAlchemy 模型解析
# ============================================================

class TestPythonStructImport:
    """测试从 Python SQLAlchemy 模型提取 struct。"""

    def test_basic_model(self):
        code = '''
from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String, unique=True)
    is_active = Column(Boolean, default=True)
'''
        structs = _parse_sqlalchemy_model(code)
        assert len(structs) == 1
        s = structs[0]
        assert s.name == "User"
        assert len(s.fields) == 4

        assert s.fields[0].name == "id"
        assert any(a.name == "primary" for a in s.fields[0].annotations)

        assert s.fields[1].name == "username"
        assert any(a.name == "unique" for a in s.fields[1].annotations)

    def test_foreign_key_detection(self):
        code = '''
from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
'''
        structs = _parse_sqlalchemy_model(code)
        assert len(structs) == 1
        user_id_field = structs[0].fields[1]
        assert user_id_field.name == "user_id"
        assert any(a.name == "foreign_key" for a in user_id_field.annotations)

    def test_nullable_type(self):
        code = '''
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class Profile(Base):
    __tablename__ = "profiles"
    id = Column(Integer, primary_key=True)
    bio = Column(String, nullable=True)
'''
        structs = _parse_sqlalchemy_model(code)
        bio = structs[0].fields[1]
        assert bio.type.is_optional
        assert bio.type.base == "Optional"

    def test_empty_file(self):
        code = "from sqlalchemy import Column\n"
        structs = _parse_sqlalchemy_model(code)
        assert len(structs) == 0

    def test_multiple_models(self):
        code = '''
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String)
'''
        structs = _parse_sqlalchemy_model(code)
        assert len(structs) == 2
        assert structs[0].name == "User"
        assert structs[1].name == "Product"


# ============================================================
# Java Entity 解析
# ============================================================

class TestJavaStructImport:
    """测试从 Java JPA/MyBatis-Plus Entity 提取 struct。"""

    def test_jpa_entity(self):
        code = '''
package com.example.entity;

import jakarta.persistence.*;

@Entity
@Table(name = "users")
public class User {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(unique = true, length = 50)
    private String username;

    private String email;
    private Boolean active;
}
'''
        structs = _parse_java_entity(code)
        assert len(structs) == 1
        s = structs[0]
        assert s.name == "User"
        assert len(s.fields) >= 3

        id_field = s.fields[0]
        assert id_field.name == "id"
        assert any(a.name == "primary" for a in id_field.annotations)

    def test_mybatis_plus_entity(self):
        code = '''
package com.example.entity;

import com.baomidou.mybatisplus.annotation.*;

@TableName("products")
public class Product {
    @TableId(type = IdType.AUTO)
    private Long id;

    private String name;
    private Double price;
}
'''
        structs = _parse_java_entity(code)
        assert len(structs) == 1
        assert structs[0].name == "Product"
        assert structs[0].fields[0].name == "id"

    def test_empty_java_file(self):
        code = "package com.example;\n"
        structs = _parse_java_entity(code)
        assert len(structs) == 0

    def test_java_type_mapping(self):
        code = '''
@Entity
public class TestEntity {
    private Long id;
    private String name;
    private Boolean active;
    private Double price;
    private Integer count;
}
'''
        structs = _parse_java_entity(code)
        assert len(structs) == 1
        fields = {f.name: f.type.base for f in structs[0].fields}
        assert fields.get("id") == "Int"
        assert fields.get("name") == "String"
        assert fields.get("active") == "Bool"
        assert fields.get("price") == "Float"
        assert fields.get("count") == "Int"


# ============================================================
# program_to_ej 序列化
# ============================================================

class TestProgramToEj:
    """测试 Program AST → .ej 文本序列化。"""

    def test_simple_struct(self):
        program = Program(
            structs=[
                StructDef(
                    name="User",
                    annotations=[Annotation("table", ["users"])],
                    fields=[
                        FieldDef(name="id", type=TypeRef(base="Int"),
                                annotations=[Annotation("primary"), Annotation("auto_increment")]),
                        FieldDef(name="username", type=TypeRef(base="String"),
                                annotations=[Annotation("unique")]),
                    ],
                ),
            ],
        )
        ej = program_to_ej(program)
        assert "struct User {" in ej
        assert '@table("users")' in ej
        assert "id: Int @primary @auto_increment" in ej
        assert "username: String @unique" in ej

    def test_fn_with_process(self):
        program = Program(
            functions=[
                FnDef(
                    name="create_user",
                    params=[Param(name="name", type=TypeRef(base="String"))],
                    return_type=TypeRef(base="User"),
                    process=ProcessIntent(intent="创建新用户"),
                ),
            ],
        )
        ej = program_to_ej(program)
        assert "fn create_user(name: String) -> User {" in ej
        assert "process {" in ej
        assert '"创建新用户"' in ej

    def test_roundtrip_from_existing_ej(self, examples_dir: Path):
        """验证：解析已知 .ej → Program → 序列化回 .ej → 再解析 → struct 名一致。"""
        from enjinc.parser import parse_file

        source = examples_dir / "user_management.ej"
        if not source.exists():
            pytest.skip("example file not found")

        original = parse_file(source)
        ej_text = program_to_ej(original)

        # 验证序列化结果包含所有 struct 名
        for s in original.structs:
            assert f"struct {s.name} {{" in ej_text, f"struct {s.name} not found in output"

        # 验证序列化结果包含所有 fn 名
        for fn in original.functions:
            assert f"fn {fn.name}(" in ej_text, f"fn {fn.name} not found in output"


# ============================================================
# from_dict 往返测试
# ============================================================

class TestFromDict:
    """测试 AST 节点的 from_dict/to_dict 往返一致性。"""

    def test_struct_roundtrip(self):
        original = StructDef(
            name="User",
            annotations=[Annotation("table", ["users"])],
            fields=[
                FieldDef(
                    name="email",
                    type=TypeRef(base="String"),
                    annotations=[Annotation("unique")],
                ),
                FieldDef(
                    name="bio",
                    type=TypeRef(base="Optional", params=[TypeRef(base="String")], is_optional=True),
                ),
            ],
        )
        restored = StructDef.from_dict(original.to_dict())
        assert restored.name == "User"
        assert len(restored.fields) == 2
        assert restored.fields[1].type.is_optional

    def test_fn_roundtrip(self):
        original = FnDef(
            name="create_order",
            params=[Param(name="user_id", type=TypeRef(base="Int"))],
            return_type=TypeRef(base="Order"),
            guard=[],
            process=ProcessIntent(intent="创建订单"),
            expect=[],
        )
        restored = FnDef.from_dict(original.to_dict())
        assert restored.name == "create_order"
        assert restored.process.intent == "创建订单"

    def test_program_roundtrip(self, examples_dir: Path):
        from enjinc.parser import parse_file
        source = examples_dir / "user_management.ej"
        if not source.exists():
            pytest.skip("example file not found")

        original = parse_file(source)
        data = original.to_dict()
        restored = Program.from_dict(data)

        assert len(restored.structs) == len(original.structs)
        assert len(restored.functions) == len(original.functions)
        assert len(restored.modules) == len(original.modules)
        assert len(restored.routes) == len(original.routes)

        for orig, rest in zip(original.structs, restored.structs):
            assert orig.name == rest.name
            assert len(orig.fields) == len(rest.fields)

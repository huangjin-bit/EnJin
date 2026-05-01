"""
============================================================
EnJin Java Spring Boot 模板渲染测试 (test_java_templates.py)
============================================================
验证 template_renderer.py 能否正确将 I-AST 渲染为 Java Spring Boot 代码。

测试覆盖:
    1. Maven pom.xml 生成
    2. application.yml 配置生成
    3. JPA Entity 类生成
    4. MyBatis-Plus Mapper 接口 + XML 生成
    5. Service Interface + ServiceImpl 生成
    6. DTO (CreateRequest/UpdateRequest/Response) 生成
    7. VO 生成
    8. Assembler 生成
    9. REST Controller 生成 (interface/controller)
    10. Kafka Event Publisher 生成
============================================================
"""

from pathlib import Path

import pytest

from enjinc.parser import parse_file
from enjinc.template_renderer import RenderConfig, render_program


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    output = tmp_path / "output"
    output.mkdir(parents=True, exist_ok=True)
    return output


class TestJavaInfrastructureRendering:
    """验证基建层文件生成。"""

    def test_pom_xml_generated(self, examples_dir: Path, output_dir: Path):
        """pom.xml 文件应包含正确的 Maven 配置。"""
        program = parse_file(examples_dir / "java_ecommerce" / "trade.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="java_springboot")
        render_program(program, config)

        pom_xml = output_dir / "java_springboot" / "pom.xml"
        assert pom_xml.exists()

        content = pom_xml.read_text(encoding="utf-8")
        assert "<groupId>trade-core</groupId>" in content
        assert "<artifactId>trade-core</artifactId>" in content
        assert "<version>1.0.0</version>" in content
        assert "spring-boot-starter-web" in content
        assert "mybatis-plus" in content
        assert "postgresql" in content
        assert "spring-kafka" in content

    def test_application_yml_generated(self, examples_dir: Path, output_dir: Path):
        """application.yml 应包含正确的 Spring Boot 配置。"""
        program = parse_file(examples_dir / "java_ecommerce" / "trade.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="java_springboot")
        render_program(program, config)

        app_yml = output_dir / "java_springboot" / "src/main/resources/application.yml"
        assert app_yml.exists()

        content = app_yml.read_text(encoding="utf-8")
        assert "trade-core" in content
        assert "postgresql" in content
        assert "  kafka:" in content

    def test_application_java_generated(self, examples_dir: Path, output_dir: Path):
        """Application.java 应包含 Spring Boot 启动类。"""
        program = parse_file(examples_dir / "java_ecommerce" / "trade.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="java_springboot")
        render_program(program, config)

        app_java = (
            output_dir / "java_springboot" / "src/main/java/trade_core/Application.java"
        )
        assert app_java.exists()

        content = app_java.read_text(encoding="utf-8")
        assert "package trade_core;" in content
        assert "@SpringBootApplication" in content
        assert "public class Application" in content

    def test_security_config_generated(self, examples_dir: Path, output_dir: Path):
        """SecurityConfig.java 应包含 Spring Security 配置。"""
        program = parse_file(examples_dir / "java_ecommerce" / "trade.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="java_springboot")
        render_program(program, config)

        security_config = (
            output_dir
            / "java_springboot"
            / "src/main/java/trade_core/infrastructure/config/SecurityConfig.java"
        )
        assert security_config.exists()

        content = security_config.read_text(encoding="utf-8")
        assert "PasswordEncoder" in content
        assert "SecurityFilterChain" in content


class TestJavaModelRendering:
    """验证 Model 层 Entity 和 Mapper 生成。"""

    def test_entity_java_per_struct(self, examples_dir: Path, tmp_path: Path):
        """每个 struct 应生成独立的 Entity.java 文件。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "java_ecommerce" / "trade.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="java_springboot")
        render_program(program, config)

        entity_dir = (
            output_dir
            / "java_springboot"
            / "src/main/java/trade_core/domain/entity"
        )
        assert (entity_dir / "User.java").exists()
        assert (entity_dir / "Product.java").exists()
        assert (entity_dir / "Order.java").exists()

        user_content = (entity_dir / "User.java").read_text(encoding="utf-8")
        assert "class User" in user_content
        assert "@TableName" in user_content
        assert "@TableId" in user_content
        assert "private Long id" in user_content
        assert "private String username" in user_content

    def test_mapper_java_per_struct(self, examples_dir: Path, tmp_path: Path):
        """每个 struct 应生成独立的 Mapper.java 文件。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "java_ecommerce" / "trade.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="java_springboot")
        render_program(program, config)

        mapper_dir = (
            output_dir
            / "java_springboot"
            / "src/main/java/trade_core/infrastructure/mapper"
        )
        assert (mapper_dir / "UserMapper.java").exists()
        assert (mapper_dir / "ProductMapper.java").exists()

        user_mapper = (mapper_dir / "UserMapper.java").read_text(encoding="utf-8")
        assert "interface UserMapper" in user_mapper
        assert "BaseMapper" in user_mapper
        assert "@Mapper" in user_mapper

    def test_mybatis_xml_per_struct(self, examples_dir: Path, tmp_path: Path):
        """每个 struct 应生成 MyBatis XML mapper 文件。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "java_ecommerce" / "trade.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="java_springboot")
        render_program(program, config)

        xml_dir = output_dir / "java_springboot" / "src/main/resources/mapper"
        assert (xml_dir / "UserMapper.xml").exists()
        assert (xml_dir / "ProductMapper.xml").exists()

        user_xml = (xml_dir / "UserMapper.xml").read_text(encoding="utf-8")
        assert "<mapper" in user_xml
        assert "resultMap" in user_xml
        assert "Base_Column_List" in user_xml


class TestJavaServiceRendering:
    """验证 Service 层生成 (Interface + ServiceImpl)。"""

    def test_service_interface_generated(self, examples_dir: Path, tmp_path: Path):
        """每个 struct 应生成 IService 接口。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "java_ecommerce" / "trade.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="java_springboot")
        render_program(program, config)

        service_dir = (
            output_dir
            / "java_springboot"
            / "src/main/java/trade_core/application/service"
        )
        assert (service_dir / "IUserService.java").exists()
        assert (service_dir / "IProductService.java").exists()

        user_iface = (service_dir / "IUserService.java").read_text(encoding="utf-8")
        assert "interface IUserService" in user_iface
        assert "findById" in user_iface
        assert "findAll" in user_iface
        assert "create" in user_iface

    def test_service_impl_generated(self, examples_dir: Path, tmp_path: Path):
        """每个 struct 应生成 ServiceImpl 实现类。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "java_ecommerce" / "trade.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="java_springboot")
        render_program(program, config)

        impl_dir = (
            output_dir
            / "java_springboot"
            / "src/main/java/trade_core/application/service/impl"
        )
        assert (impl_dir / "UserServiceImpl.java").exists()
        assert (impl_dir / "ProductServiceImpl.java").exists()

        user_impl = (impl_dir / "UserServiceImpl.java").read_text(encoding="utf-8")
        assert "class UserServiceImpl" in user_impl
        assert "@Service" in user_impl
        assert "ServiceImpl" in user_impl
        assert "implements IUserService" in user_impl


class TestJavaDTORendering:
    """验证 DTO 层生成。"""

    def test_create_request_dto(self, examples_dir: Path, tmp_path: Path):
        """每个 struct 应生成 CreateRequest DTO。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "java_ecommerce" / "trade.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="java_springboot")
        render_program(program, config)

        req_dir = (
            output_dir
            / "java_springboot"
            / "src/main/java/trade_core/interfaces/dto/request"
        )
        assert (req_dir / "UserCreateRequest.java").exists()
        assert (req_dir / "ProductCreateRequest.java").exists()

        user_req = (req_dir / "UserCreateRequest.java").read_text(encoding="utf-8")
        assert "class UserCreateRequest" in user_req
        assert "@Data" in user_req

    def test_update_request_dto(self, examples_dir: Path, tmp_path: Path):
        """每个 struct 应生成 UpdateRequest DTO。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "java_ecommerce" / "trade.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="java_springboot")
        render_program(program, config)

        req_dir = (
            output_dir
            / "java_springboot"
            / "src/main/java/trade_core/interfaces/dto/request"
        )
        assert (req_dir / "UserUpdateRequest.java").exists()

    def test_response_dto(self, examples_dir: Path, tmp_path: Path):
        """每个 struct 应生成 Response DTO（排除敏感字段）。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "java_ecommerce" / "trade.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="java_springboot")
        render_program(program, config)

        resp_dir = (
            output_dir
            / "java_springboot"
            / "src/main/java/trade_core/interfaces/dto/response"
        )
        assert (resp_dir / "UserResponse.java").exists()

        user_resp = (resp_dir / "UserResponse.java").read_text(encoding="utf-8")
        assert "class UserResponse" in user_resp
        # password 应该被排除
        assert "password" not in user_resp.lower().replace("password", "").replace("passwordhash", "")
        # 但 username 应该存在
        assert "username" in user_resp.lower()


class TestJavaVORendering:
    """验证 VO 层生成。"""

    def test_vo_generated(self, examples_dir: Path, tmp_path: Path):
        """每个 struct 应生成 VO 类。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "java_ecommerce" / "trade.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="java_springboot")
        render_program(program, config)

        vo_dir = (
            output_dir
            / "java_springboot"
            / "src/main/java/trade_core/interfaces/vo"
        )
        assert (vo_dir / "UserVO.java").exists()
        assert (vo_dir / "ProductVO.java").exists()


class TestJavaAssemblerRendering:
    """验证 Assembler 层生成。"""

    def test_assembler_generated(self, examples_dir: Path, tmp_path: Path):
        """每个 struct 应生成 Assembler 转换器。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "java_ecommerce" / "trade.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="java_springboot")
        render_program(program, config)

        asm_dir = (
            output_dir
            / "java_springboot"
            / "src/main/java/trade_core/interfaces/assembler"
        )
        assert (asm_dir / "UserAssembler.java").exists()

        user_asm = (asm_dir / "UserAssembler.java").read_text(encoding="utf-8")
        assert "class UserAssembler" in user_asm
        assert "toEntity" in user_asm
        assert "toResponse" in user_asm
        assert "toVO" in user_asm


class TestJavaControllerRendering:
    """验证 Controller 层生成。"""

    def test_controllers_generated(self, examples_dir: Path, tmp_path: Path):
        """Controller.java 文件应被创建在 interface/controller 目录下。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "java_ecommerce" / "trade.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="java_springboot")
        render_program(program, config)

        controller_dir = (
            output_dir
            / "java_springboot"
            / "src/main/java/trade_core/interfaces/controller"
        )
        assert controller_dir.exists()

        order_controller = controller_dir / "OrderServiceController.java"
        assert order_controller.exists()
        content = order_controller.read_text(encoding="utf-8")
        assert "class OrderServiceController" in content
        assert "@RestController" in content
        assert "@RequestMapping" in content

        product_controller = controller_dir / "ProductServiceController.java"
        assert product_controller.exists()

    def test_kafka_producer_generated(self, examples_dir: Path, tmp_path: Path):
        """Kafka Producer 应被生成。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        program = parse_file(examples_dir / "java_ecommerce" / "trade.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="java_springboot")
        render_program(program, config)

        kafka_producer = (
            output_dir
            / "java_springboot"
            / "src/main/java/trade_core/messaging/EventPublisher.java"
        )
        assert kafka_producer.exists()

        content = kafka_producer.read_text(encoding="utf-8")
        assert "KafkaTemplate" in content
        assert "@Component" in content
        assert "publish" in content


class TestJavaIntegration:
    """集成测试: 端到端渲染。"""

    def test_full_java_rendering(self, examples_dir: Path, output_dir: Path):
        """完整渲染所有层，验证目录结构完整。"""
        program = parse_file(examples_dir / "java_ecommerce" / "trade.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="java_springboot")
        render_program(program, config)

        target_dir = output_dir / "java_springboot"

        expected_files = [
            # Infrastructure
            "pom.xml",
            "src/main/resources/application.yml",
            "src/main/java/trade_core/Application.java",
            "src/main/java/trade_core/infrastructure/config/SecurityConfig.java",
            "src/main/java/trade_core/infrastructure/config/MybatisPlusConfig.java",
            # Entity
            "src/main/java/trade_core/domain/entity/User.java",
            "src/main/java/trade_core/domain/entity/Product.java",
            # Mapper interface
            "src/main/java/trade_core/infrastructure/mapper/UserMapper.java",
            "src/main/java/trade_core/infrastructure/mapper/ProductMapper.java",
            # MyBatis XML
            "src/main/resources/mapper/UserMapper.xml",
            "src/main/resources/mapper/ProductMapper.xml",
            # Service Interface + Impl
            "src/main/java/trade_core/application/service/IUserService.java",
            "src/main/java/trade_core/application/service/IProductService.java",
            "src/main/java/trade_core/application/service/impl/UserServiceImpl.java",
            "src/main/java/trade_core/application/service/impl/ProductServiceImpl.java",
            # DTO
            "src/main/java/trade_core/interfaces/dto/request/UserCreateRequest.java",
            "src/main/java/trade_core/interfaces/dto/request/UserUpdateRequest.java",
            "src/main/java/trade_core/interfaces/dto/response/UserResponse.java",
            # VO
            "src/main/java/trade_core/interfaces/vo/UserVO.java",
            # Assembler
            "src/main/java/trade_core/interfaces/assembler/UserAssembler.java",
            # Controller (now in interface/controller)
            "src/main/java/trade_core/interfaces/controller/OrderServiceController.java",
            "src/main/java/trade_core/interfaces/controller/ProductServiceController.java",
            "src/main/java/trade_core/interfaces/controller/HealthServiceController.java",
            # Messaging
            "src/main/java/trade_core/messaging/EventPublisher.java",
        ]

        for file_path in expected_files:
            full_path = target_dir / file_path
            assert full_path.exists(), f"文件 {file_path} 不存在"

    def test_struct_files_match(self, examples_dir: Path, output_dir: Path):
        """每个 struct 应生成独立的 .java 文件。"""
        program = parse_file(examples_dir / "java_ecommerce" / "trade.ej")
        config = RenderConfig(output_dir=output_dir, target_lang="java_springboot")
        render_program(program, config)

        entity_dir = (
            output_dir
            / "java_springboot"
            / "src/main/java/trade_core/domain/entity"
        )
        expected_entities = ["User", "Product", "Order", "OrderItem", "Payment"]
        for entity_name in expected_entities:
            java_file = entity_dir / f"{entity_name}.java"
            assert java_file.exists(), f"Entity {entity_name}.java not found"
            content = java_file.read_text(encoding="utf-8")
            assert f"class {entity_name}" in content

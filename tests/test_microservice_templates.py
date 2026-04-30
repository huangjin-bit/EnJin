"""Tests for Java Spring Boot microservice template rendering."""

import tempfile
from pathlib import Path

import pytest

from enjinc.ast_nodes import ApplicationConfig
from enjinc.parser import parse_file
from enjinc.template_renderer import RenderConfig, render_program


EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
MICROSERVICE_EJ = EXAMPLES_DIR / "java_ecommerce" / "microservice_order.ej"


def _micro_app_config(**overrides):
    defaults = {
        "java_use_spring_cloud": "true",
        "java_service_discovery": "nacos",
        "java_use_gateway": "true",
        "java_use_feign": "true",
        "java_use_sentinel": "true",
        "java_use_seata": "true",
        "java_use_nacos_config": "true",
        "java_use_tracing": "true",
        "java_use_docker": "true",
        "java_use_k8s": "true",
    }
    defaults.update(overrides)
    return ApplicationConfig(config={
        "name": "order-service",
        "target": "java_springboot",
        "layout": defaults,
    })


def _render_micro(tmp_path: Path, **config_overrides) -> Path:
    ej_file = MICROSERVICE_EJ
    if not ej_file.exists():
        pytest.skip("microservice_order.ej not found")

    program = parse_file(ej_file)
    program.application = _micro_app_config(**config_overrides)

    output_dir = tmp_path / "output"
    config = RenderConfig(target_lang="java_springboot", output_dir=output_dir)
    render_program(program, config)
    return output_dir / "java_springboot"


# ---------------------------------------------------------------
# Cloud Config tests
# ---------------------------------------------------------------

class TestMicroserviceCloudConfig:
    def test_cloud_config_generated(self, tmp_path):
        root = _render_micro(tmp_path)
        cloud_config = root / "src/main/java/order_service/infrastructure/config/CloudConfig.java"
        assert cloud_config.exists(), "CloudConfig.java not generated"
        content = cloud_config.read_text(encoding="utf-8")
        assert "EnableDiscoveryClient" in content
        assert "EnableFeignClients" in content

    def test_sentinel_config_generated(self, tmp_path):
        root = _render_micro(tmp_path)
        sentinel = root / "src/main/java/order_service/infrastructure/config/SentinelConfig.java"
        assert sentinel.exists(), "SentinelConfig.java not generated"
        content = sentinel.read_text(encoding="utf-8")
        assert "SentinelResourceAspect" in content


# ---------------------------------------------------------------
# Seata distributed transaction tests
# ---------------------------------------------------------------

class TestSeataConfig:
    def test_seata_config_generated(self, tmp_path):
        root = _render_micro(tmp_path)
        seata = root / "src/main/java/order_service/infrastructure/config/SeataConfig.java"
        assert seata.exists(), "SeataConfig.java not generated"
        content = seata.read_text(encoding="utf-8")
        assert "SeataConfig" in content
        assert "GlobalTransactional" in content

    def test_seata_yaml_section(self, tmp_path):
        root = _render_micro(tmp_path)
        yml = root / "src/main/resources/application.yml"
        content = yml.read_text(encoding="utf-8")
        assert "seata:" in content
        assert "default-tx-group" in content
        assert "tx-service-group" in content

    def test_seata_not_present_when_disabled(self, tmp_path):
        root = _render_micro(tmp_path, java_use_seata="false")
        assert not (root / "src/main/java/order_service/infrastructure/config/SeataConfig.java").exists()
        yml = root / "src/main/resources/application.yml"
        content = yml.read_text(encoding="utf-8")
        assert "seata:" not in content


# ---------------------------------------------------------------
# Nacos Config tests
# ---------------------------------------------------------------

class TestNacosConfig:
    def test_bootstrap_yml_generated(self, tmp_path):
        root = _render_micro(tmp_path)
        bootstrap = root / "src/main/resources/bootstrap.yml"
        assert bootstrap.exists(), "bootstrap.yml not generated"
        content = bootstrap.read_text(encoding="utf-8")
        assert "nacos:" in content
        assert "config:" in content
        assert "shared-configs:" in content

    def test_nacos_not_present_when_disabled(self, tmp_path):
        root = _render_micro(tmp_path, java_use_nacos_config="false")
        assert not (root / "src/main/resources/bootstrap.yml").exists()


# ---------------------------------------------------------------
# Distributed tracing tests
# ---------------------------------------------------------------

class TestTracingConfig:
    def test_zipkin_in_application_yml(self, tmp_path):
        root = _render_micro(tmp_path)
        yml = root / "src/main/resources/application.yml"
        content = yml.read_text(encoding="utf-8")
        assert "management:" in content
        assert "tracing:" in content
        assert "zipkin:" in content
        assert "9411" in content

    def test_tracing_not_present_when_disabled(self, tmp_path):
        root = _render_micro(tmp_path, java_use_tracing="false")
        yml = root / "src/main/resources/application.yml"
        content = yml.read_text(encoding="utf-8")
        assert "zipkin:" not in content


# ---------------------------------------------------------------
# Feign Client tests
# ---------------------------------------------------------------

class TestMicroserviceFeignClients:
    def test_feign_client_generated(self, tmp_path):
        root = _render_micro(tmp_path)
        client = root / "src/main/java/order_service/infrastructure/client/OrderClient.java"
        assert client.exists(), "OrderClient.java not generated"
        content = client.read_text(encoding="utf-8")
        assert "@FeignClient" in content
        assert "OrderClient" in content
        assert "getById" in content
        assert "listAll" in content

    def test_feign_fallback_generated(self, tmp_path):
        root = _render_micro(tmp_path)
        fallback = root / "src/main/java/order_service/infrastructure/client/OrderClientFallbackFactory.java"
        assert fallback.exists(), "OrderClientFallbackFactory.java not generated"
        content = fallback.read_text(encoding="utf-8")
        assert "FallbackFactory" in content

    def test_all_structs_have_feign_clients(self, tmp_path):
        root = _render_micro(tmp_path)
        client_dir = root / "src/main/java/order_service/infrastructure/client"
        clients = list(client_dir.glob("*Client.java"))
        assert len(clients) == 3, f"Expected 3 Feign clients, got {len(clients)}"


# ---------------------------------------------------------------
# Gateway tests
# ---------------------------------------------------------------

class TestMicroserviceGateway:
    def test_gateway_application_generated(self, tmp_path):
        root = _render_micro(tmp_path)
        gateway_app = root / "gateway/order_service_gateway/GatewayApplication.java"
        assert gateway_app.exists(), "GatewayApplication.java not generated"
        content = gateway_app.read_text(encoding="utf-8")
        assert "SpringApplication" in content

    def test_gateway_routes_generated(self, tmp_path):
        root = _render_micro(tmp_path)
        routes_config = root / "gateway/order_service_gateway/GatewayRouteConfig.java"
        assert routes_config.exists(), "GatewayRouteConfig.java not generated"
        content = routes_config.read_text(encoding="utf-8")
        assert "RouteLocator" in content

    def test_gateway_auth_filter_generated(self, tmp_path):
        root = _render_micro(tmp_path)
        auth_filter = root / "gateway/order_service_gateway/filter/AuthGlobalFilter.java"
        assert auth_filter.exists(), "AuthGlobalFilter.java not generated"
        content = auth_filter.read_text(encoding="utf-8")
        assert "GlobalFilter" in content
        assert "Authorization" in content


# ---------------------------------------------------------------
# Docker tests
# ---------------------------------------------------------------

class TestDockerDeploy:
    def test_dockerfile_generated(self, tmp_path):
        root = _render_micro(tmp_path)
        dockerfile = root / "deploy" / "Dockerfile"
        assert dockerfile.exists(), "Dockerfile not generated"
        content = dockerfile.read_text(encoding="utf-8")
        assert "FROM maven:3.9" in content
        assert "FROM eclipse-temurin:17" in content
        assert "ENTRYPOINT" in content

    def test_docker_compose_generated(self, tmp_path):
        root = _render_micro(tmp_path)
        compose = root / "deploy" / "docker-compose.yml"
        assert compose.exists(), "docker-compose.yml not generated"
        content = compose.read_text(encoding="utf-8")
        assert "services:" in content
        assert "postgres:" in content
        assert "kafka:" in content
        assert "nacos:" in content
        assert "zipkin:" in content
        assert "microservice-net" in content

    def test_docker_not_present_when_disabled(self, tmp_path):
        root = _render_micro(tmp_path, java_use_docker="false")
        assert not (root / "deploy" / "Dockerfile").exists()


# ---------------------------------------------------------------
# K8s tests
# ---------------------------------------------------------------

class TestK8sDeploy:
    def test_k8s_deployment_generated(self, tmp_path):
        root = _render_micro(tmp_path)
        k8s = root / "deploy" / "k8s" / "deployment.yaml"
        assert k8s.exists(), "K8s deployment.yaml not generated"
        content = k8s.read_text(encoding="utf-8")
        assert "kind: Deployment" in content
        assert "kind: Service" in content
        assert "kind: Secret" in content
        assert "replicas:" in content
        assert "readinessProbe" in content
        assert "livenessProbe" in content
        assert "NACOS_ADDR" in content

    def test_k8s_not_present_when_disabled(self, tmp_path):
        root = _render_micro(tmp_path, java_use_k8s="false")
        assert not (root / "deploy" / "k8s" / "deployment.yaml").exists()


# ---------------------------------------------------------------
# Disabled microservice — no extra files
# ---------------------------------------------------------------

class TestMicroserviceDisabled:
    def test_no_cloud_when_disabled(self, tmp_path):
        ej_file = EXAMPLES_DIR / "user_management.ej"
        if not ej_file.exists():
            pytest.skip("user_management.ej not found")

        program = parse_file(ej_file)
        output_dir = tmp_path / "output"
        config = RenderConfig(target_lang="java_springboot", output_dir=output_dir)
        render_program(program, config)
        root = output_dir / "java_springboot"

        assert not (root / "src/main/java/app/infrastructure/config/CloudConfig.java").exists()
        assert not (root / "src/main/java/app/infrastructure/config/SeataConfig.java").exists()
        assert not (root / "src/main/java/app/infrastructure/config/SentinelConfig.java").exists()
        assert not (root / "src/main/resources/bootstrap.yml").exists()
        assert not (root / "deploy").exists()


# ---------------------------------------------------------------
# Example .ej file validation
# ---------------------------------------------------------------

class TestMicroserviceExample:
    def test_microservice_ej_parses(self):
        if not MICROSERVICE_EJ.exists():
            pytest.skip("microservice_order.ej not found")
        program = parse_file(MICROSERVICE_EJ)
        assert len(program.structs) == 3
        assert len(program.functions) == 4
        assert len(program.routes) == 1

    def test_microservice_ej_full_build(self, tmp_path):
        root = _render_micro(tmp_path)
        pkg = "order_service"

        # Standard files
        assert (root / "src/main/java" / pkg / "Application.java").exists()
        assert (root / "src/main/java" / pkg / "domain/entity/Order.java").exists()
        assert (root / "src/main/java" / pkg / "interface/controller/OrderServiceController.java").exists()

        # Cloud files
        assert (root / "src/main/java" / pkg / "infrastructure/config/CloudConfig.java").exists()
        assert (root / "src/main/java" / pkg / "infrastructure/config/SentinelConfig.java").exists()
        assert (root / "src/main/java" / pkg / "infrastructure/config/SeataConfig.java").exists()

        # Bootstrap (Nacos Config)
        assert (root / "src/main/resources/bootstrap.yml").exists()

        # application.yml has tracing + seata sections
        yml = (root / "src/main/resources/application.yml").read_text(encoding="utf-8")
        assert "seata:" in yml
        assert "zipkin:" in yml

        # Feign clients
        assert (root / "src/main/java" / pkg / "infrastructure/client/OrderClient.java").exists()

        # Gateway
        assert (root / "gateway/order_service_gateway/GatewayApplication.java").exists()

        # Docker
        assert (root / "deploy/Dockerfile").exists()
        assert (root / "deploy/docker-compose.yml").exists()

        # K8s
        assert (root / "deploy/k8s/deployment.yaml").exists()

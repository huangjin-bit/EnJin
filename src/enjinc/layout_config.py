"""
============================================================
EnJin 输出布局配置 (layout_config.py)
============================================================
约定大于配置：每个目标栈有合理的默认值，用户可通过 .ej
的 application.config.layout 覆盖。
============================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field


def _to_bool(value) -> bool:
    """Convert config value to bool, handling string 'true'/'false'."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("true", "1", "yes")
    return bool(value)


@dataclass
class JavaLayoutConfig:
    """Java Spring Boot 输出布局配置"""

    base_package: str = ""  # 空 = 从 app_name 推导 (hyphens → underscores)
    use_service_interface: bool = True  # 生成 IService + ServiceImpl 分离
    use_dto: bool = True  # 生成 Request/Response DTO
    use_vo: bool = True  # 生成 View Object
    use_assembler: bool = True  # 生成 Entity <-> DTO/VO 转换器
    use_mybatis_xml: bool = True  # 生成 MyBatis XML mapper 文件

    # 微服务相关配置
    use_spring_cloud: bool = False  # 启用 Spring Cloud 微服务模式
    service_discovery: str = ""  # "" | "nacos" | "eureka"
    use_gateway: bool = False  # 生成 API Gateway 模块
    use_feign: bool = False  # 生成 Feign 客户端接口
    use_sentinel: bool = False  # 生成 Sentinel 熔断降级配置
    use_seata: bool = False  # 生成 Seata 分布式事务配置
    use_nacos_config: bool = False  # 生成 Nacos 配置中心
    use_tracing: bool = False  # 生成 Sleuth + Zipkin 链路追踪
    use_docker: bool = False  # 生成 Dockerfile + docker-compose
    use_k8s: bool = False  # 生成 K8s Deployment/Service YAML

    # 敏感字段名称列表 (这些字段不会出现在 Response DTO 和 VO 中)
    sensitive_fields: list[str] = field(
        default_factory=lambda: ["password", "passwordHash", "secret", "token"]
    )


@dataclass
class PythonLayoutConfig:
    """Python FastAPI 输出布局配置"""

    use_schemas: bool = True  # 生成 Pydantic schemas 层
    use_repository: bool = True  # 生成 Repository 数据访问层
    use_alembic: bool = False  # 生成 Alembic 迁移骨架
    api_version: str = "v1"  # API 路由版本前缀
    app_package_name: str = "app"  # 主包名

    sensitive_fields: list[str] = field(
        default_factory=lambda: ["password", "password_hash", "secret", "token"]
    )


# ---------------------------------------------------------------------------
# 工厂函数：从 app_config dict 提取布局配置
# ---------------------------------------------------------------------------

def get_java_layout(app_config: dict | None = None) -> JavaLayoutConfig:
    """从 application config 的 layout 块构建 JavaLayoutConfig，未配置的项用默认值。"""
    cfg = JavaLayoutConfig()
    if not app_config:
        return cfg
    layout = app_config.get("layout", {})
    for key, value in layout.items():
        if key == "java_base_package":
            cfg.base_package = str(value)
        elif key == "java_use_service_interface":
            cfg.use_service_interface = _to_bool(value)
        elif key == "java_use_dto":
            cfg.use_dto = _to_bool(value)
        elif key == "java_use_vo":
            cfg.use_vo = _to_bool(value)
        elif key == "java_use_assembler":
            cfg.use_assembler = _to_bool(value)
        elif key == "java_use_mybatis_xml":
            cfg.use_mybatis_xml = _to_bool(value)
        elif key == "java_use_spring_cloud":
            cfg.use_spring_cloud = _to_bool(value)
        elif key == "java_service_discovery":
            cfg.service_discovery = str(value)
        elif key == "java_use_gateway":
            cfg.use_gateway = _to_bool(value)
        elif key == "java_use_feign":
            cfg.use_feign = _to_bool(value)
        elif key == "java_use_sentinel":
            cfg.use_sentinel = _to_bool(value)
        elif key == "java_use_seata":
            cfg.use_seata = _to_bool(value)
        elif key == "java_use_nacos_config":
            cfg.use_nacos_config = _to_bool(value)
        elif key == "java_use_tracing":
            cfg.use_tracing = _to_bool(value)
        elif key == "java_use_docker":
            cfg.use_docker = _to_bool(value)
        elif key == "java_use_k8s":
            cfg.use_k8s = _to_bool(value)
        elif key == "java_sensitive_fields" and isinstance(value, list):
            cfg.sensitive_fields = value
    return cfg


def get_python_layout(app_config: dict | None = None) -> PythonLayoutConfig:
    """从 application config 的 layout 块构建 PythonLayoutConfig，未配置的项用默认值。"""
    cfg = PythonLayoutConfig()
    if not app_config:
        return cfg
    layout = app_config.get("layout", {})
    for key, value in layout.items():
        if key == "python_use_schemas":
            cfg.use_schemas = bool(value)
        elif key == "python_use_repository":
            cfg.use_repository = bool(value)
        elif key == "python_use_alembic":
            cfg.use_alembic = bool(value)
        elif key == "python_api_version":
            cfg.api_version = str(value)
        elif key == "python_app_package_name":
            cfg.app_package_name = str(value)
        elif key == "python_sensitive_fields" and isinstance(value, list):
            cfg.sensitive_fields = value
    return cfg

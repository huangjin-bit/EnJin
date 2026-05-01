"""Java Spring Boot 目标渲染器。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from enjinc.ast_nodes import FnDef, ModuleDef, RouteDef, StructDef
from enjinc.guard_compiler import compile_guards_java
from enjinc.layout_config import JavaLayoutConfig, get_java_layout
from enjinc.targets import TargetRenderer, register_target, render_template, write_file


def _pkg_path(app_name: str) -> str:
    return app_name.replace("-", "_")


def _table_name(struct: StructDef) -> str:
    for anno in struct.annotations:
        if anno.name == "table" and anno.args:
            return anno.args[0]
    return struct.name.lower() + "s"


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _app_ctx(app_name: str, app_config: dict) -> dict:
    return {
        "name": app_config.get("name", app_name),
        "version": app_config.get("version", "0.1.0"),
        "database": app_config.get("database", {}),
        "queue": app_config.get("queue", {}),
    }


@register_target
class JavaSpringBootRenderer:
    target_lang = "java_springboot"
    native_lang = "java"
    file_extension = ".java"

    def render_infrastructure(
        self, app_name: str, app_config: dict, output_dir: Path,
    ) -> None:
        t = self.target_lang
        pkg = _pkg_path(app_config.get("name", app_name))
        layout = get_java_layout(app_config)
        ctx = {"application": _app_ctx(app_name, app_config)}

        pom_ctx = {
            **ctx,
            "use_spring_cloud": layout.use_spring_cloud,
            "service_discovery": layout.service_discovery,
            "use_nacos_config": layout.use_nacos_config,
            "use_feign": layout.use_feign,
            "use_sentinel": layout.use_sentinel,
            "use_seata": layout.use_seata,
            "use_tracing": layout.use_tracing,
        }
        write_file(output_dir / "pom.xml", render_template(t, "build/pom.xml.jinja", pom_ctx))
        yml_ctx = {
            **ctx,
            "use_seata": layout.use_seata,
            "use_tracing": layout.use_tracing,
        }
        write_file(output_dir / "src/main/resources/application.yml", render_template(t, "application.yml.jinja", yml_ctx))
        write_file(
            output_dir / "src/main/java" / pkg / "Application.java",
            render_template(t, "main/Application.java.jinja", ctx),
        )
        config_dir = output_dir / "src/main/java" / pkg / "infrastructure/config"
        write_file(config_dir / "SecurityConfig.java", render_template(t, "infrastructure/config/SecurityConfig.java.jinja", ctx))
        write_file(config_dir / "MybatisPlusConfig.java", render_template(t, "infrastructure/config/MybatisPlusConfig.java.jinja", ctx))

        exc_dir = output_dir / "src/main/java" / pkg / "infrastructure/exception"
        for exc_name in ("AppException", "ResourceNotFoundException", "DuplicateResourceException", "BusinessException"):
            write_file(
                exc_dir / f"{exc_name}.java",
                render_template(t, f"infrastructure/exception/{exc_name}.java.jinja", ctx),
            )
        write_file(
            exc_dir / "GlobalExceptionHandler.java",
            render_template(t, "infrastructure/exception/GlobalExceptionHandler.java.jinja", ctx),
        )

        # ApiResponse 通用响应包装
        common_dir = output_dir / "src/main/java" / pkg / "infrastructure/common"
        write_file(
            common_dir / "ApiResponse.java",
            render_template(t, "infrastructure/common/ApiResponse.java.jinja", {"pkg": pkg}),
        )

        # Logback 日志配置
        write_file(
            output_dir / "src/main/resources/logback-spring.xml",
            render_template(t, "config/logback-spring.xml.jinja", ctx),
        )

        # .gitignore
        write_file(output_dir / ".gitignore", render_template(t, "config/gitignore.jinja", {}))

        # Spring Cloud 微服务配置
        if layout.use_spring_cloud:
            cloud_ctx = {"pkg": pkg, "service_discovery": layout.service_discovery, "use_feign": layout.use_feign}
            write_file(
                config_dir / "CloudConfig.java",
                render_template(t, "infrastructure/cloud/BootstrapConfig.java.jinja", cloud_ctx),
            )

        if layout.use_sentinel:
            write_file(
                config_dir / "SentinelConfig.java",
                render_template(t, "infrastructure/cloud/SentinelConfig.java.jinja", {"pkg": pkg}),
            )

        if layout.use_seata:
            write_file(
                config_dir / "SeataConfig.java",
                render_template(t, "infrastructure/cloud/SeataConfig.java.jinja", {"pkg": pkg}),
            )

        # Nacos Config: bootstrap.yml
        if layout.use_nacos_config:
            bootstrap_ctx = {
                "application": _app_ctx(app_name, app_config),
                "use_nacos_config": True,
                "service_discovery": layout.service_discovery,
            }
            write_file(
                output_dir / "src/main/resources/bootstrap.yml",
                render_template(t, "bootstrap.yml.jinja", bootstrap_ctx),
            )

        # Docker + K8s
        if layout.use_docker or layout.use_k8s:
            self._render_deploy(app_name, app_config, layout, output_dir)

    def render_models(
        self, structs: list[StructDef], app_name: str, output_dir: Path,
        app_config: dict | None = None,
    ) -> None:
        t = self.target_lang
        pkg = _pkg_path(app_name)
        layout = get_java_layout(app_config)

        entity_dir = output_dir / "src/main/java" / pkg / "domain/entity"
        for struct in structs:
            ctx = {"struct": struct, "application": {"name": pkg}}
            write_file(entity_dir / f"{struct.name}.java",
                       render_template(t, "domain/Entity.java.jinja", ctx))

        mapper_dir = output_dir / "src/main/java" / pkg / "infrastructure/mapper"
        for struct in structs:
            ctx = {"struct": struct, "application": {"name": pkg}}
            write_file(mapper_dir / f"{struct.name}Mapper.java",
                       render_template(t, "infrastructure/mapper/Mapper.java.jinja", ctx))

        # MyBatis XML mapper files
        if layout.use_mybatis_xml:
            xml_dir = output_dir / "src/main/resources/mapper"
            for struct in structs:
                tbl = _table_name(struct)
                non_id_fields = [f for f in struct.fields if not any(
                    a.name == "primary" for a in f.annotations
                )]
                insert_cols = ", ".join(f.name for f in non_id_fields)
                insert_ph = ", ".join(f"#{{{ _snake_to_camel(f.name) }}}" for f in non_id_fields)
                ctx = {
                    "struct": struct,
                    "pkg": pkg,
                    "table_name": tbl,
                    "insert_columns": insert_cols,
                    "insert_placeholders": insert_ph,
                }
                write_file(
                    xml_dir / f"{struct.name}Mapper.xml",
                    render_template(t, "infrastructure/mapper/MapperXML.xml.jinja", ctx),
                )

        # DTO / VO / Assembler
        if layout.use_dto:
            self._render_dtos(structs, pkg, output_dir, layout)
        if layout.use_vo:
            self._render_vos(structs, pkg, output_dir, layout)
        if layout.use_dto or layout.use_vo:
            self._render_assemblers(structs, pkg, output_dir, layout)

        # Feign 客户端（微服务间调用）
        if layout.use_feign and layout.use_dto:
            self._render_feign_clients(structs, pkg, output_dir, app_name)

    def _render_dtos(
        self, structs: list[StructDef], pkg: str, output_dir: Path, layout: JavaLayoutConfig,
    ) -> None:
        t = self.target_lang
        req_dir = output_dir / "src/main/java" / pkg / "interfaces/dto/request"
        resp_dir = output_dir / "src/main/java" / pkg / "interfaces/dto/response"

        for struct in structs:
            base_ctx = {"struct": struct, "pkg": pkg}
            write_file(
                req_dir / f"{struct.name}CreateRequest.java",
                render_template(t, "interface/dto/request/CreateRequest.java.jinja", base_ctx),
            )
            write_file(
                req_dir / f"{struct.name}UpdateRequest.java",
                render_template(t, "interface/dto/request/UpdateRequest.java.jinja", base_ctx),
            )
            write_file(
                resp_dir / f"{struct.name}Response.java",
                render_template(
                    t, "interface/dto/response/ResponseDTO.java.jinja",
                    {**base_ctx, "sensitive_fields": layout.sensitive_fields},
                ),
            )

    def _render_vos(
        self, structs: list[StructDef], pkg: str, output_dir: Path, layout: JavaLayoutConfig,
    ) -> None:
        t = self.target_lang
        vo_dir = output_dir / "src/main/java" / pkg / "interfaces/vo"

        for struct in structs:
            ctx = {"struct": struct, "pkg": pkg, "sensitive_fields": layout.sensitive_fields}
            write_file(
                vo_dir / f"{struct.name}VO.java",
                render_template(t, "interface/vo/VO.java.jinja", ctx),
            )

    def _render_assemblers(
        self, structs: list[StructDef], pkg: str, output_dir: Path, layout: JavaLayoutConfig,
    ) -> None:
        t = self.target_lang
        asm_dir = output_dir / "src/main/java" / pkg / "interfaces/assembler"

        for struct in structs:
            ctx = {
                "struct": struct,
                "pkg": pkg,
                "use_dto": layout.use_dto,
                "use_vo": layout.use_vo,
                "sensitive_fields": layout.sensitive_fields,
            }
            write_file(
                asm_dir / f"{struct.name}Assembler.java",
                render_template(t, "interface/assembler/Assembler.java.jinja", ctx),
            )

    def render_methods(
        self,
        functions: list[FnDef],
        structs: list[StructDef],
        app_name: str,
        ai_results: dict | None,
        output_dir: Path,
        app_config: dict | None = None,
    ) -> None:
        from enjinc.template_renderer import _get_ai_code
        t = self.target_lang
        pkg = _pkg_path(app_name)
        layout = get_java_layout(app_config)

        fn_by_name = {fn.name: fn for fn in functions}

        for struct in structs:
            fns_for_struct = [
                fn for fn in functions
                if self._fn_belongs_to_struct(fn, struct)
            ]
            # Group guard code by function name for proper placement
            guard_code_map: dict[str, list[str]] = {}
            ai_code = None
            for fn in fns_for_struct:
                if fn.guard:
                    guard_code_map[fn.name] = compile_guards_java(fn.guard)
                code = _get_ai_code(ai_results, "fn", fn.name)
                if code:
                    ai_code = code

            base_ctx = {"struct": struct, "pkg": pkg, "ai_code": ai_code}

            if layout.use_service_interface:
                # Generate Interface
                write_file(
                    output_dir / "src/main/java" / pkg / "application/service" / f"I{struct.name}Service.java",
                    render_template(t, "application/IService.java.jinja", base_ctx),
                )
                # Generate ServiceImpl
                impl_ctx = {**base_ctx, "guard_code": guard_code_map}
                write_file(
                    output_dir / "src/main/java" / pkg / "application/service/impl" / f"{struct.name}ServiceImpl.java",
                    render_template(t, "application/impl/ServiceImpl.java.jinja", impl_ctx),
                )
            else:
                # Legacy: single Service class
                all_guards = []
                for lines in guard_code_map.values():
                    all_guards.extend(lines)
                ctx = {**base_ctx, "guard_code": all_guards, "application": {"name": pkg}}
                write_file(
                    output_dir / "src/main/java" / pkg / "application/service" / f"{struct.name}Service.java",
                    render_template(t, "application/Service.java.jinja", ctx),
                )

    def render_modules(
        self, modules: list[ModuleDef], output_dir: Path,
    ) -> None:
        pass

    def _render_feign_clients(
        self, structs: list[StructDef], pkg: str, output_dir: Path, app_name: str,
    ) -> None:
        t = self.target_lang
        client_dir = output_dir / "src/main/java" / pkg / "infrastructure/client"
        service_name = _pkg_path(app_name)

        for struct in structs:
            ctx = {"struct": struct, "pkg": pkg, "service_name": service_name}
            write_file(
                client_dir / f"{struct.name}Client.java",
                render_template(t, "infrastructure/cloud/FeignClient.java.jinja", ctx),
            )
            write_file(
                client_dir / f"{struct.name}ClientFallbackFactory.java",
                render_template(t, "infrastructure/cloud/FeignClientFallback.java.jinja", ctx),
            )

    def render_routes(
        self,
        routes: list[RouteDef],
        app_name: str,
        ai_results: dict | None,
        output_dir: Path,
        functions: list | None = None,
        structs: list | None = None,
        app_config: dict | None = None,
    ) -> None:
        from enjinc.template_renderer import _get_ai_code
        t = self.target_lang
        pkg = _pkg_path(app_name)
        layout = get_java_layout(app_config)

        controller_dir = output_dir / "src/main/java" / pkg / "interfaces/controller"
        struct_names = {s.name for s in structs} if structs else set()

        for route in routes:
            route_ai_code = _get_ai_code(ai_results, "route", route.name)
            prefix = "/"
            for anno in route.annotations:
                if anno.name == "prefix" and anno.args:
                    prefix = anno.args[0]

            # 解析 route 依赖，提取 struct 名用于 Service 注入
            service_deps = []
            for dep in route.dependencies:
                if dep in struct_names:
                    service_deps.append(dep)

            ctx = {
                "route": route,
                "pkg": pkg,
                "prefix": prefix,
                "ai_code": route_ai_code,
                "use_dto": layout.use_dto,
                "service_deps": service_deps,
            }
            write_file(
                controller_dir / f"{route.name}Controller.java",
                render_template(t, "interface/controller/Controller.java.jinja", ctx),
            )

        kafka_dir = output_dir / "src/main/java" / pkg / "messaging"
        write_file(
            kafka_dir / "EventPublisher.java",
            render_template(t, "messaging/KafkaProducer.java.jinja", {"application": {"name": pkg}}),
        )

        # Gateway 模块
        if layout.use_gateway:
            self._last_service_discovery = layout.service_discovery
            self._last_use_tracing = layout.use_tracing
            self._render_gateway(routes, pkg, output_dir)

        migration_dir = output_dir / "src/main/resources" / "db" / "migration"
        migration_dir.mkdir(parents=True, exist_ok=True)

    def _fn_belongs_to_struct(self, fn: FnDef, struct: StructDef) -> bool:
        """判断 fn 是否属于 struct（基于返回类型或参数类型）。"""
        if fn.return_type and fn.return_type.base == struct.name:
            return True
        for param in fn.params:
            if param.type.base == struct.name:
                return True
        return False

    def _render_gateway(
        self, routes: list[RouteDef], pkg: str, output_dir: Path,
    ) -> None:
        t = self.target_lang
        gateway_dir = output_dir / "gateway"

        ctx = {"pkg": pkg, "routes": routes}

        # Gateway pom.xml
        gateway_pom_ctx = {
            "application": {"name": pkg, "version": "0.1.0"},
            "service_discovery": getattr(self, "_last_service_discovery", ""),
            "use_tracing": getattr(self, "_last_use_tracing", False),
        }
        write_file(
            gateway_dir / "pom.xml",
            render_template(t, "build/gateway-pom.xml.jinja", gateway_pom_ctx),
        )

        write_file(
            gateway_dir / f"{pkg}_gateway" / "GatewayApplication.java",
            render_template(t, "infrastructure/cloud/GatewayApplication.java.jinja", {"pkg": f"{pkg}.gateway"}),
        )
        write_file(
            gateway_dir / f"{pkg}_gateway" / "GatewayRouteConfig.java",
            render_template(t, "infrastructure/cloud/GatewayRoutes.yml.jinja", ctx),
        )
        write_file(
            gateway_dir / f"{pkg}_gateway" / "filter" / "AuthGlobalFilter.java",
            render_template(t, "infrastructure/cloud/GatewayFilter.java.jinja", {"pkg": f"{pkg}.gateway.filter"}),
        )

    def _render_deploy(
        self, app_name: str, app_config: dict, layout: JavaLayoutConfig, output_dir: Path,
    ) -> None:
        t = self.target_lang
        pkg = _pkg_path(app_name)
        app_ctx = _app_ctx(app_name, app_config)

        if layout.use_docker:
            deploy_dir = output_dir / "deploy"
            write_file(
                deploy_dir / "Dockerfile",
                render_template(t, "deploy/docker/Dockerfile.jinja", {}),
            )
            compose_ctx = {
                "application": app_ctx,
                "use_nacos_config": layout.use_nacos_config,
                "service_discovery": layout.service_discovery,
                "use_tracing": layout.use_tracing,
            }
            write_file(
                deploy_dir / "docker-compose.yml",
                render_template(t, "deploy/docker/docker-compose.yml.jinja", compose_ctx),
            )

        if layout.use_k8s:
            k8s_dir = output_dir / "deploy" / "k8s"
            k8s_ctx = {
                "app_name": pkg,
                "version": app_ctx.get("version", "0.1.0"),
                "replicas": 2,
                "image_repo": f"registry.example.com/{pkg}",
                "db_service": f"{pkg}-postgres",
                "kafka_service": f"{pkg}-kafka",
                "nacos_service": f"{pkg}-nacos",
                "use_nacos_config": layout.use_nacos_config,
                "service_discovery": layout.service_discovery,
            }
            write_file(
                k8s_dir / "deployment.yaml",
                render_template(t, "deploy/k8s/deployment.yaml.jinja", k8s_ctx),
            )

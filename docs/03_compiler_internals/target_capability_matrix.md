# 目标能力矩阵 (Target Capability Matrix)

> 本文档描述 EnJin 当前与规划中的目标栈能力边界，防止文档承诺超过实际模板与编译器能力。

---

## 1. 目标

本矩阵回答三个问题：

- 某个目标栈是否已具备基础模板能力
- 某类业务场景是否推荐落到该目标栈
- 当前能力是"已实现"还是"规划中"

---

## 2. 当前目标栈

- `python_fastapi` — app/ 包结构，含 schemas/repositories/api 版本化
- `java_springboot` — 完整分层：Entity/Mapper/XML/IService/ServiceImpl/Controller/DTO/VO/Assembler
- `python_crawler` — httpx/Scrapy/Playwright 三框架

第三方目标可通过 pip 插件安装（见 `docs/07_plugins/extension_guide.md`）。

---

## 3. P0/P1 能力清单

### P0 — 编译器核心能力（必须完成）

| # | 能力 | 状态 | 验证方式 |
|---|---|---|---|
| P0-1 | `.ej` 语法解析 → I-AST | **已完成** | 24 parser tests |
| P0-2 | 静态四层校验 | **已完成** | 26 analyzer tests |
| P0-3 | Python FastAPI 目标栈 | **已完成** | 14 template tests |
| P0-4 | Java Spring Boot 目标栈 | **已完成** | 18 template tests |
| P0-5 | 模板渲染管线 (Jinja2) | **已完成** | template_renderer 模块 |
| P0-6 | `enjinc build` CLI | **已完成** | 9 CLI tests |
| P0-7 | `enjinc analyze` CLI | **已完成** | CLI tests |
| P0-8 | `expect` 自动测试生成 | **已完成** | 20 test_generator tests |
| P0-9 | `@locked` / `native` 逃生舱 | **已完成** | parser + analyzer tests |
| P0-10 | Java 分层架构 (IService/Impl/DTO/VO/Assembler/Mapper XML) | **已完成** | 18 Java template tests |
| P0-11 | Python 分层架构 (app/ 包 + schemas/repositories/api v1) | **已完成** | 14 Python template tests |
| P0-12 | 插件式目标栈架构 (entry_points) | **已完成** | Go Gin plugin 验证 |
| P0-13 | 布局配置 (layout_config.py) | **已完成** | 约定大于配置 |

### P1 — AI 协同与扩展能力（核心增强）

| # | 能力 | 状态 | 验证方式 |
|---|---|---|---|
| P1-1 | AI 代码生成 (LLM 对接) | **已完成** | 32 AI generation tests |
| P1-2 | 多模型调度 (MultiModelConfig) | **已完成** | CLI --master/fn-provider |
| P1-3 | Prompt Router (上下文剪枝) | **已完成** | prompt_router.py |
| P1-4 | 依赖图注入 | **已完成** | 21 dependency_graph tests |
| P1-5 | Master AI 审核器 | **已完成** | 7 reviewer tests |
| P1-6 | `enjin.lock` 锁定机制 | **部分完成** | 18 lock tests，CI/CD 集成待完善 |
| P1-7 | 蓝绿数据库迁移 | **已完成** | 14 migration tests |
| P1-8 | AST 审计 (编辑距离) | **已完成** | 23 ast_audit tests |
| P1-9 | `enjinc scaffold-target` 脚手架 | **已完成** | CLI 子命令 |
| P1-10 | `enjinc verify` CI 锁定校验 | **已完成** | CLI 子命令 |
| P1-11 | `enjinc migrate` 迁移脚本 | **已完成** | CLI 子命令 |
| P1-12 | 第三方插件示例 (Go Gin) | **已完成** | examples/plugins/enjinc-go-gin/ |
| P1-13 | Seata 分布式事务 | **已完成** | 3 Seata tests |
| P1-14 | Nacos 配置中心 | **已完成** | 2 Nacos Config tests |
| P1-15 | Sleuth + Zipkin 链路追踪 | **已完成** | 2 Tracing tests |
| P1-16 | Docker + docker-compose 部署 | **已完成** | 3 Docker tests |
| P1-17 | K8s Deployment/Service YAML | **已完成** | 2 K8s tests |

### P2 — 规划中能力

| # | 能力 | 状态 |
|---|---|---|
| P2-1 | `native` 块内嵌花括号支持 | 规划中 (Phase 4) |
| P2-2 | MQ 连接模板 (Python) | 规划中 |
| P2-3 | Temporal Workflow 模板 | 规划中 |
| P2-4 | Spring StateMachine 模板 | 规划中 |
| P2-5 | 多模块 Maven 项目结构 | 规划中 |
| P2-6 | `@domain` 注解 | 规划中 |
| P2-7 | `@engine` 注解 | 规划中 |
| P2-8 | `@data_plane` 注解 | 规划中 |
| P2-9 | Queue Contract 语义 | 规划中 |
| P2-10 | `route -> module action` 调用 | 规划中 |

---

## 4. 业务场景推荐矩阵

| 场景 | 推荐目标栈 | 当前结论 |
|---|---|---|
| 高并发电商交易核心 | `java_springboot` | 主栈 |
| 智能监控 / 告警中心 | `python_fastapi` | 主栈 |
| Agent 控制平面 | `python_fastapi` | 主栈 |
| 爬虫 / 采集系统 | `python_crawler` | 主栈 |
| 风控系统 | `java_springboot` | 主栈 |
| Go 微服务 | `go_gin` (插件) | 第三方插件 |
| 大数据计算内核 | 外部原生子项目 | 不建议由 EnJin 直接生成 |

---

## 5. 模板实现状态矩阵

| 能力 | python_fastapi | java_springboot | python_crawler |
|---|---|---|---|
| `application` 基建模板 | 已实现 | 已实现 | 已实现 |
| 数据库连接模板 | 已实现 | 已实现 (Flyway) | N/A |
| 基础入口文件 | 已实现 | 已实现 (Spring Boot) | 已实现 |
| ORM / Model 骨架 | 已实现 | 已实现 (MyBatis-Plus Entity) | N/A |
| Pydantic Schema 层 | 已实现 | N/A | N/A |
| Repository 数据访问层 | 已实现 | N/A | N/A |
| Service Interface + Impl | N/A | 已实现 | N/A |
| DTO (Create/Update/Response) | N/A | 已实现 | N/A |
| VO (View Object) | N/A | 已实现 | N/A |
| Assembler (Entity-DTO 转换) | N/A | 已实现 | N/A |
| MyBatis XML Mapper | N/A | 已实现 | N/A |
| Method / Service 骨架 | 已实现 | 已实现 | 已实现 |
| Module 骨架 | 已实现 | 已实现 | 已实现 |
| Route 装配骨架 (API 版本化) | 已实现 (api/v1/) | 已实现 (REST Controller) | N/A |
| Auth 依赖注入 | 已实现 | 已实现 | N/A |
| requirements.txt / pom.xml | 已实现 | 已实现 | N/A |
| MQ 连接模板 | 规划中 | 已实现 (Kafka Producer) | N/A |
| Spring Cloud 服务发现 (Nacos) | N/A | 已实现 | N/A |
| OpenFeign 声明式客户端 | N/A | 已实现 | N/A |
| Spring Cloud Gateway | N/A | 已实现 | N/A |
| Sentinel 熔断降级 | N/A | 已实现 | N/A |
| Seata 分布式事务 | N/A | 已实现 | N/A |
| Nacos 配置中心 | N/A | 已实现 | N/A |
| Sleuth + Zipkin 链路追踪 | N/A | 已实现 | N/A |
| Dockerfile + docker-compose | N/A | 已实现 | N/A |
| K8s Deployment/Service | N/A | 已实现 | N/A |
| Workflow / Temporal 模板 | 规划中 | 不适用（默认） |
| Spring StateMachine 模板 | 不适用（默认） | 规划中 |

---

## 6. 架构语义支持矩阵

| 语义能力 | 当前文档状态 | 当前代码状态 |
|---|---|---|
| 四层隔离 | 已明确 | 部分未强制 |
| `route -> module action` | 已明确 | 未实现 |
| `@domain` | 已明确（规划） | 未实现 |
| `@engine` | 已明确（规划） | 未实现 |
| `@data_plane` | 已明确（规划） | 未实现 |
| Queue Contract | 已明确（规划） | 未实现 |
| Temporal Workflow Model | 已明确（规划） | 未实现 |
| `expect` 结构化断言 | 已实现 | 已实现 |
| `enjin.lock` | 已有骨架文档 | 部分实现 |
| 布局配置 (layout_config) | 已实现 | 已实现 |
| 插件式目标栈 (entry_points) | 已实现 | 已实现 |

---

## 7. 输出布局配置

每个目标栈支持通过 `.ej` 的 `application.config.layout` 自定义输出结构。未配置的项使用默认约定。

| 配置项 | 目标栈 | 默认值 | 说明 |
|---|---|---|---|
| `java_use_service_interface` | java_springboot | true | 生成 IService + ServiceImpl 分离 |
| `java_use_dto` | java_springboot | true | 生成 Request/Response DTO |
| `java_use_vo` | java_springboot | true | 生成 View Object |
| `java_use_assembler` | java_springboot | true | 生成 Entity-DTO 转换器 |
| `java_use_mybatis_xml` | java_springboot | true | 生成 MyBatis XML Mapper |
| `java_use_spring_cloud` | java_springboot | false | 启用 Spring Cloud 微服务模式 |
| `java_service_discovery` | java_springboot | "" | 服务发现: "nacos" / "eureka" |
| `java_use_gateway` | java_springboot | false | 生成 API Gateway 模块 |
| `java_use_feign` | java_springboot | false | 生成 OpenFeign 客户端 |
| `java_use_sentinel` | java_springboot | false | 生成 Sentinel 熔断配置 |
| `python_use_schemas` | python_fastapi | true | 生成 Pydantic Schemas 层 |
| `python_use_repository` | python_fastapi | true | 生成 Repository 数据访问层 |
| `python_api_version` | python_fastapi | "v1" | API 版本前缀 |

---

## 8. 运行时责任边界

### EnJin 负责

- 控制面骨架
- 接口契约
- 模板渲染
- 静态约束
- 测试与锁文件规范
- 布局配置
- 插件自动发现与注册

### 目标栈原生生态负责

- Java：Spring / MyBatis / StateMachine / MQ Client 深度集成
- Python：FastAPI / Temporal SDK / Scrapy / Playwright / Redis / MQ Client 深度集成
- Go：Gin / GORM / etc.（由第三方插件负责）

---

## 9. 测试覆盖状态 (427 tests passing)

| 测试文件 | 数量 | 状态 |
|---|---|---|
| `tests/test_parser.py` | 24 | ✅ |
| `tests/test_templates.py` | 14 | ✅ |
| `tests/test_java_templates.py` | 18 | ✅ |
| `tests/test_crawler_templates.py` | 11 | ✅ |
| `tests/test_test_generator.py` | 20 | ✅ |
| `tests/test_risk_control.py` | 43 | ⚠️ 1 个 Mapper 测试待更新 |
| `tests/test_integration.py` | 20 | ✅ |
| `tests/test_analyzer.py` | 26 | ✅ |
| `tests/test_cli.py` | 9 | ✅ |
| `tests/test_ai_generation.py` | 32 | ✅ |
| `tests/test_parser_stress.py` | 20+ | ⚠️ 部分慢测试 |
| `tests/test_parser_concurrency.py` | 12 | ✅ |
| `tests/test_parser_error_recovery.py` | 43 | ✅ |
| `tests/test_business_logic.py` | 19 | ✅ |
| `tests/test_enjin_lock.py` | 18 | ✅ |
| `tests/test_crash_recovery.py` | 15 | ✅ |
| `tests/test_dependency_graph.py` | 21 | ✅ |
| `tests/test_reviewer.py` | 7 | ✅ |
| `tests/test_e2e.py` | 12 | ⚠️ 爬虫 E2E import 路径待更新 |
| `tests/test_migration.py` | 14 | ✅ |
| `tests/test_ast_audit.py` | 23 | ✅ |
| `tests/test_microservice_templates.py` | 23 | ✅ |

---

## 10. 使用建议

- 文档中带 **[规划]** 的语义不得被视为当前代码已支持
- 电商场景优先做 Java 文档与模板补齐，再做业务生成
- Python 场景优先补监控 / Agent / 爬虫控制面模板
- 第三方目标栈通过 pip 插件机制扩展，无需修改 enjinc 源码
- 使用 `enjinc scaffold-target <name> --plugin` 快速创建第三方插件脚手架

---

> 本文件最后更新: 2026-05-01 | 版本: v0.5.0

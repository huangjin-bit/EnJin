# EnJin 编译器开发流水线与计划 (ROADMAP)

> **[Agent 执行指令]：** 本文件是项目的动态状态机。OpenCode 在完成任意一个子任务后，必须主动修改此文件，将 `[ ]` 更新为 `[x]`，并简要记录实现路径或踩坑点。每次开启新会话，请先读取本文件的最新进度。

## 核心编译流水线 (The Build Pipeline)

每次执行 `enjinc build` 时，系统必须严格按照以下顺序流转，不可跳过：

1. **词法/语法解析 (Lex & Parse):** Lark 读取 `.ej` 文件，生成 Parse Tree。
2. **意图降维 (AST Transformation):** Transformer 将 Parse Tree 转化为标准的 JSON I-AST（意图抽象语法树）。
3. **架构静态校验 (Static Analysis):** 检查是否存在越权调用，检查 `@locked` 缓存命中率。
4. **提示词路由 (Prompt Routing):** 根据全局 `application.ej` 配置，为未锁定的节点组装包含 Context 的 System Prompt。
5. **动态填充 (AI Generation):** 并发调用 LLM，将 `process` 意图转化为目标语言（Java/Python）代码段。
6. **模板组装 (Template Sandwich):** 将 AI 生成的代码块注入到预设的 Jinja2 框架插槽中。
7. **自动化网关 (Auto-Testing):** 运行由 `expect` 生成的单元测试。全绿则落盘并生成 `enjin.lock`，爆红则熔断重试。

---

## 当前状态: **Phase 4 - 工业级护栏与安全审计** (进行中)

### [Phase 1] 编译器前端基座 (已完成: 2026-03-16)

**目标：** 将 `.ej` 源码文本精准解析为标准化的 I-AST (Intent-AST) JSON 结构。

- [x] **1.1** 完善 `grammar.lark`，覆盖 `struct`, `fn`, `module`, `route`、`@注解`及 `expect/process/guard` 语法。
- [x] **1.2** 编写 `parser.py`（基于 Lark 的 Transformer），实现从 `.ej` 文本到 I-AST JSON 字典的精确转换。
- [x] **1.3** 编写边界测试用例，验证解析器是否能正确捕获嵌套的 `expect/process/guard` 及四层架构的层级结构。
- *动态备注：*
  - 实现路径: Lark Earley 解析器 + Transformer 模式
  - 已完成 21 个单元测试全部通过
  - 支持多行 process/init/schedule 字符串 (PROCESS_STRING)
  - native 块暂不支持内嵌花括号（Phase 4 可考虑增强）
  - 文档体系已建立: docs/ 下 6 个子域，含完整 AST Schema

### [Phase 2] 后端模板与静态装配 (已完成: 2026-04-08)

**目标：** 建立目标语言的 Jinja2 模板体系，实现 AST 到静态骨架代码的确定性生成。

- [x] **2.1** 设计目标语言（Python FastAPI + SQLAlchemy）的 `targets/python_fastapi/templates/` 物理目录树生成器。
- [x] **2.2** 编写基建层的 Jinja2 静态模板（`database.py.jinja`, `main.py.jinja`, `config.py.jinja`），不调用 AI。
- [x] **2.3** 编写业务层的 Jinja2 骨架模板，预留受控插槽（如 `{{ process_code }}`），并实现 AST 到 Jinja2 的静态数据绑定测试。
- *动态备注：*
  - 实现路径: Jinja2 模板引擎 + Environment 管理
  - 已完成 11 个模板渲染测试全部通过
  - 基建层文件 100% 确定性生成，无 AI 参与
  - 业务层预留 `process_code` 插槽，Phase 3 将注入 AI 生成内容
  - 模板文档已记录在 docs/03_compiler_internals/template_engine.md

### [Phase 2.5] Java Spring Boot 电商模板 (已完成: 2026-04-08)

**目标：** 为 Java Spring Boot 分布式电商系统建立完整模板体系。

- [x] **2.5.1** Maven `pom.xml.jinja` - Spring Boot 3.2.3 + JPA + MyBatis-Plus + Kafka + JWT + Flyway
- [x] **2.5.2** `application.yml.jinja` - Spring Boot 配置（PostgreSQL/Kafka/Security）
- [x] **2.5.3** `Application.java.jinja` - Spring Boot 主类
- [x] **2.5.4** `Entity.java.jinja` - JPA 实体（Lombok 注解）
- [x] **2.5.5** `Mapper.java.jinja` - MyBatis-Plus Mapper 接口
- [x] **2.5.6** `Service.java.jinja` - Service 层
- [x] **2.5.7** `Controller.java.jinja` - REST Controller
- [x] **2.5.8** `SecurityConfig.java.jinja` - Spring Security 配置
- [x] **2.5.9** `MybatisPlusConfig.java.jinja` - MyBatis-Plus 配置
- [x] **2.5.10** `KafkaProducer.java.jinja` - Kafka 事件发布
- [x] **2.5.11** `V1__init.sql.jinja` - Flyway 数据库迁移
- *动态备注：*
  - Java 电商示例 (`examples/java_ecommerce/trade.ej`) 包含:
    - 20 个 Struct: User, UserAddress, Category, Product, ProductSku, Cart, Order, OrderItem, Payment, Logistics, Refund, ProductReview, Coupon, UserCoupon, SearchHistory
    - 31 个 Function: 用户、订单、支付、物流、评价、优惠券等全链路
    - 7 个 Module: UserManager, ProductManager, SearchManager, CartManager, OrderManager, ReviewManager, CouponManager
    - 8 个 Route: UserService, ProductService, SearchService, CartService, OrderService, ReviewService, CouponService, HealthService
  - 已完成 11 个 Java 模板测试全部通过

### [Phase 2.6] Python 爬虫模板 (已完成: 2026-04-08)

**目标：** 为 Python 爬虫系统建立 httpx + Scrapy + Playwright 三框架模板体系。

- [x] **2.6.1** `httpx/config.py.jinja` - 爬虫配置（代理池、速率限制）
- [x] **2.6.2** `httpx/proxy_pool.py.jinja` - 异步代理池管理器
- [x] **2.6.3** `httpx/rate_limiter.py.jinja` - Token Bucket 速率限制器
- [x] **2.6.4** `httpx/crawler.py.jinja` - 异步爬虫主类
- [x] **2.6.5** `scrapy/spiders/base.py.jinja` - Scrapy Spider 基类
- [x] **2.6.6** `scrapy/items.py.jinja` - Scrapy Items
- [x] **2.6.7** `scrapy/pipelines.py.jinja` - Scrapy Pipelines (MongoDB/MySQL)
- [x] **2.6.8** `playwright/config.py.jinja` - Playwright 配置
- [x] **2.6.9** `playwright/crawler.py.jinja` - Playwright 爬虫主类
- *动态备注：*
  - Python 爬虫示例 (`examples/python_crawler/product_crawler.ej`) 包含:
    - 4 个 Struct: Product, Category, Review, PriceHistory
    - 6 个 Function: crawl_product_list, crawl_product_detail, crawl_category_list, crawl_product_reviews, search_products, check_price_alert
    - 3 个 Module: HttpxCrawler, ScrapyCrawler, PlaywrightCrawler
  - 已完成 11 个 Python 爬虫模板测试全部通过

### [Phase 2.7] Java 风控系统模板 (已完成: 2026-04-08)

**目标：** 为 Java Spring Boot 电商系统建立独立的风控模块。

- [x] **2.7.1** `RiskEntity.java.jinja` - 风控实体（JPA + Lombok）
- [x] **2.7.2** `RiskMapper.java.jinja` - MyBatis-Plus Mapper 接口
- [x] **2.7.3** `RiskService.java.jinja` - 风控核心服务（规则引擎、风险评估、黑白名单）
- [x] **2.7.4** `RiskController.java.jinja` - 风控 API 控制器
- [x] **2.7.5** `V2__init_risk_control.sql.jinja` - Flyway 风控数据库迁移
- *动态备注：*
  - 风控系统示例 (`examples/java_ecommerce/risk_control.ej`) 包含:
    - 14 个 Struct: RiskRule, RiskEvent, RiskProfile, RiskBlacklist, RiskWhitelist, RiskAlert, DeviceFingerprint, RiskOperationLog, RiskDecision, BlacklistResult, WhitelistResult, RuleResult, RiskStatistics, RiskTrendItem
    - 29 个 Function: 用户/订单/支付/优惠券风控评估, 黑白名单管理, 风控档案, 预警管理, 设备指纹, 规则引擎, 实时决策, 统计报表
    - 1 个 Module: RiskControlManager
    - 1 个 Route: RiskControlService
    - 预置 26 条风控规则（用户注册、登录、订单、支付、优惠券、设备）
  - 已完成 43 个风控测试全部通过（含生成代码逻辑验证）
  - 风控系统与 trade.ej 主系统通过 Integration 层深度集成

### [Phase 3] AI 路由与协同生成 (已完成: 2026-04-08)

**目标：** 在真实生产约束下实现 `process` 意图的 AI 动态代码生成，精准控制 Prompt 上下文、Token 消耗与多目标栈边界。

- [x] **3.1** 编写 `PromptRouter`（`prompt_router.py`），根据 AST 节点类型（Model/Method 等）组装差异化的 System Prompt，实现基于上下文剪枝的 Prompt 拼装机制。
- [x] **3.2** 对接 LLM API，实现 `llm_client.py`，支持 OpenAI/DeepSeek/Anthropic，提供熔断重试、并发控制、Token 统计。
- [x] **3.3** 实现 `CodeGenerator`，整合 Prompt Router 和 LLM Client，基于 intent_hash 的 `@locked` 缓存机制。
- [x] **3.4** 实现 `EnjinLock` 持久化缓存，支持多目标栈独立缓存。
- *动态备注：*
  - 已完成 30 个 AI Generation 测试全部通过
  - PromptRouter 支持: python_fastapi, java_springboot, python_crawler
  - LLMClient 支持: OpenAI, DeepSeek, Anthropic
  - EnjinLock 支持: 基于 intent_hash 的缓存，JSON 格式持久化
  - 熔断器: 连续失败 5 次后开启，60 秒后尝试恢复

### [Phase 4] 工业级护栏与安全审计 (进行中)

**目标：** 实现 `@locked`/`native` 逃生舱、`expect` 自动测试生成与 `enjin.lock` 构建锁定。

- [x] **4.1** 解析器实现 `@locked` 与 `native` 关键字的逃生舱拦截逻辑。
- [x] **4.2** 根据 `expect` 意图，利用 Jinja2 自动生成对应的 pytest/JUnit 单元测试文件。实现意图源码映射表 (Source Map) 生成器。
- [ ] **4.3** 研发 `enjin.lock` 锁定机制，确保 CI/CD 环境的绝对确定性。构建"蓝绿数据库迁移"脚本生成模块雏形。
- *动态备注：*
  - `test_generator.py` 实现 `expect` 断言解析（property_eq, throws, status_eq, contains）
  - Jinja2 模板: `test_fn.py.jinja` (pytest), `test/Test.java.jinja` (JUnit)
  - 已完成 20 个 test_generator 测试全部通过（含 3 个实际运行 pytest 的集成测试）
  - `enjin.lock` 需要支持多编译单元与多目标栈的独立缓存边界

### [Phase 5] AI 上下文增强 + 架构可扩展性 (已完成: 2026-04-28)

**目标：** 让 AI 具备项目全局视野，建立目标栈的插件式架构。

- [x] **5.1** 实现依赖图提取 (`dependency_graph.py`)，从 Program AST 提取 fn→struct、module→fn、route→module 调用关系，渲染为文本注入 AI system prompt。
- [x] **5.2** 实现 Master AI 审核器 (`reviewer.py`)，审核所有子 AI 生成代码，提意见但不修改。支持最多 1 轮审核重试。
- [x] **5.3** 实现多模型调度 (`MultiModelConfig`)，支持不同层使用不同 LLM 模型。CLI 新增 `--master-provider/model`、`--fn-provider/model`、`--no-review` 参数。
- [x] **5.4** 重构目标栈架构为注册式 (`TargetRenderer` 协议 + `TARGET_REGISTRY`)，消除 `template_renderer.py` 中的硬编码 if/elif 链。新增目标无需修改编译器核心。
- [x] **5.5** 修复模板渲染问题：main.py 路由注册、models.py Column 缩进、route.py 参数列表缩进、Controller.java @PathVariable 缩进、List<T> 返回类型支持。
- [x] **5.6** 新增示例项目：`blog_platform.ej`（博客平台，3 struct + 6 fn + 6 端点）、`task_manager.ej`（任务管理，3 struct + 7 fn + 双 route + 8 端点）。
- *动态备注：*
  - 依赖图注入让 AI 能看到完整的项目结构，不再"盲写"
  - Master AI 只审核不修改，子 AI 按审核意见修正，确保代码质量
  - 目标栈架构从 4-6 文件改动降为 2 文件改动（renderer.py + templates/）
  - 345 个测试全部通过，三个目标栈 + 五个示例项目均构建验证通过

---

## 测试覆盖状态 (358 tests passing)

| 测试文件 | 数量 | 状态 |
|---|---|---|
| `tests/test_parser.py` | 24 | ✅ |
| `tests/test_templates.py` | 14 | ✅ |
| `tests/test_java_templates.py` | 18 | ✅ |
| `tests/test_crawler_templates.py` | 11 | ✅ |
| `tests/test_test_generator.py` | 20 | ✅ |
| `tests/test_risk_control.py` | 43 | ⚠️ 部分需更新 |
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
| `tests/test_e2e.py` | 12 | ✅ |
| `tests/test_migration.py` | 14 | ✅ |
| `tests/test_ast_audit.py` | 23 | ✅ |

### 架构优化 (2026-04-30)

- **constants.py**: 集中管理注解名、类型映射、HTTP 方法、异常映射、engine 注册表，消除 ~300 处硬编码
- **annotations.py**: 统一注解查询和参数提取（`has_annotation`、`get_annotation_param`），替代分散的 `any(a.name == "X" for a in ...)` 模式
- **guard_compiler.py**: 异常类名通过 `GUARD_EXCEPTIONS` 注册表查表生成，新增 guard 类型只需在 constants.py 追加
- **renderer.py**: `_py_type_str` 从 if/elif 改为 `ENJIN_TO_PYTHON` dict lookup
- **prompt_router.py**: Java 类型映射使用 `ENJIN_TO_JAVA`，route 注解提取使用 `annotations.py` 工具函数

### 输出结构重构 (2026-04-30)

- **layout_config.py**: 新增布局配置系统 (`JavaLayoutConfig` / `PythonLayoutConfig`)，约定大于配置
- **Java Spring Boot**:
  - Service Interface (`I{Entity}Service`) + ServiceImpl (`{Entity}ServiceImpl`) 分离
  - MyBatis XML mapper 文件 (`{Entity}Mapper.xml`) 含 resultMap 和 CRUD
  - DTO: `{Entity}CreateRequest` / `{Entity}UpdateRequest` / `{Entity}Response`
  - VO: `{Entity}VO` 视图对象
  - Assembler: `{Entity}Assembler` Entity-DTO/VO 转换器
  - Controller 从 `web/controller` 迁移至 `interface/controller`
  - 修复 guard 代码溢出 bug、Controller 命名不匹配、application.yml 包名
- **Python FastAPI**:
  - 封装为 `app/` 包 (core/, models/, schemas/, services/, api/v1/, repositories/)
  - 新增 Schemas 层 (Pydantic Create/Update/Response per struct)
  - 新增 Repository 层 (SQLAlchemy 查询隔离)
  - 路由从 `routes/` 迁移至 `api/v1/`，支持版本化
  - 新增 `requirements.txt` 自动生成
- **358 tests passing**

### 微服务与测试修复 (2026-05-01)

- **Java 微服务模板体系**:
  - Spring Cloud 服务发现 (Nacos/Eureka) — `CloudConfig.java`
  - OpenFeign 声明式客户端 — `{Entity}Client.java` + `{Entity}ClientFallbackFactory.java`
  - Spring Cloud Gateway — `GatewayApplication.java` + `GatewayRouteConfig.java` + `AuthGlobalFilter.java`
  - Sentinel 熔断降级 — `SentinelConfig.java`
  - 通过 `application.config.layout` 启用: `java_use_spring_cloud`, `java_use_feign`, `java_use_gateway`, `java_use_sentinel`
- **示例**: `examples/java_ecommerce/microservice_order.ej` — 完整微服务订单服务
- **测试修复**:
  - 修复 Python Crawler E2E (rate_limiter, proxy_pool) — 添加 sys.path 解决 import 问题
  - 修复 RiskMapper.java.jinja — 修正 context 变量类型和接口生成
  - 新增 11 个微服务模板测试
- **模板引擎**: 共享宏 `targets/_shared/macros.jinja`，多目录 FileSystemLoader
- **411 tests passing**

> 本文件最后更新: 2026-05-01 | 版本: v1.4.0

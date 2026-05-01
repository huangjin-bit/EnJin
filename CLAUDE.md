# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# EnJin (enjinc)

意图驱动的 AI 原生元编程语言编译器。将 `.ej` 意图源码解析为 I-AST，再编译为 Java (Spring Boot) 或 Python (FastAPI/爬虫) 目标代码。

## 技术栈

- Python 3.11+，setuptools 构建
- Lark (Earley 解析器) + Jinja2 (模板引擎)
- pytest 测试，358+ 测试用例

## 开发命令

- 安装：`pip install -e ".[dev]"`
- 安装 AI 依赖：`pip install -e ".[dev,ai]"`（LLM 集成需要 httpx）
- 全量测试：`pytest`
- 跳过慢测试：`pytest -m "not slow"`
- 单文件测试：`pytest tests/test_parser.py`
- 单个用例：`pytest tests/test_parser.py::test_struct_with_annotations -v`
- 构建：`enjinc build <source>` / `enjinc analyze <source>`
- 列出目标：`enjinc targets`
- 示例：`enjinc build examples/user_management.ej --target python_fastapi`
- 指定 AI：`enjinc build examples/blog_platform.ej --use-ai --provider openai --model gpt-4`
- Master 审核：`enjinc build app.ej --use-ai --master-provider anthropic --master-model claude-3-opus`

## 编译流水线

`enjinc build` 严格按以下顺序流转：

1. **词法/语法解析** — Lark 将 `.ej` → Parse Tree
2. **AST 转换** — Transformer 将 Parse Tree → I-AST JSON（`parser.py`）
3. **静态校验** — 四层架构校验 + `@locked` 缓存检查（`analyzer.py`）
4. **Prompt 路由** — 依赖图注入 + 组装差异化 System Prompt（`prompt_router.py`）
5. **AI 生成** — 多模型按层调用 LLM，Master AI 审核（`code_generator.py` + `llm_client.py`）
6. **模板组装** — AI 产物注入 Jinja2 框架插槽（`template_renderer.py`）
7. **自动测试** — `expect` 生成单元测试，全绿落盘 `enjin.lock`（`test_generator.py`）

## 核心架构规则

最高法则见 `ENJIN_CONSTITUTION.md`，关键约束：

- **四层隔离**：`struct`(Model) → `fn`(Method) → `module`(Module) → `route`(Service)，严格单向调用，越级直接拒绝
- **人类霸权**：`@locked` 禁止 AI 调用，`native` 块禁止篡改，`@human_maintained` 放弃生成权
- **确定性构建**：基建层由 Jinja2 模板硬编码，AI 仅填充 `{{ slot }}` 插槽
- **成本控制**：依赖图上下文注入，分级模型调用

## 项目结构要点

- `src/enjinc/` — 编译器核心（pipeline 各阶段）
- `src/enjinc/constants.py` — 集中常量注册中心（注解名、类型映射、异常映射、engine 注册表）
- `src/enjinc/annotations.py` — 注解工具函数（`has_annotation`、`get_annotation_param`）
- `src/enjinc/layout_config.py` — 输出布局配置（JavaLayoutConfig / PythonLayoutConfig，约定大于配置）
- `src/enjinc/migration.py` — 蓝绿双态迁移（struct diff → 影子表双写 SQL + Alembic 迁移）
- `src/enjinc/ast_audit.py` — AST 编辑距离审计（Python/Java 代码结构化对比）
- `src/enjinc/targets/` — 目标栈（entry_points 插件式架构）：
  - `targets/__init__.py` — TargetRenderer 协议 + 全局注册表 + entry_points 自动发现
  - `targets/<name>/renderer.py` — 每个目标的渲染器（实现 TargetRenderer 并用 `@register_target`）
  - `targets/<name>/templates/` — Jinja2 模板
- `src/enjinc/dependency_graph.py` — 依赖图提取（struct/fn/module/route 关系 + struct→struct foreign_key）
- `src/enjinc/reviewer.py` — Master AI 审核器（只审核不修改）
- `examples/` — `.ej` 示例：user_management、blog_platform、task_manager、Java 电商/风控、Python 爬虫
- `docs/` — 7 个子域：语言规范、架构、编译器内部、AI 集成、测试安全、ADR、插件扩展

## 输出项目结构

### Java Spring Boot

```
{pkg}/
  domain/entity/{StructName}.java              — JPA 实体
  infrastructure/mapper/{StructName}Mapper.java — MyBatis-Plus Mapper 接口
  application/service/I{StructName}Service.java — Service 接口
  application/service/impl/{StructName}ServiceImpl.java — Service 实现
  interface/controller/{RouteName}Controller.java — REST Controller
  interface/dto/request/{StructName}CreateRequest.java — 创建 DTO
  interface/dto/request/{StructName}UpdateRequest.java — 更新 DTO
  interface/dto/response/{StructName}Response.java — 响应 DTO
  interface/vo/{StructName}VO.java              — 视图对象
  interface/assembler/{StructName}Assembler.java — Entity-DTO 转换器
  messaging/EventPublisher.java
src/main/resources/mapper/{StructName}Mapper.xml — MyBatis XML
src/main/resources/application.yml
```

### Python FastAPI

```
app/
  main.py                     — FastAPI 入口
  core/config.py              — 配置
  core/database.py            — 数据库连接
  core/exceptions.py          — 异常层级
  core/security.py            — JWT 认证（仅 @auth 路由）
  models/{struct}.py          — SQLAlchemy ORM 模型
  schemas/{struct}.py         — Pydantic Create/Update/Response schema
  services/{fn}.py            — 业务逻辑函数
  repositories/{struct}_repository.py — 数据访问层
  api/v1/{route}.py           — 版本化路由
  modules/{module}.py         — 模块初始化
tests/
requirements.txt
```

## 新增目标栈（插件式）

内置目标与第三方插件使用完全相同的机制：

**内置**（在 `src/enjinc/targets/<name>/` 下开发）：
1. 创建 `templates/*.jinja`
2. 创建 `renderer.py`，用 `@register_target` 装饰
3. 在 `pyproject.toml` 的 `[project.entry-points."enjinc.targets"]` 添加一行

**第三方**（独立 pip 包，无需修改 enjinc 源码）：
1. 在自己的 `pyproject.toml` 声明 `[project.entry-points."enjinc.targets"]`
2. 实现 `TargetRenderer` 协议 + `@register_target`
3. `pip install enjinc-go-gin` 即可用 `--target go_gin`

完整指南见 `docs/07_plugins/extension_guide.md`。

## 已知问题

- `native` 块暂不支持内嵌花括号 (Phase 4 待增强)
- `test_parser_stress.py` 部分慢测试（用 `-m "not slow"` 跳过）
- `enjin.lock` 锁定机制尚在开发中 (Phase 4.3)
- `test_risk_control.py` 中 RiskMapper 模板测试需要更新（风控模块独立渲染逻辑）

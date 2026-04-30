# 模板引擎与插槽注入规范 (Template Engine & Slot Injection)

> 本文档定义目标语言 Jinja2 模板的插槽 (Slot) 规范及分层输出架构。

---

## 模板分类

### 1. 基建模板 (Infrastructure Templates)

100% 确定性生成，严禁 AI 参与：

| 模板文件 | 目标产物 | 说明 |
|---|---|---|
| `config.py.jinja` | `app/core/config.py` | 全局配置加载 |
| `database.py.jinja` | `app/core/database.py` | 数据库连接与会话管理 |
| `exceptions.py.jinja` | `app/core/exceptions.py` | 异常层级定义 |
| `deps.py.jinja` | `app/core/security.py` | JWT 认证依赖 |
| `main.py.jinja` | `app/main.py` | 应用入口文件 |

### 2. 业务模板 (Business Templates)

业务逻辑只允许进入受控插槽：

| 模板文件 | 目标产物 | 插槽 |
|---|---|---|
| `models.py.jinja` | `app/models/<struct>.py` | `{{ field_definitions }}` |
| `schemas.py.jinja` | `app/schemas/<struct>.py` | Pydantic Create/Update/Response |
| `services.py.jinja` | `app/services/<fn>.py` | `{{ guard_code }}`, `{{ ai_code }}` |
| `repository.py.jinja` | `app/repositories/<struct>_repository.py` | CRUD 方法 |
| `route.py.jinja` | `app/api/v1/<route>.py` | `{{ endpoint_handlers }}` |
| `routes__init__.py.jinja` | `app/api/v1/__init__.py` | 动态路由注册 |
| `modules.py.jinja` | `app/modules/<module>.py` | `{{ init_logic }}`, `{{ schedule_logic }}` |

## 插槽命名约定

- `{{ guard_code }}` — 由 guard 规则确定性生成的校验代码
- `{{ ai_code }}` — 由 AI 根据 process 意图生成的业务代码
- `{{ field_definitions }}` — 由 struct 定义确定性生成的 ORM 字段
- `{{ endpoint_handlers }}` — 由 route 定义生成的路由处理函数
- `{{ sensitive_fields }}` — 敏感字段列表，Response DTO 和 VO 中排除

## 目标栈现状

### python_fastapi

```
app/
  main.py
  core/ (config, database, exceptions, security)
  models/<struct>.py          — SQLAlchemy ORM
  schemas/<struct>.py         — Pydantic Create/Update/Response
  services/<fn>.py            — 业务逻辑
  repositories/<struct>_repository.py — 数据访问层
  api/v1/<route>.py           — 版本化路由
  modules/<module>.py         — 初始化与调度
tests/
requirements.txt
```

### java_springboot

```
{pkg}/
  domain/entity/{Struct}.java
  infrastructure/mapper/{Struct}Mapper.java + XML
  application/service/I{Struct}Service.java + impl/{Struct}ServiceImpl.java
  interface/controller/{Route}Controller.java
  interface/dto/request/{Struct}CreateRequest.java + UpdateRequest.java
  interface/dto/response/{Struct}Response.java
  interface/vo/{Struct}VO.java
  interface/assembler/{Struct}Assembler.java
  messaging/EventPublisher.java
src/main/resources/mapper/{Struct}Mapper.xml
src/main/resources/application.yml
```

### python_crawler

```
httpx/ (config, proxy_pool, rate_limiter, crawler, crawl_tasks, scheduler)
scrapy/ (items, pipelines, spiders/base)
playwright/ (config, crawler)
```

## [规划] 生产骨架扩展插槽

以下插槽属于后续生产级模板的保留能力：

- `{{ middleware_clients }}` — Redis / MQ / Search / Storage / Workflow 客户端包装
- `{{ health_checks }}` — 健康检查与 readiness / liveness 探针
- `{{ trace_context }}` — Trace ID / Span 上下文透传
- `{{ worker_entry }}` — 异步 worker / Temporal activity 入口

---

> 本文件最后更新: 2026-04-30 | 版本: v0.5.0

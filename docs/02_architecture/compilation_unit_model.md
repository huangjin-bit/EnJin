# 编译单元模型 (Compilation Unit Model)

> 本文档定义 EnJin 在真实生产仓库中的编译边界，解决 Java/Spring 电商主栈与 Python 监控 / Agent / 爬虫多目标共存的问题。

---

## 1. 核心定义

### 1.1 Workspace

`Workspace` 指整个仓库或 monorepo，是源码、文档、共享契约、多个服务编译单元的容器。

### 1.2 Compilation Unit

`Compilation Unit` 是 EnJin 的最小编译与交付边界，满足以下约束：

- 只能生成一个可部署产物
- 只能绑定一个目标技术栈
- 只能有一个 `application.ej` 作为该单元的技术栈入口
- 可以包含多个 `module` / `fn` / `struct` / `route`
- 可以包含多个 `@domain`，但所有 domain 都属于同一运行时与发布单元

### 1.3 Domain

`Domain` 是编译单元内部的限界上下文，用于上下文剪枝、跨域可见性治理与 Prompt 物理隔离。

### 1.4 Shared Contract

`Shared Contract` 指跨编译单元共享的契约层定义，例如：

- DTO / struct 字段签名
- gRPC / `.proto` 协议
- 事件 schema
- OpenAPI / JSON Schema

共享契约不是共享实现。任何编译单元都**禁止**直接透传其他编译单元的 `process`、数据库细节和内部补偿逻辑。

---

## 2. 核心原则

### 2.1 一个编译单元只对应一个目标栈

- 电商交易核心单元：`java_springboot`
- 监控单元：`python_fastapi`
- Agent 控制平面单元：`python_fastapi`
- 爬虫 / 采集单元：`python_fastapi`

**禁止**一个编译单元同时输出 Java 与 Python 两种主产物。

### 2.2 一个编译单元只对应一个部署责任

编译单元应与真实部署单元一致或近似一致，例如：

- `trade-core`
- `monitoring-center`
- `agent-control-plane`
- `crawler-hub`

**禁止**把“整个公司所有系统”塞进一个 `application.ej` 下编译。

### 2.3 Domain Bubble 发生在编译单元内部

Prompt Routing 时的边界顺序必须为：

`Compilation Unit -> Domain -> Module -> Fn`

先按编译单元切割，再按 domain 进一步裁剪，最后再抽取当前节点所需签名。

### 2.4 跨编译单元协作只通过契约

编译单元之间只能通过以下方式协作：

- HTTP / gRPC 接口契约
- MQ 事件契约
- 共享 schema 文档
- 生成后的 SDK / Client 包装

**禁止**跨编译单元共享 AST 内部节点或直接共享 `process` 上下文。

---

## 3. 推荐目录模型

```text
workspace/
├── shared/
│   ├── contracts/
│   │   ├── order_events/
│   │   ├── payment_api/
│   │   └── monitoring_schema/
│   └── docs/
├── services/
│   ├── trade-core/
│   │   ├── application.ej
│   │   ├── order.ej
│   │   ├── payment.ej
│   │   └── inventory.ej
│   ├── monitoring-center/
│   │   ├── application.ej
│   │   ├── alerts.ej
│   │   └── collectors.ej
│   ├── agent-control-plane/
│   │   ├── application.ej
│   │   ├── workflows.ej
│   │   └── tools.ej
│   └── crawler-hub/
│       ├── application.ej
│       ├── jobs.ej
│       └── pipelines.ej
└── docs/
```

---

## 4. 编译行为

### 4.1 编译入口

每次编译应面向单个编译单元执行，而不是面向整个 monorepo 一次性编译：

```text
enjinc build services/trade-core
enjinc build services/monitoring-center
enjinc build services/agent-control-plane
enjinc build services/crawler-hub
```

### 4.2 输出边界

每个编译单元独立生成：

- 目标语言源码
- 单元测试
- `enjin.lock`
- 中间件连接模板
- 产物级配置

锁文件、缓存、测试结果都不应在不同编译单元之间混用。

### 4.3 Prompt Routing 边界

为某个节点组装 Prompt 时：

- 只允许读取当前编译单元内的 AST
- 若存在 `@domain`，必须先裁剪到当前 domain
- 跨编译单元只能读取共享契约，不得读取兄弟单元源码

---

## 5. 与当前主栈分工的映射

### 5.1 Java / Spring 电商交易核心

推荐拆为一个或多个 Java 编译单元：

- `trade-core`
- `order-orchestrator`
- `promotion-engine`（若后续拆分）

默认目标：`java_springboot`

### 5.2 Python 智能监控

推荐独立为 Python 编译单元：

- `monitoring-center`
- `ops-rule-engine`

默认目标：`python_fastapi`

### 5.3 Python Agent

推荐独立为 Python 编译单元：

- `agent-control-plane`
- `agent-worker`（若后续拆分）

默认目标：`python_fastapi`

### 5.4 Python 爬虫

推荐独立为 Python 编译单元：

- `crawler-hub`
- `crawler-scheduler`

默认目标：`python_fastapi`

---

## 6. 编译期必须校验的规则

未来 `analyzer.py` 至少应校验：

- 一个编译单元只能存在一个 `application.ej`
- 一个编译单元只能声明一个 `target`
- 同一编译单元内不得混入不兼容的目标模板语义
- 跨编译单元引用只能来自共享契约，不得直接引用内部实现
- `route` 只能绑定当前编译单元内 `module` 导出的 action

---

## 7. 当前实现状态

### 已明确

- 编译单元应是最小部署边界
- Java/Spring 与 Python 工作负载必须物理分单元
- Prompt 不得跨编译单元读取内部 AST

### 尚未落地

- 编译器尚未内建多编译单元扫描与编译调度能力
- `application.ej` 仍按自由配置字典解析
- 共享契约目录尚未形成正式编译入口

---

> 本文件最后更新: 2026-03-24 | 版本: v0.1.0

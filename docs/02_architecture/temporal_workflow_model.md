# Temporal 工作流模型 (Temporal Workflow Model)

> 本文档定义 EnJin 在 Python Agent 控制平面中的 Temporal 承接方式，明确哪些语义由 EnJin 负责，哪些必须交给原生实现。

---

## 1. 适用范围

Temporal 在 EnJin 中默认用于：

- Agent 长时工作流
- Human-in-the-loop 审批流
- 多步工具调用编排
- 需要重试、超时、补偿与回放的异步控制流

Temporal **不默认用于**：

- Java 电商核心的短事务状态流
- 高频热点同步交易链路
- 需要极低延迟的同步 API 处理

电商交易核心的状态流默认仍优先使用 `Spring StateMachine`，而不是把所有流程都抬到 Temporal。

---

## 2. 核心原则

### 2.1 EnJin 只生成控制骨架

EnJin 负责生成：

- Workflow / Activity 契约
- Workflow 输入输出 DTO
- Signal / Query 接口外壳
- Retry / Timeout / Task Queue 配置骨架
- Worker 注册与可观测性骨架

EnJin 不负责生成：

- Planner / Reflector 智能内核
- 工具内部业务实现
- 多 Agent 协商策略
- 向量召回 / rerank 策略
- 长链推理优化逻辑

### 2.2 Workflow 属于编排层，而不是原子业务层

Temporal 的 Workflow 语义应落在 `module` 级编排层，而不是让 `fn` 直接承担长时工作流编排职责。

因此：

- `fn` 继续承担原子操作 / 协议包装 / tool adapter
- `module` 承担 Workflow 编排入口
- `route` 只暴露面向外部的触发与查询入口

### 2.3 工作流必须可审计、可重放、可限流

所有 Workflow 设计都必须显式考虑：

- 重试策略
- 超时策略
- 幂等键
- Trace / Audit
- 回放安全性

---

## 3. 推荐语义映射

### 3.1 Module 级引擎入口

建议以 `@engine(type="workflow", framework="temporal")` 作用于 `module`：

```ej
@engine(type="workflow", framework="temporal")
module AgentSessionWorkflow {
    use plan_task
    use call_tool
    use summarize_result
}
```

### 3.2 Fn 级 Activity / Tool 契约

原子步骤仍由 `fn` 承担：

```ej
@api_contract
fn call_tool(tool_name: String, input: String) -> String {
    process { "调用工具契约，不在此层实现长工作流编排" }
}
```

### 3.3 Route 级触发入口

`route` 只暴露 workflow trigger / query / signal 外层网关：

```ej
route AgentGateway {
    use AgentSessionApp

    POST "/sessions" -> start_session
    GET "/sessions/{id}" -> get_session_status
}
```

---

## 4. Workflow 合约字段

未来编译器应支持的 Workflow 元信息至少包括：

- `workflow_name`
- `task_queue`
- `execution_timeout`
- `run_timeout`
- `retry_policy`
- `idempotency_key`
- `signals`
- `queries`
- `search_attributes`

这些字段可以最终落入：

- `ModuleDef.engine`
- `ApplicationConfig.workflow`
- 生成后的 Temporal worker / workflow 配置文件

---

## 5. Retry / Timeout 规范

### 5.1 默认要求

- 每个 Workflow 必须有超时边界
- 每个 Activity 必须有重试策略
- 外部 side effect 必须有幂等保护

### 5.2 不应默认无限重试

编译器不得生成无限重试策略。默认应要求：

- 最大重试次数
- backoff 策略
- 不可重试异常列表

### 5.3 人工介入节点

对于需要人工审批 / 人工确认的步骤，应通过：

- Signal
- Query
- Approval timeout
- Escalation hook

来建模，而不是靠 `sleep` 或轮询硬编码。

---

## 6. 可观测性要求

Temporal 工作流骨架应默认集成：

- Trace ID 透传
- Workflow / Run ID 日志上下文
- Activity 失败埋点
- 重试次数监控
- Workflow 卡死 / 超时告警入口

---

## 7. 编译器应生成的内容

对于 Agent 项目中的 Temporal 语义，编译器应生成：

- Workflow 接口与实现骨架
- Activity 接口与注册骨架
- Worker 启动骨架
- Signal / Query 注册外壳
- 配置读取与 Task Queue 装配
- 回放安全提示与日志包装

---

## 8. 编译器不得生成的内容

- 多 Agent 自主协商策略
- Planner 自反思逻辑
- 复杂工具选择策略
- 模型路由优化器
- 向量检索与 rerank 内核

这些能力可以通过 `native`、`@human_maintained` 或外部子项目承接。

---

## 9. 与 Queue / Domain 的关系

- Workflow 触发消息可以进入 MQ，但 MQ 只是触发媒介，不替代 Temporal 的状态语义
- Domain Bubble 仍然生效，跨域只允许看到导出契约，不允许透传其他 domain 的内部 workflow 实现
- Prompt Routing 时，只允许暴露 workflow / activity 签名、DTO、超时 / 重试边界

---

## 10. 当前实现状态

### 已明确

- Agent 长时工作流默认使用 Temporal
- Temporal 语义属于模块级编排层
- EnJin 只负责控制骨架，不生成智能内核

### 尚未落地

- 解析器尚未支持 module 级 `@engine`
- AST 尚未具备 `ModuleDef.engine` 字段
- Python 目标模板尚未生成 Temporal worker / workflow 骨架

---

> 本文件最后更新: 2026-03-24 | 版本: v0.1.0

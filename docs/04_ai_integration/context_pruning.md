# 上下文剪枝算法 (Context Pruning)

> 本文档记录 EnJin 编译器如何最小化发送给 LLM 的 Token 数量。

---

## 核心原则

**永远不要把整个项目的 AST 塞给 LLM。** 只提取与当前节点强相关的最小上下文。
补充原则：
- `@domain` 是上下文隔离的第一边界，Prompt 组装必须先按领域裁剪。
- 跨域只允许暴露显式导出的契约签名，禁止透传 `process`、数据库细节、缓存策略与内部补偿逻辑。
- `@locked`、`native`、`@human_maintained` 节点默认不进入 LLM Prompt。

## 剪枝策略 (Phase 3 实现)

### 策略 1: 签名提取

对于一个 `fn` 节点的 process 生成，只需向 LLM 提供：
- 当前函数的签名（名称、参数、返回类型）
- 依赖的 struct 定义（只要字段名和类型，不要注解细节）
- guard 中引用的字段约束
若当前函数位于某个 `@domain` 模块中，还需额外满足：
- 仅传当前 domain 内的 struct 字段签名
- 跨域依赖仅传 `@api_contract` 或 module export 暴露出的签名
- 严禁把跨域函数的 `process`、`expect` 与数据库实现细节传入 Prompt

### 策略 2: 深度限制

依赖链最多追溯 2 层：
- fn → 直接依赖的 struct（第 1 层）
- struct → 外键引用的其他 struct 的签名（第 2 层，仅签名）
对高成本场景补充限制：
- 电商交易核心：优先传 action 契约、DTO、错误语义，不传中间件调优细节
- Python 监控：优先传规则定义、告警结构、通知契约，不传采集核心循环
- Agent / Temporal：优先传 workflow / activity 签名、工具契约、超时与重试边界，不传长链推理中间状态

### 策略 3: 缓存命中跳过

已 `@locked` 的节点在组装上下文时完全跳过，不计入 Token。

### 策略 4: Token 预算硬限制

- 每个节点的 Prompt 必须记录 input_tokens / output_tokens
- 超出预算时优先裁掉跨域签名，再裁掉低优先级 struct
- 禁止为了“提高成功率”而退化为整项目 AST 透传

## 度量指标 (待实现)

- 每次 AI 调用的 input_tokens / output_tokens 记录
- 平均每个 process 节点的上下文 Token 数
- 缓存命中率
- 跨域裁剪命中率
- 被 `@locked` / `native` 跳过的节点数量

---
> 本文件最后更新: 2026-03-24 | 版本: v0.2.0

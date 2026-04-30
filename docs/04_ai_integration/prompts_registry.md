# Prompt 档案库 (Prompts Registry)

> **维护协议：** 每次修改发送给 LLM 的 Prompt 结构时，必须在本文件追加一条变更记录，
> 包含：版本号、修改日期、diff 对比、修改理由、预期行为变化。

---

## 当前状态

Phase 3 实现。本文件为骨架，待 PromptRouter 开发时填充。
在当前架构下，任何 Prompt 设计都必须先满足以下前置约束：
- 只能针对单个 `Compilation Unit` 组装 Prompt
- 若存在 `@domain`，必须先按 domain 做物理裁剪
- 跨域只允许暴露导出契约与签名，不允许透传 `process`
- `@locked`、`native`、`@human_maintained` 节点默认不进入 Prompt
- Java/Spring 与 Python 编译单元的 Prompt 模板不得混用

## 模板结构预览

每个 Prompt 条目的记录格式：

```markdown
### PROMPT-001: fn/process 业务逻辑生成

- **版本:** v1.0
- **修改日期:** YYYY-MM-DD
- **触发条件:** FnDef 节点含有 process 块，且 is_locked=false
- **编译单元边界:** `services/trade-core` / `services/agent-control-plane` / ...
- **Domain 边界:** `order` / `monitoring` / `agent` / ...
- **System Prompt:**
  (完整内容)
- **User Prompt 模板:**
  (完整内容，含 {{ 变量 }} 插值)
- **预期输出格式:**
  (纯代码，无 markdown 包裹)
- **变更历史:**
  | 版本 | 日期 | 变更内容 | 理由 |
  |---|---|---|---|
```

## 首批建议登记的 Prompt 条目

- `PROMPT-001`：`fn/process` 的 Python 控制面逻辑生成
- `PROMPT-002`：`fn/process` 的 Java/Spring 交易逻辑生成
- `PROMPT-003`：Module 级 `@engine` 声明的工作流 / 状态流配置生成
- `PROMPT-004`：Queue Contract 适配器骨架生成

---
> 本文件最后更新: 2026-03-24 | 版本: v0.2.0 (骨架)

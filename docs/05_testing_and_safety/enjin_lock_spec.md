# enjin.lock 确定性构建规范

> 本文档定义 `enjin.lock` 文件的结构与 Hash 生成规则。

---

## 目的

`enjin.lock` 确保 CI/CD 环境中编译产物 100% 可复现。
在锁定状态下，编译器完全不调用 LLM，只从 lock 文件中读取已缓存的生成代码。

补充原则：
- `enjin.lock` 必须以**编译单元**为边界独立生成，不能跨编译单元共享缓存。
- Java 电商主栈与 Python 监控 / Agent / 爬虫栈必须拥有各自独立的 lock 文件。
- lock 文件不仅锁定 AI 产物，也锁定其所依赖的目标栈与关键语义元信息。

## 文件格式 (预案)

```json
{
  "version": "1.0",
  "generated_at": "2026-03-16T12:00:00Z",
  "compiler_version": "0.1.0",
  "compilation_unit_id": "services/trade-core",
  "target": "java_springboot",
  "nodes": {
    "<ast_node_hash>": {
      "node_type": "fn",
      "name": "register_user",
      "intent_hash": "sha256:abc123...",
      "generated_code": "public User registerUser(...) { ... }",
      "generated_at": "2026-03-16T11:30:00Z",
      "model_used": "gpt-4",
      "tokens_consumed": { "input": 450, "output": 320 }
    }
  }
}
```

## Hash 计算规则

AST Node Hash = SHA-256 of:
1. 节点类型 (node_type)
2. 编译单元标识 (compilation_unit_id)
3. 目标栈 (target)
4. 函数 / 模块签名 (名称 + 参数类型 + 返回类型 或导出 action)
5. guard 规则列表
6. process 意图文本
7. 依赖的 struct 的字段签名
8. 关键规划态元信息（如 module export / domain / engine / data_plane）在正式落地后应纳入哈希

**不参与 Hash 计算的：** 注释、空格、expect 断言（测试不影响业务代码缓存）。

## 多目标栈说明

- 若某编译单元目标为 `java_springboot`，其 lock 文件不应缓存 Python 业务产物
- 若某编译单元目标为 `python_fastapi`，其 lock 文件不应缓存 Java 业务产物
- 同一 monorepo 可存在多个 lock 文件，但每个 lock 文件只服务一个编译单元

---
> 本文件最后更新: 2026-03-24 | 版本: v0.2.0

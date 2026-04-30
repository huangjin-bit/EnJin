# 人类-AI 协同机制 (Human-AI Collaboration)

> 本文档说明 EnJin 中人类代码如何与 AI 生成代码共存。

---

## 三种逃生舱机制

### 1. `native` — 原生代码注入

当 AI 无法生成满足需求的代码时，开发者可直接注入目标语言代码：

```ej
fn custom_hash(data: String) -> String {
    native python {
        import hashlib
        return hashlib.sha256(data.encode()).hexdigest()
    }
}
```

**编译器行为：** 原封不动地将 `native` 块中的内容写入目标文件。AI 严禁触碰。

### 2. `@locked` — 缓存锁定

```ej
@locked
fn get_user_by_id(id: Int) -> User {
    process { "根据 ID 查询用户" }
}
```

**编译器行为：** 直接从 `enjin.lock` 读取上次生成的代码，完全跳过 LLM 调用。
补充约束：
- `@locked` 的缓存命中范围以**编译单元**为边界，禁止跨编译单元复用 lock 产物。
- 被 `@locked` 标记的节点在 Prompt Routing 时默认完全跳过，不进入上下文。

### 3. `@human_maintained` — 人类全权维护

```ej
@human_maintained
fn legacy_auth(token: String) -> Bool {
    // 此函数由人类在目标代码中手动维护
    // 编译器不生成任何代码
}
```

**编译器行为：** 生成函数签名骨架但留空函数体，由人类在产物目录中手动填写。
补充约束：
- `@human_maintained` 节点默认不进入 LLM Prompt。
- 人工维护代码应局限在当前编译单元内，不作为跨域或跨编译单元的实现透传来源。

---

## 代码继承与覆盖优先级

当同一函数同时存在多种代码来源时，优先级如下（从高到低）：

1. `native` 原生代码块 — 最高优先级
2. `@human_maintained` 人工代码 — 次高
3. `@locked` 缓存代码 — 第三
4. AI 动态生成代码 — 最低优先级

---

> 本文件最后更新: 2026-03-24 | 版本: v0.2.0

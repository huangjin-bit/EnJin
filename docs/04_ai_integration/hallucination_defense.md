# AI 幻觉防御机制 (Hallucination Defense)

> 本文档说明 EnJin 如何利用语言层面的约束来防御 AI 生成的幻觉代码。

---

## 防御层次

### 第 0 层: 编译单元与 Domain Bubble 物理隔离

在进入 LLM 之前，编译器必须先完成：

- 编译单元边界裁剪
- `@domain` 领域边界裁剪
- 跨域签名导出过滤

这意味着 AI 从物理上**看不到**其他编译单元或其他 domain 的 `process`、数据库细节与内部补偿逻辑。

### 第 1 层: guard 强转断言

所有 guard 规则被编译为函数最开头的硬编码断言。
即使 AI 在 process 中生成了跳过校验的代码，guard 断言也会在其之前执行。

```python
# 由 guard 确定性生成（非 AI），位于函数最开头
def register_user(username: str, email: str, password: str) -> User:
    if not (len(username) > 0):
        raise ValueError("用户名不能为空")
    if not ("@" in email):
        raise ValueError("邮箱格式不合法")
    # --- AI 生成的代码从这里开始 ---
    ...
```

### 第 2 层: expect 逻辑守恒审计

每次 AI 生成新代码后，必须通过 expect 自动生成的单元测试。
若测试失败，编译器熔断并拒绝此次生成结果。
补充说明：当前 `expect` 在 AST 中先以 `raw` 文本保存，测试生成阶段再做结构化拆解并映射到 pytest / JUnit。

### 第 3 层: AST 编辑距离审计

当 LLM 模型升级（如 GPT-4 → GPT-5）导致生成的代码结构发生重大变化时，
编译器计算新旧代码的 AST 编辑距离。若超过阈值，触发人工审核。

### 第 4 层: 模板物理隔离

AI 生成的代码被严格限定在 Jinja2 模板的 `{{ slot }}` 插槽中。
基础设施层代码完全由人工审计的模板硬编码生成，AI 无法触及。

---

> 本文件最后更新: 2026-03-24 | 版本: v0.2.0

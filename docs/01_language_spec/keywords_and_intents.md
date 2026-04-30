# 关键字与意图语义 (Keywords & Intents)

> **维护协议：** 新增意图关键字前，必须先在此文档定义其语义边界，审核后方可修改 grammar.lark。

---

## 1. 三段意图体 (Intent Triplet)

EnJin 的 `fn` 函数体使用三段意图结构来精确控制人类、编译器、AI 的职责边界。

### 1.1 guard — 防御性校验

**语义：** 声明函数执行的前置条件。编译器必须将其翻译为目标函数**最开头**的断言或异常抛出。

**语法：**
```ej
guard {
    <布尔表达式> : "<错误信息>"
    ...
}
```

**编译行为：**
- Python 目标：生成 `if not (expr): raise ValueError("msg")` 
- Java 目标：生成 `if (!(expr)) throw new IllegalArgumentException("msg");`
- guard 块中的每一条规则都是**独立的**，不存在短路逻辑
- guard 生成的代码**必须**位于函数体的第一行，在任何业务逻辑之前

**支持的表达式：**
| 表达式 | 含义 | 示例 |
|---|---|---|
| `field.length > N` | 字符串/列表长度校验 | `username.length > 0` |
| `field.contains(X)` | 包含校验 | `email.contains("@")` |
| `field > N` / `field < N` | 数值范围校验 | `age > 0` |
| `not exists(Model, field=val)` | 数据库唯一性校验 | `not exists(User, email=email)` |
| `field != null` | 非空校验 | `username != null` |
| `field.matches(regex)` | 正则匹配 | `phone.matches("^1[3-9]\\d{9}$")` |

### 1.2 process — 核心业务意图

**语义：** 用自然语言描述该函数的业务逻辑。这是 AI 唯一的代码生成入口。

**语法：**
```ej
process {
    "自然语言意图描述，可以是多行文本。
     AI 根据此描述生成目标语言的具体实现代码。"
}
```

**编译行为：**
1. 编译器提取 process 中的意图文本
2. 结合函数签名、参数类型、依赖的 struct 定义，组装 Prompt
3. 调用 LLM 生成目标语言代码
4. 将生成的代码注入 Jinja2 模板的受控插槽（如 `{{ process_code }}`）

**约束：**
- process 块中**只能包含字符串字面量**，不能包含任何代码
- 一个 fn 中最多一个 process 块
- `@locked` 标注的函数，其 process 直接读取缓存，不调用 AI

### 1.3 expect — 测试断言

**语义：** 声明函数的预期行为，编译器将自动生成对应的单元测试文件。

**语法：**
```ej
expect {
    函数调用.属性 == 预期值
    函数调用.throws("预期异常信息")
    ...
}
```

**编译行为：**
- Python 目标：生成独立的 `test_<fn_name>.py` 文件中的 pytest 用例
- Java 目标：生成独立的 `<FnName>Test.java` 文件中的 JUnit 用例
- 解析阶段先将断言保存为 `ExpectAssertion.raw`，测试生成阶段再做结构化拆解
- expect 中的断言**不会**出现在业务代码中，严格物理隔离

**支持的断言类型：**
| 断言 | 含义 | 示例 |
|---|---|---|
| `.属性 == 值` | 属性等值断言 | `register("alice", "a@t.com", "pass123").username == "alice"` |
| `.throws("msg")` | 异常断言 | `register("", "bad", "12345678").throws("用户名不能为空")` |
| `.status == code` | HTTP 状态码断言 | `get_user(999).status == 404` |
| `.count == N` | 结果数量断言 | `list_users().count == 5` |

---

## 2. 逃生舱关键字

### 2.1 native — 原生代码注入

**语义：** 绕过 AI 生成，直接将目标语言的原生代码注入到编译产物中。

```ej
native <target_lang> {
    // 原生代码，原封不动注入
}
```

- 支持的目标：`python`, `java`
- 编译器**绝对禁止**修改 native 块中的任何内容
- 一个 fn 可包含多个 native 块（按目标语言分别注入）

### 2.2 @locked — 缓存锁定

**语义：** 标注的节点跳过 AI 生成，直接使用 `enjin.lock` 中的缓存代码。

**触发条件：** AST Hash 未变化时自动锁定；或人类手动标注 `@locked` 强制锁定。

### 2.3 @human_maintained — 人类维护

**语义：** AI 完全放弃该模块/函数的生成权，由人类全权维护。

---

> 本文件最后更新: 2026-03-24 | 版本: v0.2.0

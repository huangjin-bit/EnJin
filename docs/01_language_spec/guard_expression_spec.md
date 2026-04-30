# Guard 表达式编译规范 (Guard Expression Compilation Spec)

> 本文档定义 `.ej` 中 `guard` 块内表达式如何被编译为目标语言的断言代码。

---

## 1. 表达式分类

Guard 表达式分为两类，编译器必须区分对待：

### 1.1 纯内存断言 (In-Memory Assertion)

不涉及外部 IO，可直接翻译为目标语言的条件判断：

| 表达式 | 语义 | Python 产物 | Java 产物 |
|---|---|---|---|
| `field.length > N` | 字符串/列表长度 | `if not (len(field) > N):` | `if (!(field.length() > N))` |
| `field.length < N` | 字符串/列表长度 | `if not (len(field) < N):` | `if (!(field.length() < N))` |
| `field.contains(X)` | 包含校验 | `if not (X in field):` | `if (!field.contains(X))` |
| `field > N` / `field < N` | 数值范围 | `if not (field > N):` | `if (!(field > N))` |
| `field != null` | 非空校验 | `if field is None:` | `if (field == null)` |
| `field.matches(regex)` | 正则匹配 | `if not re.match(regex, field):` | `if (!field.matches(regex))` |
| `field >= N` / `field <= N` | 数值边界 | `if not (field >= N):` | `if (!(field >= N))` |

**编译规则：**

- 所有纯内存断言生成的代码必须位于函数体**最开头**
- 每条规则独立判断，不存在短路逻辑
- 失败时抛出异常，携带 guard 中声明的错误消息

### 1.2 数据库查询断言 (Query Assertion)

需要发起数据库查询，编译逻辑更复杂：

| 表达式 | 语义 | Python 产物 | Java 产物 |
|---|---|---|---|
| `not exists(Model, field=val)` | 唯一性校验 | `if db.query(Model).filter_by(field=val).first() is not None:` | `if (repository.findByField(val).isPresent())` |
| `exists(Model, field=val)` | 存在性校验 | `if db.query(Model).filter_by(field=val).first() is None:` | `if (repository.findByField(val).isEmpty())` |

**编译规则：**

- 数据库查询断言必须在纯内存断言**之后**执行（先做廉价校验）
- 编译器需要识别 `exists` / `not exists` 关键字
- `Model` 必须解析为当前编译单元内已声明的 `struct`
- `field=val` 中的 `field` 必须为该 struct 的合法字段名
- `val` 必须解析为当前函数的参数名或字面量

---

## 2. 属性映射规则

`.ej` 的 guard 表达式使用统一语法，编译器需按目标栈翻译：

| `.ej` 属性 | Python 映射 | Java 映射 |
|---|---|---|
| `field.length` | `len(field)` | `field.length()` (String) / `field.size()` (Collection) |
| `field.contains(x)` | `x in field` | `field.contains(x)` |
| `field.matches(regex)` | `re.match(regex, field)` | `field.matches(regex)` |

---

## 3. 异常映射

Guard 断言失败时的异常类型：

| 场景 | Python 异常 | Java 异常 |
|---|---|---|
| 纯内存断言失败 | `ValueError(message)` | `IllegalArgumentException(message)` |
| 数据库唯一性冲突 | `ConflictError(message)` | `DuplicateResourceException(message)` |
| 数据库存在性失败 | `NotFoundError(message)` | `ResourceNotFoundException(message)` |

具体异常类型应由 EnJin 的错误类型模型统一定义，详见 `error_model.md`。

---

## 4. 生成代码的排列顺序

```
fn foo(x: String, y: Int) -> Result {
    guard {
        x.length > 0 : "x 不能为空"        // 纯内存 #1
        y > 0 : "y 必须为正"                // 纯内存 #2
        not exists(User, email=x) : "已存在" // 数据库查询 #1
    }
    process { ... }
}
```

生成的 Python 代码：

```python
def foo(x: str, y: int) -> Result:
    # --- Guard: 纯内存断言（最先执行）---
    if not (len(x) > 0):
        raise ValueError("x 不能为空")
    if not (y > 0):
        raise ValueError("y 必须为正")
    # --- Guard: 数据库查询断言 ---
    if db.query(User).filter_by(email=x).first() is not None:
        raise ConflictError("已存在")
    # --- AI 生成的业务逻辑 ---
    ...
```

---

## 5. 当前实现状态

### 已实现

- `grammar.lark` 将 guard 表达式保存为 raw text
- AST 的 `GuardRule` 包含 `expr` 和 `message`

### 待实现

- 编译器尚未将 guard 表达式拆解为结构化 AST
- guard → 目标代码的翻译器尚未实现
- `exists` / `not exists` 的数据库查询生成尚未实现
- 异常类型映射待错误模型文档确定后落地

---

> 本文件最后更新: 2026-03-24 | 版本: v0.1.0

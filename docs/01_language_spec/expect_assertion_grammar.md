# Expect 断言解析规范 (Expect Assertion Grammar)

> 本文档定义 `expect` 块中断言表达式的解析规则，供 `test_generator.py` 在测试生成阶段使用。

---

## 1. 两阶段流程回顾

1. **解析阶段**：`parser.py` 将 expect 断言保存为 `ExpectAssertion.raw`（原始文本）
2. **测试生成阶段**：`test_generator.py` 将 `raw` 解析为结构化断言并映射到 pytest / JUnit

本文档定义第 2 阶段的解析规则。

---

## 2. 断言表达式 EBNF

```ebnf
assertion       := call_expr "." assertion_method
call_expr       := IDENTIFIER "(" arg_list? ")"
arg_list        := arg ("," arg)*
arg              := STRING_LITERAL | NUMBER_LITERAL | IDENTIFIER
assertion_method := eq_assertion | throws_assertion | status_assertion | count_assertion

eq_assertion     := IDENTIFIER "==" literal
throws_assertion := "throws" "(" STRING_LITERAL ")"
status_assertion := "status" "==" NUMBER_LITERAL
count_assertion  := "count" "==" NUMBER_LITERAL

literal          := STRING_LITERAL | NUMBER_LITERAL | "true" | "false" | "null"

STRING_LITERAL   := '"' [^"]* '"'
NUMBER_LITERAL   := [0-9]+
IDENTIFIER       := [a-zA-Z_][a-zA-Z0-9_]*
```

---

## 3. 断言类型与解析规则

### 3.1 属性等值断言 (eq)

**模式：** `call_expr.property == value`

```
register_user("alice", "a@t.com", "pass123").username == "alice"
```

**解析结果：**
```json
{
  "type": "eq",
  "call": { "fn": "register_user", "args": ["alice", "a@t.com", "pass123"] },
  "field": "username",
  "expected": "alice"
}
```

### 3.2 异常断言 (throws)

**模式：** `call_expr.throws("message")`

```
register_user("", "a@b.com", "12345678").throws("用户名不能为空")
```

**解析结果：**
```json
{
  "type": "throws",
  "call": { "fn": "register_user", "args": ["", "a@b.com", "12345678"] },
  "expected_message": "用户名不能为空"
}
```

### 3.3 HTTP 状态码断言 (status)

**模式：** `call_expr.status == code`

```
get_user(999).status == 404
```

**解析结果：**
```json
{
  "type": "status",
  "call": { "fn": "get_user", "args": [999] },
  "expected_status": 404
}
```

### 3.4 结果数量断言 (count)

**模式：** `call_expr.count == n`

```
list_users().count == 5
```

**解析结果：**
```json
{
  "type": "count",
  "call": { "fn": "list_users", "args": [] },
  "expected_count": 5
}
```

---

## 4. 目标代码映射

| 断言类型 | Python (pytest) | Java (JUnit) |
|---|---|---|
| `eq` | `assert result.field == value` | `assertEquals(value, result.getField())` |
| `throws` | `with pytest.raises(ExcType, match="msg"):` | `assertThrows(ExcType.class, () -> ...)` |
| `status` | `assert response.status_code == code` | `assertEquals(code, response.getStatusCode())` |
| `count` | `assert len(result) == n` | `assertEquals(n, result.size())` |

`throws` 断言的异常类型推断规则详见 `error_model.md` 第 5 节。

---

## 5. 解析容错

- 若 raw 文本无法匹配任何已知模式，`test_generator.py` 应发出 `UnparsableExpectWarning` 并跳过该条断言，不应导致整体编译失败
- 后续可考虑支持更复杂的断言模式（链式调用、嵌套属性等），但第一阶段保持上述 4 种即可

---

## 6. 当前实现状态

### 已明确

- 4 种核心断言类型及其 EBNF
- 结构化 JSON 中间表示
- 目标代码映射表

### 待实现

- `test_generator.py` 中的 raw → structured 解析器
- 异常类型推断与 `error_model.md` 的联动
- 链式断言扩展

---

> 本文件最后更新: 2026-03-24 | 版本: v0.1.0

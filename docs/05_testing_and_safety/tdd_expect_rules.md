# TDD: expect 意图到测试代码的转换规则

> 本文档定义 `.ej` 中 `expect` 块如何自动转化为目标语言的单元测试。
> 当前 `parser.py` 仍将 `expect` 断言保存为 `raw` 文本；结构化拆解属于测试生成阶段职责，而不是解析阶段职责。

## 转换规则总览

转换流程分为两段：

1. **解析阶段：** `expect` 原样进入 AST，保存为 `ExpectAssertion.raw`
2. **测试生成阶段：** `test_generator.py` 再把 `raw` 拆解成结构化断言类型（如 `eq`、`throws`、`status`、`count`）

| expect 断言类型 | Python (pytest) 产物 | Java (JUnit) 产物 |
|---|---|---|
| `.field == value` | `assert result.field == value` | `assertEquals(value, result.getField())` |
| `.throws("msg")` | `with pytest.raises(ValueError, match="msg")` | `assertThrows(IllegalArgumentException.class, ...)` |
| `.status == code` | `assert response.status_code == code` | `assertEquals(code, response.getStatusCode())` |
| `.count == n` | `assert len(result) == n` | `assertEquals(n, result.size())` |

## 产物文件命名

- Python: `tests/test_<fn_name>.py`
- Java: `src/test/java/<package>/<FnName>Test.java`

## 示例

### .ej 源码
```ej
expect {
    register_user("alice", "alice@test.com", "password123").username == "alice"
    register_user("", "bad", "12345678").throws("用户名不能为空")
}
```

### 当前 AST 中的形态
```json
[
  { "raw": "register_user(\"alice\", \"alice@test.com\", \"password123\").username == \"alice\"" },
  { "raw": "register_user(\"\", \"bad\", \"12345678\").throws(\"用户名不能为空\")" }
]
```

### 生成的 pytest 代码
```python
def test_register_user_returns_correct_username():
    result = register_user("alice", "alice@test.com", "password123")
    assert result.username == "alice"

def test_register_user_rejects_empty_username():
    with pytest.raises(ValueError, match="用户名不能为空"):
        register_user("", "bad", "12345678")
```

## 目标栈建议

- Java / JUnit：优先用于电商交易核心
- Python / pytest：优先用于监控、Agent、爬虫与 Python 控制面项目

## 生成器职责边界

`test_generator.py` 至少应负责：

- 解析 `ExpectAssertion.raw`
- 识别断言类型
- 将断言映射到 pytest / JUnit
- 处理 `route -> module action` 的调用语义，而不是继续假定 `route` 直接绑定裸 `fn`

---
> 本文件最后更新: 2026-03-24 | 版本: v0.2.0

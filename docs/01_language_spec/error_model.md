# EnJin 错误与异常类型模型 (Error Model)

> 本文档定义 EnJin 编译产物中的异常类型层次，统一 guard 断言、业务异常与 HTTP 状态码的映射关系。

---

## 1. 设计目标

- 为 `guard` 断言失败提供明确的异常类型映射
- 为 `expect` 的 `.throws("msg")` 断言提供类型锚定
- 为 `route` 层提供异常到 HTTP 状态码的自动映射
- 保持 Java 与 Python 异常体系的对称性

---

## 2. 异常类型层次

EnJin 定义以下标准异常语义，编译器按目标栈生成对应异常类：

| EnJin 语义异常 | 触发场景 | HTTP 状态码 | Python 映射 | Java 映射 |
|---|---|---|---|---|
| `ValidationError` | guard 纯内存断言失败 | 400 | `ValueError` | `IllegalArgumentException` |
| `ConflictError` | guard `not exists()` 唯一性冲突 | 409 | `ConflictError` (自定义) | `DuplicateResourceException` (自定义) |
| `NotFoundError` | guard `exists()` 存在性失败 / 业务查询无结果 | 404 | `NotFoundError` (自定义) | `ResourceNotFoundException` (自定义) |
| `AuthenticationError` | `@auth` 认证失败 | 401 | `AuthenticationError` | `AuthenticationException` |
| `ForbiddenError` | 权限不足 | 403 | `ForbiddenError` | `ForbiddenException` |
| `BusinessError` | process 生成的业务逻辑中的通用业务异常 | 422 | `BusinessError` (自定义) | `BusinessException` (自定义) |

---

## 3. Guard → 异常映射规则

编译器根据 guard 表达式类型自动选择异常：

| Guard 表达式类型 | 映射异常 |
|---|---|
| 纯内存断言（`length`、`contains`、`matches`、比较运算） | `ValidationError` |
| `not exists(Model, ...)` | `ConflictError` |
| `exists(Model, ...)` | `NotFoundError` |

---

## 4. Route 层异常捕获

编译器在 `route` 层应自动生成全局异常处理器，将 EnJin 语义异常映射为 HTTP 响应：

### Python (FastAPI)

```python
@app.exception_handler(ValueError)
async def validation_error_handler(request, exc):
    return JSONResponse(status_code=400, content={"error": str(exc)})

@app.exception_handler(ConflictError)
async def conflict_error_handler(request, exc):
    return JSONResponse(status_code=409, content={"error": str(exc)})

@app.exception_handler(NotFoundError)
async def not_found_error_handler(request, exc):
    return JSONResponse(status_code=404, content={"error": str(exc)})
```

### Java (Spring Boot)

```java
@RestControllerAdvice
public class GlobalExceptionHandler {
    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ErrorResponse> handleValidation(IllegalArgumentException e) {
        return ResponseEntity.badRequest().body(new ErrorResponse(e.getMessage()));
    }

    @ExceptionHandler(DuplicateResourceException.class)
    public ResponseEntity<ErrorResponse> handleConflict(DuplicateResourceException e) {
        return ResponseEntity.status(409).body(new ErrorResponse(e.getMessage()));
    }

    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<ErrorResponse> handleNotFound(ResourceNotFoundException e) {
        return ResponseEntity.status(404).body(new ErrorResponse(e.getMessage()));
    }
}
```

---

## 5. Expect 中的 `.throws()` 锚定

`expect` 断言中的 `.throws("msg")` 按以下规则匹配异常：

- 匹配基于**错误消息文本**，而不是异常类型
- 测试生成器根据消息文本在 guard 中的出现位置，推断预期异常类型
- 若消息未出现在 guard 中，默认匹配 `BusinessError`

示例：

```ej
guard {
    username.length > 0 : "用户名不能为空"  // → ValidationError
    not exists(User, email=email) : "邮箱已被注册"  // → ConflictError
}

expect {
    register("", "a@b.com").throws("用户名不能为空")  // pytest: raises(ValueError)
    register("bob", "existing@t.com").throws("邮箱已被注册")  // pytest: raises(ConflictError)
}
```

---

## 6. 自定义异常基类生成

编译器应在基建模板中生成统一的异常基类：

### Python

```python
# exceptions.py (由模板确定性生成)
class AppError(Exception):
    """EnJin 应用异常基类"""
    pass

class ConflictError(AppError):
    pass

class NotFoundError(AppError):
    pass

class BusinessError(AppError):
    pass

class AuthenticationError(AppError):
    pass

class ForbiddenError(AppError):
    pass
```

### Java

```java
// exceptions/ 目录（由模板确定性生成）
public abstract class AppException extends RuntimeException { ... }
public class DuplicateResourceException extends AppException { ... }
public class ResourceNotFoundException extends AppException { ... }
public class BusinessException extends AppException { ... }
public class AuthenticationException extends AppException { ... }
public class ForbiddenException extends AppException { ... }
```

---

## 7. 与模板引擎的关系

异常基类文件属于**基建模板**，100% 确定性生成，不经过 AI：

- Python: `exceptions.py.jinja` → `exceptions.py`
- Java: `exceptions/*.java.jinja` → `exceptions/*.java`

全局异常处理器同样属于基建模板。

---

## 8. 当前实现状态

### 已明确

- Guard 异常映射规则
- 异常到 HTTP 状态码的对应关系
- 异常基类属于基建模板

### 待实现

- 异常基类模板文件
- 全局异常处理器模板
- Guard 编译器的异常类型选择逻辑
- `test_generator.py` 的 `.throws()` 类型推断

---

> 本文件最后更新: 2026-03-24 | 版本: v0.1.0

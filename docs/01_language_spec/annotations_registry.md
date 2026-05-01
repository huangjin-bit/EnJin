# 注解注册表 (Annotations Registry)

> **维护协议：** 新增任何 @注解 前，必须先在此文档注册其签名、触发条件与目标行为。
> 未在此处注册的注解，编译器应拒绝解析并报错。
> 带有 **[规划]** 标记的注解表示名称与目标语义已经保留，但仍需等待 parser / analyzer / codegen 配套落地。

---

## 注解语法格式

```
@name                          // 标记注解（无参数）
@name("positional_arg")       // 位置参数注解
@name(key="value")            // 具名参数注解
@name("pos", key="value")    // 混合参数注解
```

---

## Model 层注解 (用于 struct 和字段)

### struct 级注解

| 注解 | 参数 | 目标行为 | 示例 |
|---|---|---|---|
| `@table` | `(name: String)` | 指定数据库表名。若省略则使用 struct 名的 snake_case | `@table("users")` |

### 字段级注解

| 注解 | 参数 | 目标行为 | 示例 |
|---|---|---|---|
| `@primary` | 无 | 标记为主键 | `id: Int @primary` |
| `@auto_increment` | 无 | 主键自增 | `id: Int @primary @auto_increment` |
| `@unique` | 无 | 唯一约束 | `email: String @unique` |
| `@max_length` | `(n: Int)` | 字符串最大长度约束 | `name: String @max_length(50)` |
| `@min_length` | `(n: Int)` | 字符串最小长度约束 | `code: String @min_length(6)` |
| `@default` | `(value: Any)` | 字段默认值。`"now()"` 为特殊时间戳函数 | `@default("active")` |
| `@nullable` | 无 | 允许 NULL 值 | `bio: String @nullable` |
| `@index` | 无 | 创建数据库索引 | `username: String @index` |
| `@foreign_key` | `(ref: String)` | 外键引用，格式 `"Table.field"` | `@foreign_key("User.id")` |
| `@soft_delete` | 无 | 启用软删除（添加 deleted_at 字段，删除时置时间戳而非物理删除） | `@soft_delete` |
| `@audit_log` | 无 | 启用审计日志（自动记录创建人、修改人、时间戳） | `@audit_log` |
| `@versioned` | 无 | 启用乐观锁版本号（添加 version 字段，更新时自动递增） | `@versioned` |

---

## Method 层注解 (用于 fn)

| 注解 | 参数 | 目标行为 | 示例 |
|---|---|---|---|
| `@locked` | 无 | **跳过 AI 生成**，使用 enjin.lock 缓存。编译器绝对禁止调用 LLM | `@locked fn get_user(...)` |
| `@human_maintained` | 无 | AI 完全放弃生成权，由人类全权维护 | `@human_maintained fn ...` |
| `@transactional` | 无 | 将函数包裹在数据库事务中 (Python: `async with session.begin()`) | `@transactional fn transfer(...)` |
| `@retry` | `(max: Int)` | 失败自动重试。生成 tenacity/resilience4j 重试装饰器 | `@retry(3)` |
| `@cached` | `(ttl: Int)` | 结果缓存，ttl 单位秒 | `@cached(300)` |
| `@cache` | `(ttl: Int)` | 同 `@cached`，别名 | `@cache(300)` |
| `@deprecated` | `(msg: String)` | 标记为废弃，生成 deprecation warning | `@deprecated("use v2")` |
| `@data_plane` | `(protocol: String, engine: String)` | **[部分落地]** 将 `fn` 标记为数据面接口。当前 `analyzer.py` 已做语义约束：`@data_plane` 函数禁止 `native` 实现块（避免数据面计算内核直接落入契约层） | `@data_plane(protocol="grpc", engine="flink")` |
| `@api_contract` | 无 | **[部分落地]** 将 `fn` 标记为跨域可见的接口契约。当前 `analyzer.py` 已做语义约束：`@api_contract` 函数禁止 `native` 实现块（仅保留契约语义） | `@api_contract fn charge(...)` |

---

## Module 层注解 (用于 module)

| 注解 | 参数 | 目标行为 | 示例 |
|---|---|---|---|
| `@engine` | `(type: String, framework: String)` | **[部分落地]** 将 `module` 标记为声明式引擎入口。当前 `analyzer.py` 已做语义约束：禁止重复声明、限制 `type` 取值 (`workflow/state_machine`)、并校验 `framework/type` 组合（如 `temporal -> workflow`） | `@engine(type="state_machine", framework="spring_statemachine") module OrderWorkflow { ... }` |
| `@domain` | `(name: String)` | **[部分落地]** 将模块标记为限界上下文。当前 `analyzer.py` 已做最小检查（参数形态校验、重复注解校验、跨 domain module 直接依赖阻断）；Prompt 路由层的 domain 裁剪仍待后续实现 | `@domain(name="order") module OrderApp { ... }` |

---

## Service 层注解 (用于 route)

| 注解 | 参数 | 目标行为 | 示例 |
|---|---|---|---|
| `@prefix` | `(path: String)` | 路由前缀。所有子路由的路径自动拼接此前缀 | `@prefix("/api/v1/users")` |
| `@auth` | `(strategy: String)` | 认证策略。可选 `"jwt"`, `"api_key"`, `"oauth2"` | `@auth("jwt")` |
| `@rate_limit` | `(rpm: Int)` | 每分钟请求限流 | `@rate_limit(100)` |

---

## 注解扩展规则

1. **注册即合法：** 编译器只识别本文件中注册的注解。未注册的 `@xxx` 当前在静态分析阶段报 `ANNOTATION_UNKNOWN`。
2. **参数类型校验：** 编译器在 AST 静态分析阶段校验注解参数的类型与个数；不匹配时报 `ANNOTATION_INVALID_ARGS`。
3. **作用域限制：** 每个注解有其合法的附着对象（struct/field/fn/module/route/endpoint）；作用域错误时报 `ANNOTATION_INVALID_SCOPE`。
4. **规划态注解：** 已注册但标记为 **[规划]** 的注解，在配套实现落地前仅表示保留语义，不代表当前 parser 已完全支持其编译行为。
5. **自定义注解 (Phase 4+)：** 未来可能支持用户通过 `annotation` 关键字自定义注解行为。

---

> 本文件最后更新: 2026-05-01 | 版本: v0.3.0

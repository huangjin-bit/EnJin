# I-AST 标准 JSON Schema (Intent Abstract Syntax Tree)

> **维护协议：[极度重要]** 本文件定义了 EnJin 编译器的核心数据结构。
> 任何 Parser 的修改必须**先更新本文件**。ast_nodes.py 和 parser.py 必须与本文件严格一致。
> 违反此协议将导致整个编译流水线断裂。
> 带有 **[规划]** 标记的内容仅表示后续扩展方向，不代表当前 `parser.py` 已产出对应字段。

---

## 1. 顶层结构 (Program)

解析一个或多个 `.ej` 文件后，产出一个 `Program` 节点：

```json
{
  "node_type": "program",
  "application": { /* ApplicationConfig | null */ },
  "structs": [ /* StructDef[] */ ],
  "functions": [ /* FnDef[] */ ],
  "modules": [ /* ModuleDef[] */ ],
  "routes": [ /* RouteDef[] */ ]
}
```

每个顶层列表内的元素按源码中的声明顺序排列。

---

## 2. 公共子结构

### 2.1 Annotation (注解)

```json
{
  "name": "table",
  "args": ["users"],
  "kwargs": {}
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | `string` | 注解名称（不含 `@` 前缀） |
| `args` | `(string\|int\|float)[]` | 位置参数列表 |
| `kwargs` | `object` | 具名参数字典 |

### 2.2 TypeRef (类型引用)

```json
{
  "base": "String",
  "params": [],
  "is_optional": false
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `base` | `string` | 基础类型名：`Int`, `Float`, `String`, `Bool`, `DateTime`, `Enum`, `List`, 或 struct 名称 |
| `params` | `(string\|TypeRef)[]` | 泛型参数。`List<String>` → `params: [{"base":"String"}]`；`Enum("a","b")` → `params: ["a","b"]` |
| `is_optional` | `bool` | 是否为 `Optional<T>`。若为 true，`base` 为内部类型 |

### 2.3 Param (函数参数)

```json
{
  "name": "username",
  "type": { "base": "String", "params": [], "is_optional": false }
}
```

---

## 3. Model 层 — StructDef

```json
{
  "node_type": "struct",
  "name": "User",
  "annotations": [
    { "name": "table", "args": ["users"], "kwargs": {} }
  ],
  "fields": [
    {
      "name": "id",
      "type": { "base": "Int", "params": [], "is_optional": false },
      "annotations": [
        { "name": "primary", "args": [], "kwargs": {} },
        { "name": "auto_increment", "args": [], "kwargs": {} }
      ]
    },
    {
      "name": "username",
      "type": { "base": "String", "params": [], "is_optional": false },
      "annotations": [
        { "name": "unique", "args": [], "kwargs": {} },
        { "name": "max_length", "args": [50], "kwargs": {} }
      ]
    },
    {
      "name": "status",
      "type": { "base": "Enum", "params": ["active", "banned", "suspended"], "is_optional": false },
      "annotations": [
        { "name": "default", "args": ["active"], "kwargs": {} }
      ]
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `node_type` | `"struct"` | 固定值，标识节点类型 |
| `name` | `string` | struct 名称（PascalCase） |
| `annotations` | `Annotation[]` | struct 级注解列表 |
| `fields` | `FieldDef[]` | 字段定义列表 |

### FieldDef

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | `string` | 字段名（snake_case） |
| `type` | `TypeRef` | 字段类型 |
| `annotations` | `Annotation[]` | 字段级注解列表 |

---

## 4. Method 层 — FnDef

```json
{
  "node_type": "fn",
  "name": "register_user",
  "annotations": [
    { "name": "transactional", "args": [], "kwargs": {} }
  ],
  "params": [
    { "name": "username", "type": { "base": "String", "params": [], "is_optional": false } },
    { "name": "email", "type": { "base": "String", "params": [], "is_optional": false } },
    { "name": "password", "type": { "base": "String", "params": [], "is_optional": false } }
  ],
  "return_type": { "base": "User", "params": [], "is_optional": false },
  "guard": [
    { "expr": "username.length > 0", "message": "用户名不能为空" },
    { "expr": "email.contains(\"@\")", "message": "邮箱格式不合法" },
    { "expr": "not exists(User, email=email)", "message": "邮箱已被注册" },
    { "expr": "password.length >= 8", "message": "密码至少 8 位" }
  ],
  "process": {
    "intent": "创建一个新的 User 实例，密码使用 bcrypt 哈希加密，status 默认为 active，写入数据库并返回",
    "hash": null
  },
  "expect": [
    {
      "raw": "register_user(\"alice\", \"alice@test.com\", \"password123\").username == \"alice\""
    },
    {
      "raw": "register_user(\"\", \"a@b.com\", \"12345678\").throws(\"用户名不能为空\")"
    }
  ],
  "native_blocks": [],
  "is_locked": false
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `node_type` | `"fn"` | 固定值 |
| `name` | `string` | 函数名（snake_case） |
| `annotations` | `Annotation[]` | 函数级注解 |
| `params` | `Param[]` | 参数列表 |
| `return_type` | `TypeRef \| null` | 返回类型，void 函数为 null |
| `guard` | `GuardRule[]` | 防御性校验规则列表（可为空列表） |
| `process` | `ProcessIntent \| null` | AI 生成意图（与 native_blocks 互斥） |
| `expect` | `ExpectAssertion[]` | 测试断言列表（可为空列表） |
| `native_blocks` | `NativeBlock[]` | 原生代码块列表，当前实现中每项包含 `target` 与 `code` |
| `is_locked` | `bool` | 是否被 `@locked` 锁定 |

### GuardRule

| 字段 | 类型 | 说明 |
|---|---|---|
| `expr` | `string` | 布尔表达式的原始文本 |
| `message` | `string` | 校验失败时的错误信息 |

### ProcessIntent

| 字段 | 类型 | 说明 |
|---|---|---|
| `intent` | `string` | 自然语言意图描述 |
| `hash` | `string \| null` | 意图文本的 SHA-256 哈希值（由编译器生成，用于缓存命中） |

### ExpectAssertion

| 字段 | 类型 | 说明 |
|---|---|---|
| `raw` | `string` | 断言原始文本。当前 Phase 1/2 仅做原样保留，结构化拆解留待测试生成阶段实现 |

### NativeBlock

| 字段 | 类型 | 说明 |
|---|---|---|
| `target` | `string` | 目标语言名，如 `python`、`java` |
| `code` | `string` | 原生代码文本，编译器必须原样保留 |

---

## 5. Module 层 — ModuleDef

```json
{
  "node_type": "module",
  "name": "UserManager",
  "annotations": [
    { "name": "domain", "args": [], "kwargs": { "name": "user" } }
  ],
  "dependencies": ["User", "register_user", "send_welcome_email"],
  "exports": [
    { "action": "register", "target": "register_user" },
    { "action": "detail", "target": "get_user_by_id" }
  ],
  "init": {
    "intent": "初始化用户服务的连接池，预热缓存"
  },
  "schedules": [
    {
      "frequency": "daily",
      "cron": "02:00",
      "intent": "清理 30 天未激活的用户账号"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `node_type` | `"module"` | 固定值 |
| `name` | `string` | 模块名（PascalCase） |
| `annotations` | `Annotation[]` | 模块级注解列表（如 `@domain`、`@engine`） |
| `dependencies` | `string[]` | `use` 声明的依赖名称列表 |
| `exports` | `ModuleExport[]` | `export` 声明的 action 映射列表 |
| `init` | `ProcessIntent \| null` | 初始化意图 |
| `schedules` | `ScheduleDef[]` | 调度任务列表 |

当前实现中，`@domain`、`@engine` 等注解先统一保存在 `annotations` 中，语义级强校验由后续 `analyzer.py` 负责。

### ScheduleDef

| 字段 | 类型 | 说明 |
|---|---|---|
| `frequency` | `string` | 频率关键字：`daily`, `hourly`, `weekly`, `cron` |
| `cron` | `string` | 时间表达式 |
| `intent` | `string` | 任务意图描述 |

### ModuleExport

| 字段 | 类型 | 说明 |
|---|---|---|
| `action` | `string` | 对外暴露的 action 名称（供 route 绑定） |
| `target` | `string` | 绑定到的内部 `fn` 名称 |

---

## 6. Service 层 — RouteDef

```json
{
  "node_type": "route",
  "name": "UserService",
  "annotations": [
    { "name": "prefix", "args": ["/api/v1/users"], "kwargs": {} }
  ],
  "dependencies": ["UserManager"],
  "endpoints": [
    {
      "method": "POST",
      "path": "/register",
      "handler": "register",
      "annotations": [],
      "is_locked": false
    },
    {
      "method": "GET",
      "path": "/{id}",
      "handler": "detail",
      "annotations": [],
      "is_locked": false
    },
    {
      "method": "DELETE",
      "path": "/{id}",
      "handler": "remove",
      "annotations": [
        { "name": "locked", "args": [], "kwargs": {} }
      ],
      "is_locked": true
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `node_type` | `"route"` | 固定值 |
| `name` | `string` | 服务名（PascalCase） |
| `annotations` | `Annotation[]` | 服务级注解（如 @prefix） |
| `dependencies` | `string[]` | `use` 声明的依赖 |
| `endpoints` | `EndpointDef[]` | 路由端点列表 |

### EndpointDef

| 字段 | 类型 | 说明 |
|---|---|---|
| `method` | `string` | HTTP 方法：GET/POST/PUT/DELETE/PATCH |
| `path` | `string` | 路由路径 |
| `handler` | `string` | 当前为端点映射符号名；架构语义上应解析为 `module` 导出的 action 名 |
| `annotations` | `Annotation[]` | 端点级注解 |
| `is_locked` | `bool` | 是否锁定 |

---

## 7. ApplicationConfig (全局配置)

```json
{
  "node_type": "application",
  "name": "trade-core",
  "version": "1.0.0",
  "target": "java_springboot",
  "database": {
    "driver": "postgresql",
    "host": "env(\"DB_HOST\")",
    "port": 5432,
    "name": "trade_db"
  },
  "queue": {
    "primary": "kafka",
    "secondary": "rocketmq"
  },
  "workflow": {
    "engine": "temporal"
  },
  "ai": {
    "provider": "openai",
    "model": "gpt-4",
    "max_tokens_per_call": 2000,
    "cache_strategy": "ast_hash"
  }
}
```

`Program.application` 应理解为“当前编译单元的唯一 ApplicationConfig”。未来进入多编译单元编译模式后，每个编译单元都应独立拥有自己的 `Program.application`，而不是在单个 Program 中混装多个目标栈。

`ApplicationConfig.config` 当前本质为自由嵌套字典。Redis、MQ、Search、Workflow、Observability 等中间件的强校验规则，计划由后续 `analyzer.py` 负责补齐。

---

## 8. [规划] 后续 AST 扩展方向

- `ModuleDef.domain`：承载 `@domain(name="...")` 的领域边界元数据
- `ModuleDef.engine`：承载 `@engine` 的声明式状态流 / 工作流元信息
- `FnDef.data_plane`：承载 `@data_plane` 的协议与运行时元信息
- `ExpectAssertion` 结构化拆解：在测试生成阶段将 `raw` 解析为结构化断言

---

## 9. 完整 I-AST 示例

解析一个包含所有四层的 `.ej` 文件后的完整输出：

```json
{
  "node_type": "program",
  "application": {
    "node_type": "application",
    "name": "trade-core",
    "version": "1.0.0",
    "target": "java_springboot",
    "database": { "driver": "postgresql", "host": "env(\"DB_HOST\")", "port": 5432, "name": "trade_db" },
    "queue": { "primary": "kafka", "secondary": "rocketmq" },
    "workflow": { "engine": "temporal" },
    "ai": { "provider": "openai", "model": "gpt-4", "max_tokens_per_call": 2000, "cache_strategy": "ast_hash" }
  },
  "structs": [ /* StructDef 列表 */ ],
  "functions": [ /* FnDef 列表 */ ],
  "modules": [ /* ModuleDef 列表 */ ],
  "routes": [ /* RouteDef 列表 */ ]
}
```

---

> 本文件最后更新: 2026-03-24 | 版本: v0.3.0
> 关联文件: `src/enjinc/ast_nodes.py`, `src/enjinc/parser.py`

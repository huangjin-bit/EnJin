# EnJin 语法规范 (Syntax Specification)

> **维护协议：** 本文件中“已实现”部分必须与 `src/enjinc/grammar.lark` 保持绝对同步。
> 任何语法变更必须先更新本文件，经人类审核后才能修改解析器。
> 带有 **[规划]** 标记的内容表示已审核通过、但尚未落入解析器的扩展草案；实现前仍需先修改本文件并经人类审核。

---

## 1. 文件结构

一个 `.ej` 文件可包含以下顶层声明（顺序不限）：

```
program := (struct_def | fn_def | module_def | route_def | application_def)*
```

注释使用 `//` 单行注释。

## 2. 类型系统

### 2.1 基础类型
| 类型 | 说明 | 示例 |
|---|---|---|
| `Int` | 整数 | `age: Int` |
| `Float` | 浮点数 | `price: Float` |
| `String` | 字符串 | `name: String` |
| `Bool` | 布尔值 | `active: Bool` |
| `DateTime` | 日期时间 | `created_at: DateTime` |

### 2.2 复合类型
| 类型 | 说明 | 示例 |
|---|---|---|
| `Enum("a","b")` | 枚举 | `status: Enum("active","banned")` |
| `List<T>` | 列表 | `tags: List<String>` |
| `Optional<T>` | 可选 | `bio: Optional<String>` |
| `ModelRef` | 模型引用 | `author: User` (引用另一个 struct) |

## 3. Model 层 — struct

```ej
@table("table_name")
struct StructName {
    field_name: Type @annotation1 @annotation2(arg)
    ...
}
```

- `struct` 定义纯数据结构，映射到数据库表
- 字段声明格式：`名称: 类型 @注解*`
- 不允许包含任何行为逻辑

## 4. Method 层 — fn (三段意图体)

```ej
@annotation
fn function_name(param: Type, ...) -> ReturnType {
    guard {
        条件表达式 : "错误信息"
        ...
    }

    process {
        "自然语言意图描述"
    }

    expect {
        调用表达式.断言
        ...
    }
}
```

### 4.1 三段体顺序
三段体中至少包含 `process`，`guard` 和 `expect` 可选。若同时存在，顺序**必须**为：
1. `guard` — 防御性校验
2. `process` — 业务逻辑意图
3. `expect` — 测试断言

### 4.2 native 逃生舱
当需要直接注入目标语言代码时，使用 `native` 替代 `process`：

```ej
fn custom_hash(data: String) -> String {
    native python {
        import hashlib
        return hashlib.sha256(data.encode()).hexdigest()
    }
    native java {
        return DigestUtils.sha256Hex(data);
    }
}
```

`native` 块中的代码**原封不动**注入目标文件，AI 严禁修改。

**花括号支持：** `native` 块当前支持一层花括号嵌套（如 Java 的 `if (...) { ... }`）。多层深度嵌套花括号暂不支持，后续 Phase 可考虑引入花括号计数或定界符方案增强。

## 5. Module 层 — module

```ej
module ModuleName {
    use DependencyName
    ...

    init {
        "初始化意图描述"
    }

    schedule <frequency> at "<cron>" {
        "调度任务意图描述"
    }
}
```

- `use` 声明对 struct/fn/其他 module 的依赖
- `export` 将内部 `fn` 以 action 名称导出给 `route` 层
- `init` 模块初始化逻辑 (AI 生成)
- `schedule` 定义定时/周期性后台任务

**schedule 频率关键字：**

| 关键字 | 含义 | `at` 参数格式 |
|---|---|---|
| `daily` | 每天 | `"HH:MM"` |
| `hourly` | 每小时 | `"MM"` (分钟) |
| `weekly` | 每周 | `"DAY HH:MM"` (如 `"MON 09:00"`) |
| `cron` | 自定义 cron | `"cron_expression"` (如 `"0 2 * * *"`) |

### 5.1 module 导出语义

`module` 是 `route` 与 `fn` 之间的唯一合法桥梁。`route` 只能绑定 `module` 导出的 action，不能直接绑定裸 `fn`。

```ej
module OrderApp {
    use create_order
    use cancel_order

    export create = create_order
    export cancel = cancel_order
}
```

- `export` 声明将内部 `fn` 以 action 名称暴露给 `route` 层
- `use` 引入依赖，`export` 导出能力，两者互补
- 一个 `fn` 可以被多个 `module` 以不同 action 名称导出
- 语法层与 AST 层已支持 `export`，`ModuleDef.exports` 可用于后续 `route` 绑定校验
- `analyzer.py` 已落地最小校验（`route -> module action`、action 重名歧义、export 合法性、module 依赖图 DAG、最小 domain 边界）
- `analyzer.py` 已落地首批规划态注解语义校验（`@engine` type/framework 约束、`@api_contract` / `@data_plane` 禁止 native 实现块）
- 更完整语义校验（例如细粒度跨 domain 白名单与编排能力白名单）仍待后续扩展

## 6. Service 层 — route

```ej
@prefix("/api/v1/resource")
route ServiceName {
    use ModuleName

    HTTP_METHOD "path" -> action_name
    ...
}
```

支持的 HTTP 方法：`GET`, `POST`, `PUT`, `DELETE`, `PATCH`

- 在语法层面，`->` 后仍是一个符号名称。
- 在架构语义上，该符号必须解析为 `module` 导出的 action，而不是裸 `fn` 名称。
- 当前仓库中的 `route -> fn` 示例属于历史过渡写法，后续将由静态分析器收敛并拒绝。

## 7. 全局配置 — application

```ej
application {
    name: "trade-core"
    version: "1.0.0"
    target: "java_springboot"

    database {
        driver: "postgresql"
        host: env("DB_HOST")
        port: 5432
        name: "trade_db"
    }

    queue {
        primary: "kafka"
        secondary: "rocketmq"
    }

    workflow {
        engine: "temporal"
    }

    ai {
        provider: "openai"
        model: "gpt-4"
        max_tokens_per_call: 2000
        cache_strategy: "ast_hash"
    }
}
```

- `application` 块是全局唯一的技术栈配置入口
- 严禁在此处编写业务逻辑
- `env("VAR")` 函数引用环境变量
- 每个 `Compilation Unit` 只能有一个 `application` 块；一个 `application` 只能绑定一个 `target`
- 多编译单元组织方式详见 `docs/02_architecture/compilation_unit_model.md`
补充约束：
- 电商交易核心默认目标栈为 `java_springboot`
- Python 目标栈主要用于监控、Agent 与爬虫场景
- `queue`、`workflow` 等中间件配置当前属于已实现语法允许的嵌套配置结构，具体校验规则待 `analyzer.py` 落地

## 8. 注解语法

```
@annotation_name                    // 无参注解
@annotation_name("arg")            // 单参注解
@annotation_name(key="value")      // 具名参数注解
```

### 8.1 [部分落地] 核心注解扩展
以下注解已通过架构评审，当前已落地首批静态语义校验：

```ej
@engine(type="state_machine", framework="spring_statemachine")
module OrderWorkflow {
    use create_order
    use pay_order
    use ship_order
}

@data_plane(protocol="grpc", engine="flink")
fn calculate_ctr(user_id: Int, product_id: Int) -> Float {
    process { "只描述接口契约，不描述计算内核" }
}

@domain(name="order")
module OrderService {
    use Order
}
```

- `@engine`：用于 Module 层编排入口，只生成声明式状态流 / 工作流配置，不生成底层状态机算法
- `@data_plane`：只生成协议与外层包裹代码，不生成具体数据面计算逻辑
- `@domain`：限制上下文剪枝范围，只允许当前领域结构进入 Prompt
- 当前 analyzer 约束：
  - `@engine`：禁止重复声明；`type` 仅允许 `workflow/state_machine`；`temporal -> workflow`、`spring_statemachine -> state_machine`
  - `@api_contract` / `@data_plane`：函数禁止 `native` 实现块

详见 `annotations_registry.md` 获取完整注解列表。

---

> 本文件最后更新: 2026-03-25 | 版本: v0.3.0

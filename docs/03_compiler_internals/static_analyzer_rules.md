# 静态分析规则规范 (Static Analyzer Rules)

> 本文档定义 `src/enjinc/analyzer.py` 当前已落地的最小规则集与错误码。

---

## 1. 入口与职责

静态分析发生在 AST Transform 之后、Prompt Routing 之前：

```text
.ej -> parser.py -> Program AST -> analyzer.py -> (通过) -> 下一阶段
```

当前提供的 API：

- `analyze(program) -> list[AnalysisIssue]`
- `assert_valid(program) -> None`（失败时抛 `EnJinAnalysisError`）
- `analyze_file(path) -> list[AnalysisIssue]`

CLI 集成（`src/enjinc/cli.py`）：

- `enjinc build <source>`：默认执行 `assert_valid`，若有问题直接阻断渲染
- `enjinc build --skip-analysis`：显式跳过静态分析（仅建议调试时使用）
- `enjinc analyze <source> --strict`：发现问题返回非 0 退出码，便于 CI 集成

---

## 2. 已实现规则

### 2.1 Route 层依赖约束

- `route` 只能 `use module`
- `route` 不能 `use struct` / `fn`

错误码：

- `ROUTE_CANNOT_USE_MODEL`
- `ROUTE_CANNOT_USE_METHOD`
- `ROUTE_UNKNOWN_DEPENDENCY`

### 2.2 Route handler 绑定约束

- `route` 的 endpoint `handler` 必须是其依赖 module 导出的 action
- 禁止直接绑定裸 `fn`

错误码：

- `ROUTE_BINDS_RAW_FN`
- `ROUTE_ACTION_NOT_EXPORTED`

### 2.3 多 module action 歧义约束

- 当一个 route 依赖多个 module 时，若多个 module 导出同名 action，判定为歧义

错误码：

- `ROUTE_AMBIGUOUS_ACTION`

### 2.4 Module 层依赖与导出约束

- `module` 不能依赖 `route`
- `module export` 的 target 必须是存在的 `fn`
- `module export` 的 target 必须在 module 的 `use` 声明中出现
- 同一 module 内 action 名称不能重复

错误码：

- `MODULE_CANNOT_USE_ROUTE`
- `MODULE_UNKNOWN_DEPENDENCY`
- `MODULE_EXPORT_TARGET_NOT_FN`
- `MODULE_EXPORT_TARGET_NOT_IN_USE`
- `MODULE_DUPLICATE_EXPORT_ACTION`

### 2.5 Module 依赖图约束 (DAG)

- module-to-module 依赖必须是有向无环图 (DAG)
- 若存在 `A -> B -> C -> A` 这类循环依赖，编译拒绝

错误码：

- `MODULE_DEPENDENCY_CYCLE`

### 2.6 Domain 边界与注解形态约束（最小落地）

- 当两个 module 都声明了 `@domain`，禁止直接跨 domain 依赖
- 同一 module 上 `@domain` 只能出现一次
- `@domain` 参数必须为非空字符串：`@domain(name="...")` 或 `@domain("...")`

错误码：

- `MODULE_CROSS_DOMAIN_DEPENDENCY`
- `MODULE_DUPLICATE_DOMAIN_ANNOTATION`
- `MODULE_INVALID_DOMAIN_ANNOTATION`

### 2.7 注解注册表约束

- 仅允许使用注册表中的注解名
- 注解必须附着在其合法作用域（struct/field/fn/module/route/endpoint）
- 注解参数数量与类型必须匹配注册签名

错误码：

- `ANNOTATION_UNKNOWN`
- `ANNOTATION_INVALID_SCOPE`
- `ANNOTATION_INVALID_ARGS`

### 2.8 规划态注解语义约束（已落地首批）

- `@engine`
  - 同一 module 禁止重复声明
  - `type` 仅允许：`workflow` / `state_machine`
  - `framework/type` 组合校验：
    - `temporal -> workflow`
    - `spring_statemachine -> state_machine`
- `@api_contract`
  - 函数禁止包含 `native` 实现块（仅保留契约语义）
- `@data_plane`
  - 函数禁止包含 `native` 实现块（避免数据面计算内核直接落入契约层）

错误码：

- `MODULE_DUPLICATE_ENGINE_ANNOTATION`
- `MODULE_ENGINE_UNSUPPORTED_TYPE`
- `MODULE_ENGINE_FRAMEWORK_TYPE_MISMATCH`
- `API_CONTRACT_HAS_NATIVE_IMPL`
- `DATA_PLANE_HAS_NATIVE_IMPL`

---

## 3. 问题数据结构

`AnalysisIssue` 结构：

```json
{
  "code": "ROUTE_BINDS_RAW_FN",
  "message": "route 'UserService' endpoint 'POST /register' binds raw fn 'register_user'...",
  "context": "route:UserService"
}
```

聚合异常 `EnJinAnalysisError` 会携带 `issues: list[AnalysisIssue]`，方便上层 CLI/IDE 展示。

---

## 4. 覆盖测试

对应测试文件：`tests/test_analyzer.py`

当前覆盖：

- 合法示例通过 (`examples/user_management.ej`)
- route 直绑裸 fn
- route 非法依赖 fn
- route handler 非导出 action
- module 越级依赖 route
- export target 非 fn
- export target 未声明在 use 中
- 多 module 同名 action 歧义
- module-to-module 依赖循环
- 跨 domain module 直接依赖
- `@domain` 注解重复与非法参数
- 未注册注解
- 注解作用域错误
- 注解参数类型/个数错误
- 重复 `@engine` 声明
- `@engine` type 非法与 framework/type 组合冲突
- `@api_contract` / `@data_plane` 搭配 native 实现块

---

## 5. 下一阶段扩展

当前规则属于“最小可用”集合。后续建议补齐：

- Queue 能力与 annotation 组合约束
- 编译单元级目标栈约束
- 更细粒度跨 domain 越权检查（如 `@api_contract` 白名单）
- 规划态注解的更深语义校验（例如跨层暴露边界、编排能力白名单）

---

> 本文件最后更新: 2026-03-25 | 版本: v0.4.0

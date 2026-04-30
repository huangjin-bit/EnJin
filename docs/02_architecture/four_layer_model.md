# 四层架构模型 (Four-Layer Architecture)

> 本文档定义 EnJin 的核心架构隔离原则。

---

## 调用链 (严格单向)

```
Service (route)
    │  ← 只能绑定 Module 导出的 action
    ▼
Module (module)
    │  ← 只能编排 Method 和 Model
    ▼
Method (fn)
    │  ← 只能操作 Model（读写数据）
    ▼
Model (struct)
    ← 纯数据定义，不调用任何层
```

补充约束：

- `route` **不能**直接绑定裸 `fn`，只能绑定 `module` 导出的 action。
- `module` 负责对外暴露可编排的业务入口，`fn` 只负责原子业务逻辑。
- 跨领域协作只能通过显式导出的契约进行，禁止透传其他领域的 `process`、数据库细节与内部补偿逻辑。

## 违规检测规则

编译器在 AST 静态分析阶段必须检查以下违规：

| 违规类型 | 示例 | 错误级别 |
|---|---|---|
| Service 直绑裸 Method | route 内直接引用 fn（未经 module export） | ERROR: 编译拒绝 |
| Service 越级调用 Model | route 内直接操作 struct 字段 | ERROR: 编译拒绝 |
| Module 越级调用 Service | module 内引用 route | ERROR: 编译拒绝 |
| Method 调用 Module/Service | fn 内引用 module 或 route | ERROR: 编译拒绝 |
| 跨域读取内部实现 | 当前 domain 透传其他 domain 的 `process` / 数据库细节 | ERROR: 编译拒绝 |
| Model 包含行为逻辑 | struct 内出现 process/guard | ERROR: 编译拒绝 |

## 依赖声明机制

每个层级通过 `use` 关键字显式声明对下级的依赖：

```ej
module UserManager {
    use User              // 依赖 Model 层
    use register_user     // 依赖 Method 层
}

route UserService {
    use UserManager       // 依赖 Module 层
}
```

`module` 是 `route` 与 `fn` 之间的唯一合法桥梁。`route` 只能面向 `module` 暴露出的 action 建立 HTTP/gRPC 入口，不能直接将端点映射到裸 `fn`。

## 当前实现差距 (待补齐)

- `grammar.lark` 已支持 `module` 级 `annotation_list` 和 `export` 声明语法。
- `examples/user_management.ej` 已更新为使用 `export` + `route -> action` 模式。
- `parser.py` 与 I-AST 已支持 `ModuleDef.annotations` / `ModuleDef.exports` 字段产出。
- `analyzer.py` 已落地最小校验能力：`route` 依赖层级、`route -> module export action`、`module` 越级依赖与 export 合法性。
- `analyzer.py` 已支持 module 依赖图循环检测（DAG）与最小 domain 边界检查（跨域 module 直接依赖阻断）。
- 更完整的语义校验（Queue 能力、编译单元级目标约束、细粒度跨域白名单）仍待后续扩展。

编译器通过 `use` 声明构建依赖图 (DAG)，若检测到环形依赖则编译报错。

---
> 本文件最后更新: 2026-03-24 | 版本: v0.2.0

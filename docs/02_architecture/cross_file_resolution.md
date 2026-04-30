# 跨文件引用解析规则 (Cross-File Resolution)

> 本文档定义同一编译单元内多个 `.ej` 文件之间的名称解析机制。

---

## 1. 核心规则：编译单元内隐式全量可见

同一 `Compilation Unit` 内的所有 `.ej` 文件，其顶层声明（`struct`、`fn`、`module`、`route`）对该编译单元内的所有其他文件**隐式可见**。

- 不需要 `import` 语句
- 不需要指定来源文件路径
- `use` 只声明名称依赖，不指明物理文件

理由：

- EnJin 是意图语言，不是系统编程语言；保持语法极简是核心哲学
- 一个编译单元的规模受限于"单个可部署产物"，天然不会膨胀到需要包管理的程度
- 文件拆分是组织手段，不是可见性边界

---

## 2. 名称唯一性约束

在同一编译单元内：

- `struct` 名称必须唯一（PascalCase）
- `fn` 名称必须唯一（snake_case）
- `module` 名称必须唯一（PascalCase）
- `route` 名称必须唯一（PascalCase）
- `application` 块必须唯一（最多一个）

`analyzer.py` 在静态分析阶段必须检查名称冲突，若检测到同名声明则报 `DuplicateNameError`。

---

## 3. 编译器加载顺序

编译单元的编译入口为其根目录：

```text
enjinc build services/trade-core
```

编译器应：

1. 扫描 `services/trade-core/` 下所有 `.ej` 文件（不递归子目录，除非显式配置）
2. 按文件名字典序加载（确保确定性）
3. 合并所有文件的顶层声明到一个 `Program` 节点
4. 运行静态分析（名称唯一性、四层调用链、domain 边界等）
5. 进入后续编译流程

---

## 4. `use` 声明的解析

`use` 声明中的名称按以下优先级解析：

1. 当前编译单元内的 `struct` 名称
2. 当前编译单元内的 `fn` 名称
3. 当前编译单元内的 `module` 名称
4. 共享契约目录中的 schema 名称（Phase 3+）

若名称无法解析，编译器应报 `UnresolvedReferenceError`。

---

## 5. 跨编译单元引用

跨编译单元的名称**不可**通过 `use` 直接引用。跨编译单元协作必须通过：

- 共享契约（`shared/contracts/`）
- 生成后的 SDK / Client 包装
- HTTP / gRPC / MQ 接口

详见 `compilation_unit_model.md` 第 2.4 节。

---

## 6. 推荐的文件拆分策略

| 拆分维度 | 示例 |
|---|---|
| 按 domain | `order.ej`、`payment.ej`、`inventory.ej` |
| 按层级 | `models.ej`、`services.ej`、`routes.ej` |
| 混合 | `order_models.ej`、`order_services.ej` |

推荐按 domain 拆分，每个 `.ej` 文件包含该 domain 的 struct + fn + module + route。

---

## 7. 当前实现状态

### 已实现

- 解析器可从单个 `.ej` 文件生成 `Program` AST

### 待实现

- 多文件合并到单个 `Program` 的加载器
- 名称唯一性校验
- `UnresolvedReferenceError` 报错
- 共享契约目录的解析入口

---

> 本文件最后更新: 2026-03-24 | 版本: v0.1.0

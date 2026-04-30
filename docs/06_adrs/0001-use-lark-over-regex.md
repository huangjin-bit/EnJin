# ADR-0001: 使用 Lark 而非正则表达式作为解析器

- **状态:** 已采纳 (Accepted)
- **日期:** 2026-03-16
- **决策者:** EnJin 架构组

## 背景 (Context)

EnJin 编译器需要将 `.ej` 源码解析为结构化的 I-AST。
可选方案包括：手写正则匹配、递归下降解析器、解析器生成器 (Lark/ANTLR/PLY)。

EnJin 的语法特征：
- 四层嵌套结构 (struct/fn/module/route)
- 块级语法 (guard{}/process{}/expect{})
- 注解系统 (@annotation(args))
- 自然语言字符串嵌入 (process 中的意图描述)

## 决策 (Decision)

**采用 Lark 解析器生成器**，使用 EBNF 语法文件 (`grammar.lark`) 定义文法。

理由：
1. **声明式语法定义：** `.lark` 文件直接对应 EBNF，可读性远超手写正则。
2. **Transformer 模式：** Lark 的 Transformer 类可直接将 Parse Tree 映射为 Python 对象 (I-AST)，无需手写遍历逻辑。
3. **Earley/LALR 双模式：** 开发期用 Earley（容错性强），稳定后切 LALR（性能高）。
4. **纯 Python 实现：** 零编译依赖，与项目技术栈完全一致。
5. **错误定位：** Lark 提供行号/列号级别的语法错误报告。

排除方案：
- **正则表达式：** 无法处理嵌套结构和上下文相关的语法。
- **ANTLR：** 需要 Java 运行时生成 Python Parser，增加构建复杂度。
- **PLY：** 已停止维护，API 设计过时。

## 后果 (Consequences)

- **正面：** 语法变更只需修改 `.lark` 文件和对应 Transformer 方法，开发速度快。
- **正面：** 语法定义文件可直接作为文档的一部分 (docs/01_language_spec/syntax.md 与其同步)。
- **负面：** 团队成员需要学习 Lark 的 EBNF 方言和 Transformer 模式。
- **负面：** Earley 模式在大文件上可能存在性能瓶颈（后续可切换至 LALR）。

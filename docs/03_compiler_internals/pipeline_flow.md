# 编译流水线 (Compilation Pipeline)

> 本文档描述 `enjinc build` 的完整 7 步编译流程。

---

## 流水线总览

```
.ej Source Code
       │
       ▼
[1] Lex & Parse ──────── Lark + grammar.lark
       │
       ▼
[2] AST Transform ────── parser.py Transformer → I-AST (JSON)
       │
       ▼
[3] Static Analysis ──── 编译单元边界 / 四层调用链 / domain 裁剪 / route→module action / Queue 能力校验
       │
       ▼
[4] Prompt Routing ───── PromptRouter: 编译单元裁剪 + domain 裁剪 + System Prompt 组装
       │
       ▼
[5] AI Generation ────── LLM API 调用 (仅 process 节点)
       │
       ▼
[6] Template Assembly ── Jinja2 模板渲染：骨架 + AI 插槽 → 目标代码
       │
       ▼
[7] Auto-Testing ─────── expect(raw) → 结构化断言 → pytest/JUnit 测试运行
       │
       ├── 全绿 → 落盘 + 生成 enjin.lock
       └── 爆红 → 熔断 + 错误报告
```

补充说明：

- 编译入口应首先定位到单个 `Compilation Unit`，而不是整仓 AST 全量进入流水线。
- Prompt Routing 前必须完成静态裁剪，禁止用“整项目 AST 喂模型”替代治理逻辑。
- `expect` 当前在 AST 中仍以 `raw` 存储，测试生成阶段再负责结构化拆解。
- 当前 `enjinc build` 默认执行静态分析并在违规时阻断渲染；可通过 `--skip-analysis` 显式跳过（仅用于调试）。
- 当前 `enjinc analyze --strict` 在发现静态分析问题时返回非 0 退出码，便于 CI 集成。

## 各步骤对应代码模块

| 步骤 | 模块文件 | Phase |
|---|---|---|
| [1] Lex & Parse | `src/enjinc/grammar.lark` | Phase 1 |
| [2] AST Transform | `src/enjinc/parser.py` | Phase 1 |
| [3] Static Analysis | `src/enjinc/analyzer.py` (已实现最小规则) | Phase 1+ |
| [4] Prompt Routing | `src/enjinc/prompt_router.py` (已实现) | Phase 3 |
| [5] AI Generation | `src/enjinc/code_generator.py` (已实现) | Phase 3 |
| [6] Template Assembly | `src/enjinc/template_renderer.py` + `targets/<name>/renderer.py` | Phase 2+ |
| [7] Auto-Testing | `src/enjinc/test_generator.py` (已实现) | Phase 4 |

---
> 本文件最后更新: 2026-04-30 | 版本: v0.5.0

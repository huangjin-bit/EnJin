# EnJin 目标栈扩展开发指南

本文档面向想要为 EnJin 编译器新增目标栈的第三方开发者。

---

## 概述

EnJin 使用 **Python entry_points 插件机制**，第三方开发者可以独立发布 pip 包来扩展新的目标语言。用户只需 `pip install enjinc-go-gin`，新目标就自动可用：

```bash
pip install enjinc-go-gin
enjinc build app.ej --target go_gin
```

无需 fork、无需修改 EnJin 源码。

---

## 工作原理

```
pip install enjinc-go-gin
        │
        ▼
pyproject.toml 声明:
[project.entry-points."enjinc.targets"]
go_gin = "enjinc_go_gin.renderer"
        │
        ▼
enjinc 启动时调用 importlib.metadata.entry_points(group="enjinc.targets")
        │
        ▼
自动 import enjinc_go_gin.renderer
        │
        ▼
@register_target 装饰器触发 → 注册到 TARGET_REGISTRY
        │
        ▼
enjinc build --target go_gin 即可使用
```

---

## 开发步骤

### Step 1: 创建项目结构

```
enjinc-go-gin/
├── pyproject.toml
└── src/
    └── enjinc_go_gin/
        ├── __init__.py
        ├── renderer.py          ← 核心：实现 TargetRenderer 协议
        └── templates/           ← Jinja2 模板
            ├── main.go.jinja
            ├── model.go.jinja
            ├── handler.go.jinja
            └── go.mod.jinja
```

### Step 2: 编写 pyproject.toml

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "enjinc-go-gin"
version = "0.1.0"
description = "Go Gin target for EnJin Compiler"
requires-python = ">=3.11"
dependencies = [
    "enjinc>=0.1.0",    # 依赖 EnJin 核心
    "jinja2>=3.1.3",    # 模板引擎（通常由 enjinc 传递依赖）
]

# 关键：声明 EnJin 插件入口点
[project.entry-points."enjinc.targets"]
go_gin = "enjinc_go_gin.renderer"

[tool.setuptools.packages.find]
where = ["src"]
```

### Step 3: 实现 renderer.py

```python
"""Go Gin target renderer for EnJin."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from enjinc.ast_nodes import FnDef, ModuleDef, RouteDef, StructDef
from enjinc.targets import register_target, render_template, write_file


@register_target
class GoGinRenderer:
    """Go Gin Web Framework 目标渲染器。"""

    target_lang = "go_gin"       # 唯一标识，用于 --target 参数
    native_lang = "go"            # native 逃生舱语言
    file_extension = ".go"        # 生成代码文件后缀

    def render_infrastructure(
        self, app_name: str, app_config: dict, output_dir: Path,
    ) -> None:
        """生成基建文件：main.go, go.mod, config 等。"""
        t = self.target_lang
        ctx = {"app_name": app_name, "app_config": app_config}

        write_file(output_dir / "main.go",
                   render_template(t, "main.go.jinja", ctx))
        write_file(output_dir / "go.mod",
                   render_template(t, "go.mod.jinja", ctx))

    def render_models(
        self, structs: list[StructDef], app_name: str, output_dir: Path,
        app_config: dict | None = None,
    ) -> None:
        """生成 Go struct 模型。"""
        t = self.target_lang
        models_dir = output_dir / "models"
        for struct in structs:
            ctx = {"struct": struct}
            write_file(
                models_dir / f"{struct.name.lower()}.go",
                render_template(t, "model.go.jinja", ctx),
            )

    def render_methods(
        self,
        functions: list[FnDef],
        structs: list[StructDef],
        app_name: str,
        ai_results: dict | None,
        output_dir: Path,
        app_config: dict | None = None,
    ) -> None:
        """生成业务逻辑函数（Go 方法）。"""
        from enjinc.template_renderer import _get_ai_code
        t = self.target_lang
        services_dir = output_dir / "services"
        for fn in functions:
            ctx = {
                "fn": fn,
                "ai_code": _get_ai_code(ai_results, "fn", fn.name),
            }
            write_file(
                services_dir / f"{fn.name}.go",
                render_template(t, "handler.go.jinja", ctx),
            )

    def render_modules(
        self, modules: list[ModuleDef], output_dir: Path,
    ) -> None:
        """Go 没有模块层，空实现。"""
        pass

    def render_routes(
        self,
        routes: list[RouteDef],
        app_name: str,
        ai_results: dict | None,
        output_dir: Path,
        functions: list | None = None,
        structs: list | None = None,
        app_config: dict | None = None,
    ) -> None:
        """生成 HTTP 路由处理器。"""
        from enjinc.template_renderer import _get_ai_code
        t = self.target_lang
        routes_dir = output_dir / "routes"
        for route in routes:
            ctx = {
                "route": route,
                "ai_code": _get_ai_code(ai_results, "route", route.name),
            }
            write_file(
                routes_dir / f"{route.name.lower()}.go",
                render_template(t, "route.go.jinja", ctx),
            )
```

### Step 4: 编写 Jinja2 模板

模板放在 `src/enjinc_go_gin/templates/` 下。EnJin 会自动定位到你的包目录。

**main.go.jinja 示例**:

```go
package main

import (
    "github.com/gin-gonic/gin"
    "{{ app_name }}/routes"
)

func main() {
    r := gin.Default()

    // Register routes
    routes.RegisterAll(r)

    r.Run(":8080")
}
```

**model.go.jinja 示例**:

```go
package models

// {{ struct.name }} model
type {{ struct.name }} struct {
{% for field in struct.fields %}
    {{ field.name | snake_to_camel }}  {{ go_type(field) }}  `json:"{{ field.name }}"`
{% endfor %}
}
```

### Step 5: 发布

```bash
# 本地开发测试
pip install -e .

# 验证
enjinc targets  # 应该看到 go_gin
enjinc build examples/blog_platform.ej --target go_gin

# 发布到 PyPI
python -m build
twine upload dist/*
```

---

## 协议参考

所有渲染器必须实现 `TargetRenderer` 协议的 5 个方法 + 3 个属性：

| 方法/属性 | 说明 | 必须？ |
|---|---|---|
| `target_lang: str` | 目标标识符 (如 `"go_gin"`) | 是 |
| `native_lang: str` | native 语言 (如 `"go"`) | 是 |
| `file_extension: str` | 文件后缀 (如 `".go"`) | 是 |
| `render_infrastructure()` | 基建文件 (入口、配置) | 是 |
| `render_models()` | ORM/数据模型 | 是 |
| `render_methods()` | 业务逻辑函数 | 是 |
| `render_modules()` | 模块初始化/调度 | 是 (可 pass) |
| `render_routes()` | HTTP 路由 | 是 (可 pass) |

可选参数（协议签名中带默认值，不实现也能通过）：
- `app_config: dict | None = None` — 应用配置，用于布局定制
- `structs: list | None = None` — struct 列表 (render_routes)
- `functions: list | None = None` — 函数列表 (render_routes)

---

## 模板工具函数

EnJin 提供以下内置工具，无需自己实现：

```python
from enjinc.targets import render_template, write_file
from enjinc.template_renderer import _get_ai_code

# render_template(target_lang, template_name, context) → str
#   自动定位到你的 templates/ 目录

# write_file(path, content) → None
#   自动创建父目录，UTF-8 写入

# _get_ai_code(ai_results, "fn", fn_name) → str | None
#   提取 AI 生成的代码（已清理 markdown 标记）
```

Jinja2 内置过滤器：
- `snake_to_camel` — `user_name` → `userName`
- `snake_to_pascal` — `user_name` → `UserName`
- `pluralize_en` — `category` → `categories`
- `dedent` / `strip_lines`

---

## 测试

建议的测试策略：

```python
# tests/test_go_gin_templates.py
from pathlib import Path
from enjinc.parser import parse_file
from enjinc.template_renderer import RenderConfig, render_program

def test_go_gin_generates_main():
    program = parse_file("examples/user_management.ej")
    config = RenderConfig(target_lang="go_gin", output_dir=Path("test_output"))
    render_program(program, config)

    assert (Path("test_output/go_gin/main.go")).exists()
    assert (Path("test_output/go_gin/models/user.go")).exists()
```

---

## 完整示例

参考 EnJin 内置目标的实现：

- **Python FastAPI**: `src/enjinc/targets/python_fastapi/`
- **Java Spring Boot**: `src/enjinc/targets/java_springboot/`
- **Python Crawler**: `src/enjinc/targets/python_crawler/`

这三个内置目标使用与第三方插件完全相同的协议和注册机制。

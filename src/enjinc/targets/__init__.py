"""
============================================================
EnJin Target Renderer Protocol (targets/__init__.py)
============================================================
定义目标渲染器的协议接口。新增目标有两种方式：

内置目标（随 enjinc 一起发布）：
  在 targets/<name>/ 下写 renderer.py + templates/

第三方插件（pip install 独立安装）：
  在 pyproject.toml 声明 [project.entry-points."enjinc.targets"]
  实现同样协议即可，无需修改 enjinc 源码。

两者使用完全相同的 @register_target 注册机制。
============================================================
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from enjinc.ast_nodes import FnDef, ModuleDef, RouteDef, StructDef
from enjinc.jinja_utils import get_jinja_env


def render_template(target_lang: str, template_name: str, context: dict[str, Any]) -> str:
    """渲染单个 Jinja2 模板。"""
    env = get_jinja_env(target_lang)
    template = env.get_template(template_name)
    return template.render(**context)


def write_file(path: Path, content: str) -> None:
    """写入文件，自动创建父目录。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


@runtime_checkable
class TargetRenderer(Protocol):
    """目标渲染器协议。每个目标栈实现此协议。"""

    @property
    def target_lang(self) -> str:
        """目标语言标识符，如 'python_fastapi'。"""
        ...

    @property
    def native_lang(self) -> str:
        """native 逃生舱对应的目标语言，如 'python' 或 'java'。"""
        ...

    @property
    def file_extension(self) -> str:
        """生成代码的文件扩展名，如 '.py' 或 '.java'。"""
        ...

    def render_infrastructure(
        self, app_name: str, app_config: dict, output_dir: Path,
    ) -> None:
        """渲染基建层文件（config, database, main 等）。"""
        ...

    def render_models(
        self, structs: list[StructDef], app_name: str, output_dir: Path,
        app_config: dict | None = None,
    ) -> None:
        """渲染 Model 层（ORM 实体类）。"""
        ...

    def render_methods(
        self,
        functions: list[FnDef],
        structs: list[StructDef],
        app_name: str,
        ai_results: dict | None,
        output_dir: Path,
        app_config: dict | None = None,
    ) -> None:
        """渲染 Method 层（业务逻辑函数）。"""
        ...

    def render_modules(
        self, modules: list[ModuleDef], output_dir: Path,
    ) -> None:
        """渲染 Module 层（初始化和调度）。"""
        ...

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
        """渲染 Service 层（HTTP 路由）。"""
        ...


# 全局目标注册表
TARGET_REGISTRY: dict[str, Any] = {}


def register_target(renderer_cls: type) -> type:
    """装饰器：将 TargetRenderer 子类注册到全局注册表。"""
    instance = renderer_cls()
    TARGET_REGISTRY[instance.target_lang] = instance
    return renderer_cls


def get_renderer(target_lang: str) -> TargetRenderer | None:
    """获取指定目标的渲染器实例。"""
    return TARGET_REGISTRY.get(target_lang)


def list_targets() -> list[str]:
    """列出所有已注册的目标。"""
    return sorted(TARGET_REGISTRY.keys())


def get_target_info() -> list[dict[str, str]]:
    """返回所有已注册目标的详细信息（名称 + 来源）。"""
    import importlib.metadata
    info = []
    # 构建 entry_point name → package 映射
    ep_sources = {}
    try:
        for ep in importlib.metadata.entry_points(group="enjinc.targets"):
            ep_sources[ep.name] = ep.value.split(".")[0]
    except Exception:
        pass

    for name in sorted(TARGET_REGISTRY.keys()):
        source_pkg = ep_sources.get(name, "built-in")
        info.append({"name": name, "source": source_pkg})
    return info


# 内置目标（回退机制：entry_points 不可用时仍能加载）
_BUILTIN_TARGETS = [
    "python_fastapi",
    "java_springboot",
    "python_crawler",
]


def _auto_discover():
    """
    自动发现并加载所有目标渲染器。

    优先通过 importlib.metadata.entry_points() 发现（包括第三方插件），
    然后回退加载内置目标。
    """
    import importlib

    # 1. 通过 entry_points 发现所有已注册目标（内置 + 第三方插件）
    discovered_names = set()
    try:
        for ep in importlib.metadata.entry_points(group="enjinc.targets"):
            discovered_names.add(ep.name)
            if ep.name not in TARGET_REGISTRY:
                try:
                    ep.load()  # 触发 @register_target 装饰器
                except Exception as exc:
                    print(f"[enjinc] Failed to load plugin target '{ep.name}': {exc}")
    except Exception:
        pass

    # 2. 回退：加载内置目标（处理 entry_points 不可用的情况，如开发模式 editable install）
    for name in _BUILTIN_TARGETS:
        if name not in TARGET_REGISTRY:
            try:
                importlib.import_module(f"enjinc.targets.{name}.renderer")
            except (ImportError, ModuleNotFoundError):
                pass


_auto_discover()


def rediscover_targets():
    """手动重新扫描 entry_points，加载新安装的插件。

    在 CLI 入口调用，确保用户 pip install 后立即可用，
    无需重启 Python 解释器。
    """
    import importlib.metadata

    for ep in importlib.metadata.entry_points(group="enjinc.targets"):
        if ep.name not in TARGET_REGISTRY:
            try:
                ep.load()
            except Exception as exc:
                print(f"[enjinc] Failed to load plugin target '{ep.name}': {exc}")

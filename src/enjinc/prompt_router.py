"""
============================================================
EnJin Prompt Router (prompt_router.py)
============================================================
本模块负责根据 AST 节点类型和目标语言，为 AI 生成阶段组装差异化的 System Prompt。

支持的目标语言:
    - python_fastapi
    - java_springboot
    - python_crawler

Prompt 模板策略:
    - Model 层: 生成数据访问代码 (JPA Entity / SQLAlchemy Model)
    - Method 层: 生成业务逻辑代码 (Service Method)
    - Module 层: 生成初始化和调度代码
    - Route 层: 生成 HTTP 路由代码
============================================================
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional

from enjinc.ast_nodes import (
    ApplicationConfig,
    FnDef,
    ModuleDef,
    Program,
    RouteDef,
    StructDef,
)
from enjinc.annotations import (
    has_annotation,
    get_engine_config,
    get_data_plane_config,
    get_prefix_path,
    get_auth_strategy,
)
from enjinc.constants import (
    ANNO_API_CONTRACT,
    ANNO_DATA_PLANE,
    ANNO_ENGINE,
    ENGINE_REGISTRY,
    ENJIN_TO_JAVA,
)


@dataclass
class PromptContext:
    """Prompt 上下文，包含渲染所需的所有信息。"""

    program: Program
    target_lang: str
    app_config: dict = field(default_factory=dict)
    dep_graph: Optional[object] = None
    review_comments: Optional[list] = None

    @property
    def app_name(self) -> str:
        return self.app_config.get("name", "app")

    @property
    def app_version(self) -> str:
        return self.app_config.get("version", "0.1.0")

    @property
    def database_config(self) -> dict:
        return self.app_config.get("database", {})

    @property
    def queue_config(self) -> dict:
        return self.app_config.get("queue", {})


@dataclass
class GeneratedPrompt:
    """生成的 Prompt 结果。"""

    system_prompt: str
    user_prompt: str
    intent_hash: str


def _compute_hash(text: str) -> str:
    """计算文本的 SHA-256 哈希值。"""
    return hashlib.sha256(text.encode()).hexdigest()


def _build_dep_context(ctx: PromptContext, node_type: str = "", node_ref: object = None) -> str:
    """构建依赖图上下文文本（按节点类型精准注入，不注入全量依赖图）。"""
    if not ctx.dep_graph:
        return ""
    if node_type == "fn" and node_ref:
        return ctx.dep_graph.render_fn_context(node_ref.name)
    if node_type == "route" and node_ref:
        return ctx.dep_graph.render_route_context(node_ref.name)
    if node_type == "struct" and node_ref:
        return ctx.dep_graph.render_struct_context(node_ref.name)
    if node_type == "module" and node_ref:
        return ctx.dep_graph.render_module_context(node_ref.name)
    return ""


def _build_review_context(ctx: PromptContext, node_key: str) -> str:
    """构建针对特定节点的审核意见上下文。"""
    if not ctx.review_comments:
        return ""
    relevant = [c for c in ctx.review_comments if c.node_key == node_key]
    if not relevant:
        return ""
    lines = ["## 架构审核意见（请据此修正）"]
    for c in relevant:
        lines.append(f"- [{c.severity}] {c.message}")
        lines.append(f"  建议: {c.suggestion}")
    return "\n".join(lines)


def _get_python_fastapi_model_prompt(
    struct: StructDef, ctx: PromptContext
) -> GeneratedPrompt:
    """为 Python FastAPI 生成 Model 层 Prompt。"""
    fields_desc = []
    for field in struct.fields:
        type_name = field.type.base
        if field.type.is_optional:
            type_name = f"Optional[{type_name}]"
        if field.type.params:
            params = ", ".join(str(p) for p in field.type.params)
            type_name = f"{type_name}[{params}]"
        annotations = [a.name for a in field.annotations]
        fields_desc.append(f"    {field.name}: {type_name}  # @{annotations}")

    fields_str = "\n".join(fields_desc) if fields_desc else "    # 无字段"

    dep_ctx = _build_dep_context(ctx, "struct", struct)
    review_ctx = _build_review_context(ctx, f"struct:{struct.name}")

    from enjinc.prompts.python_fastapi import MODEL_SYSTEM as TEMPLATE
    system_prompt = TEMPLATE.format(
        table_name=f"{struct.name.lower()}s",
        dep_ctx=dep_ctx,
        review_ctx=review_ctx,
        fields_str=fields_str,
    )

    user_prompt = f"生成 {struct.name} 的 SQLAlchemy Model 类"

    intent_text = f"Model:{struct.name}:" + json.dumps(
        [f.to_dict() for f in struct.fields], sort_keys=True
    )
    intent_hash = _compute_hash(intent_text)

    return GeneratedPrompt(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        intent_hash=intent_hash,
    )


def _get_annotation_semantics(fn: FnDef) -> str:
    """提取 @api_contract/@data_plane 注解的语义描述，注入 prompt。"""
    lines = []
    annotation_names = {a.name for a in fn.annotations}
    if ANNO_API_CONTRACT in annotation_names:
        lines.append(
            "此函数标记了 @api_contract，必须严格遵守 OpenAPI 契约：\n"
            "1. 输入参数和返回类型必须与 API schema 精确匹配\n"
            "2. 必须包含完整的 HTTP 错误响应处理 (400/404/409/422)\n"
            "3. 必须使用 Pydantic 模型进行请求/响应验证"
        )
    if ANNO_DATA_PLANE in annotation_names:
        protocol, engine = get_data_plane_config(fn.annotations)
        lines.append(
            f"此函数标记了 @data_plane (protocol={protocol}, engine={engine})，是数据访问层：\n"
            "1. 必须只包含数据读写操作，不含业务逻辑\n"
            "2. 使用 SQLAlchemy ORM 进行数据库操作\n"
            "3. 必须处理数据库连接异常和超时\n"
            f"4. 数据协议: {protocol or 'SQL'}, 存储引擎: {engine or 'PostgreSQL'}"
        )
    return "\n".join(lines)


def _get_python_fastapi_method_prompt(fn: FnDef, ctx: PromptContext) -> GeneratedPrompt:
    """为 Python FastAPI 生成 Method 层 Prompt。"""
    params_str = ", ".join(f"{p.name}: {p.type.base}" for p in fn.params)
    return_type = fn.return_type.base if fn.return_type else "None"

    guard_rules = ""
    if fn.guard:
        guard_rules = "防御性校验规则:\n" + "\n".join(
            f"  - {g.expr}: {g.message}" for g in fn.guard
        )

    annotation_semantics = _get_annotation_semantics(fn)
    process_intent = fn.process.intent if fn.process else "无"

    dep_ctx = _build_dep_context(ctx, "fn", fn)
    review_ctx = _build_review_context(ctx, f"fn:{fn.name}")

    from enjinc.prompts.python_fastapi import METHOD_SYSTEM as TEMPLATE
    system_prompt = TEMPLATE.format(
        dep_ctx=dep_ctx,
        review_ctx=review_ctx,
        fn_name=fn.name,
        params_str=params_str,
        return_type=return_type,
        guard_rules=f"防御性校验规则:\n{guard_rules}" if guard_rules else "无防御性校验规则",
        annotation_semantics=annotation_semantics,
        process_intent=process_intent,
    )

    user_prompt = f"实现 {fn.name} 函数，业务逻辑: {process_intent}"

    intent_text = f"Method:{fn.name}:" + (fn.process.intent if fn.process else "native")
    intent_hash = _compute_hash(intent_text)

    return GeneratedPrompt(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        intent_hash=intent_hash,
    )


def _get_java_springboot_model_prompt(
    struct: StructDef, ctx: PromptContext
) -> GeneratedPrompt:
    """为 Java Spring Boot 生成 Model 层 Prompt。"""
    fields_desc = []
    for field in struct.fields:
        type_name = ENJIN_TO_JAVA.get(field.type.base, field.type.base)
        if field.type.is_optional:
            type_name = f"Optional<{type_name}>"

        annotations = [a.name for a in field.annotations]
        fields_desc.append(f"    private {type_name} {field.name};  // @{annotations}")

    fields_str = "\n".join(fields_desc) if fields_desc else "    // 无字段"

    dep_ctx = _build_dep_context(ctx, "struct", struct)
    review_ctx = _build_review_context(ctx, f"struct:{struct.name}")

    system_prompt = f"""你是一个专业的 Java Spring Boot 后端工程师。
你的任务是根据以下 struct 定义生成对应的 JPA Entity 代码。

目标框架: Java Spring Boot + JPA + MyBatis-Plus
实体名: {struct.name}
表名: {struct.name.lower()}s

{dep_ctx}

{review_ctx}

请生成符合以下规范的 Java 代码:
1. 使用 @Entity, @Table, @Column 等 JPA 注解
2. 使用 Lombok @Data, @NoArgsConstructor, @AllArgsConstructor, @Builder
3. 主键使用 @Id 和 @GeneratedValue(strategy = GenerationType.IDENTITY)
4. 字段名使用 camelCase，列名使用 snake_case
5. 日期类型使用 java.time.LocalDateTime
6. 返回纯 Java 代码，不要包含解释文字

字段定义:
{fields_str}

请只返回 Java 代码，不要包含 markdown 代码块标记。"""

    user_prompt = f"生成 {struct.name} 的 JPA Entity 类"

    intent_text = f"Model:{struct.name}:" + json.dumps(
        [f.to_dict() for f in struct.fields], sort_keys=True
    )
    intent_hash = _compute_hash(intent_text)

    return GeneratedPrompt(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        intent_hash=intent_hash,
    )


def _get_java_springboot_method_prompt(
    fn: FnDef, ctx: PromptContext
) -> GeneratedPrompt:
    """为 Java Spring Boot 生成 Method 层 Prompt。"""
    params_str = ", ".join(f"{p.name} {ENJIN_TO_JAVA.get(p.type.base, p.type.base)}" for p in fn.params)
    return_type = ENJIN_TO_JAVA.get(fn.return_type.base, fn.return_type.base) if fn.return_type else "void"

    guard_rules = ""
    if fn.guard:
        guard_rules = "防御性校验规则:\n" + "\n".join(
            f"  - {g.expr}: {g.message}" for g in fn.guard
        )

    annotation_semantics = _get_annotation_semantics(fn)
    process_intent = fn.process.intent if fn.process else "无"

    dep_ctx = _build_dep_context(ctx, "fn", fn)
    review_ctx = _build_review_context(ctx, f"fn:{fn.name}")

    system_prompt = f"""你是一个专业的 Java Spring Boot 后端工程师。
你的任务是根据以下函数定义生成对应的 Spring Service 方法代码。

目标框架: Java Spring Boot + MyBatis-Plus

{dep_ctx}

{review_ctx}

函数名: {fn.name}
参数: {params_str}
返回类型: {return_type}

{f"防御性校验规则:\n{guard_rules}" if guard_rules else "无防御性校验规则"}

{annotation_semantics}

业务意图: {process_intent}

请生成符合以下规范的 Java 代码:
1. 使用 @Service 注解的 Service 类
2. 使用 @Transactional 进行事务管理
3. 参数验证使用 if 条件和 IllegalArgumentException
4. 数据库操作使用 MyBatis-Plus 的 IService 和 BaseMapper
5. 返回结果使用 Optional 包装
6. 返回纯 Java 代码，不要包含解释文字

请只返回 Java 代码，不要包含 markdown 代码块标记。"""

    user_prompt = f"实现 {fn.name} 函数，业务逻辑: {process_intent}"

    intent_text = f"Method:{fn.name}:" + (fn.process.intent if fn.process else "native")
    intent_hash = _compute_hash(intent_text)

    return GeneratedPrompt(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        intent_hash=intent_hash,
    )


def _get_python_crawler_method_prompt(fn: FnDef, ctx: PromptContext) -> GeneratedPrompt:
    """为 Python Crawler 生成 Method 层 Prompt。"""
    params_str = ", ".join(f"{p.name}: {p.type.base}" for p in fn.params)
    return_type = fn.return_type.base if fn.return_type else "None"

    process_intent = fn.process.intent if fn.process else "无"

    dep_ctx = _build_dep_context(ctx, "fn", fn)
    review_ctx = _build_review_context(ctx, f"fn:{fn.name}")

    system_prompt = f"""你是一个专业的 Python 爬虫工程师。
你的任务是根据以下函数定义生成对应的爬虫方法代码。

目标框架: Python (httpx / Scrapy / Playwright)

{dep_ctx}

{review_ctx}

函数名: {fn.name}
参数: {params_str}
返回类型: {return_type}

业务意图: {process_intent}

请生成符合以下规范的 Python 代码:
1. 使用异步函数 async def（httpx 场景）
2. 或使用 Scrapy Spider 的 parse 方法（Scrapy 场景）
3. 或使用 Playwright 的 page 操作（Playwright 场景）
4. 包含错误处理和重试逻辑
5. 返回纯 Python 代码，不要包含解释文字

请只返回 Python 代码，不要包含 markdown 代码块标记。"""

    user_prompt = f"实现 {fn.name} 爬虫函数，业务逻辑: {process_intent}"

    intent_text = f"Method:{fn.name}:" + (fn.process.intent if fn.process else "native")
    intent_hash = _compute_hash(intent_text)

    return GeneratedPrompt(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        intent_hash=intent_hash,
    )


class PromptRouter:
    """Prompt 路由中枢，根据 AST 节点类型分发到对应的 Prompt 生成器。"""

    def __init__(self, target_lang: str = "python_fastapi"):
        self.target_lang = target_lang
        self._prompt_generators = {
            ("struct", "python_fastapi"): _get_python_fastapi_model_prompt,
            ("fn", "python_fastapi"): _get_python_fastapi_method_prompt,
            ("struct", "java_springboot"): _get_java_springboot_model_prompt,
            ("fn", "java_springboot"): _get_java_springboot_method_prompt,
            ("fn", "python_crawler"): _get_python_crawler_method_prompt,
        }

    def route_struct(self, struct: StructDef, ctx: PromptContext) -> GeneratedPrompt:
        """为 struct 生成 Prompt。"""
        key = ("struct", self.target_lang)
        if key in self._prompt_generators:
            return self._prompt_generators[key](struct, ctx)
        return self._fallback_prompt(f"struct:{struct.name}")

    def route_fn(self, fn: FnDef, ctx: PromptContext) -> GeneratedPrompt:
        """为 fn 生成 Prompt。"""
        key = ("fn", self.target_lang)
        if key in self._prompt_generators:
            return self._prompt_generators[key](fn, ctx)
        return self._fallback_prompt(f"fn:{fn.name}")

    def route_module(self, module: ModuleDef, ctx: PromptContext) -> GeneratedPrompt:
        """为 module 生成 Prompt。"""
        init_intent = module.init.intent if module.init else "初始化模块"
        schedule_desc = ""
        if module.schedules:
            schedule_desc = "\n调度任务:\n" + "\n".join(
                f"  - {s.frequency} at {s.cron}: {s.intent}" for s in module.schedules
            )

        # 提取 @engine 配置，影响 prompt 内容
        engine_desc = ""
        engine_type, framework = get_engine_config(module.annotations)
        if engine_type:
            engine_desc = f"\n引擎类型: {engine_type} ({framework})"
            framework_prompt = ENGINE_REGISTRY.get(engine_type, {}).get(framework, "")
            if framework_prompt:
                engine_desc += f"\n{framework_prompt}"

        dep_ctx = _build_dep_context(ctx, "module", module)
        review_ctx = _build_review_context(ctx, f"module:{module.name}")

        system_prompt = f"""你是一个专业的 Python/Java 后端工程师。
你的任务是为模块生成初始化和调度代码。

模块名: {module.name}
依赖: {", ".join(module.dependencies)}
导出: {", ".join(f"{e.action}={e.target}" for e in module.exports)}
{engine_desc}

{dep_ctx}

{review_ctx}

初始化意图: {init_intent}
{schedule_desc}

请生成符合以下规范的代码:
1. 初始化代码包含资源连接池初始化
2. 调度代码使用 @Scheduled 注解（Java）或 APScheduler（Python）
3. 返回纯代码，不要包含解释文字

请只返回代码，不要包含 markdown 代码块标记。"""

        user_prompt = f"实现 {module.name} 模块的初始化和调度"

        intent_text = f"Module:{module.name}:" + (
            module.init.intent if module.init else ""
        )
        intent_hash = _compute_hash(intent_text)

        return GeneratedPrompt(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            intent_hash=intent_hash,
        )

    def route_route(self, route: RouteDef, ctx: PromptContext) -> GeneratedPrompt:
        """为 route 生成 Prompt。"""
        endpoints_desc = "\n".join(
            f"  - {e.method} {e.path} -> {e.handler}" for e in route.endpoints
        )

        prefix = get_prefix_path(route.annotations)
        auth = get_auth_strategy(route.annotations)

        dep_ctx = _build_dep_context(ctx, "route", route)
        review_ctx = _build_review_context(ctx, f"route:{route.name}")

        system_prompt = f"""你是一个专业的后端工程师。
你的任务是为 HTTP 路由生成代码。

路由名: {route.name}
前缀: {prefix}
认证: {auth}

{dep_ctx}

{review_ctx}

端点:
{endpoints_desc}

请生成符合以下规范的代码:
1. Python FastAPI 使用 @router.decorator
2. Java Spring Boot 使用 @RestController 和 @RequestMapping
3. 返回纯代码，不要包含解释文字

请只返回代码，不要包含 markdown 代码块标记。"""

        user_prompt = f"实现 {route.name} 路由的 HTTP 端点"

        intent_text = f"Route:{route.name}:" + json.dumps(
            [(e.method, e.path, e.handler) for e in route.endpoints], sort_keys=True
        )
        intent_hash = _compute_hash(intent_text)

        return GeneratedPrompt(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            intent_hash=intent_hash,
        )

    def _fallback_prompt(self, node_desc: str) -> GeneratedPrompt:
        """兜底 Prompt 生成器。"""
        system_prompt = "你是一个专业的程序员。请根据以下描述生成代码。"
        user_prompt = f"生成 {node_desc} 的代码"
        intent_hash = _compute_hash(node_desc)

        return GeneratedPrompt(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            intent_hash=intent_hash,
        )


def create_router(target_lang: str) -> PromptRouter:
    """创建指定目标语言的 Prompt 路由。"""
    return PromptRouter(target_lang=target_lang)

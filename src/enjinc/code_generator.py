"""
============================================================
EnJin Code Generator (code_generator.py)
============================================================
本模块负责协调 Prompt Router 和 LLM Client，将 process 意图转化为目标语言代码。

核心流程:
1. 根据 AST 节点类型通过 PromptRouter 生成 Prompt
2. 通过 LLMClient 调用 AI 生成代码（支持按层使用不同模型）
3. 处理 @locked 缓存逻辑
4. Master AI 审核生成代码（可选）
5. 将生成的代码注入到 Jinja2 模板的 process 插槽中

缓存机制:
    - 基于 intent_hash 的本地缓存
    - 支持 enjin.lock 文件持久化
    - 支持多目标栈独立缓存
============================================================
"""

from __future__ import annotations

import json
import logging
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from enjinc.annotations import is_human_maintained
from enjinc.ast_nodes import (
    ApplicationConfig,
    FnDef,
    ModuleDef,
    Program,
    RouteDef,
    StructDef,
)
from enjinc.dependency_graph import DependencyGraph
from enjinc.prompt_router import (
    GeneratedPrompt,
    PromptContext,
    PromptRouter,
    create_router,
)
from enjinc.llm_client import (
    LLMClient,
    LLMConfig,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    MultiModelConfig,
    create_client,
    create_multi_client,
)
from enjinc.reviewer import MasterReviewer

logger = logging.getLogger(__name__)


@dataclass
class GenerationResult:
    """代码生成结果。"""

    node_type: str
    node_name: str
    generated_code: str
    intent_hash: str
    cached: bool
    usage: Optional[LLMUsage] = None


@dataclass
class GenerationStats:
    """生成统计信息。"""

    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_usage: LLMUsage = field(default_factory=lambda: LLMUsage(0, 0, 0))

    def record_hit(self):
        self.cache_hits += 1
        self.total_requests += 1

    def record_miss(self, usage: LLMUsage):
        self.cache_misses += 1
        self.total_requests += 1
        self.total_usage.prompt_tokens += usage.prompt_tokens
        self.total_usage.completion_tokens += usage.completion_tokens
        self.total_usage.total_tokens += usage.total_tokens


@dataclass
class EnjinLockEntry:
    """enjin.lock 单条记录。"""

    intent_hash: str
    target_lang: str
    generated_code: str
    model: str
    created_at: str
    node_type: str = ""
    node_name: str = ""
    tokens_consumed: Optional[dict] = None


class EnjinLock:
    """enjin.lock 文件管理器。"""

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path
        self._cache: dict[str, EnjinLockEntry] = {}
        self._load()

    def _load(self):
        """从文件加载缓存（向后兼容旧格式）。"""
        if self.lock_path.exists():
            try:
                data = json.loads(self.lock_path.read_text(encoding="utf-8"))
                for entry in data.get("entries", []):
                    key = f"{entry['intent_hash']}:{entry['target_lang']}"
                    self._cache[key] = EnjinLockEntry(
                        intent_hash=entry["intent_hash"],
                        target_lang=entry["target_lang"],
                        generated_code=entry["generated_code"],
                        model=entry["model"],
                        created_at=entry["created_at"],
                        node_type=entry.get("node_type", ""),
                        node_name=entry.get("node_name", ""),
                        tokens_consumed=entry.get("tokens_consumed"),
                    )
                logger.info(f"Loaded {len(self._cache)} entries from enjin.lock")
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logger.warning(f"Failed to load enjin.lock: {e}")

    def _save(self):
        """保存缓存到文件。"""
        from enjinc import __version__
        data = {
            "version": "1.0",
            "compiler_version": __version__,
            "entries": [entry.__dict__ for entry in self._cache.values()],
        }
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info(f"Saved {len(self._cache)} entries to enjin.lock")

    def get(self, intent_hash: str, target_lang: str) -> Optional[str]:
        """获取缓存的代码。"""
        key = f"{intent_hash}:{target_lang}"
        entry = self._cache.get(key)
        return entry.generated_code if entry else None

    def put(self, intent_hash: str, target_lang: str, code: str, model: str,
            node_type: str = "", node_name: str = "",
            tokens_consumed: Optional[dict] = None):
        """缓存代码。"""
        import datetime

        key = f"{intent_hash}:{target_lang}"
        self._cache[key] = EnjinLockEntry(
            intent_hash=intent_hash,
            target_lang=target_lang,
            generated_code=code,
            model=model,
            created_at=datetime.datetime.now().isoformat(),
            node_type=node_type,
            node_name=node_name,
            tokens_consumed=tokens_consumed,
        )

    def flush(self):
        """强制刷新到磁盘。"""
        self._save()


class CodeGenerator:
    """代码生成器，协调 Prompt Router、LLM Client 和 Master Reviewer。"""

    def __init__(
        self,
        target_lang: str,
        multi_config: Optional[MultiModelConfig] = None,
        lock_path: Optional[Path] = None,
        use_ai: bool = True,
        no_review: bool = False,
    ):
        self.target_lang = target_lang
        self.router = create_router(target_lang)
        self.lock_path = lock_path or Path(".enjinc/enjin.lock")
        self.lock = EnjinLock(self.lock_path) if use_ai else None
        self.use_ai = use_ai
        self.stats = GenerationStats()
        self.no_review = no_review

        if use_ai and multi_config:
            self._multi_config = multi_config
            self._clients = create_multi_client(multi_config)
            if multi_config.master and not no_review:
                self._reviewer = MasterReviewer(LLMClient(multi_config.master))
            else:
                self._reviewer = None
        elif use_ai:
            default_config = LLMConfig()
            self._multi_config = MultiModelConfig(default=default_config)
            self._clients = {"struct": create_client(), "fn": create_client(),
                             "module": create_client(), "route": create_client()}
            self._reviewer = None
        else:
            self._multi_config = None
            self._clients = {}
            self._reviewer = None

    def _get_client(self, node_type: str) -> LLMClient:
        """获取对应层的 LLMClient。"""
        return self._clients.get(node_type) or self._clients.get("fn")

    def _generate_node(
        self,
        node_type: str,
        node_name: str,
        prompt: GeneratedPrompt,
        lock_cache: bool = True,
    ) -> GenerationResult:
        """通用节点生成逻辑：检查缓存 → 调用 LLM → 写入锁。"""
        if lock_cache:
            cached_code = (
                self.lock.get(prompt.intent_hash, self.target_lang)
                if self.lock
                else None
            )
            if cached_code:
                self.stats.record_hit()
                return GenerationResult(
                    node_type=node_type,
                    node_name=node_name,
                    generated_code=cached_code,
                    intent_hash=prompt.intent_hash,
                    cached=True,
                )

        if not self.use_ai:
            return GenerationResult(
                node_type=node_type,
                node_name=node_name,
                generated_code=f"# TODO: Implement {node_name} with AI",
                intent_hash=prompt.intent_hash,
                cached=False,
            )

        client = self._get_client(node_type)
        response = client.generate(
            LLMRequest(
                system_prompt=prompt.system_prompt,
                user_prompt=prompt.user_prompt,
                intent_hash=prompt.intent_hash,
            )
        )

        self.stats.record_miss(response.usage)
        if self.lock and lock_cache:
            tokens = None
            if response.usage:
                tokens = {
                    "input": response.usage.prompt_tokens,
                    "output": response.usage.completion_tokens,
                }
            self.lock.put(
                prompt.intent_hash, self.target_lang, response.content, response.model,
                node_type=node_type, node_name=node_name,
                tokens_consumed=tokens,
            )

        return GenerationResult(
            node_type=node_type,
            node_name=node_name,
            generated_code=response.content,
            intent_hash=prompt.intent_hash,
            cached=response.cached,
            usage=response.usage,
        )

    def generate_struct(
        self, struct: StructDef, ctx: PromptContext
    ) -> GenerationResult:
        """生成 struct 的代码。"""
        prompt = self.router.route_struct(struct, ctx)
        return self._generate_node("struct", struct.name, prompt)

    def generate_fn(self, fn: FnDef, ctx: PromptContext) -> GenerationResult:
        """生成 fn 的代码。"""
        if is_human_maintained(fn.annotations):
            return GenerationResult(
                node_type="fn",
                node_name=fn.name,
                generated_code=f"# @human_maintained: AI generation disabled for {fn.name}",
                intent_hash="",
                cached=False,
            )

        if fn.native_blocks:
            native_code = "\n".join(
                nb.code
                for nb in fn.native_blocks
                if nb.target == self._get_native_target()
            )
            return GenerationResult(
                node_type="fn",
                node_name=fn.name,
                generated_code=native_code,
                intent_hash="",
                cached=False,
            )

        if fn.is_locked:
            cached_code = (
                self.lock.get(self._compute_fn_hash(fn), self.target_lang)
                if self.lock
                else None
            )
            if cached_code:
                self.stats.record_hit()
                return GenerationResult(
                    node_type="fn",
                    node_name=fn.name,
                    generated_code=cached_code,
                    intent_hash=self._compute_fn_hash(fn),
                    cached=True,
                )

        prompt = self.router.route_fn(fn, ctx)
        return self._generate_node("fn", fn.name, prompt, lock_cache=fn.is_locked)

    def generate_module(
        self, module: ModuleDef, ctx: PromptContext
    ) -> GenerationResult:
        """生成 module 的代码。"""
        prompt = self.router.route_module(module, ctx)
        return self._generate_node("module", module.name, prompt)

    def generate_route(self, route: RouteDef, ctx: PromptContext) -> GenerationResult:
        """生成 route 的代码。"""
        prompt = self.router.route_route(route, ctx)
        return self._generate_node("route", route.name, prompt)

    def generate_program(self, program: Program) -> dict[str, GenerationResult]:
        """生成整个 Program 的代码。"""
        app_config = program.application.config if program.application else {}
        dep_graph = DependencyGraph.build(program)

        ctx = PromptContext(
            program=program,
            target_lang=self.target_lang,
            app_config=app_config,
            dep_graph=dep_graph,
        )

        results = {}

        for fn in program.functions:
            results[f"fn:{fn.name}"] = self.generate_fn(fn, ctx)

        for route in program.routes:
            results[f"route:{route.name}"] = self.generate_route(route, ctx)

        # Master AI 审核
        if self._reviewer:
            review = self._reviewer.review(dep_graph, results)
            if not review.approved and review.comments:
                logger.info(
                    f"Master AI review: {len(review.comments)} issues, re-generating"
                )
                ctx.review_comments = review.comments
                self._regenerate_flagged(program, ctx, results, review.comments)

        # AST 编辑距离审计（逻辑守恒校验）
        self._audit_generated_code(results)

        if self.lock:
            self.lock.flush()

        return results

    def _regenerate_flagged(
        self,
        program: Program,
        ctx: PromptContext,
        results: dict[str, GenerationResult],
        comments: list,
    ) -> None:
        """根据 Master AI 审核意见，重新生成有问题的节点。"""
        flagged_keys = {c.node_key for c in comments}

        for struct in program.structs:
            key = f"struct:{struct.name}"
            if key in flagged_keys:
                results[key] = self.generate_struct(struct, ctx)

        for fn in program.functions:
            key = f"fn:{fn.name}"
            if key in flagged_keys:
                results[key] = self.generate_fn(fn, ctx)

        for module in program.modules:
            key = f"module:{module.name}"
            if key in flagged_keys:
                results[key] = self.generate_module(module, ctx)

        for route in program.routes:
            key = f"route:{route.name}"
            if key in flagged_keys:
                results[key] = self.generate_route(route, ctx)

    def _get_native_target(self) -> str:
        """获取当前目标语言对应的 native 目标。"""
        from enjinc.targets import get_renderer
        renderer = get_renderer(self.target_lang)
        if renderer:
            return renderer.native_lang
        return self.target_lang.split("_")[0]

    def _audit_generated_code(self, results: dict[str, GenerationResult]) -> None:
        """AST 编辑距离审计：对比 lock 文件中的旧代码与新生成的代码。"""
        if not self.lock:
            return
        try:
            from enjinc.ast_audit import audit_code
        except ImportError:
            return

        lang = self._get_native_target()
        for key, result in results.items():
            if result.cached or not result.generated_code:
                continue
            old_code = self.lock.get(result.intent_hash, self.target_lang)
            if not old_code or old_code == result.generated_code:
                continue
            audit = audit_code(old_code, result.generated_code, lang)
            if not audit.passed:
                logger.warning(
                    f"AST audit failed for {key}: distance={audit.distance.total_distance:.2f}, "
                    f"blocked={[n for n in audit.blocked_nodes]}"
                )
            elif audit.warnings:
                for w in audit.warnings:
                    logger.info(f"AST audit warning for {key}: {w}")

    def _compute_fn_hash(self, fn: FnDef) -> str:
        """计算 fn 的哈希值。"""
        content = json.dumps(fn.to_dict(), sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()

    def get_stats(self) -> GenerationStats:
        """获取生成统计信息。"""
        return self.stats


def create_generator(
    target_lang: str,
    provider: str = "openai",
    model: str = "gpt-4",
    use_ai: bool = False,
    master_provider: Optional[str] = None,
    master_model: Optional[str] = None,
    fn_provider: Optional[str] = None,
    fn_model: Optional[str] = None,
    no_review: bool = False,
) -> CodeGenerator:
    """创建代码生成器。"""
    if not use_ai:
        return CodeGenerator(target_lang=target_lang, use_ai=False)

    default_config = LLMConfig(provider=provider, model=model)
    overrides = {}
    if fn_provider or fn_model:
        overrides["fn"] = LLMConfig(
            provider=fn_provider or provider,
            model=fn_model or model,
        )

    master_config = None
    if master_provider or master_model:
        master_config = LLMConfig(
            provider=master_provider or provider,
            model=master_model or model,
        )

    multi_config = MultiModelConfig(
        default=default_config,
        overrides=overrides,
        master=master_config,
    )

    return CodeGenerator(
        target_lang=target_lang,
        multi_config=multi_config,
        use_ai=True,
        no_review=no_review,
    )

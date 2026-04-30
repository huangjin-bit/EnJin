"""
============================================================
EnJin AI Generation 测试 (test_ai_generation.py)
============================================================
验证 prompt_router.py, llm_client.py, code_generator.py 的功能。

测试覆盖:
    1. PromptRouter - 不同目标语言的 Prompt 生成
    2. LLMClient - 缓存和熔断机制
    3. CodeGenerator - 代码生成流程
    4. EnjinLock - 缓存持久化
============================================================
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from enjinc.ast_nodes import (
    ApplicationConfig,
    FnDef,
    GuardRule,
    ModuleDef,
    ModuleExport,
    Param,
    ProcessIntent,
    Program,
    RouteDef,
    EndpointDef,
    ScheduleDef,
    StructDef,
    FieldDef,
    TypeRef,
    Annotation,
)
from enjinc.prompt_router import (
    GeneratedPrompt,
    PromptContext,
    PromptRouter,
    create_router,
    _compute_hash,
)
from enjinc.llm_client import (
    LLMClient,
    LLMConfig,
    LLMResponse,
    LLMUsage,
    LLMRequest,
    LLMCircuitBreaker,
    create_client,
    LLMConfigError,
)
from enjinc.code_generator import (
    CodeGenerator,
    GenerationResult,
    GenerationStats,
    EnjinLock,
    EnjinLockEntry,
    create_generator,
)


@pytest.fixture
def sample_program() -> Program:
    """创建示例 Program。"""
    user_struct = StructDef(
        name="User",
        annotations=[Annotation(name="table", args=["users"])],
        fields=[
            FieldDef(
                name="id",
                type=TypeRef(base="Int"),
                annotations=[Annotation(name="primary")],
            ),
            FieldDef(
                name="username",
                type=TypeRef(base="String"),
                annotations=[Annotation(name="unique")],
            ),
            FieldDef(
                name="email",
                type=TypeRef(base="String"),
                annotations=[Annotation(name="unique")],
            ),
        ],
    )

    register_fn = FnDef(
        name="register_user",
        annotations=[Annotation(name="transactional")],
        params=[
            Param(name="username", type=TypeRef(base="String")),
            Param(name="email", type=TypeRef(base="String")),
            Param(name="password", type=TypeRef(base="String")),
        ],
        return_type=TypeRef(base="User"),
        guard=[
            GuardRule(expr="username.length > 0", message="用户名不能为空"),
            GuardRule(expr="email.contains('@')", message="邮箱格式不合法"),
        ],
        process=ProcessIntent(intent="创建一个新用户，密码使用 bcrypt 哈希加密"),
    )

    order_module = ModuleDef(
        name="OrderManager",
        annotations=[Annotation(name="domain", kwargs={"name": "order"})],
        dependencies=["Order", "create_order", "pay_order"],
        exports=[
            ModuleExport(action="create", target="create_order"),
            ModuleExport(action="pay", target="pay_order"),
        ],
        init=ProcessIntent(intent="初始化订单服务"),
        schedules=[
            ScheduleDef(frequency="daily", cron="02:00", intent="取消超时订单"),
        ],
    )

    order_service = RouteDef(
        name="OrderService",
        annotations=[Annotation(name="prefix", args=["/api/v1/orders"])],
        dependencies=["OrderManager"],
        endpoints=[
            EndpointDef(method="POST", path="/create", handler="create"),
            EndpointDef(method="POST", path="/pay", handler="pay"),
        ],
    )

    return Program(
        application=ApplicationConfig(
            config={
                "name": "test-app",
                "version": "1.0.0",
                "target": "python_fastapi",
                "database": {"driver": "postgresql"},
            }
        ),
        structs=[user_struct],
        functions=[register_fn],
        modules=[order_module],
        routes=[order_service],
    )


class TestPromptRouter:
    """测试 Prompt Router。"""

    def test_create_router_python_fastapi(self):
        """创建 Python FastAPI Router。"""
        router = create_router("python_fastapi")
        assert router.target_lang == "python_fastapi"

    def test_create_router_java_springboot(self):
        """创建 Java Spring Boot Router。"""
        router = create_router("java_springboot")
        assert router.target_lang == "java_springboot"

    def test_route_struct_python_fastapi(self, sample_program):
        """路由 struct 到 Python FastAPI Prompt。"""
        router = create_router("python_fastapi")
        ctx = PromptContext(program=sample_program, target_lang="python_fastapi")
        struct = sample_program.structs[0]

        prompt = router.route_struct(struct, ctx)

        assert isinstance(prompt, GeneratedPrompt)
        assert "Python FastAPI" in prompt.system_prompt
        assert "SQLAlchemy" in prompt.system_prompt
        assert "id" in prompt.system_prompt
        assert "username" in prompt.system_prompt
        assert len(prompt.intent_hash) == 64

    def test_route_fn_python_fastapi(self, sample_program):
        """路由 fn 到 Python FastAPI Prompt。"""
        router = create_router("python_fastapi")
        ctx = PromptContext(program=sample_program, target_lang="python_fastapi")
        fn = sample_program.functions[0]

        prompt = router.route_fn(fn, ctx)

        assert isinstance(prompt, GeneratedPrompt)
        assert "FastAPI" in prompt.system_prompt
        assert "register_user" in prompt.system_prompt
        assert "async def" in prompt.system_prompt
        assert "bcrypt" in prompt.system_prompt or "加密" in prompt.system_prompt

    def test_route_struct_java_springboot(self, sample_program):
        """路由 struct 到 Java Spring Boot Prompt。"""
        router = create_router("java_springboot")
        ctx = PromptContext(program=sample_program, target_lang="java_springboot")
        struct = sample_program.structs[0]

        prompt = router.route_struct(struct, ctx)

        assert isinstance(prompt, GeneratedPrompt)
        assert "Java Spring Boot" in prompt.system_prompt
        assert "JPA" in prompt.system_prompt
        assert "Entity" in prompt.system_prompt

    def test_route_module(self, sample_program):
        """路由 module Prompt。"""
        router = create_router("python_fastapi")
        ctx = PromptContext(program=sample_program, target_lang="python_fastapi")
        module = sample_program.modules[0]

        prompt = router.route_module(module, ctx)

        assert isinstance(prompt, GeneratedPrompt)
        assert "OrderManager" in prompt.system_prompt
        assert "初始化" in prompt.system_prompt
        assert "调度" in prompt.system_prompt

    def test_route_route(self, sample_program):
        """路由 route Prompt。"""
        router = create_router("python_fastapi")
        ctx = PromptContext(program=sample_program, target_lang="python_fastapi")
        route = sample_program.routes[0]

        prompt = router.route_route(route, ctx)

        assert isinstance(prompt, GeneratedPrompt)
        assert "OrderService" in prompt.system_prompt
        assert "POST" in prompt.system_prompt
        assert "/api/v1/orders" in prompt.system_prompt

    def test_compute_hash_deterministic(self, sample_program):
        """测试哈希计算是确定性的。"""
        struct = sample_program.structs[0]
        router = create_router("python_fastapi")
        ctx = PromptContext(program=sample_program, target_lang="python_fastapi")

        prompt1 = router.route_struct(struct, ctx)
        prompt2 = router.route_struct(struct, ctx)

        assert prompt1.intent_hash == prompt2.intent_hash

    def test_prompt_context_properties(self, sample_program):
        """测试 PromptContext 属性。"""
        app_config = (
            sample_program.application.config if sample_program.application else {}
        )
        ctx = PromptContext(
            program=sample_program, target_lang="python_fastapi", app_config=app_config
        )

        assert ctx.app_name == "test-app"
        assert ctx.app_version == "1.0.0"
        assert ctx.database_config.get("driver") == "postgresql"


class TestLLMCircuitBreaker:
    """测试 LLM 熔断器。"""

    def test_circuit_breaker_initial_state(self):
        """熔断器初始状态为关闭。"""
        cb = LLMCircuitBreaker(failure_threshold=3)
        assert cb.is_open is False
        assert cb.can_attempt() is True

    def test_circuit_breaker_opens_after_threshold(self):
        """熔断器在连续失败后打开。"""
        cb = LLMCircuitBreaker(failure_threshold=3)

        cb.record_failure()
        assert cb.can_attempt() is True
        cb.record_failure()
        assert cb.can_attempt() is True
        cb.record_failure()
        assert cb.is_open is True
        assert cb.can_attempt() is False

    def test_circuit_breaker_closes_after_recovery(self):
        """熔断器在恢复时间后可以再次尝试。"""
        import time

        cb = LLMCircuitBreaker(failure_threshold=1, recovery_timeout=1)

        cb.record_failure()
        assert cb.is_open is True
        assert cb.can_attempt() is False

        time.sleep(1.1)
        assert cb.can_attempt() is True
        assert cb.is_open is False

    def test_circuit_breaker_records_success(self):
        """熔断器记录成功。"""
        cb = LLMCircuitBreaker(failure_threshold=3)

        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.failures == 0
        assert cb.is_open is False


class TestLLMClient:
    """测试 LLM Client。"""

    def test_llm_config_defaults(self):
        """测试 LLM 配置默认值。"""
        config = LLMConfig()
        assert config.provider == "openai"
        assert config.model == "gpt-4"
        assert config.max_tokens == 2000
        assert config.temperature == 0.2

    def test_llm_request(self):
        """测试 LLM 请求创建。"""
        request = LLMRequest(
            system_prompt="You are a coder",
            user_prompt="Write hello world",
            intent_hash="abc123",
        )
        assert request.system_prompt == "You are a coder"
        assert request.user_prompt == "Write hello world"
        assert request.intent_hash == "abc123"

    def test_create_client(self):
        """测试创建 LLM 客户端。"""
        client = create_client(provider="openai", model="gpt-4")
        assert isinstance(client, LLMClient)
        assert client.config.provider == "openai"
        assert client.config.model == "gpt-4"


class TestCodeGenerator:
    """测试 Code Generator。"""

    def test_create_generator(self):
        """测试创建代码生成器。"""
        gen = create_generator("python_fastapi", use_ai=False)
        assert isinstance(gen, CodeGenerator)
        assert gen.target_lang == "python_fastapi"
        assert gen.use_ai is False

    def test_generator_uses_lock_cache(self, tmp_path, sample_program):
        """测试生成器使用 lock 缓存。"""
        lock_path = tmp_path / ".enjinc" / "enjin.lock"
        gen = create_generator("python_fastapi", use_ai=True)
        gen.lock_path = lock_path
        gen.lock = EnjinLock(lock_path)

        ctx = PromptContext(program=sample_program, target_lang="python_fastapi")
        struct = sample_program.structs[0]

        prompt = gen.router.route_struct(struct, ctx)
        gen.lock.put(prompt.intent_hash, "python_fastapi", "# cached code", "gpt-4")

        result = gen.generate_struct(struct, ctx)
        assert result.cached is True
        assert result.generated_code == "# cached code"

    def test_generator_no_ai_returns_placeholder(self, sample_program):
        """测试 use_ai=False 时返回占位符。"""
        gen = create_generator("python_fastapi", use_ai=False)
        ctx = PromptContext(program=sample_program, target_lang="python_fastapi")
        struct = sample_program.structs[0]

        result = gen.generate_struct(struct, ctx)
        assert "TODO" in result.generated_code
        assert result.cached is False

    def test_generator_native_block(self, sample_program):
        """测试生成器处理 native 块。"""
        fn = FnDef(
            name="custom_hash",
            native_blocks=[
                MagicMock(
                    target="python",
                    code="import hashlib\nreturn hashlib.md5(data).hexdigest()",
                )
            ],
        )
        gen = create_generator("python_fastapi", use_ai=True)
        ctx = PromptContext(program=sample_program, target_lang="python_fastapi")

        with patch.object(gen, "_get_native_target", return_value="python"):
            result = gen.generate_fn(fn, ctx)

        assert result.node_type == "fn"
        assert "hashlib" in result.generated_code or "md5" in result.generated_code

    def test_generation_stats(self, sample_program):
        """测试生成统计。"""
        stats = GenerationStats()
        assert stats.total_requests == 0
        assert stats.cache_hits == 0
        assert stats.cache_misses == 0

        stats.record_hit()
        assert stats.total_requests == 1
        assert stats.cache_hits == 1

        stats.record_miss(LLMUsage(100, 50, 150))
        assert stats.total_requests == 2
        assert stats.cache_misses == 1
        assert stats.total_usage.total_tokens == 150

    def test_generator_stats_accumulation(self, sample_program):
        """测试生成器统计累积。"""
        gen = create_generator("python_fastapi", use_ai=False)
        ctx = PromptContext(program=sample_program, target_lang="python_fastapi")

        result1 = gen.generate_struct(sample_program.structs[0], ctx)
        result2 = gen.generate_fn(sample_program.functions[0], ctx)

        stats = gen.get_stats()
        assert stats.total_requests == 0
        assert result1.cached is False
        assert result2.cached is False


class TestEnjinLock:
    """测试 enjin.lock 文件管理。"""

    def test_lock_entry_creation(self):
        """测试锁条目创建。"""
        entry = EnjinLockEntry(
            intent_hash="abc123",
            target_lang="python_fastapi",
            generated_code="print('hello')",
            model="gpt-4",
            created_at="2024-01-01T00:00:00",
        )
        assert entry.intent_hash == "abc123"
        assert entry.target_lang == "python_fastapi"
        assert entry.generated_code == "print('hello')"

    def test_lock_get_miss(self, tmp_path):
        """测试缓存未命中。"""
        lock_path = tmp_path / "enjin.lock"
        lock = EnjinLock(lock_path)

        result = lock.get("nonexistent", "python_fastapi")
        assert result is None

    def test_lock_put_and_get(self, tmp_path):
        """测试缓存存取。"""
        lock_path = tmp_path / "enjin.lock"
        lock = EnjinLock(lock_path)

        lock.put("hash123", "python_fastapi", "print('hello')", "gpt-4")
        result = lock.get("hash123", "python_fastapi")

        assert result == "print('hello')"

    def test_lock_flush_writes_file(self, tmp_path):
        """测试 flush 写入文件。"""
        lock_path = tmp_path / "enjin.lock"
        lock = EnjinLock(lock_path)

        lock.put("hash123", "python_fastapi", "print('hello')", "gpt-4")
        lock.flush()

        assert lock_path.exists()
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        assert len(data["entries"]) == 1
        assert data["entries"][0]["intent_hash"] == "hash123"

    def test_lock_load_existing(self, tmp_path):
        """测试加载已存在的 lock 文件。"""
        lock_path = tmp_path / "enjin.lock"
        lock_data = {
            "version": "1.0",
            "entries": [
                {
                    "intent_hash": "existing_hash",
                    "target_lang": "python_fastapi",
                    "generated_code": "print('existing')",
                    "model": "gpt-4",
                    "created_at": "2024-01-01T00:00:00",
                }
            ],
        }
        lock_path.write_text(json.dumps(lock_data), encoding="utf-8")

        lock = EnjinLock(lock_path)
        result = lock.get("existing_hash", "python_fastapi")

        assert result == "print('existing')"

    def test_lock_multiple_targets(self, tmp_path):
        """测试多目标栈独立缓存。"""
        lock_path = tmp_path / "enjin.lock"
        lock = EnjinLock(lock_path)

        lock.put("hash123", "python_fastapi", "# python", "gpt-4")
        lock.put("hash123", "java_springboot", "// java", "gpt-4")

        assert lock.get("hash123", "python_fastapi") == "# python"
        assert lock.get("hash123", "java_springboot") == "// java"
        assert lock.get("hash123", "python_crawler") is None


class TestIntegration:
    """集成测试。"""

    def test_full_pipeline_without_ai(self, sample_program):
        """测试完整流水线（无 AI）。"""
        gen = create_generator("python_fastapi", use_ai=False)

        results = gen.generate_program(sample_program)

        assert len(results) == 2
        assert "fn:register_user" in results
        assert "route:OrderService" in results

        for key, result in results.items():
            assert isinstance(result, GenerationResult)
            assert result.node_name
            if not result.cached:
                assert "TODO" in result.generated_code or result.generated_code

    def test_filtered_generation(self, sample_program):
        """测试选择性生成。"""
        gen = create_generator("java_springboot", use_ai=False)
        ctx = PromptContext(program=sample_program, target_lang="java_springboot")

        result = gen.generate_struct(sample_program.structs[0], ctx)
        assert result.node_type == "struct"
        assert result.node_name == "User"


class TestHumanMaintainedGeneration:
    """验证 @human_maintained fn 在 code_generator 中不触发 LLM 调用。"""

    def _make_human_maintained_fn(self):
        """创建带 @human_maintained 注解的 fn。"""
        from enjinc.ast_nodes import FnDef, Annotation, Param, TypeRef, ProcessIntent
        return FnDef(
            name="legacy_auth",
            params=[Param(name="token", type=TypeRef(base="String"))],
            return_type=TypeRef(base="Bool"),
            annotations=[Annotation(name="human_maintained", args=[], kwargs={})],
            process=ProcessIntent(intent="遗留认证逻辑"),
        )

    def test_human_maintained_returns_placeholder(self):
        """@human_maintained fn 应返回占位注释，不调用 LLM。"""
        fn = self._make_human_maintained_fn()
        gen = CodeGenerator(target_lang="python_fastapi", use_ai=True)
        ctx = PromptContext(program=Program(), target_lang="python_fastapi")
        result = gen.generate_fn(fn, ctx)

        assert "@human_maintained" in result.generated_code
        assert result.cached is False
        assert result.intent_hash == ""

    def test_human_maintained_no_stats_impact(self):
        """@human_maintained fn 不应影响 cache hit/miss 统计。"""
        fn = self._make_human_maintained_fn()
        gen = CodeGenerator(target_lang="python_fastapi", use_ai=True)
        ctx = PromptContext(program=Program(), target_lang="python_fastapi")
        gen.generate_fn(fn, ctx)

        stats = gen.get_stats()
        assert stats.total_requests == 0
        assert stats.cache_hits == 0

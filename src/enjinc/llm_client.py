"""
============================================================
EnJin LLM Client (llm_client.py)
============================================================
本模块负责与 LLM API 交互，实现 process 意图到目标语言代码的动态生成。

支持的 Provider:
    - openai (GPT-4, GPT-3.5-turbo)
    - deepseek (DeepSeek Coder)
    - anthropic (Claude 3)

功能特性:
    - 并发请求控制
    - Token 消耗统计
    - 请求缓存（基于 intent_hash）
    - 熔断重试机制
    - 超时控制
============================================================
"""

from __future__ import annotations

import os
import time
import logging
from dataclasses import dataclass, field
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import httpx

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """LLM 响应结果。"""

    content: str
    model: str
    usage: LLMUsage
    intent_hash: str
    cached: bool = False


@dataclass
class LLMUsage:
    """Token 使用统计。"""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass
class LLMConfig:
    """LLM 配置。"""

    provider: str = "openai"
    model: str = "gpt-4"
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    max_tokens: int = 2000
    temperature: float = 0.2
    timeout: int = 120


@dataclass
class LLMRequest:
    """LLM 请求。"""

    system_prompt: str
    user_prompt: str
    intent_hash: str


class LLMCircuitBreaker:
    """熔断器，防止 LLM 服务不可用时持续请求。"""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time: Optional[float] = None
        self.is_open = False

    def record_success(self):
        """记录成功调用。"""
        self.failures = 0
        self.is_open = False

    def record_failure(self):
        """记录失败调用。"""
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.is_open = True
            logger.warning(f"Circuit breaker opened after {self.failures} failures")

    def can_attempt(self) -> bool:
        """检查是否可以尝试请求。"""
        if not self.is_open:
            return True

        if (
            self.last_failure_time
            and (time.time() - self.last_failure_time) > self.recovery_timeout
        ):
            self.is_open = False
            self.failures = 0
            logger.info("Circuit breaker half-open, allowing request")
            return True

        return False


class LLMClient:
    """LLM API 客户端。"""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self._cache: dict[str, LLMResponse] = {}
        self._circuit_breaker = LLMCircuitBreaker()
        self._executor = ThreadPoolExecutor(max_workers=5)
        self._total_usage = LLMUsage(0, 0, 0)

    def _get_cache_key(self, request: LLMRequest) -> str:
        """获取缓存键。"""
        return f"{request.intent_hash}:{self.config.model}"

    def _is_cached(self, request: LLMRequest) -> Optional[LLMResponse]:
        """检查请求是否已缓存。"""
        key = self._get_cache_key(request)
        return self._cache.get(key)

    def _cache_response(self, request: LLMRequest, response: LLMResponse):
        """缓存响应。"""
        key = self._get_cache_key(request)
        response.cached = True
        self._cache[key] = response

    def generate(self, request: LLMRequest) -> LLMResponse:
        """生成代码。"""
        if not self._circuit_breaker.can_attempt():
            cached = self._is_cached(request)
            if cached:
                logger.info(f"Using cached response for {request.intent_hash}")
                return cached
            raise LLMServiceUnavailableError(
                "Circuit breaker is open and no cached response available"
            )

        cached = self._is_cached(request)
        if cached:
            logger.info(f"Using cached response for {request.intent_hash}")
            return cached

        try:
            response = self._call_api(request)
            self._circuit_breaker.record_success()
            self._cache_response(request, response)
            self._total_usage.completion_tokens += response.usage.completion_tokens
            self._total_usage.prompt_tokens += response.usage.prompt_tokens
            self._total_usage.total_tokens += response.usage.total_tokens
            return response
        except Exception as e:
            self._circuit_breaker.record_failure()
            logger.error(f"LLM API call failed: {type(e).__name__}: {e}")
            raise

    def _call_api(self, request: LLMRequest) -> LLMResponse:
        """调用 LLM API。"""
        if self.config.provider == "openai":
            return self._call_openai(request)
        elif self.config.provider == "deepseek":
            return self._call_deepseek(request)
        elif self.config.provider == "anthropic":
            return self._call_anthropic(request)
        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")

    def _call_openai(self, request: LLMRequest) -> LLMResponse:
        """调用 OpenAI API。"""
        api_key = self.config.api_key or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise LLMConfigError("OPENAI_API_KEY not set")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }

        with httpx.Client(timeout=self.config.timeout) as client:
            response = client.post(
                f"{self.config.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            llm_usage = LLMUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            )

            return LLMResponse(
                content=content,
                model=self.config.model,
                usage=llm_usage,
                intent_hash=request.intent_hash,
            )

    def _call_deepseek(self, request: LLMRequest) -> LLMResponse:
        """调用 DeepSeek API。"""
        api_key = self.config.api_key or os.getenv("DEEPSEEK_API_KEY", "")
        if not api_key:
            raise LLMConfigError("DEEPSEEK_API_KEY not set")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.config.model or "deepseek-coder",
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
        }

        with httpx.Client(timeout=self.config.timeout) as client:
            response = client.post(
                f"{self.config.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            llm_usage = LLMUsage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            )

            return LLMResponse(
                content=content,
                model=self.config.model,
                usage=llm_usage,
                intent_hash=request.intent_hash,
            )

    def _call_anthropic(self, request: LLMRequest) -> LLMResponse:
        """调用 Anthropic API。"""
        api_key = self.config.api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            raise LLMConfigError("ANTHROPIC_API_KEY not set")

        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        payload = {
            "model": self.config.model or "claude-3-opus-20240229",
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": [
                {
                    "role": "user",
                    "content": f"{request.system_prompt}\n\n{request.user_prompt}",
                },
            ],
        }

        with httpx.Client(timeout=self.config.timeout) as client:
            response = client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            content = data["content"][0]["text"]
            usage = data.get("usage", {})
            llm_usage = LLMUsage(
                prompt_tokens=usage.get("input_tokens", 0),
                completion_tokens=usage.get("output_tokens", 0),
                total_tokens=usage.get("input_tokens", 0)
                + usage.get("output_tokens", 0),
            )

            return LLMResponse(
                content=content,
                model=self.config.model,
                usage=llm_usage,
                intent_hash=request.intent_hash,
            )

    def get_total_usage(self) -> LLMUsage:
        """获取总 Token 消耗。"""
        return self._total_usage

    def clear_cache(self):
        """清空缓存。"""
        self._cache.clear()


class LLMConfigError(Exception):
    """LLM 配置错误。"""

    pass


class LLMServiceUnavailableError(Exception):
    """LLM 服务不可用（熔断器开启）。"""

    pass


@dataclass
class MultiModelConfig:
    """多模型配置：不同层使用不同模型。"""

    default: LLMConfig
    overrides: dict[str, LLMConfig] = field(default_factory=dict)
    master: Optional["LLMConfig"] = None

    def get_config(self, node_type: str) -> LLMConfig:
        """获取指定层的 LLMConfig，无覆盖时用默认。"""
        return self.overrides.get(node_type, self.default)


def create_client(provider: str = "openai", model: str = "gpt-4") -> LLMClient:
    """创建 LLM 客户端。"""
    config = LLMConfig(provider=provider, model=model)
    return LLMClient(config)


def create_multi_client(config: MultiModelConfig) -> dict[str, LLMClient]:
    """为每种 node_type 创建独立的 LLMClient 实例。"""
    clients: dict[str, LLMClient] = {}
    for node_type in ("struct", "fn", "module", "route"):
        cfg = config.get_config(node_type)
        clients[node_type] = LLMClient(cfg)
    return clients

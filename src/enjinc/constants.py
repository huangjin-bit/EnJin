"""
============================================================
EnJin 编译器常量注册中心 (constants.py)
============================================================
集中管理所有魔法字符串：注解名、错误码、类型映射、目标语言标识等。
消除各模块的硬编码，便于迭代扩展。

修改协议:
    新增注解 / 目标语言 / 类型映射只需在此文件追加，
    其余模块通过 import 引用，无需到处改字符串。
============================================================
"""

from __future__ import annotations


# ============================================================
# 1. 目标语言标识
# ============================================================

TARGET_PYTHON_FASTAPI = "python_fastapi"
TARGET_JAVA_SPRINGBOOT = "java_springboot"
TARGET_PYTHON_CRAWLER = "python_crawler"

KNOWN_TARGETS = [TARGET_PYTHON_FASTAPI, TARGET_JAVA_SPRINGBOOT, TARGET_PYTHON_CRAWLER]

DEFAULT_TARGET = TARGET_PYTHON_FASTAPI


# ============================================================
# 2. 注解名称
# ============================================================

# Field annotations
ANNO_PRIMARY = "primary"
ANNO_AUTO_INCREMENT = "auto_increment"
ANNO_UNIQUE = "unique"
ANNO_MAX_LENGTH = "max_length"
ANNO_MIN_LENGTH = "min_length"
ANNO_DEFAULT = "default"
ANNO_NULLABLE = "nullable"
ANNO_INDEX = "index"
ANNO_FOREIGN_KEY = "foreign_key"
ANNO_TABLE = "table"

# Function annotations
ANNO_LOCKED = "locked"
ANNO_HUMAN_MAINTAINED = "human_maintained"
ANNO_TRANSACTIONAL = "transactional"
ANNO_RETRY = "retry"
ANNO_CACHED = "cached"
ANNO_DEPRECATED = "deprecated"
ANNO_DATA_PLANE = "data_plane"
ANNO_API_CONTRACT = "api_contract"

# Module annotations
ANNO_ENGINE = "engine"
ANNO_DOMAIN = "domain"

# Route annotations
ANNO_PREFIX = "prefix"
ANNO_AUTH = "auth"
ANNO_RATE_LIMIT = "rate_limit"


# ============================================================
# 3. 原始类型集合 (EnJin 基础类型，非用户自定义)
# ============================================================

PRIMITIVE_TYPES = frozenset({
    "Int", "Float", "String", "Bool", "DateTime",
    "List", "Map", "Optional", "Enum",
})


# ============================================================
# 4. 类型映射表 (EnJin → 目标语言)
# ============================================================

ENJIN_TO_PYTHON: dict[str, str] = {
    "Int": "int",
    "Float": "float",
    "Bool": "bool",
    "String": "str",
    "DateTime": "str",
    "Enum": "str",
}

ENJIN_TO_JAVA: dict[str, str] = {
    "Int": "Long",
    "Float": "Double",
    "Bool": "Boolean",
    "String": "String",
    "DateTime": "java.time.LocalDateTime",
}

ENJIN_TO_SQL: dict[str, str] = {
    "Int": "INTEGER",
    "Float": "DOUBLE PRECISION",
    "String": "TEXT",
    "Bool": "BOOLEAN",
    "DateTime": "TIMESTAMP",
    "List": "JSONB",
    "Map": "JSONB",
    "Enum": "TEXT",
}

ENJIN_TO_ALEMBIC: dict[str, str] = {
    "Int": "Integer()",
    "Float": "Float()",
    "String": "String()",
    "Bool": "Boolean()",
    "DateTime": "DateTime()",
    "List": "JSON()",
    "Map": "JSON()",
    "Enum": "String()",
}


# ============================================================
# 5. HTTP 方法
# ============================================================

HTTP_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH")
MUTATING_HTTP_METHODS = ("POST", "PUT", "PATCH")


# ============================================================
# 6. Guard 异常映射 (guard_type → target_lang → exception class)
# ============================================================

GUARD_EXCEPTIONS: dict[str, dict[str, str]] = {
    "not_exists": {
        "python": "ConflictError",
        "java": "DuplicateResourceException",
    },
    "exists": {
        "python": "NotFoundError",
        "java": "ResourceNotFoundException",
    },
    "default": {
        "python": "ValueError",
        "java": "IllegalArgumentException",
    },
}


# ============================================================
# 7. Engine 框架注册表
# ============================================================

ENGINE_REGISTRY: dict[str, dict[str, str]] = {
    "workflow": {
        "temporal": "请生成 Temporal 工作流代码：使用 @workflow.defn, @activity.defn, 工作流信号和查询。",
    },
    "state_machine": {
        "spring_statemachine": "请生成 Spring StateMachine 代码：状态配置、转换器、事件监听器。",
    },
}

SUPPORTED_ENGINE_TYPES = set(ENGINE_REGISTRY.keys())


# ============================================================
# 8. LLM Provider 标识
# ============================================================

PROVIDER_OPENAI = "openai"
PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_ANTHROPIC = "anthropic"

KNOWN_PROVIDERS = [PROVIDER_OPENAI, PROVIDER_DEEPSEEK, PROVIDER_ANTHROPIC]

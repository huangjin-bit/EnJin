# EnJin

意图驱动的 AI 原生元编程语言。用自然语言描述业务意图，编译器自动生成可运行的 Java / Python 项目代码。

## 为什么需要 EnJin？

直接让 AI 生成的代码往往存在上下文丢失、结构混乱、不可复现等问题。EnJin 通过以下方式解决：

- **四层隔离架构**（struct → fn → module → route）将大需求拆分为小节点，每个节点的上下文边界清晰，避免 AI 注意力偏移
- **确定性构建**：基建层由 Jinja2 模板硬编码，AI 仅填充业务逻辑插槽，相同输入产生相同输出
- **内置安全约束**：`@locked` 禁止 AI 篡改已审核代码，`native` 块保护手写逻辑，`@human_maintained` 放弃 AI 生成权

实际效果：单次需求生成的无效 Token 消耗降低约 60%，节点代码生成准确率提升约 80%。

## 快速上手

### 安装

```bash
# 基础安装
pip install -e .

# 含 AI 集成（需要 httpx）
pip install -e ".[ai]"

# 含开发工具（pytest 等）
pip install -e ".[dev]"

# 全部安装
pip install -e ".[dev,ai]"
```

要求 Python 3.11+。

### 5 分钟示例

创建一个 `hello.ej` 文件：

```ej
// 定义数据模型
struct User {
    id: Int @primary @auto_increment
    username: String @unique @max_length(50)
    email: String @unique
}

// 定义业务方法
fn register_user(username: String, email: String) -> User {
    guard {
        username.length > 0 : "用户名不能为空"
        email.contains("@") : "邮箱格式不合法"
    }

    process {
        "创建一个新的 User 实例，保存到数据库并返回。"
    }

    expect {
        register_user("alice", "alice@test.com").username == "alice"
    }
}

// 定义 HTTP 接口
@prefix("/api/v1/users")
route UserService {
    POST "/register" -> register
}
```

编译为 Java Spring Boot 项目：

```bash
enjinc build hello.ej --target java_springboot
```

编译为 Python FastAPI 项目：

```bash
enjinc build hello.ej --target python_fastapi
```

使用 AI 辅助生成业务逻辑：

```bash
enjinc build hello.ej --target java_springboot --use-ai --provider openai --model gpt-4
```

### 查看所有支持的目标

```bash
enjinc targets
```

## 语言核心概念

### 四层隔离架构

```
┌─────────────────────────────────────┐
│  route（Service 层）                  │  HTTP 接口定义
│  绑定 module 导出的 action            │
├─────────────────────────────────────┤
│  module（Module 层）                  │  模块作用域与调度
│  组合 fn，声明依赖与定时任务            │
├─────────────────────────────────────┤
│  fn（Method 层）                      │  原子业务方法
│  guard → process → expect 三段意图体  │
├─────────────────────────────────────┤
│  struct（Model 层）                   │  纯数据模型
│  映射到数据库表                        │
└─────────────────────────────────────┘
```

**严格单向调用**：route → module → fn → struct。越级调用直接被编译器拒绝。

### 三段意图体

每个 `fn` 由三段组成：

```ej
fn create_order(user_id: Int, product_id: Int) -> Order {
    guard {
        // 前置条件：输入验证、业务规则检查
        user_id > 0 : "用户 ID 无效"
        exists(User, id=user_id) : "用户不存在"
    }

    process {
        // 业务意图：用自然语言描述"做什么"
        "创建一个新订单，关联用户和商品，
         计算总价，扣减库存，返回订单对象。"
    }

    expect {
        // 期望断言：自动生成单元测试
        create_order(1, 100).status == "pending"
        create_order(999, 100).throws("用户不存在")
    }
}
```

### 关键注解

| 注解 | 作用 |
|------|------|
| `@locked` | 锁定函数，禁止 AI 覆写，仅读取缓存 |
| `@transactional` | 标记事务性操作 |
| `@auth("jwt")` | 路由级认证要求 |
| `@table("name")` | 指定数据库表名 |
| `@foreign_key("Ref.field")` | 外键关联 |
| `@primary` / `@auto_increment` | 主键标记 |
| `@default("value")` | 字段默认值 |
| `@unique` | 唯一约束 |
| `@max_length(n)` | 最大长度约束 |
| `@sensitive` | 敏感字段（不出现在 Response/VO 中） |

### native 逃生舱

需要精确控制时，直接写目标语言代码：

```ej
fn hash_password(raw: String) -> String {
    native python {
        import hashlib
        return hashlib.sha256(raw.encode()).hexdigest()
    }
}
```

## 编译流水线

```
.ej 源码
  ↓ Lark Earley 解析器
Parse Tree
  ↓ Transformer
I-AST（意图抽象语法树）
  ↓ Analyzer（四层校验 + @locked 检查）
  ↓ Prompt Router（依赖图 + System Prompt）
  ↓ LLM Code Generator（多模型按层调用）
  ↓ Template Renderer（Jinja2 框架 + AI 插槽）
  ↓ Test Generator（expect → 单元测试）
可运行的目标项目
```

## 支持的目标栈

### Java Spring Boot

生成完整的 DDD 分层项目：Entity → Mapper → Service（接口 + 实现）→ DTO → VO → Assembler → Controller，含 Flyway 迁移、Docker/K8s 部署配置。

可选 Spring Cloud 微服务：Nacos 配置中心、Feign 客户端、Sentinel 熔断、Seata 分布式事务、API Gateway。

### Python FastAPI

生成 FastAPI 项目：SQLAlchemy ORM、Pydantic Schema、Repository 层、版本化路由，含依赖注入和 JWT 认证。

### Python 爬虫

生成爬虫项目：基于 httpx/aiohttp 的异步采集框架，含反爬策略和数据处理管道。

### 第三方扩展

通过 entry_points 插件机制，无需修改 enjinc 源码即可添加新目标（如 Go Gin、Rust Actix）。详见 `docs/07_plugins/extension_guide.md`。

## 更多示例

| 文件 | 说明 |
|------|------|
| `examples/user_management.ej` | 用户管理（完整四层示例） |
| `examples/blog_platform.ej` | 博客平台 |
| `examples/task_manager.ej` | 任务管理器 |
| `examples/java_ecommerce/trade.ej` | 电商系统（13 个 struct，最全面） |
| `examples/java_ecommerce/risk_control.ej` | 风控系统 |
| `examples/java_ecommerce/microservice_order.ej` | 微服务订单（Spring Cloud 全家桶） |
| `examples/python_crawler/product_crawler.ej` | 商品爬虫 |

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行全量测试（447+ 用例）
pytest

# 跳过慢测试
pytest -m "not slow"

# 运行单个测试
pytest tests/test_parser.py -v

# 代码覆盖率
pytest --cov=enjinc
```

## 技术栈

- **Python 3.11+** / setuptools 构建
- **Lark**（Earley 解析器）— .ej → Parse Tree
- **Jinja2** — 模板骨架代码生成
- **httpx**（可选）— LLM API 调用
- **pytest** — 测试框架

## 项目结构

```
src/enjinc/
  cli.py                  # CLI 入口（enjinc 命令）
  parser.py               # 词法/语法解析 → I-AST
  analyzer.py             # 静态校验（四层规则）
  prompt_router.py        # AI Prompt 路由
  code_generator.py       # AI 代码生成
  llm_client.py           # LLM 客户端
  template_renderer.py    # 模板组装
  test_generator.py       # expect → 单元测试
  dependency_graph.py     # 依赖图提取
  constants.py            # 常量注册中心
  layout_config.py        # 输出布局配置
  grammar.lark            # .ej 语法规则
  targets/                # 目标栈（插件式架构）
    java_springboot/      # Java Spring Boot
    python_fastapi/       # Python FastAPI
    python_crawler/       # Python 爬虫
examples/                 # .ej 示例文件
docs/                     # 文档（7 个子域）
tests/                    # 测试用例
```

## License

MIT

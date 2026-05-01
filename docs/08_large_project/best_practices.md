# EnJin 大型项目工程规范

本文档为大型项目使用 EnJin 提供工程化最佳实践指南。

## 一、DSL 设计规范

### 模块化拆分

不要把所有业务写在单个 `.ej` 文件里。按领域边界拆分 DSL 文件：

```
domain/
  user.ej        # 用户域
  order.ej       # 订单域
  pay.ej         # 支付域
  product.ej     # 商品域
```

每个领域模块独立维护，通过 `import` 语法互相引用，避免单文件过大难以维护。

### 公共抽象下沉

把通用字段、通用接口抽成公共模板：

```ej
// base.ej — 公共基础定义
struct BaseEntity {
    id: Int @primary @auto_increment
    created_at: DateTime @default("now()")
    updated_at: DateTime @default("now()")
    deleted: Bool @default("false")
}
```

所有业务实体继承公共模板，保证全项目风格统一。

### 注释和契约前置

在 DSL 里为每个实体、字段、接口写清楚业务含义、约束规则：

```ej
struct User {
    // 用户名，3-50字符，全局唯一
    username: String @unique @min_length(3) @max_length(50)
    // 用户状态：active-正常, banned-封禁, suspended-冻结
    status: Enum("active", "banned", "suspended") @default("active")
}
```

EnJin 生成代码时自动把注释带到 JavaDoc 和验证注解里，实现"文档即代码"。

## 二、生成代码的可扩展性设计

### 严格区分自动生成代码和自定义代码

| 目录 | 用途 | 规则 |
|------|------|------|
| `src/*/generated/` | EnJin 自动生成 | 禁止手动修改，重新构建直接覆盖 |
| `src/*/custom/` | 自定义业务逻辑 | 通过继承或组合扩展生成代码 |

扩展方式示例：

```java
// 自定义服务继承生成服务
public class CustomUserService extends GeneratedUserService {
    @Override
    public User register(String username, String email, String password) {
        // 自定义注册逻辑：发送欢迎邮件等
        User user = super.register(username, email, password);
        emailService.sendWelcome(user.getEmail());
        return user;
    }
}
```

### 预留扩展点

在 DSL 里定义业务钩子：

```ej
fn create_order(user_id: Int, product_id: Int) -> Order {
    process {
        "创建订单。
         beforeSave: 校验库存、计算折扣
         afterCreate: 发送订单通知、扣减库存"
    }
}
```

EnJin 生成代码时自动预留 `beforeSave`、`afterUpdate`、`onDelete` 等扩展点，自定义逻辑只需实现钩子接口。

### 配置完全外部化

所有环境相关配置统一放到配置中心（Nacos/Apollo）或多环境 Profile。生成的代码只留配置注入点：

```yaml
# 生成的代码不硬编码，全部引用环境变量
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
```

## 三、架构治理

### 分层隔离

严格遵守 DDD 四层架构的依赖规则：

- Controller 只能依赖 Service
- Service 只能依赖 Repository 和领域实体
- 禁止跨层调用、禁止把业务逻辑写到 Controller 里

EnJin 编译器会在 `analyze` 阶段自动检测越级调用并拒绝编译。

### 微服务场景的契约统一

所有服务的接口契约都用 DSL 统一管理。EnJin 自动生成：
- 服务提供者的接口实现
- 服务消费者的 Feign/Dubbo 调用代码

保证上下游接口一致性，避免联调参数不匹配。

### 分布式场景能力规划

提前在 DSL 中定义分布式需求：

```ej
@transactional(global=true)    // 分布式事务，自动集成 Seata
fn create_order(...) -> Order { ... }

@rate_limit(limit=1000)        // 限流，自动集成 Sentinel
route OrderService { ... }

@cache(expire=3600)            // 缓存，自动生成 Redis 逻辑
fn get_product(id: Int) -> Product { ... }
```

## 四、工程化保障

### DSL 纳入版本管理

所有 `.ej` DSL 文件和生成的代码一起纳入 Git 管理。每次修改 DSL 都要写清楚提交说明，做到"需求变更可追溯、代码生成可回滚"。

### CI/CD 流水线集成

```yaml
# 示例 CI 流水线
stages:
  - generate    # enjinc build source.ej --target java_springboot
  - compile     # mvn compile
  - test        # mvn test
  - deploy      # 自动部署
```

提交 DSL → 自动生成代码 → 自动编译 → 自动测试 → 自动部署，无需人工干预。

### 测试自动化

- EnJin 自动从 `expect` 块生成单元测试骨架
- 核心模块测试覆盖率不低于 80%
- AI 生成的业务逻辑必须经过充分测试验证

### Code Review 规则

- 所有 DSL 修改必须经过架构师 Review
- AI 生成的业务逻辑必须经过资深开发 Review

## 五、性能与稳定性保障

### 数据库设计前置优化

```ej
struct Order {
    user_id: Int @foreign_key("User.id") @index    // 自动创建索引
    status: String @index                          // 查询字段加索引
    created_at: DateTime @index                    // 时间范围查询加索引
}
```

复杂查询可直接在 DSL 里定义多表关联，自动生成 Join 查询代码。

### 监控埋点自动集成

开启监控配置后，生成的代码自动集成：
- Prometheus 接口耗时、数据库操作耗时、异常率指标
- SkyWalking 链路追踪
- 无需开发手动写埋点代码

### 灰度发布支持

EnJin 生成的接口默认支持流量染色和灰度路由规则，新功能上线可用灰度发布降低故障影响范围。

## 六、团队协作规范

### 统一模板和规则

- 整个团队使用统一的 EnJin 模板、命名规范、依赖版本
- 团队定制模板上传到内部模板仓库，全员使用同一模板
- 避免不同开发生成的代码风格不一致

### 权限控制

- 核心 DSL 文件（公共基础模块、核心交易模块）设置编辑权限
- 只有架构师可以修改核心 DSL
- 避免随意修改导致全项目生成代码出现问题

### 公共模板沉淀

把常用业务场景做成公共模板库：
- Excel 导入导出
- 消息发送（短信/邮件/推送）
- 文件上传下载
- 审批流程
- 数据权限

后续新项目直接复用，不需要重复开发。

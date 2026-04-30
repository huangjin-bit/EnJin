# 队列契约模型 (Queue Contract)

> 本文档定义 EnJin 对消息队列的统一抽象，以支持第一阶段默认双适配器：Kafka 与 RocketMQ。

---

## 1. 目标

EnJin 不直接暴露底层 MQ 客户端细节，而是定义统一的 Queue Contract，用于：

- 生成 Producer / Consumer 外壳
- 生成序列化与反序列化包装
- 生成重试、死信、监控埋点、健康检查骨架
- 在编译期校验所声明能力是否被目标 MQ 适配器支持

EnJin **不负责**：

- Kafka 分区调优
- RocketMQ Broker / NameServer 拓扑调优
- 消费组再均衡策略优化
- 高吞吐序列化优化
- 底层消息系统运维脚本

---

## 2. 当前默认适配器

第一阶段默认支持：

- `kafka`
- `rocketmq`

第二阶段可考虑增加：

- `rabbitmq`
- `pulsar`

在第一阶段，编译器应优先把适配能力做扎实，而不是盲目扩增适配器数量。

---

## 3. 统一消息契约

### 3.1 Message Envelope

EnJin 统一消息包络建议抽象为：

```json
{
  "topic": "order.created",
  "key": "order-123",
  "headers": {
    "trace_id": "xxx",
    "tenant_id": "xxx"
  },
  "payload": {
    "order_id": 123,
    "user_id": 456
  },
  "meta": {
    "delivery": "at_least_once",
    "ordering_key": "user-456",
    "retry_policy": "default",
    "delay_seconds": 0
  }
}
```

### 3.2 必备字段

- `topic`：主题 / 逻辑事件名
- `key`：分区键 / 业务键
- `headers`：透传上下文，如 trace、tenant、auth 信息
- `payload`：业务负载
- `meta.delivery`：交付语义
- `meta.retry_policy`：重试策略标识

### 3.3 推荐字段

- `ordering_key`
- `delay_seconds`
- `schema_version`
- `source_service`
- `timestamp`

---

## 4. 默认交付语义

EnJin 的默认队列语义应保持保守：

- 默认：`at_least_once`
- 默认启用：幂等键
- 默认启用：死信队列入口
- 默认要求：消费者业务处理函数幂等

**禁止**编译器假设“天然 exactly-once”。

---

## 5. 能力矩阵

| 能力 | Kafka | RocketMQ | EnJin 合约行为 |
|---|---|---|---|
| Topic 发布 | 支持 | 支持 | 必备 |
| Consumer Group | 支持 | 支持 | 必备 |
| Key / 分区键 | 支持 | 支持 | 必备 |
| 顺序消息 | 部分支持（按 partition/key） | 支持 | 需显式声明 |
| 延迟消息 | 需额外方案 | 原生较强 | 需 capability 校验 |
| 死信队列 | 支持 | 支持 | 必备骨架 |
| 重试 | 支持 | 支持 | 必备骨架 |
| 事务消息 | 有限制 | 支持较强 | 需 capability 校验 |
| 广播消费 | 非默认 | 支持 | 非默认能力 |

说明：

- EnJin 应以“能力声明 + 适配器校验”方式处理差异，而不是假装 Kafka 与 RocketMQ 完全同构。
- 若业务声明了某项能力，而选定适配器不支持，`analyzer.py` 必须在编译期报错。

---

## 6. 配置模型建议

`application.ej` 中建议采用如下风格：

```ej
application {
    target: "java_springboot"

    queue {
        primary: "kafka"
        secondary: "rocketmq"
        default_delivery: "at_least_once"
        require_idempotency: 1
    }
}
```

当前语法层把这些配置当作嵌套字典；后续由 `analyzer.py` 做强校验。

---

## 7. 编译器应生成的内容

对于 Queue Contract，编译器应生成：

- 统一 Producer 包装层
- 统一 Consumer 外壳
- Schema 注册与 payload 编码入口
- Trace / Metrics 埋点入口
- Retry / Dead Letter 钩子
- Health Check / Readiness 探针

对于 Java/Spring 电商主栈，应优先生成：

- Kafka Producer / Consumer 包装
- RocketMQ Producer / Consumer 包装
- Outbox 发布桥接层
- 统一异常包装与日志上下文

对于 Python 监控 / Agent / 爬虫，应优先生成：

- 轻量 Producer / Consumer 客户端包装
- 重试 / 限流 / 失败告警入口
- 采集与调度的消息边界外壳

---

## 8. 编译器不得生成的内容

- Kafka 分区数与副本调优策略
- RocketMQ Broker 路由调优
- 复杂批量压缩参数
- 消费者线程模型深度优化
- 集群运维与扩容脚本

这些属于运行时工程优化，不属于 EnJin 的控制面职责。

---

## 9. 未来静态校验要求

`analyzer.py` 至少要校验：

- 是否声明了合法的主适配器
- 是否请求了适配器不支持的能力
- 是否为至少一次投递声明了幂等要求
- 是否存在 Dead Letter 处理入口
- 是否跨 domain 泄露底层 MQ 客户端细节

---

## 10. 当前实现状态

### 已明确

- 双适配器第一阶段默认：`kafka` + `rocketmq`
- Queue 应有统一契约层，而不是业务直接耦合底层客户端
- MQ 能力差异必须进入编译期治理

### 尚未落地

- 语法层尚无专门的 queue 能力声明 DSL
- `analyzer.py` 尚未校验 capability flags
- Java / Python MQ 模板尚未生成

---

> 本文件最后更新: 2026-03-24 | 版本: v0.1.0

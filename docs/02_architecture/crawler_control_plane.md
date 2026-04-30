# 爬虫控制面模型 (Crawler Control Plane)

> 本文档定义 EnJin 在 Python 爬虫 / 采集系统中的职责边界，明确控制面与抓取内核的分离方式。

---

## 1. 目标定位

EnJin 在爬虫场景中应负责：

- 抓取任务契约
- 调度入口与任务编排骨架
- 存储管道外壳
- 失败重试与告警入口
- 限流与合规配置入口
- Trace / Metrics / Audit 接入点

EnJin 不应负责：

- 反爬绕过策略
- 浏览器指纹与设备伪装
- 验证码识别与对抗
- JS 逆向逻辑
- 代理池调度算法
- 高并发抓取调优

---

## 2. 核心原则

### 2.1 控制面与抓取内核分离

控制面由 EnJin 生成，抓取内核由 Python 原生生态承接：

- 控制面：任务定义、调度、状态追踪、告警、入库管道
- 数据面 / 执行面：Scrapy、Playwright、Selenium、代理池、浏览器容器

### 2.2 默认把爬虫视作“高风险集成系统”

编译器不得假设：

- 目标站允许高频抓取
- 浏览器自动化一定稳定
- 代理池一定可用
- 反爬绕过一定合法

因此默认需要：

- 限流入口
- 退避入口
- 来源标识
- 失败审计
- 人工接管钩子

### 2.3 爬虫工作负载属于 Python 编译单元

爬虫与采集系统默认属于 Python 目标栈，不进入 Java/Spring 电商交易核心编译单元。

---

## 3. 推荐架构

```text
route / scheduler trigger
        │
        ▼
module crawl orchestration
        │
        ├── fn build_request_contract
        ├── fn dispatch_job
        ├── fn persist_result
        └── fn notify_failure
        │
        ▼
Python native runtime
(Scrapy / Playwright / Selenium / Proxy Pool)
```

说明：

- `route` 负责对外暴露任务入口、状态查询、人工重试接口
- `module` 负责抓取任务编排
- `fn` 负责原子步骤，如请求构建、结果入库、告警发送
- 真正的抓取执行内核由 Python 原生运行时承接

---

## 4. 建议中间件矩阵

- API：FastAPI
- Queue：Kafka / RocketMQ
- Cache：Redis
- Browser Runtime：Playwright / Selenium
- Storage：PostgreSQL / ClickHouse / S3/MinIO
- Observability：OpenTelemetry + Prometheus
- Scheduling：Cron / MQ Trigger / 外部调度器

---

## 5. 合规与稳定性要求

编译器生成的爬虫控制骨架至少应预留：

- 请求频率限制
- 失败退避策略
- 封禁后熔断入口
- robots / 来源声明配置位
- 手工禁用任务开关
- 审计日志与结果追踪

**禁止** AI 凭空生成“自动绕过风控”类逻辑。

---

## 6. 编译器应生成的内容

- Crawl Job DTO
- 调度入口骨架
- 存储 / 清洗管道外壳
- 重试 / 失败告警钩子
- Trace / Metrics / Health Check 接入点
- MQ 任务分发包装层

---

## 7. 编译器不得生成的内容

- 反爬脚本
- 验证码破解逻辑
- 代理轮换策略优化
- 浏览器自动化对抗逻辑
- 抓取吞吐性能极限优化

---

## 8. 当前实现状态

### 已明确

- 爬虫属于 Python 工作负载
- EnJin 负责爬虫控制面，不负责抓取内核
- 合规、限流、失败审计必须是一等关注项

### 尚未落地

- 尚无爬虫专用模板骨架
- 尚无爬虫调度 / 存储 DSL
- 尚无抓取任务控制面的静态校验规则

---

> 本文件最后更新: 2026-03-24 | 版本: v0.1.0

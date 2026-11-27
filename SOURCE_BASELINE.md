# 源码基线与核对记录

<!-- upstream-sha: 80926f92df182d258118456ae458043af0d7e807 -->
<!-- upstream-version: 2.1.0-SNAPSHOT -->

核对日期：**2026-11-27**（Asia/Shanghai）。官方 main 在本次核对时指向 [`80926f92df182d258118456ae458043af0d7e807`](https://github.com/agentscope-ai/agentscope-java/commit/80926f92df182d258118456ae458043af0d7e807)（提交日期 `2026-11-26`），提交主题为 `test: deflake four single-OS CI failure classes under -T1C contention (#4435)`。根 POM 的 `<revision>` 是 **`2.1.0-SNAPSHOT`**。

所有框架章节与 `images/*.svg` 全景图统一对齐这份源码快照。main 仍会持续演进；阅读固定 SHA 链接能精确复现本次结论。各章不再携带不同的“最新 main”日期；已发布标签（`v2.0.3`、`v2.0.4`、`v2.0.5`、`v2.1.0-BETA1`）与当前 `main` 的差异集中记录在对应演进说明与第 10 章版本对比表中。

## 可复算的结构事实

| 指标 | 数量 | 口径 |
|---|---:|---|
| 根聚合模块 | 7 | 根 POM 直接 `<modules>`（`agentscope-durable` 已取代原 `agentscope-service`） |
| core 直接子包 | 22 | `agentscope-core/src/main/java/io/agentscope/core/` 直接子目录（`journal` 取代原 `session`） |
| AgentEventType 枚举值 | 32 | 枚举常量，不把兼容 alias 重复计数 |
| extensions 一级模块 | 27 | 包含 `agentscope-spring-boot-starters` 聚合与 6 个 `agentscope-extensions-durable-*` 模块；已移除 `controlplane` |
| extensions 聚合 POM | 13 | 递归模块中 packaging 为 pom |
| extensions jar 模块 | 72 | packaging 为 jar，包含端到端测试模块 |
| extensions 可发布 jar | 71 | 排除 `maven.deploy.skip=true` 的 `model-e2e-tests`；不等于已发布到 Maven Central |
| starters jar | 14 | starters 聚合下的直接模块 |
| documentation2 子包 | 17 | 示例源码目录的直接子目录 |

`agentscope-durable` 父 POM 设置 `maven.deploy.skip=true`（开发态核心层，发布由独立流程显式触发），因此 `durable-runtime`、`durable-worker` 与 3 个 `durable-adapter-*` 不计入上面的 extensions 发布数；而 `agentscope-extensions-durable-{jdbc,http,sandbox,rocketmq,objects,mcp}` 位于 `agentscope-extensions` 下（`skip=false`），已同步纳入 `agentscope-bom` 与 `agentscope-all`（`optional=true`）。原 `agentscope-service` 与 `agentscope-extensions-controlplane` 已于 `#4154` 从主干移除。

## 主链源码索引

方法链接指向声明行；阅读时沿方法体追下游调用，不把类之间的概念关联当作直接调用边。

| 源码入口 | 核对内容 |
|---|---|
| [pom.xml](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/pom.xml#L30) | 项目版本与 7 个顶层聚合模块 |
| [AgentBase#call](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/agent/AgentBase.java#L244) | 公共调用入口 |
| [AgentBase#runLifecycle](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/agent/AgentBase.java#L317) | 生命周期资源边界 |
| [AgentBase#runInContext](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/agent/AgentBase.java#L325) | 运行控制与按 Thread 串行准入 |
| [AgentBase#runLifecycleBody](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/agent/AgentBase.java#L397) | `usingWhen` 异步获取、执行与取消门闩清理 |
| [AgentBase#executeCallBody](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/agent/AgentBase.java#L450) | preCall / doCall / host.finish / postCall |
| [ReActAgent#buildAgentStream](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L1559) | 四级运行身份、入口模型解析与事件流 |
| [ReActAgent#buildIdentifiedAgentStream](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L1630) | onAgent 链与最终事件 |
| [ReActAgent#acquireCallExecution](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L951) | ThreadJournal writer 租约获取与启动取消保护 |
| [ReActAgent#releaseCallExecution](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L1076) | 完成 / 失败 / 取消释放与 `closeStateWrites` 门闩 |
| [ReActAgent#beforeAgentExecution](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L1092) | 槽位激活、`onAgentStateReady` 与 `CapabilitySurface` 解析 |
| [ReActAgent#beforeCallComplete](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L1256) | `finalizationStep` 与 `onAgentFinish` 扩展点 |
| [ReActAgent#doCallInner](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L2698) | 延迟模型答案续跑与 pending 工具入口分流 |
| [ReActAgent#reasoning](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L3340) | `REASONING` 宿主边界、推理与请求准备 |
| [ReActAgent#acting](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L4043) | `ACTING` 宿主边界、授权裁剪与权限分流 |
| [ReActAgent#isFinished](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L5649) | 普通回复与服务端工具结束条件 |
| [ReActAgent#saveStateToSession](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L618) | journal checkpoint + main 线程镜像与 standalone 保存选择 |
| [ReActAgent#saveStateAfterCallFailure](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L710) | 失败保存与原异常保留 |
| [InvocationRecorder#checkpoint](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/journal/InvocationRecorder.java#L731) | 原生 ThreadJournal 状态 checkpoint |
| [InvocationRecorder#finish](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/journal/InvocationRecorder.java#L861) | Run 终态写入与 writer 释放 |
| [AtomicJournalStorage](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/journal/AtomicJournalStorage.java#L27) | 具备 CAS 原子提交与批量读取能力的日志存储契约 |
| [ThreadRecovery#reconcile](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/journal/ThreadRecovery.java#L31) | 未决工具副作用的显式人工对账恢复 |
| [AgentExecutionHost](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/agent/AgentExecutionHost.java#L29) | 执行宿主协作边界（`REASONING / MODEL / ACTING / FINALIZATION`） |
| [CapabilitySurface](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/agent/CapabilitySurface.java#L50) | 请求级技能、工具组与工具授权面 |
| [Toolkit#callTool](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/tool/Toolkit.java#L837) | 单工具复用执行设施 |
| [Toolkit#callTools](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/tool/Toolkit.java#L883) | 批量工具执行 |
| [ToolSearchMiddleware](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/tool/search/ToolSearchMiddleware.java#L42) | 按需工具检索与延迟加载中间件 |
| [ToolExecutor](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/tool/ToolExecutor.java#L67) | 参数、授权、拦截器、超时与执行回调 |
| [ToolCallsAccumulator](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/agent/accumulator/ToolCallsAccumulator.java#L41) | 流式工具参数完整性检查 |
| [MiddlewareBase](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/middleware/MiddlewareBase.java#L80) | 8 个扩展点与 `activePoints()` 契约 |
| [ModelRequestPreparer](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/middleware/ModelRequestPreparer.java#L28) | 模型请求准备扩展 |
| [AgentEventType](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/event/AgentEventType.java#L40) | 32 种流式事件 |
| [ToolResultState](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-core/src/main/java/io/agentscope/core/message/ToolResultState.java#L20) | 包含 SUSPENDED 的工具结果状态 |
| [HarnessAgent.Builder#build](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-harness/src/main/java/io/agentscope/harness/agent/HarnessAgent.java#L2802) | Harness Builder 装配入口 |
| [WorkspaceThreadJournalStore](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-harness/src/main/java/io/agentscope/harness/agent/journal/WorkspaceThreadJournalStore.java#L33) | 工作区与分布式命名空间下的默认 ThreadJournalStore |
| [HarnessContextBuilder](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-harness/src/main/java/io/agentscope/harness/agent/context/HarnessContextBuilder.java#L53) | 上下文选择、渲染与预算 |
| [CompactionMiddleware](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-harness/src/main/java/io/agentscope/harness/agent/middleware/CompactionMiddleware.java#L65) | 压缩与 overflow recovery |
| [VerificationService](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-harness/src/main/java/io/agentscope/harness/agent/verification/VerificationService.java#L42) | 确定性验证服务 |
| [DurableRuntime](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-durable/durable-runtime/src/main/java/io/agentscope/durable/DurableRuntime.java#L75) | 持久执行运行时组装、租约调度与恢复入口 |
| [AgentScopeAdapter#forHarness](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-durable/durable-adapters/durable-adapter-harness-agentscope/src/main/java/io/agentscope/durable/agentscope/AgentScopeAdapter.java#L178) | 原生 HarnessAgent / ReActAgent 与 Durable 的桥接适配器 |
| [agentscope-extensions/pom.xml](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-extensions/pom.xml#L33) | 扩展一级聚合 |
| [agentscope-durable/README.md](https://github.com/agentscope-ai/agentscope-java/blob/80926f92df182d258118456ae458043af0d7e807/agentscope-durable/README.md#L1) | Durable 架构边界、Brain-Hands 模型与使用说明 |

## 应用示例边界

第 9 章及各章 customer_work 小节保留 [`17007e4a`](https://github.com/liulangjietou/customer_work/tree/17007e4a) 应用快照（依赖 AgentScope `2.0.3`），作为历史集成示例。应用侧名称与方法不能被视为本次 main 的 API 保证。本次更新框架侧链路、兼容边界与图示，不宣称已迁移或验收该应用。

## 复验方法

准备官方仓库的本次提交后，在本指南根目录运行：

```bash
python3 scripts/verify_docs.py --source-root /path/to/agentscope-java
```

脚本检查源码 HEAD / POM 版本、各章基线、结构计数、固定提交链接的文件和行号、索引中的方法名、Markdown 本地资源、代码围栏、全部 `images/*.svg` XML 与源码链接。它不替代行为核对，也不声称执行了上游 Java 回归测试。

Mermaid 代码块需核验语法合法性；SVG 可用 `rsvg-convert` 转成 PNG 检查文字与连线。此次验证记录随 PR 提供。版本更新时先变更本文件基线，再逐章核对行为与图片，最后执行验证；不能只替换 SHA 和版本号。

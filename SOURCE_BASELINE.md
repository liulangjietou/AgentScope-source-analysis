# 源码基线与核对记录

<!-- upstream-sha: dcb131a3f257f06e2b7ddcd3dacfe75d31d04028 -->
<!-- upstream-version: 2.1.0-SNAPSHOT -->

核对日期：**2026-10-26**（America/New_York）。官方 main 在本次核对时指向 [`dcb131a3f257f06e2b7ddcd3dacfe75d31d04028`](https://github.com/agentscope-ai/agentscope-java/commit/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028)，提交主题为 `fix(a2a): resolve agent card once per execution (#3767)`。根 POM 的 `<revision>` 是 **`2.1.0-SNAPSHOT`**。

所有框架章节与 SVG 使用这份源码快照。main 仍会继续变化；阅读固定 SHA 链接能复现本次结论。各章不再携带不同的“最新 main”日期。

## 可复算的结构事实

| 指标 | 数量 | 口径 |
|---|---:|---|
| 根聚合模块 | 7 | 根 POM 直接 `<modules>` |
| core 直接子包 | 22 | `agentscope-core/src/main/java/io/agentscope/core/` 直接子目录 |
| AgentEventType 枚举值 | 32 | 枚举常量，不把兼容 alias 重复计数 |
| extensions 一级模块 | 22 | 包含 `agentscope-spring-boot-starters` 聚合 |
| extensions 聚合 POM | 13 | 递归模块中 packaging 为 pom |
| extensions jar 模块 | 67 | packaging 为 jar，包含端到端测试模块 |
| extensions 可发布 jar | 66 | 排除 `maven.deploy.skip=true` 的 model-e2e-tests；不等于已发布到 Maven Central |
| starters jar | 14 | starters 聚合下的直接模块 |
| documentation2 子包 | 17 | 示例源码目录的直接子目录 |

service 的 Java 子模块继承 service 父 POM 的 `maven.deploy.skip=true`，不计入上面的 extensions 发布数。BOM、聚合 POM、Java 模块和平台发行包是不同口径。

最新提交 #3767 调整 A2A 客户端为每次执行只解析一次 Agent Card，并增加调用次数与失败边界测试。第 8 章说明执行与构建期解析的区别，源码和测试链接同样固定到本次 SHA。

## 主链源码索引

方法链接指向声明行；阅读时沿方法体追下游调用，不把类之间的概念关联当作直接调用边。

| 源码入口 | 核对内容 |
|---|---|
| [pom.xml](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/pom.xml#L30) | 项目版本与顶层聚合 |
| [AgentBase#call](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/agent/AgentBase.java#L240) | 公共调用入口 |
| [AgentBase#runLifecycle](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/agent/AgentBase.java#L313) | 生命周期资源边界 |
| [AgentBase#runInContext](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/agent/AgentBase.java#L321) | 运行控制与串行准入 |
| [AgentBase#runLifecycleBody](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/agent/AgentBase.java#L378) | 异步获取与释放会话资源 |
| [AgentBase#executeCallBody](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/agent/AgentBase.java#L418) | preCall / doCall / postCall |
| [ReActAgent#buildAgentStream](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L1290) | 执行身份与事件流 |
| [ReActAgent#buildIdentifiedAgentStream](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L1332) | onAgent 链与最终事件 |
| [ReActAgent#acquireCallExecution](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L825) | Native Session 获取 |
| [ReActAgent#releaseCallExecution](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L899) | 完成 / 失败 / 取消释放 |
| [ReActAgent#doCallInner](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L2178) | pending 工具入口分流 |
| [ReActAgent#reasoning](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L2798) | 推理与请求准备 |
| [ReActAgent#acting](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L3463) | 工具与权限分流 |
| [ReActAgent#isFinished](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L4802) | 普通回复与服务端工具结束条件 |
| [ReActAgent#saveStateToSession](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L542) | checkpoint / legacy 保存选择 |
| [ReActAgent#saveStateAfterCallFailure](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/ReActAgent.java#L583) | 失败保存与原异常保留 |
| [SessionRecorder#checkpoint](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/session/SessionRecorder.java#L399) | 原生日志状态 checkpoint |
| [SessionRecorder#finish](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/session/SessionRecorder.java#L464) | 回合终态与 writer 释放 |
| [AtomicSessionStorage](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/session/AtomicSessionStorage.java#L24) | 具备原子提交能力的 Session 存储契约 |
| [SessionRecovery](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/session/SessionRecovery.java#L33) | 日志投影与恢复 |
| [Toolkit#callTool](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/tool/Toolkit.java#L560) | 单工具复用执行设施 |
| [Toolkit#callTools](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/tool/Toolkit.java#L602) | 批量工具执行 |
| [ToolExecutor](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/tool/ToolExecutor.java#L67) | 参数、拦截器、超时与执行回调 |
| [ToolCallsAccumulator](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/agent/accumulator/ToolCallsAccumulator.java#L41) | 流式工具参数完整性检查 |
| [MiddlewareBase](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/middleware/MiddlewareBase.java#L71) | 洋葱切点与状态就绪回调 |
| [ModelRequestPreparer](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/middleware/ModelRequestPreparer.java#L28) | 模型请求准备扩展 |
| [AgentEventType](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/event/AgentEventType.java#L40) | 32 种事件 |
| [ToolResultState](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-core/src/main/java/io/agentscope/core/message/ToolResultState.java#L20) | 包含 SUSPENDED 的工具结果状态 |
| [HarnessAgent#build](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-harness/src/main/java/io/agentscope/harness/agent/HarnessAgent.java#L2598) | Harness Builder 装配 |
| [AgentSession](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-harness/src/main/java/io/agentscope/harness/agent/session/AgentSession.java#L59) | 会话操作编排入口 |
| [HarnessContextBuilder](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-harness/src/main/java/io/agentscope/harness/agent/context/HarnessContextBuilder.java#L53) | 上下文选择、渲染与预算 |
| [CompactionMiddleware](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-harness/src/main/java/io/agentscope/harness/agent/middleware/CompactionMiddleware.java#L65) | 压缩与 overflow recovery |
| [VerificationService](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-harness/src/main/java/io/agentscope/harness/agent/verification/VerificationService.java#L42) | 确定性验证服务 |
| [agentscope-extensions/pom.xml](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-extensions/pom.xml#L33) | 扩展一级聚合 |
| [README](https://github.com/agentscope-ai/agentscope-java/blob/dcb131a3f257f06e2b7ddcd3dacfe75d31d04028/agentscope-service/README.md#L1) | 平台结构与公开入口 |

## 应用示例边界

第 9 章及各章 customer_work 小节保留 [`17007e4a`](https://github.com/liulangjietou/customer_work/tree/17007e4a) 应用快照（依赖 AgentScope `2.0.3`），作为历史集成示例。应用侧名称与方法不能被视为本次 main 的 API 保证。本次更新框架侧链路、兼容边界与图示，不宣称已迁移或验收该应用。

## 复验方法

准备官方仓库的本次提交后，在本指南根目录运行：

```bash
python3 scripts/verify_docs.py --source-root /path/to/agentscope-java
```

脚本检查源码 HEAD / POM 版本、各章基线、结构计数、固定提交链接的文件和行号、索引中的方法名、Markdown 本地资源、代码围栏、SVG XML 与源码链接。它不替代行为核对，也不声称执行了上游 Java 回归测试。

Mermaid 代码块还需用 Mermaid CLI 实际渲染；SVG 可用 `rsvg-convert` 转成 PNG 检查文字与连线。此次验证记录随 PR 提供。版本更新时先变更本文件基线，再逐章核对行为与图片，最后执行验证；不能只替换 SHA 和版本号。

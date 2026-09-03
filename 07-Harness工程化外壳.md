# 第 7 章 Harness 工程化外壳（核心）

> 路径前缀：`agentscope-harness/src/main/java/io/agentscope/harness/`
> 裸 ReAct 只解决"一轮任务"；跑数小时、累积状态、需要文件系统与子 Agent 的长任务，靠 Harness。本章讲 `HarnessAgent` 如何在**不改 ReAct 算法一行**的前提下叠加这些能力。

## 7.1 组合而非继承：HarnessAgent 的结构

`agent/HarnessAgent.java`（2884 行）**implements `Agent`，内部组合一个 `ReActAgent delegate`**。所有 `call/streamEvents` 重载都经 `wrappedCall`（`:900`）：

```mermaid
flowchart TB
    HC["HarnessAgent#call (:677，8 个重载)"] --> ESD["HarnessAgent#ensureSessionDefaults (:972)<br/>补默认 sessionId/userId"]
    ESD --> WC["HarnessAgent#wrappedCall (:900)"]
    WC --> ACQ["SandboxLifecycleMiddleware#acquireForCall<br/>获取沙箱租约"]
    ACQ --> DEL["ReActAgent#call<br/>进入第 3 章的完整循环<br/>（Harness 能力已作为 middleware/tool 注入其中）"]
    DEL --> REL["SandboxLifecycleMiddleware#releaseForCall<br/>释放租约"]
    DEL -.->|"上下文溢出错误"| REC["HarnessAgent#recoverFromOverflow (:1004)<br/>压缩后重试兜底"]
```

官方架构文档（`docs/v2/en/docs/harness/architecture.md`）的三条核心原则，读 Harness 源码前先记住：

1. **能力叠加在推理循环之上，而非嵌入其中**——workspace 注入、压缩、子 Agent、沙箱、Plan Mode 各自挂在循环的关键时刻（以 Middleware/Tool 形式），核心算法零改动；
2. **能力之间互不依赖，只共享三个对象**——`RuntimeContext`（本次调用是谁）、workspace（读写哪些文件）、`AgentStateStore`（如何恢复）；
3. **内置 middleware 顺序固定，用户 middleware 永远排在最前面（最外层）。**

## 7.2 Builder 装配：内置 Middleware 的固定顺序

`HarnessAgent.Builder#build`（`:2264` 起，约 600 行）向内部 `ReActAgent.Builder` 按固定顺序注入内置 middleware（列表顺序 = 洋葱层次，第 6 章）：

```
用户 middleware（最外层）
→ SandboxLifecycleMiddleware (:2428) → AgentTraceMiddleware (:2431)
→ WorkspaceContextMiddleware (:2437) → AtPathExpansionMiddleware (:2449)
→ TranscriptMiddleware (:2467)
→ MemoryFlushMiddleware (:2479) → MemoryMaintenanceMiddleware (:2499)
→ CompactionMiddleware (:2514) → ToolResultEvictionMiddleware (:2520)
→ InboxMiddleware (:2523) → TeamsMiddleware (:2533)
→ DynamicSubagentsMiddleware/SubagentsMiddleware (:2551/:2565)
→ AsyncToolMiddleware (:2576) → PlanModeMiddleware (:2648)
→ SkillUsageMiddleware (:2744)/SkillCuratorMiddleware (:2771) → HarnessSkillMiddleware (:2822)
```

每一项都由对应的 builder 开关决定是否注入，所以实际链长取决于你开了哪些能力；但**相对顺序是硬编码在 `build()` 里的**，不可调。读这段代码时按行号顺着往下扫一遍，就得到了当前版本的完整洋葱层次——这比记表格可靠，因为新能力总是插进来。

另一入口 `HarnessAgent.Builder.fromAgent(existingReActAgent)` 可把现成 ReActAgent 包成 HarnessAgent（customer_work 的渠道接入就这么用，见 7.6）。

## 7.3 能力子包地图

```mermaid
flowchart TB
    HA["HarnessAgent（组合 ReActAgent delegate）"]
    HA --> WS["workspace/<br/>WorkspaceManager / PathPolicy<br/>工作区目录布局与路径规范化"]
    HA --> FS["filesystem/<br/>LocalFilesystem / RemoteFilesystem / SandboxBackedFilesystem<br/>OverlayFilesystem 可插拔文件系统"]
    HA --> SB["sandbox/<br/>SandboxManager / SandboxLease / DockerSandbox<br/>租约 + 快照恢复 + 执行守卫"]
    HA --> MEM["memory/<br/>MemoryConsolidator / compaction.ConversationCompactor<br/>三层记忆与上下文压缩"]
    HA --> SUB["subagent/<br/>SubagentFactory / task.TaskRepository<br/>Markdown 声明子 Agent，同步/后台执行"]
    HA --> SK["skill/<br/>runtime.SkillRuntime / curator.SkillCurator<br/>技能自演化闭环"]
    HA --> BUS["bus/<br/>MessageBus / WorkspaceMessageBus<br/>队列/回放日志/广播 三种消费模式"]
    HA --> GW["gateway/<br/>HarnessGateway / SessionTurnGate / channel.Channel<br/>多渠道消息入口与会话互斥"]
    HA --> TOOLS["tool(s)/<br/>FilesystemTool / ShellExecuteTool / AgentSpawnTool<br/>TaskTool / PlanModeTools / SkillManageTool ..."]
```

各子包一句话 + 关键类：

| 子包 | 关键类 | 要点 |
|---|---|---|
| `workspace` | `WorkspaceManager`、`WorkspaceIndex`、`PathPolicy`、`plan/PlanModeManager` | 工作区是所有能力的物理基座；沙箱/远端模式下**必须走它而非 `java.nio.Files`** |
| `filesystem` | `local/LocalFilesystem(WithShell)`、`remote/RemoteFilesystem`、`sandbox/SandboxBackedFilesystem`、`OverlayFilesystem`、`spec/{Local,Remote,Sandbox}FilesystemSpec` | 同一套读写/grep/glob 抽象，物理落点（本地/远端/沙箱）是配置选择 |
| `sandbox` | `SandboxManager`、`SandboxLease`、`SandboxIsolationKey`、`SandboxExecutionGuard`、`snapshot/*`、`impl/docker/DockerSandbox*` | 租约式生命周期；快照支持跨进程恢复；`IsolationScope`（SESSION/USER/AGENT/GLOBAL）决定隔离粒度 |
| `memory` | `MemoryConfig`、`MemoryConsolidator`、`compaction/{ConversationCompactor,CompactionConfig,ToolResultEvictionConfig}`、`session/SessionTree` | 三层：上下文 → 每日 `memory/YYYY-MM-DD.md` → 节流后台任务合并进 `MEMORY.md`；压缩是**结构化**的（保留目标/状态/发现/下一步），超大工具结果落盘驱逐 |
| `subagent` | `SubagentDeclaration`、`SubagentFactory`、`AgentSpecLoader`、`task/{BackgroundTask,TaskRepository,WorkspaceTaskRepository,TaskStatus}` | Markdown 声明子 Agent；`agent_spawn` 工具触发；后台任务结果经 system-reminder 推回主 Agent，无需轮询 |
| `skill` | `WorkspaceSkillRepository`、`runtime/{SkillRuntime,SkillLoadTool}`、`curator/{SkillCurator,SkillPromoter,SkillSecurityScanner,SkillPromotionGate}` | 自演化闭环：使用统计 → 提案 → 安全扫描 → 审批门 → 晋升为 `workspace/skills/` 下的 Markdown |
| `bus` | `MessageBus`、`WorkspaceMessageBus`、`AsyncToolRegistry` | 三种消费模式：排空队列（单消费者）/ 回放日志（多消费者各自游标）/ 瞬时广播；key 约定如 `agentscope:inbox:<sessionId>` |
| `gateway` | `HarnessGateway`、`MsgContext`、`SessionTurnGate`、`SubagentRegistry`、`channel/{Channel,ChannelRouter,InboundMessage,OutboundAddress}` | 渠道消息 → `MsgContext#canonicalKey` 稳定映射 sessionId → `SessionTurnGate` 每会话公平互斥 → 路由到注册的 `HarnessAgent#call`；`lastRouteBySession` 支持主动推送 |
| `transcript` | `TranscriptStore`、`FilesystemTranscriptStore`、`ObjectStoreTranscriptStore`、`TranscriptRef` | 会话逐事件归档，与 KV 型 `BaseStore` 正交。写入是**不可变分段**（`{tenant}/{agentId}/{sessionId}/events/{seqStart}-{seqEnd}-{writerId}.jsonl`）而非就地追加，多写者不会互相覆盖 |
| `team` | `TeamClient`、`LocalTeamClient`、`TeamContext`、`TeamCreateSpec`、`TeamMemberSpec`、`TeamConflictException` | 多 Agent 协作的任务板 + 信箱模型；`LocalTeamClient` 走 `BaseStore` 的 CAS，另有控制面 HTTP 实现。对应 `TeamsMiddleware` 与 `TeamTool` |
| `coordination` | `PeriodicGate`、`LocalPeriodicGate`、`StoreBackedPeriodicGate` | 周期性后台工作的**最小间隔闸门**：`tryClaim()` 返回 true 才准跑。7.3 末尾"压缩/记忆蒸馏有节流"就是靠它；`StoreBackedPeriodicGate` 让节流跨节点生效，多副本部署下不会每个副本各跑一遍蒸馏 |
| `artifact` | `ArtifactDeliveryTarget`、`ArtifactDeliveryRequest`、`ArtifactDeliveryResult` | 产物出境的传输抽象，配合 `deliver_artifact` 工具（见 7.4） |
| `tool`/`tools` | `FilesystemTool`、`ShellExecuteTool`、`TaskTool`、`AgentSpawnTool`、`ArtifactDeliveryTool`、`MemorySaveTool` 等、`ToolsConfig`（`workspace/tools.json` 声明 MCP 与过滤） | Harness 的能力以内置工具形式暴露给模型 |

**状态三层**（官方文档口径，与第 2 章衔接）：in-call（`AgentState` + `RuntimeContext`）→ cross-call（每次 call 结束自动存/下次自动读，另有永不压缩的全量会话日志 `sessions/<sessionId>.log.jsonl`）→ long-term（`MEMORY.md` 蒸馏，每步推理注入 system prompt）。三条不变式：**system prompt 每步重建**（改 `AGENTS.md`/`MEMORY.md` 立即生效）；压缩/记忆蒸馏有节流（不是每轮都跑）；持久化统一由 core 的 `ReActAgent` + `AgentStateStore` 负责，Harness 不再自带持久化钩子。

## 7.4 几个容易忽略但很实用的机制

### `deliver_artifact`：沙箱里的产物怎么出来

沙箱是个封闭盒子——Agent 在里面生成了报告、图表、压缩包，宿主拿不到。以前各家自己写"从沙箱下载再上传到某处"的胶水代码。现在这条路被收敛成一个内置工具：

```
模型调 deliver_artifact(filePath, fileName?, description?, force?)
  → ArtifactDeliveryTool 从 AbstractFilesystem 把文件下载出来（沙箱工作区也好、远端也好）
  → 交给 builder 上配置的 ArtifactDeliveryTarget 负责运输（对象存储、回调、消息推送……由你实现）
  → 返回 ArtifactDeliveryResult
```

几个设计约束值得注意：

- **不配 `ArtifactDeliveryTarget` 就不注册这个工具**（`Builder#artifactDeliveryTarget(...)`，`:1982`）。没有出境通道时，模型的工具列表里根本看不到它——比"工具存在但一调就报错"干净。`disableFilesystemTools` 也会一并关掉它。
- `fileName` 必须是**纯文件名**：不许有路径分隔符、不许是 `.` 或 `..`。运输目的地的命名空间不由模型的输入决定。
- `force` 默认 `false`，同名文件存在时不覆盖——产物交付是有外部副作用的操作，默认取保守档。

### MCP 注册从"只打日志"到"有回执"

MCP server 注册一直是 **best-effort**：某台 server 起不来、或者 `listTools` 超时，只记日志、不阻断启动（第 4 章 4.6 里 customer_work 也是这个 fail-open 策略）。问题是宿主服务只能去 grep 日志，没法用程序判断"我配的 8 个 MCP，现在几个是活的"。

现在多了一对类型：

```java
public record McpServerRegistrationResult(
        String serverName, String transport, Status status, Instant completedAt, Throwable cause) { }
// Status: SUCCESS / FAILED / SKIPPED

@FunctionalInterface
public interface McpServerRegistrationListener {
    void onCompleted(McpServerRegistrationResult result);   // 每个 server 终态回调一次
}
```

record 的紧凑构造器做了不变式校验：`SUCCESS` 不许带 `cause`，非 `SUCCESS` 必须带 `cause`。挂上 `Builder#mcpServerRegistrationListener(...)` 就能把不健康的 MCP 配置采集进监控、下线或告警——**best-effort 的语义没变，变的是失败对调用方从此可见**。

### 记忆刷写改成 fire-and-forget

`MemoryFlushMiddleware` 原本用 `concatWith` 把记忆刷写接在 agent 事件流后面。后果是：默认 `FlushMode.ALWAYS` 下，**每一次对话的 `onComplete` 都要等一整轮 LLM 抽取 + 磁盘写入**才发出——用户看到最后一个字之后，还要干等好几秒流才算结束。

现在改为 `doOnComplete` + `subscribeOn(boundedElastic()).subscribe()`：对话流立即完成，刷写在后台跑。配套一个必要的细节——**刷写前先 `new ArrayList<>(state.getContext())` 快照一份会话列表**，否则下一次调用清空 state 时，后台还在读的那个 list 会被并发改掉。`MemoryMaintenanceMiddleware` 是同样的结构，一并改了。

代价是显式的：刷写失败不再影响本次对话（它已经完成了），所以**要靠日志和指标观测后台刷写，不能靠调用方的返回值**。

### 文件搜索工具的输出封顶

`grep_files` / `glob_files` 曾被归类为"自限流"的工具，实际不是——一个宽松的 pattern 打在大仓库上，几万行结果直接灌进上下文，一次就把窗口撑爆。现在两个工具都有 `limit` 参数：

| 工具 | 默认 | 硬上限 |
|---|---|---|
| `grep_files` | 100 | 1000 |
| `glob_files` | 200 | 1000 |

超出时截断并追加一条说明，告诉模型"还有多少条没显示"——让它知道该缩小搜索范围，而不是以为自己看到了全部。只有 `list_files` 仍算自限流（正常就返回一个目录的条目）。另外 `read_file` 的区间读改成了流式，读大文件的指定行段不再把整个文件载进内存。

### 沙箱绑定按调用隔离

`SandboxLifecycleMiddleware` 早期把沙箱绑定放在 agent 实例级字段上。一个 `HarnessAgent` 并发服务多个会话时（第 3 章讲过这是框架的正常用法），A 会话的租约会被 B 会话覆写，出现串沙箱。现在绑定是**每次 call 独立**的，与 `CallExecution` 的 per-call 作用域对齐。这条修正的意义和第 3 章 `CallExecution` 设计成 per-call 是同一个：**凡是"属于本次调用"的东西，就不能挂在 agent 实例上**。

### 子 Agent 的两处继承与描述

- `SubagentFactory` 现在能带 `description`。以前自定义工厂注册的子 Agent 在 `agent_spawn` 的工具描述里没有说明文字，模型只能靠名字猜什么时候该派它。
- 子 Agent 现在**继承父 Agent 的 memory 配置**。此前子 Agent 用默认 memory 配置，父 Agent 关掉的记忆能力在子 Agent 里又活了过来，行为不一致。

## 7.5 何时用 ReActAgent，何时用 HarnessAgent

| 场景 | 选择 |
|---|---|
| 对话、意图识别、轻量工具调用 | `ReActAgent` 足够 |
| 需要文件系统/工作区、长任务、上下文压缩、子 Agent、Plan Mode、沙箱执行代码 | `HarnessAgent` |
| 已有 ReActAgent 想加渠道/工程能力 | `HarnessAgent.Builder.fromAgent(agent)` 包装 |

## 7.6 customer_work 实战

### 全量配置的 HarnessAgent 装配

`customer-work-starter/.../agent/HarnessAgentFactory#createHarnessAgent` 是 Harness Builder 用法的活字典，在内层 ReActAgent 之上叠加：

```
HarnessAgent.Builder.fromAgent(innerReActAgent)
  .stateStore(...)  .permissionContext(...)
  .generateOptions(...)          ← 规避框架 #1644：不显式设置则 streamEvents NPE（第 10 章坑 2）
  .workspace(...)  .compaction(ContextMemoryFactory#createCompaction)   ← CompactionConfig 按 yml 的
                                    context.{compression-enabled,max-token,msg-threshold,last-keep} 生成
  .memory(MemoryConfig)  .environmentMemory(...)
  .toolResultEviction(ToolResultEvictionConfig.defaults())
  .enableSkillManageTool()  .enableSkillCurator(SkillCuratorConfig.defaults())
  .additionalContextFile(...)
  .enablePlanMode().allowShellInPlanMode().planFileDirectory(...)
  .subagentFactory(name, id -> expert)    ← 把 MultiAgentOrchestrator 的三个专家注册为 subagent
  + applySandbox：LocalFilesystemSpec | DockerFilesystemSpec + IsolationScope.{SESSION,USER,AGENT,GLOBAL}
```

每个能力对应 `customer-work.harness.*` 一个配置开关——"每个能力 = 一个开关 + 一个可替换实现"是该项目的总设计原则。

### 用 MybatisTaskRepository 替换框架实现

admin 的 VibeCoding 场景里，子 Agent 后台任务（`agent_spawn`）默认由 `subagent/task/WorkspaceTaskRepository` 落工作区文件；`customer-admin-server/.../workspace/task/runtime/MybatisTaskRepository implements TaskRepository` 改为落库，任务列表就能进管理界面查询。**Harness 的每个子系统都留了接口缝**，这是替换点用法的范例。

### 渠道接入：fromAgent 包装

`customer-channel/.../DingTalkChannelConfigurer#start`：`HarnessAgent.Builder.fromAgent(customerServiceAgent)` + `DingTalkChannel` + `ChannelConfig`（Stream 模式 WebSocket，免公网回调），飞书/企微同构——**同一个业务 Agent，包一层就接入一个新渠道**，gateway/channel 抽象（7.3）在生产中的直接体现。

### VibeCoding：workspace 布局

`workspace/vibecoding/service/VibeCodingService` 的目录设计：HarnessAgent workspace 根为 `{agentCode}/`（`MEMORY.md` 跨会话共享），会话级目录 `data/admin-workspace/{agentCode}/sessions/{sessionId}/`——对应 7.3 的三层状态：agent 级记忆与会话级工作产物分层存放。

### 多 Agent 编排：框架之外的 Reactor 手工编排

1.x 的 `Pipelines` 编排 API 在 2.0 已移除。`MultiAgentOrchestrator#consult` 用纯 Reactor 实现"快慢车道"：规则快车道（关键词命中唯一意图直接路由）→ LLM 分诊 → fanout 三个专家 ReActAgent（各自 `subscribeOn(boundedElastic)` + `maxConcurrency` 限流 + 单专家 timeout 隔离）→ reduce 归纳统一口径。**框架提供 Agent 原语，编排交给通用响应式代数**——这是 2.0 的明确取向（详细链路见第 9 章场景 8）。

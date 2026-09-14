# 第 7 章 Harness 工程化外壳（核心）

> 路径前缀：`agentscope-harness/src/main/java/io/agentscope/harness/`
> 裸 ReAct 只解决"一轮任务"；跑数小时、累积状态、需要文件系统与子 Agent 的长任务，靠 Harness。本章讲 `HarnessAgent` 如何在**不改 ReAct 算法一行**的前提下叠加这些能力。

## 7.1 组合而非继承：HarnessAgent 的结构

`agent/HarnessAgent.java`（2922 行）**implements `Agent`，内部组合一个 `ReActAgent delegate`**。所有 `call/streamEvents` 重载都经 `wrappedCall`（`:938`）：

```mermaid
flowchart TB
    HC["HarnessAgent#call (:715，8 个重载)"] --> ESD["HarnessAgent#ensureSessionDefaults (:1010)<br/>补默认 sessionId/userId"]
    ESD --> WC["HarnessAgent#wrappedCall (:938)"]
    WC --> ACQ["SandboxLifecycleMiddleware#acquireForCall<br/>获取沙箱租约"]
    ACQ --> DEL["ReActAgent#call<br/>进入第 3 章的完整循环<br/>（Harness 能力已作为 middleware/tool 注入其中）"]
    DEL --> REL["SandboxLifecycleMiddleware#releaseForCall<br/>释放租约"]
    DEL -.->|"上下文溢出错误"| REC["HarnessAgent#recoverFromOverflow (:1042)<br/>压缩后重试兜底"]
```

官方架构文档（`docs/v2/en/docs/harness/architecture.md`）的三条核心原则，读 Harness 源码前先记住：

1. **能力叠加在推理循环之上，而非嵌入其中**——workspace 注入、压缩、子 Agent、沙箱、Plan Mode 各自挂在循环的关键时刻（以 Middleware/Tool 形式），核心算法零改动；
2. **能力之间互不依赖，只共享三个对象**——`RuntimeContext`（本次调用是谁）、workspace（读写哪些文件）、`AgentStateStore`（如何恢复）；
3. **内置 middleware 顺序固定，用户 middleware 永远排在最前面（最外层）。** 这条在源码层面有个前提：用户 middleware 经 `Builder#middleware(...)` 在调用时就直接注册进内层 `ReActAgent.Builder`（`:1588`），早于 `build()` 注入的全部内置层，所以同为默认 `order()=1` 时才排在最外。一旦你的 middleware 覆写了 `order()` 并返回 0 或负数，它会被排序到所有内置层**里面**（排序规则见第 6 章 6.1）。

## 7.2 Builder 装配：内置 Middleware 的固定顺序

`HarnessAgent.Builder#build`（`:2302` 起，约 600 行）向内部 `ReActAgent.Builder` 按固定顺序注入内置 middleware（列表顺序 = 洋葱层次，第 6 章）：

```
用户 middleware（最外层）
→ SandboxLifecycleMiddleware (:2466) → AgentTraceMiddleware (:2469)
→ WorkspaceContextMiddleware (:2475) → AtPathExpansionMiddleware (:2487)
→ TranscriptMiddleware (:2505)
→ MemoryFlushMiddleware (:2517) → MemoryMaintenanceMiddleware (:2537)
→ CompactionMiddleware (:2552) → ToolResultEvictionMiddleware (:2558)
→ InboxMiddleware (:2561) → TeamsMiddleware (:2571)
→ DynamicSubagentsMiddleware/SubagentsMiddleware (:2589/:2603)
→ AsyncToolMiddleware (:2614) → PlanModeMiddleware (:2686)
→ SkillUsageMiddleware (:2782)/SkillCuratorMiddleware (:2809) → HarnessSkillMiddleware (:2860)
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

### 两条核心链路：agent_spawn 与上下文压缩

**`agent_spawn`**（`tool/AgentSpawnTool.java`）是子 Agent 能力的入口。模型的一次调用会按"有没有任务、超时设多少、是不是远程"分流到四条执行路径：

```mermaid
flowchart TB
    SP["AgentSpawnTool#agentSpawn (:301)"] --> DEP{"嵌套深度 > MAX_SPAWN_DEPTH（3）？"}
    DEP -->|"是"| E1["Error: Maximum spawn depth exceeded"]
    DEP -->|"否"| CR["DefaultAgentManager#createAgentIfPresent (:107)<br/>按 agent_id 取声明式 / 自定义工厂子 Agent"]
    CR --> PREP["persistSpawnEntry (:1053) 登记会话<br/>propagatePlanMode (:739) 父在 Plan Mode 则子只读<br/>propagateParentDenyRules (:1713) 下发 DENY"]
    PREP --> TASK{"带 task？"}
    TASK -->|"否"| ACC["status: accepted<br/>只建会话，等后续 agent_send"]
    TASK -->|"是"| TO{"resolveEffectiveTimeoutMs (:1531)"}
    TO -->|"0：纯后台"| BG["TaskRepository#putTask<br/>本地：LocalTaskRunSpec 内 invokeAgent(...).block()<br/>远程：RemoteTaskRunSpec<br/>立即返回 task_id"]
    TO -->|"> 0 且远程"| RS["runRemoteSyncReactive (:1292)<br/>经 agent-protocol 调远端（第 8 章）"]
    TO -->|"> 0 且本地"| TP["execWithTimeoutPromotion (:881)<br/>execLocalSync 与超时赛跑"]
    TP --> LS["execLocalSync (:768)<br/>注入 FORWARDING_CONTEXT_KEY<br/>子 Agent 事件转发进父流（第 6 章 6.3）"]
    TP -->|"超时 + forceSync"| INT["interruptAgent (:985)<br/>返回 status: timeout"]
    TP -->|"超时，未强制同步"| PRO["转为后台任务继续跑，不丢弃已进行的工作"]
    ACC --> EXP["withSubagentExposedEvent (:1575)<br/>按需发 SubagentExposedEvent"]
    BG --> EXP
    RS --> EXP
    LS --> EXP
```

两点值得注意。**纯后台路径看不到子 Agent 的流式事件**：`LocalTaskRunSpec` 在后台线程里 `block()` 等结果，没有父级 Context，自然也没有转发 emitter——这是有意为之，后台任务的结果经 `SubagentsMiddleware` 以 system-reminder 形式在下一轮推回主 Agent。**同步路径超时默认不中断**：`execWithTimeoutPromotion` 让子 Agent 转去后台继续跑，只有开启 force-sync 时才会调用 `interruptAgent` 真正打断。

**上下文压缩**挂在 `onReasoning` 上，每轮推理前检查一次：

```mermaid
flowchart TB
    CM["CompactionMiddleware#onReasoning (:76)<br/>非 ReActAgent 直接放行"] --> SPLIT["拆出首条 SYSTEM 消息，其余为 conversation"]
    SPLIT --> CI["ConversationCompactor#compactIfNeeded (ConversationCompactor.java:92)"]
    CI --> PRE["truncateArgs (:612) 截断超长工具参数<br/>→ pruneToolResults (:510) 修剪旧工具结果"]
    PRE --> TOK["TokenCounterUtil#calculateToken (:73)<br/>ThinkingBlock 按实际长度计（见 7.4）"]
    TOK --> SC{"shouldCompact (:217)？"}
    SC -->|"否"| PASS["next.apply(原输入)"]
    SC -->|"是"| CUT["determineCutoffIndex (:245)<br/>→ findSafeCutoffPoint (:296) 切点落在 TOOL 消息上时<br/>回退到发起该调用的 ASSISTANT 消息之前，不拆开调用与结果"]
    CUT --> FL["flushBeforeCompact：MemoryFlushManager#flushMemories (:115)<br/>先把要被压掉的前缀蒸馏进记忆"]
    FL --> OFF["offloadBeforeCompact：全量消息落盘，拿到文件路径"]
    OFF --> SUMM["summarizePrefix (:344) 调模型总结前缀<br/>→ buildSummaryMessage (:454) 附带落盘路径"]
    SUMM --> APPLY["CompactionMiddleware#applyToContext (:220)<br/>摘要 + 保留尾部 写回 AgentState"]
    APPLY --> NEXT["next.apply(SYSTEM + 压缩后消息)"]
    CI -.->|"异常：中断原样抛出，其余只打日志"| PASS
```

压缩的顺序是**先蒸馏、再落盘、最后总结**：被压掉的那段对话先由 `flushMemories` 提取进长期记忆，再把全量消息写到文件，摘要里带上文件路径，模型需要细节时还能读回原文。压缩失败时降级为不压缩、继续推理，但**中断异常例外**——它会原样抛出。这正是 v2.0.3 的修正（#2659），此前用户中断会被吞掉，记成一次"压缩失败"。

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

- **不配 `ArtifactDeliveryTarget` 就不注册这个工具**（`Builder#artifactDeliveryTarget(...)`，`:2020`）。没有出境通道时，模型的工具列表里根本看不到它——比"工具存在但一调就报错"干净。`disableFilesystemTools` 也会一并关掉它。
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

2.0.3 的实际实现比"起一个后台订阅"多了一层**按节流 key 排队**，避免同一用户或会话的刷写并发执行、互相踩踏：

```mermaid
flowchart TB
    OA["MemoryFlushMiddleware#onAgent (:153)<br/>next.apply(input).doOnComplete(...)"] -->|"流正常完成才触发<br/>出错或取消都不刷"| SCH["scheduleFlush (:162)<br/>key = compositeTimerKey (:310)<br/>= memory-flush:SCOPE:timerKey"]
    SCH --> Q{"FLUSH_QUEUES[key] 正在运行？"}
    Q -->|"否"| RUN["runFlush (:203)<br/>Mono.defer(doFlush).subscribeOn(boundedElastic).subscribe()"]
    Q -->|"是"| PEND["pending.put(会话键, 任务)<br/>同一会话只保留最新一个，旧的被替换"]
    RUN --> DF["doFlush (:251)<br/>new ArrayList(state.getContext()) 快照"]
    DF --> SH{"shouldFlushNow (:291)"}
    SH -->|"ALWAYS"| FM["MemoryFlushManager#flushMemories (MemoryFlushManager.java:115)<br/>模型抽取 → 写 memory/YYYY-MM-DD.md"]
    SH -->|"THROTTLED"| PG["PeriodicGate#tryClaim(key, minGap)"]
    PG -->|"抢到时间窗"| FM
    PG -->|"窗口内"| SKIP["跳过"]
    SH -->|"NEVER"| SKIP
    FM --> FIN["doFinally → drainFlushQueue (:214)<br/>取出下一个 pending 任务继续跑，队列空则移除 key"]
    SKIP --> FIN
    PEND -.-> FIN
```

这里有个取舍：排队的任务在**真正执行时**才读取会话状态，而不是在加入队列时读。所以一次刷写进行期间，同一会话又完成了几轮对话，只会再补一次刷写，读到的是最新的上下文，不会每一轮各刷一遍。

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

- `Builder#subagentFactory(name, description, factory)`（`:1917`）多了带 `description` 的重载，内部存为 `HarnessAgentBuilderSupport.SubagentFactoryEntry(name, description, factory)`。以前自定义工厂注册的子 Agent 在 `agent_spawn` 的工具描述里只有名字，模型只能靠名字猜什么时候该派它；`description` 为空时仍回退为名字。
- 子 Agent 现在**继承父 Agent 的 memory 配置**。此前子 Agent 用默认 memory 配置，父 Agent 关掉的记忆能力在子 Agent 里又活了过来，行为不一致。
- **父 Agent 的 DENY 规则强制下发**（2.0.1）。`AgentSpawnTool#collectParentDenyRules`（`AgentSpawnTool.java:1258`）把父 `PermissionContextState` 里的 deny 规则摊平后带给子 Agent，本地子 Agent 与远程子 Agent（经 `RemoteSubmitContext`）走同一份。只下发 DENY、不下发 ALLOW 是刻意的：**子 Agent 的权限只能比父更紧，不能借派生绕过父级的禁令**。声明式子 Agent 可以在 `SubagentDeclaration` 上关掉 `inheritParentPermissions`，默认开启。

**发版说明与 tag 不一致的一条**：v2.0.3 的 GitHub Release 列了「子 Agent 继承 pending 工具恢复开关」（#3017），但对应提交 `787aa01d` 只在 main 分支上，**v2.0.3 tag 并不包含**——tag 源码里 `enablePendingToolRecovery` 只在 `HarnessAgent.Builder`（`:1654`）和 `fromAgent` 复制时出现，不会传给子 Agent。用 2.0.3 的话，子 Agent 需要在其自身构建处显式开启。

> **main 已变更（未发版）**：#3017 已在 main 合入（`787aa01d`）。父 `HarnessAgent` 的 `enablePendingToolRecovery` 会下发给声明式子 Agent 和内置的 general-purpose 子 Agent；声明式子 Agent 还可以在 Markdown frontmatter 里用 `enable_pending_tool_recovery`（或驼峰写法）单独覆盖——子 Agent 自己声明了就用自己的，没声明才继承父级。

### 同一实例上的会话级操作补齐

`HarnessAgent` 是组合而非继承（7.1），所以 `ReActAgent` 上新增的会话级 API 不会自动出现在它身上，得逐个转发。截至 v2.0.3 已补齐：

| API | 位置 | 说明 |
|---|---|---|
| `interrupt(ctx)` / `interrupt(ctx, msg)` / `interrupt(userId, sessionId)` / `interrupt(userId, sessionId, msg)` | `:598`~`:627` | 2.0.3 才补上（#2600）。此前 `HarnessAgent` 只有无参和 `(Msg)` 两个重载，**只能打断默认会话**——用它并发服务多会话时，业务侧根本没法中断指定用户的那一次调用 |
| `clearContext(ctx)` / `clearContext(userId, sessionId)` | `:352` / `:365` | 清空模型可见的会话上下文，身份与权限/工具/任务状态保留（语义详见第 2 章 2.4） |
| `clearStateCache()` 及两个按会话的重载 | `:373`~`:394` | 只释放本地缓存，不动 store |

### 后台节流的 key 不能撞

`MemoryFlushMiddleware` 与 `MemoryMaintenanceMiddleware` 都靠 `PeriodicGate`（7.3 的 `coordination` 子包）做最小间隔节流，两者配置的间隔也不同。但早期它们算出的闸门 key 都是 `isolationScope + ":" + timerKey`——**同一个 key**。结果是先跑的那个占住时间窗，另一个在窗口内一直 `tryClaim()` 失败：配置了"每 10 分钟刷写、每 6 小时维护"，实际可能维护永远跑不起来。

v2.0.3 给 key 加了操作前缀（#2993）：

```java
return "memory-flush:"       + isolationScope.name() + ":" + timerKeyFor(rc);   // MemoryFlushMiddleware.java:311
return "memory-maintenance:" + isolationScope.name() + ":" + timerKeyFor(rc);   // MemoryMaintenanceMiddleware.java:181
```

原来的 scope 前缀是为了隔离维度（`userId` 恰好等于某个 `sessionId` 时不串）；这次补的是**操作**维度。自己用 `PeriodicGate` 做节流时，key 要同时带上"谁"和"做什么"。

### 文件系统层三处"不再把错误吞成空结果"

这几条是同一类问题——**错误被伪装成合法的空结果**，模型据此做出错误决策，而且日志里什么都看不到：

- **`LocalFilesystemWithShell#execute` 管道死锁**（#2839）。旧实现先 `proc.waitFor(timeout)`，结束后才 `readAllBytes()` 读 stdout/stderr。子进程输出一旦超过 OS 管道缓冲区（Linux 默认 64KiB，macOS 更小），就阻塞在写管道上等人读，而父进程在等它退出——互相等到超时，**被误报成"命令超时"**。现在改为起两个 daemon 线程（`drainAsync`，`LocalFilesystemWithShell.java:464`）在 `waitFor`（`:358`）期间并发读空两个流。这是 `ProcessBuilder` 的经典坑，自己写进程调用时同样适用。
- **沙箱文件系统读操作**（#2967）。`ls` / `read` / `grep` / `glob` 此前不检查 `execute()` 是否成功：命令本身没跑起来（沙箱失联、超时）时，`ls` 返回空列表、`read` 返回 `file_not_found`，模型会以为"目录是空的""文件不存在"然后去新建。现在 `BaseSandboxFilesystem` 统一先判 `isSuccess()`，失败就带上 `executeFailureMessage`（`:458`）返回错误；只有"命令确实跑了、退出码 >0 且不是超时的 124"才仍判为文件不存在。
- **`ls()`**（#2413）同理，`LocalFilesystem`、`BaseSandboxFilesystem` 与 `FilesystemTool` 三处一起改为出错即报错，而不是静默返回空列表。

### 压缩的 token 估算把 thinking 算进去了

`TokenCounterUtil`（`memory/compaction/TokenCounterUtil.java:132`）估算上下文 token 数时，`ThinkingBlock` 以前按一个固定的兜底开销计。推理模型一轮的 thinking 可能有几千 token，被严重低估的后果是**压缩触发得太晚**，真正发请求时才撞上模型的上下文上限。现在按 thinking 文本实际长度估算，嵌套在 `ToolResultBlock` 里的 thinking 也一并计入（#3009）。

### 其它 2.0.1 起的小项

- 默认工作区可由环境变量 `AGENTSCOPE_WORKSPACE`（`:1143`）指定，便于镜像打包时把工作区挂到固定卷上。

> **main 已变更（未发版）**：内置的 `web_fetch` 与 `web_search`（后者依赖 Tavily，需要 `TAVILY_API_KEY`）在 2.0.3 的 `Builder#build` 里是**无条件注册**的（`HarnessAgent.java:2670`），不受任何开关控制——内网部署时模型照样能在工具列表里看到它们，调用时才失败。main 新增 `Builder#disableWebTools()`（#3075），以及 `Builder#webHttpClient(HttpClient)`，用于注入自定义的 `HttpClient`，比如配代理或出网白名单（#3103）。

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

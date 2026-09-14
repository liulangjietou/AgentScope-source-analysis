# 第 9 章 customer_work 场景全景映射（实战）

> 本章从**业务场景**视角出发：每个场景 = 用了什么 AgentScope 能力 + 入口在哪 + 调用链长什么样 + 对应本指南哪一章。
> 实战路径相对 customer_work 仓库根；`starter/...` 代表 `customer-work-starter/src/main/java/com/richard/fyoung/customerwork/...`，`admin/...` 代表 `customer-admin-server/src/main/java/com/richard/fyoung/customeradmin/...`。
> 本章的方法级链路图（带行号的 mermaid 图）依据 customer_work main 分支 `85fde31`（2026-09-10，已升级至 agentscope 2.0.3）逐一核对；图中 customer_work 侧行号基于该提交，框架侧行号基于 v2.0.3。正文文字写于更早的版本，个别包路径与现状不同，以图中类名为准。

## 9.0 项目模块与请求流向

```mermaid
flowchart LR
    subgraph FRONT["前端"]
        H5["customer-work-app (H5, 5175)"]
        ADMIN_W["customer-admin-web (Vue3, 5174)"]
    end
    GW["customer-work-gateway<br/>Spring Cloud Gateway + Nacos"]
    subgraph BACK["后端"]
        APP["customer-work-app-server :8080<br/>客服应用 HTTP/SSE/WS"]
        CH["customer-channel :8081<br/>钉钉/飞书/企微/微信 + 官方五套 Web 端"]
        ADM["customer-admin-server :8082<br/>后台管理 + 工作区对话 + VibeCoding"]
    end
    STARTER["customer-work-starter<br/>全部 AgentScope 集成代码所在地<br/>（@AutoConfiguration 自动装配）"]
    H5 --> GW --> APP
    ADMIN_W --> GW --> ADM
    APP --> STARTER
    CH --> STARTER
    ADM -->|"排除自动装配，显式 new"| STARTER
```

## 9.1 场景速查表

| # | 业务场景 | AgentScope 能力 | 入口 | 详见 |
|---|---|---|---|---|
| 1 | 客服同步对话 | `ReActAgent#call` + StateStore + 权限 + Middleware 链 | `starter/service/CustomerServiceService#chat` | 第 3 章 |
| 2 | 流式回复（SSE） | `ReActAgent#streamEvents` 事件流 | 同上 `#chatStream` | 第 3、6 章 |
| 3 | 结构化意图识别 | `call(prompt, Class, ctx)` 结构化输出 | 同上 `#classifyIntent` | 第 3 章 3.7 |
| 4 | 知识库检索 / RAG | `Knowledge` + `RAGMode.AGENTIC` + 自研注入 middleware | `starter/rag/KnowledgeProvider` | 本章 9.2 |
| 5 | 七域业务工具 | `Toolkit` 分组 + `@Tool` + 后端 SPI | `starter/tool/ToolRegistrar` | 第 4 章 |
| 6 | MCP / AI 网关 | `McpClientBuilder` + `HigressMcpClientBuilder` | `starter/tool/McpToolkitConfigurer` | 第 4 章 |
| 7 | 三层会话记忆 | StateStore（L1）+ `LongTermMemory`（L2）+ 自研 FactLog（L3）+ Compaction | `starter/memory/` | 第 2、7 章 |
| 8 | 多 Agent 编排 | 多 `ReActAgent` + Reactor 手工编排 + subagent 注册 | `starter/agent/MultiAgentOrchestrator` | 本章 9.3 |
| 9 | Harness 高级能力 | Plan Mode / Sandbox / Subagent / 技能自演化 | `starter/agent/HarnessAgentFactory` | 第 7 章 |
| 10 | 人机协作（审批+转人工） | `PermissionEngine` ask 规则 + `@Tool` 转工单 | `starter/config/PermissionConfig`、`tool/HumanHandoffTools` | 本章 9.4 |
| 11 | 多渠道接入 | harness `Channel` + `DingTalkStreamClient` 复用 | `customer-channel/.../XxxChannelConfigurer` | 第 7、8 章 |
| 12 | AG-UI 协议 | `AguiAgentAdapter` + `AguiEventEncoder` | `starter/agent/AguiService` | 第 8 章 |
| 13 | A2A 对外导出 | `AgentScopeA2aServer` + 自定义 `AgentRunner` | `admin/a2a/A2aController` | 第 8 章 |
| 14 | 定时任务驱动 Agent | `XxlJobAgentScheduler` / 同步 `Agent#call` | `starter/config/XxlJobSchedulerConfig`、`admin/aiconfig/scheduledtask/` | 第 8 章 |
| 15 | VibeCoding 编码助手 | HarnessAgent workspace + `agent_spawn` + 自研 `TaskRepository` | `admin/workspace/vibecoding/` | 第 7 章 |
| 16 | 可观测与调用日志 | `OtelTracingMiddleware` + 自研 `Tracer` + `JsonlTraceExporter` + 打点 middleware | `starter/observability/`、`starter/calllog/` | 第 6 章 |
| 17 | 配置热更新 | Nacos 提示词 + `MutableDelegatingModel#swap` | `starter/config/NacosPromptService`、`RuntimeConfigApplier` | 第 5 章 |

场景 1/2/3/5/6/9 的调用链已在对应章节的实战小节展开，下面细讲四个跨章节的综合场景。

### 场景 1~3：一次客服请求的三条入口

同步对话、流式回复、意图识别共用 `CustomerServiceService` 与 `CustomerServiceAgentFactory`，但各自对 Agent 的持有方式不同：

```mermaid
flowchart TB
    subgraph S1["场景 1：同步对话"]
        C1["CustomerServiceController#chat (:63)"] --> SV1["CustomerServiceService#chat (:331)"]
        SV1 --> Q1{"TenantQuotaGuard#check (:50)"}
        Q1 -->|"超额拒绝"| QR["QUOTA_EXCEEDED_REPLY"]
        Q1 -->|"放行 / 降级"| SC1{"启用语义缓存？<br/>SemanticCacheService#lookup (:107)"}
        SC1 -->|"命中"| HIT["applyOutboundGuard (:270) 出站过滤后直接返回"]
        SC1 -->|"未命中 / 未启用"| IA["invokeAgent (:363)"]
        IA --> RA["resolveAgent (:807)<br/>sessionAgents.computeIfAbsent → CustomerServiceAgentFactory#createAgent (:208)"]
        RA --> LOCK["withSessionLock (:845) 应用侧会话串行"]
        LOCK --> CALL["ReActAgent#call(spotlightAttachments(text), ctx)<br/>ctx = CustomerServiceAgentFactory#contextFor (:146)"]
        Q1 -.->|"降级"| DEG["contextWrite(ModelRoutingContext#preferFallback (:25))<br/>路由到备用模型"]
    end
    subgraph S2["场景 2：流式回复"]
        C2["CustomerServiceController#chatStream (:74)"] --> SV2["CustomerServiceService#chatStream (:414)"]
        SV2 --> SC2{"语义缓存"}
        SC2 -->|"命中"| SCA["streamCachedAnswer (:468) 切块模拟流式"]
        SC2 -->|"未命中"| SFC["streamFromAgentAndCache (:487)"]
        SFC --> SFA["streamFromAgent (:506)<br/>withSessionLockFlux (:856)"]
        SFA --> SE["ReActAgent#streamEvents → publishOn(boundedElastic)<br/>取 TextBlockDeltaEvent；无 delta 时用 AgentResultEvent 补全文"]
        SE --> GUARD["newOutboundGuard (:257) → SensitiveWordStreamGuard<br/>流末 flush (:113) 吐出攒住的尾部"]
    end
    subgraph S3["场景 3：结构化意图识别"]
        C3["CustomerServiceController#classifyIntent (:96)"] --> SV3["CustomerServiceService#classifyIntent (:594)"]
        SV3 --> USING["Mono.using：CustomerServiceAgentFactory#createAgent(intent:{sessionId})<br/>一次性 Agent，用完 AgentResourceCloser#closeQuietly (:25)"]
        USING --> SO["ReActAgent#call(prompt, IntentResult.class, ctx)<br/>（第 3 章 3.7 结构化输出）"]
        SO -->|"无结构化数据 / 异常"| FB["fallbackIntent：intent = other，转人工兜底"]
        SV3 -.-> SUB["整体 subscribeOn(boundedElastic)"]
    end
```

三条入口对 Agent 实例的管理方式各不一样，这是读这段代码的关键：同步和流式复用 `sessionAgents` 里的会话级热实例（`resolveAgent` 用 `computeIfAbsent`）；意图识别每次用 `Mono.using` 新建一个 `"intent:"` 前缀的临时 Agent，用完立即关闭，不污染真实会话，也不占热缓存。

## 9.2 场景 4：RAG 的两条互补路径

```mermaid
flowchart TB
    subgraph P1["路径一：框架原生 RAG（AGENTIC 模式）"]
        B["CustomerServiceAgentFactory#createAgent<br/>builder.knowledge(...).ragMode(RAGMode.AGENTIC)"]
        KP["KnowledgeProvider#build 四后端切换<br/>memory: 自研 InMemoryKeywordKnowledge implements Knowledge<br/>simple: SimpleKnowledge + DashScopeTextEmbedding + InMemoryStore<br/>bailian: BailianKnowledge ／ dify: DifyKnowledge"]
        KRT["模型经 KnowledgeRetrievalTools 自主决定何时检索<br/>（core rag 包，第 8 章）"]
        B --> KP --> KRT
    end
    subgraph P2["路径二：瞬态注入 Middleware（GENERIC 式，自研实现）"]
        KIM["KnowledgeInjectionMiddleware#onReasoning<br/>每轮末尾追加 METADATA_SYNTHETIC 消息，不落 AgentState.context"]
        SPOT["ContentSpotlighter.wrap 随机标签隔离<br/>+ onSystemPrompt 幂等追加防注入规则"]
        KIM --> SPOT
    end
    P1 -.->|"模型主动查"| LLM["进入模型的消息"]
    P2 -.->|"每轮自动注入"| LLM
```

另有工具形式第三入口：`starter/tool/KnowledgeBaseTools`（`@Tool` 委托 `KnowledgeBackend` SPI）。三条路径可并存，靠配置选择。工程细节：`KnowledgeProvider` 用 `@PostConstruct warmUp()` 启动期预热，规避 `block()` 落在 `reactor-http-nio` 线程抛 `IllegalStateException`（第 10 章坑 4）；admin 侧 `KnowledgeRetrievalMiddleware` 直接继承 starter 的注入 middleware，只换数据源。

## 9.3 场景 8：多 Agent 编排（快慢车道 + 并行会诊 + reduce）

```mermaid
flowchart TB
    IN["CustomerServiceController#consult (:123)"] --> ORCH["MultiAgentOrchestrator#consult (:257)"]
    ORCH --> EN{"multi-agent.enabled ？"}
    EN -->|"否"| DIS["DISABLED_REPLY"]
    EN -->|"是"| BS["buildSpecialists (:181)<br/>按配置 experts 逐个构建专家 ReActAgent<br/>（按 order 排序，按 toolGroups 装配工具）"]
    BS --> MODE{"mode = sequential ？"}
    MODE -->|"是"| SEQ["sequential (:433) 专家依次调用"]
    MODE -->|"否"| SEL["selectExperts (:293)"]
    SEL --> RT{"routing-enabled ？"}
    RT -->|"否"| ALL["全部专家"]
    RT -->|"是"| FAST{"fast-route-enabled 且<br/>fastRouteIntent (:361) 恰好命中一类意图？<br/>（关键词来自配置 routeKeywords，多类命中视为模糊）"}
    FAST -->|"命中"| PICK["expertsForIntent (:335) 按意图挑专家"]
    FAST -->|"未命中"| ROUTER["routerAgent (:454) 一次性路由 Agent<br/>ReActAgent#call(text, IntentResult.class, ctx)"]
    ROUTER -->|"成功"| PICK
    ROUTER -->|"失败"| ALL
    PICK --> FAN["fanout (:384)<br/>flatMap(task.subscribeOn(boundedElastic), maxConcurrency)<br/>每个专家 callExpert (:417)，单专家超时隔离"]
    ALL --> FAN
    FAN --> RED["reduce (:396)<br/>reduceEnabled 且多于一个专家 → reducerAgent (:474) 归纳统一口径<br/>否则 aggregate (:442) 直接拼接；归纳失败退回拼接"]
    SEQ --> CLOSE["doFinally → closeAgents (:488)"]
    RED --> CLOSE
```

要点：规则先行省 LLM 成本；专家互相隔离（一个超时不拖垮整单）；同一批专家还被 `HarnessAgentFactory` 经 `builder.subagentFactory(name, id -> expert)` 注册为 harness subagent（第 7 章），主 Agent 也能通过 `agent_spawn` 委派——**同一组 Agent，两种编排入口**。

## 9.4 场景 10：人机协作全链路（审批 + 转人工 + 工单）

```mermaid
flowchart TB
    U["用户：我要退款"] --> AGENT["ReActAgent 推理<br/>产生 ToolUseBlock(退款工具)"]
    AGENT --> PERM["PermissionEngine 评估（第 3 章 3.5）<br/>PermissionConfig 按配置 addAskRule(tool, *, ASK)"]
    PERM --> ASKED["RequireUserConfirmEvent + PERMISSION_ASKING 终态<br/>状态落 StateStore，调用返回"]
    ASKED --> CONFIRM["前端确认 → 下次 call 带 METADATA_CONFIRM_RESULTS<br/>→ doCallInner 情况 4 → resumeAgent 直进 acting"]
    AGENT --> HAND["或模型调 HumanHandoffTools#transferToHuman (:50)"]
    HAND --> HS["HandoffService#create (:87)"]
    HS --> LEG{"isLegacyMode (:238) ？"}
    LEG -->|"是"| LS["legacyStore.save 独立转人工单"]
    LEG -->|"否"| TK["TicketService#findActiveBySession (:247)<br/>没有则 createForSession (:49)"]
    TK --> RH["TicketService#requestHandoff (:70)<br/>AI_SERVING → WAITING_AGENT（BOT 发起）"]
    RH --> EN["原状态为 AI_SERVING 时 fireEnrichment (:112)<br/>异步补全会话总结等信息"]
    HAND -.->|"任何异常"| BUSY["onErrorResume：回复「人工坐席通道繁忙，已为您记录」<br/>不中断对话（fail-open）"]
    subgraph OBS["旁路观测"]
        HAM["HumanApprovalMiddleware#onActing (:37)<br/>命中受控工具只打日志；order() = MiddlewareOrders.HUMAN_APPROVAL<br/>真正的闸门在 PermissionEngine"]
    end
    AGENT -.-> OBS
```

配套两个"裸 Model"辅助（第 5 章 5.6）：`TicketClassifier#classify` 智能分单（抽 JSON 得 category/skill/priority/emotion，fail-open 降级规则版）、`ConversationSummaryService` 转人工前的会话总结。

## 9.5 其余场景一句话导航

- **场景 7（三层记忆）**：L1 = `SessionConfig` 四后端 StateStore（第 2 章实战）；L2 = `LongTermMemoryProvider` 四后端（memory 自研 / bailian / mem0 / reme，`LongTermMemoryMode.BOTH`）；L3 = 自研 `FactLog` append-only 事实流水；压缩 = `ContextMemoryFactory#createCompaction` → Harness `CompactionConfig`（第 7 章实战）。
- **场景 11（多渠道）**：演示线走框架 `Channel`（第 7 章实战）；生产线 `customer-channel/.../access/dingtalk/DingTalkStreamConnector` 实现自研 `ImChannelConnector` SPI，复用框架 `DingTalkStreamClient`（JDK WebSocket），消息经 `ChannelMessagePipeline` → `AdminOpenApiClient` 调 admin 开放 API——**框架类库可以只取传输层复用**。
- **场景 12（AG-UI）**：`CustomerServiceController#agui` → `AguiService#run` → `AguiAgentAdapter(agent, config).run(RunAgentInput)` → `AguiEventEncoder#encode` → SSE。8081 侧另有官方 starter 自动装配的同款端点，一套协议两种集成深度。
- **场景 13（A2A）**：`admin/a2a/A2aController`（`/.well-known/agent-card.json` + JSON-RPC）→ `AgentScopeA2aServer` + `ConfigurableAgentCard`；执行器 `AdminAgentRunner implements AgentRunner`，与页面对话共用 `AgentInstanceCache`。默认关闭（`admin.a2a.enabled=false`）。
- **场景 14（定时任务）**：starter 走官方 `XxlJobAgentScheduler`（cron 只在 XXL-JOB 控制台配）；admin 的 `ScheduledTaskService#execute` 每次分配全新 sessionId 同步 `Agent#call` 并落执行历史——定时驱动下"每次执行独立会话"是刻意选择。
- **场景 16（可观测）**：三套并存各管一段——`OtelTracingConfig`（OTel + OTLP gRPC，与自研 `LoggingTracer` 互斥）、`AgentCallTimingMiddleware`（`onModelCall` 取 `ChatUsage`、按 `ToolKindRegistry` 归类 TOOL/MCP/SKILL 分段耗时）、`JsonlTraceExporter`（数据飞轮 JSONL 落盘）。
- **场景 17（热更新）**：`NacosPromptService`（系统提示词优先取 Nacos，回退内置 + `runtimeFacts()` 注入当前日期）+ `RuntimeConfigApplier` → `MutableDelegatingModel#swap`（第 5 章装饰器栈）+ `flushHotAgents` 清缓存不动 StateStore——**提示词、模型、Agent 缓存三层各自的热更新粒度**。

### 场景 11 / 12 / 13 / 14 / 17 的方法级链路

```mermaid
flowchart LR
    subgraph S11["场景 11：钉钉渠道（customer-channel 生产线）"]
        D1["DingTalkStreamConnector#start (:63)<br/>复用框架 DingTalkStreamClient（WebSocket）"] --> D2["onMessage (:92)"]
        D2 --> D3["ChannelMessagePipeline#submit (:38)<br/>按 serialKey 串行执行"]
        D3 --> D4["handle (:45)<br/>非文本提示 · 新会话指令 → resetSession (:109)"]
        D4 --> D5["AdminOpenApiClient#resolveSession (:104)<br/>per-message 模式则生成一次性会话"]
        D5 --> D6["AdminOpenApiClient#chat (:150)<br/>POST admin 开放 API，blockLast(超时)"]
    end
```

```mermaid
flowchart LR
    subgraph S12["场景 12：AG-UI"]
        A1["CustomerServiceController#agui (:134)"] --> A2["AguiService#run (:60)<br/>Flux.using 按会话新建 Agent，结束时 closeQuietly"]
        A2 --> A3["AguiAgentAdapter#run (框架 AguiAgentAdapter.java:125)<br/>AgentEvent → AguiEvent"]
        A3 --> A4["AguiService#finalizeEvent (:82)<br/>按 messageId 累积文本，捕获终态"]
        A4 --> A5["AguiEventEncoder#encode (框架 :52) → SSE"]
    end
    subgraph S13["场景 13：A2A 对外导出（admin）"]
        B1["A2aController#agentCard (:78)<br/>→ AgentScopeA2aServer#getAgentCard (框架 :151)"]
        B2["A2aController#jsonRpc (:92)<br/>→ AgentScopeA2aServer#getTransportWrapper (框架 :113)"] --> B3["AgentScopeAgentExecutor#execute (框架 :107)"]
        B3 --> B4["AdminAgentRunner#streamEvents (:73)<br/>Flux.defer 包住装配异常 · 绑定租户与调用身份"]
        B4 --> B5["AgentInstanceCache#getOrBuild (:46)<br/>与后台对话共用实例缓存"]
        B5 --> B6["agentEvents (:130) → Agent#streamEvents"]
    end
```

```mermaid
flowchart LR
    subgraph S14["场景 14：定时任务（admin）"]
        T1["ScheduledTaskService#execute (:211)<br/>先插入执行记录"] --> T2["callAgent (:238)<br/>sessionId = sched-{taskCode}-{毫秒时间戳}"]
        T2 --> T3["AdminAgentInstanceFactory#build (:367)<br/>contextFor (:332)"]
        T3 --> T4["callWithContext (:278)<br/>ReActAgent 或 HarnessAgent#call<br/>block(executeTimeoutSeconds)"]
    end
    subgraph S17["场景 17：配置热更新（starter）"]
        H1["NacosRuntimeConfigService#receiveConfigInfo (:182)<br/>→ applyConfig (:237)"] --> H2["RuntimeConfigApplier#apply (:139)<br/>synchronized · 先全量校验"]
        H2 --> H3["ModelConfig#buildChain (:68)<br/>或按路由策略 / 在线实验构建新模型链"]
        H3 --> H4["applyMcp · applyAgent<br/>→ NacosPromptService#updatePrompt (:109)"]
        H4 --> H5["MutableDelegatingModel#swap (:47) 原子替换"]
        H5 --> H6["CustomerServiceService#flushHotAgents (:751)<br/>清热缓存，StateStore 不动"]
        H2 -.->|"任一步异常"| H7["保留旧配置，返回 false"]
    end
```

场景 17 有一个设计点值得注意：**先把新模型链、MCP、Agent 配置全部准备好，最后才依次生效**。`RuntimeConfigApplier#apply` 在构建阶段任何一步出错都直接返回 `false`，旧配置原样保留；而 `swap` 与 `flushHotAgents` 放在最后，保证热 Agent 缓存被清空时，新模型链已经就位。

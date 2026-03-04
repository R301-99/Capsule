
# Capsule 项目全上下文文档（Complete Context Transfer）

**文档用途：** 将 Capsule 项目从概念萌芽到当前设计的全部上下文、设计决策、思维演进、技术方案完整移交给新的专家。阅读此文档后，你应能完全理解项目的来龙去脉、当前状态与下一步方向。

**文档生成时间：** 2026-03-04  
**文档作者：** 架构师（AI 协作角色），基于与项目发起人的完整设计对话  
**文档版本：** v1.0-full-context

---

## 第一部分：项目起源与动机

### 1.1 发起人画像

一名技术型独立开发者，有完整编程能力。正在探索用 Multi-Agent（多个 AI 编程 Agent 协同）的方式开发中大型个人项目。他不需要 AI 完全自主，但希望自己只做决策，不做体力活。

### 1.2 实际使用场景（项目起点）

发起人在实际项目中使用了"架构师 Agent + QA Agent + 前端 Agent + 后端 Agent"的多 Agent 架构：
- 人类只与架构师 Agent 交互
- 架构师负责设计项目架构，再下发任务给各个 Coder Agent
- 这种分工有助于上下文管理和降低子模块复杂度

### 1.3 遭遇的系统性失败

在实际运行中，发起人遭遇了两类核心失败：

**失败类型 A：任务拆解与契约不够硬**
- Agent 不按规定格式开发
- 产出经常不可验收
- Agent 会自己瞎改不该改的东西
- 需要人类三番五次重试

**失败类型 B：上下文溢出与长跑偏**
- 架构师 Agent 在复杂任务中丢失旧共识
- 早期定下的规范被 Agent 遗忘
- Agent 自己发明新的命名规范和实现方式

**根本原因分析：**
- 大模型是概率系统，天生反确定性
- 用自然语言管理一个由概率机器组成的系统，结果必然失控
- 没有任何硬性的形式化约束边界

### 1.4 最初的解决思路

发起人的初始想法是：全流程形式化验证。每一步的开发、反馈、检验、沟通必须严格形式化，才能驾驭这个黑盒开发系统。

技术方向：使用 CLI 版本的 Codex（而非 IDE 版本），配合自动调度工具，让 Agent 自动调用和反馈给其他 Agent，最终一个出口反馈给人类，形成自循环系统。

---

## 第二部分：问题的本质（核心洞察演进）

> 这是整个项目最重要的部分。设计经历了三次认知升级，每次都更逼近本质。

### 2.1 第一层认知：契约驱动（Contract-First）

最初的解法思路：用确定的工程系统（契约、状态机、验证流水线）包裹不确定的大模型（Agent）。

这一层产出了：
- 五类原子契约（Role/Task/Interface/Behavior/Boundary）
- 四级验证门禁（L0 格式/L1 一致性/L2 行为/L3 边界）
- 打回协议与断路器
- Human-in-the-loop 标准化出口

评价：这是正确的工程方向，但它本质上是在"管理流程"，没有回答"系统是否在收敛"。

### 2.2 第二层认知：意图结晶（Intent Crystallization）

来自 GPT 架构师（即我）的提议：引入 Intent Contract（意图宪法），让意图从液态（探索中）→ 凝胶态（基本明确）→ 结晶态（冻结为硬约束），并新增 L4 Intent Alignment Gate。

来自 Claude 的提议：四态光谱模型（Nebula → Hypothesis → Decision → Contract），并强调"Decision 是因，Contract 是果"——需要追踪决策的因果关系。

评价：两个方案都增强了对"方向性"的治理，但发起人指出——"不够本质，没有质变，只是一种优秀的 agent 架构"。

### 2.3 第三层认知：约束累积（Constraint Accumulation）——最终洞察

经过深度思考后到达的核心洞察：

**AI 擅长生成可能性。软件工程是消灭可能性。**

整个软件工程的本质动作是：从无限可能的解空间里，一步步收窄，直到只剩一个可工作的系统。

AI 做的是相反的事：它在每次调用时重新展开可能性。它没有任何机制把"已经排除的可能性"固化下来。

**当前所有 AI coding 工具的根本问题：它们是无状态的可能性生成器，而软件工程需要的是有状态的可能性消灭器。**

**质变临界点：每一次交互（成功、失败、决策、发现）都产生一条持久的、机器可执行的约束，使得后续所有工作的解空间比之前更小。永远收窄，不可回弹。**

### 2.4 Capsule 的终极定义（基于第三层认知）

> Capsule 是一个围绕 AI 代码生成器的约束累积与执行系统。
> 它保证每一次交互都让解空间变小，永远收敛，不可回弹。
> 人类的角色是：在关键分叉点选择"排除哪些可能性"。
> AI 的角色是：在已排除的可能性之外，生成候选方案。
> 系统的角色是：捕获约束、持久化约束、执行约束、证明收敛。

### 2.5 用约束累积重新理解之前所有设计

之前设计的所有组件都不需要推翻，但需要视角转换：

- **契约** = 已结晶的约束集合
- **门禁** = 约束的执行点
- **证据** = 约束的来源与证明
- **状态** = 当前约束集合的快照
- **人类出口** = 在约束不足以自动判定时，请求人类产生新约束
- **打回/重试** = 强制 Agent 在约束空间内重新生成
- **断路器** = 当前约束可能不足，需要人类补充新约束

判断标准：**这个功能/流程/工件，是否让系统在每一轮之后，约束集合严格增长（或至少不缩小）？是→留。否→砍。**

### 2.6 用约束累积解释两个核心痛点

**痛点 A（不可验收、瞎改）的根因：**
Agent 不知道哪些可能性已被排除。
解法：每次调用 Agent 前，系统把所有已积累的约束注入为硬边界（不是提示词，而是门禁规则）。Agent 的产出必须在约束空间内，否则物理拒绝。

**痛点 B（跑偏、丢共识）的根因：**
共识只存在于上下文（会丢）。
解法：共识 = 约束。约束不在上下文里，在持久化存储里。每次调用重新加载，不依赖聊天历史。Agent 的上下文可以丢，但约束集永远不丢。

---

## 第三部分：约束的核心模型

### 3.1 约束的最小数据结构

一条约束只需要回答三个问题：

1. **什么不可以 / 什么必须**（约束内容）
2. **为什么**（来源：哪个决策/失败/成功/接口产生了它）
3. **违反了怎么办**（后果：打回/终止/人类审查）

所有更复杂的结构都是这三个字段的派生。

### 3.2 约束的四个来源（覆盖一切产生约束的事件）

1. **人类决策**：人类说"用 JWT"，这就是一条约束
2. **成功验证**：测试通过了，这个行为就被锁定为"必须保持"
3. **失败教训**：某种做法导致打回，这条路就被标记为"不可再走"
4. **接口固化**：两个模块之间达成了通信格式，这就是双方的硬边界

### 3.3 约束累积的核心循环

```
做一件事
    │
    ▼
产生结果（成功/失败/发现/决策）
    │
    ▼
从结果中提取约束
    │
    ▼
约束被持久化、不可撤销
    │
    ▼
下一件事的解空间更小
    │
    ▼
做下一件事（在更小的空间里）
```

每转一圈，系统就更确定一点。这就是收敛。当前所有 AI coding 工具没有这个循环。

---

## 第四部分：Capsule 不是什么 / 是什么（市场定位）

### 4.1 Capsule 不是什么

- ❌ 不是 AI 编辑器（不替代 Cursor / Copilot）
- ❌ 不是全自主 Agent（不追求无人值守）
- ❌ 不是通用 Agent 框架（不是 LangGraph 的竞争对手）
- ❌ 不是企业级 DevOps 平台
- ❌ 不是代码生成服务
- ❌ 不是工作流引擎、契约框架、Agent 编排系统——这些都是手段

### 4.2 Capsule 是什么

- ✅ 本地运行的 CLI 工具
- ✅ 围绕 AI 代码生成器的约束累积与执行系统
- ✅ 保证多 Agent 开发过程持续收敛的治理系统
- ✅ 个人开发者的"AI 开发团队操作系统"
- ✅ 以约束为第一性原理，契约/门禁/状态/证据/人类出口为实现手段

### 4.3 市场空白

```
工具类型          代表产品           核心局限
────────────────────────────────────────────────────
IDE 插件型        Cursor, Copilot    单 Agent，无流程管理，无约束累积
全自主型          Devin              不可控，面向企业，无收敛保证
多 Agent 框架     MetaGPT, CrewAI    软沟通，无硬性约束，无门禁
编排框架          LangGraph          低层原语，无 Domain 设计，无约束体系

Capsule 的位置：
  约束累积驱动 · 个人开发者 · Human-in-the-loop · 可控的半自动化 · 保证收敛
  ← 这个位置，目前没有任何产品占据
```

---

## 第五部分：核心设计哲学

### 5.1 第一原则

**以确定性战胜不确定性。**

更精确地说：**通过持续累积约束，把 AI 的无限可能性空间收窄为工程上唯一正确的解。**

### 5.2 四条信条

**信条一：约束是门卫，不是建议**
每一步的输入输出，必须通过形式化验证才能流转。没有"大概对"，只有"通过"和"不通过"。

**信条二：规则写在约束里，不写在 Prompt 里**
Prompt 可以被遗忘，约束不会。Prompt 可以被曲解，约束不会。Agent 的行为边界由约束定义，不由 Prompt 约束。

**信条三：Agent 是无状态的函数，约束集由系统管理**
不依赖聊天历史传递上下文。每次调用 Agent，都携带完整的约束集快照。Agent 不记忆，系统记忆。

**信条四：人类是约束的生产者，不是调试者**
Capsule 不追求让人类消失。系统自动处理所有可自动化的验证和重试。只在需要"产生新约束"时，呼叫人类。

---

## 第六部分：系统架构

### 6.1 两个平面（核心架构分离）

**Governance Plane（治理平面，确定性，系统核心）**
- Contract Registry（约束/契约与版本管理）
- Gate Engine（约束的验证与执行）
- State Ledger（事实与证据的持久化）
- Decision Log（人类裁决记录）

> 这一层必须"死板"，越死板越好。

**Execution Plane（执行平面，可替换）**
- Executor Adapter（Codex CLI 只是第一个适配器）
- Tooling（测试、lint、扫描、git diff）

> 这一层必须"可替换"，但输出必须被治理平面标准化成 Evidence。

### 6.2 五层架构（由外到内）

```
┌──────────────────────────────────────────────────────────────────┐
│   Layer 5: 人机交互层 (Human-in-the-loop Layer)                  │
│   CLI 界面 · Human Review 出口 · 断路器通知 · 进度报告            │
├──────────────────────────────────────────────────────────────────┤
│   Layer 4: 语义层 (Semantic Layer)                               │
│   需求形式化 · 对话式澄清 · 任务拆解 · 契约生成                   │
├──────────────────────────────────────────────────────────────────┤
│   Layer 3: 编排层 (Orchestration Layer)                          │
│   工作流状态机 · 角色调度 · 条件路由 · 并行管理                   │
├──────────────────────────────────────────────────────────────────┤
│   Layer 2: 契约层 (Contract Layer)          ← 系统心脏           │
│   约束类型体系 · 多级验证流水线 · 打回协议 · 断路器               │
├──────────────────────────────────────────────────────────────────┤
│   Layer 1: 状态层 (State Layer)                                  │
│   项目状态机 · 历史记录 · 断点续跑 · 审计日志                     │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    执行层（外部工具，Execution Plane）
                    Codex CLI · 测试运行器 · Git
```

### 6.3 数据流全景

```
人类（自然语言需求）
        │
        ▼
  语义层：需求澄清 → 形式化 → 生成约束/契约包
        │
        ▼
  编排层：选择工作流 → 分发给角色
        │
        ▼
  契约层：INPUT GATE（注入全部约束）→ Agent 执行 → OUTPUT GATE（验证约束）
        │                                              │
        │ 通过                                        失败
        ▼                                              ▼
  状态层：持久化 + 从结果中提取新约束            打回协议（携带诊断）
        │                                              │
        ▼                                              ▼
  约束集增长                                    断路器 → Human Gate
        │                                              │
        ▼                                              ▼
  下一任务在更小的解空间内执行                   人类产生新约束 → 写回
```

### 6.4 技术选型

```
编排底座：    v0.1 先用 Lean Orchestrator（自研极简串行）
              后续可接入 LangGraph 作为可选适配器
执行引擎：    Codex CLI（codex exec），设计上允许未来替换
实现语言：    Python
运行方式：    本地 CLI，无云端依赖
配置格式：    YAML（角色、工作流、契约均为配置文件）
状态格式：    JSON（PROJECT_STATE.json）
契约校验：    JSON Schema（真相源）+ Pydantic（开发便利层）
VCS：         Git（差异与边界审计的基础）
```

### 6.5 技术选型的关键决策与理由

**LangGraph 为何不作为 v0.1 强依赖：**
- 概念与依赖过重，会拖慢独立维护者的迭代节奏
- v0.1 只需串行工作流，Lean Orchestrator 足够
- 设计上预留 Orchestration Port，后续可接入 LangGraph 适配器

**Codex CLI 为何被降级为"适配器"：**
- Capsule 设计上必须允许未来替换执行引擎
- 内核只消费 ExecutionEvidence，不消费 Codex 专有日志
- 通过 Executor Port 抽象解耦

**Pydantic vs JSON Schema：**
- JSON Schema 文件是契约层的正式规范（语言无关、引擎无关）
- Pydantic 模型用于 Python 内部的类型安全与解析便利
- 推荐 Model-first 路线：Pydantic 定义 → CI 导出 JSON Schema 固化
- Pydantic AI 仅用于语义层（让 Agent 输出结构化内容），不进入契约层

---

## 第七部分：契约体系（约束的形式化载体）

### 7.1 元契约规范（所有契约的统一结构）

#### 7.1.1 严格度策略：Pragmatic（P 档）

**设计决策：核心严格，外围宽松。**
- 核心严格：所有契约的 `meta` 禁止未知字段（additionalProperties=false）
- 外围宽松：扩展只能进入 `extensions` 命名空间（唯一扩展口）
- 默认拒绝未知字段：扩展必须走 `extensions`，不允许随手加字段

#### 7.1.2 版本策略

- 强制 SemVer（`MAJOR.MINOR.PATCH`，正则 `^\d+\.\d+\.\d+$`）
- 引用允许范围表达（如 `1.x`），但在运行前必须锁定为精确版本
- 锁定结果写入 state + gate_report + evidence

#### 7.1.3 不可变性

- ACTIVE 契约不可原地修改
- 修改走新版本（copy-on-write）
- 旧版本进入 DEPRECATED 或冻结（策略可配）
- AMENDING 表示"正在起草新版本"，不等于改旧文件

#### 7.1.4 Contract Envelope（统一信封结构）

所有契约文件统一为：

```yaml
contract:
  meta:       # 核心严格
    type: ...
    id: ...
    version: ...
    status: ...
    created_by: ...
    created_at: ...
    dependencies: [...]
    validation: ...
    on_failure: ...
  spec: {}    # 各类型自定义，默认也严格
  extensions: {}   # 唯一扩展口（可选，允许任意结构）
```

#### 7.1.5 meta 字段详细定义

- `type`：枚举  
  `role | task | interface | behavior | boundary | gate_report | evidence | human_decision`
- `id`：分层字符串  
  格式：`<type>.<domain>.<name>`（例 `interface.user_auth`、`task.user_auth.login_api`）
- `version`：SemVer 字符串
- `status`：枚举  
  `draft | pending_review | active | amending | deprecated`
- `created_by`：枚举  
  `role.architect | role.qa | role.coder_backend | role.coder_frontend | human | system`
- `created_at`：ISO 8601 时间戳
- `dependencies`：ContractRef 数组（允许空）
- `validation`：验证声明
- `on_failure`：失败策略

#### 7.1.6 ContractRef（引用规范）

```yaml
ref:
  id: "behavior.user_auth"
  version: "1.x"     # 允许范围（仅在未锁定阶段）
  # 锁定后变为：
  version: "1.0.3"   # 精确版本
```

硬规则：Task 进入执行态前，所有 dependencies 必须被解析为精确版本并写入 state/evidence/gate_report。

v0.1 范围引用仅支持 `MAJOR.x`，不支持更复杂的 semver range。

#### 7.1.7 validation 字段

```yaml
validation:
  schema: "contracts/schemas/task.contract.schema.json"
  checks: []   # 预留未来脚本/命令型校验
```

- `schema` 必填：指向 L0 校验使用的 schema 文件
- `checks` 可选：预留扩展

#### 7.1.8 on_failure 字段

```yaml
on_failure:
  action: "retry" | "halt" | "human_escalation"
  max_retries: 3
  severity: "low" | "mid" | "high"
```

#### 7.1.9 契约生命周期

```
DRAFT → PENDING_REVIEW → ACTIVE → AMENDING → DEPRECATED

规则：
  ACTIVE 不可原地改写，修改产生新版本
  AMENDING 期间，依赖此契约的所有任务自动暂停
  DEPRECATED 永久存档，不可删除
```

### 7.2 五类原子契约

#### 类型 I：角色契约（Role Contract）

回答：你是谁？你能做什么？你不能碰什么？

```yaml
spec:
  display_name: "Backend Coder"
  capabilities:
    read:  ["src/backend/**", "contracts/**", "CAPSULE.md"]
    write: ["src/backend/**", "tests/backend/**"]
    exec:  ["pytest", "python", "pip"]
  prohibitions:
    write: ["contracts/schemas/**", "state/**", ".env*"]
    exec:  ["git push", "git reset", "rm -rf"]
  retry_policy:
    max_retries: 3
  confidence_threshold: 0.7
```

执行期硬规则：默认拒绝。任何写入/命令若不在 capabilities 且不在 prohibitions 外 → L3/halt。

#### 类型 II：任务契约（Task Contract）

回答：这件事规格是什么？谁来做？怎么算做完？

```yaml
spec:
  assigned_to: "role.coder_backend"
  scope:
    include: ["src/backend/auth/**"]
    exclude: ["src/backend/auth/middleware.py"]
    create_allowed: ["src/backend/auth/"]
  acceptance:
    behavior_ref: { id: "behavior.user_auth", version: "1.x" }
    interface_refs: [{ id: "interface.user_auth", version: "1.x" }]
    max_new_files: 5
  token_budget: 8000
```

#### 类型 III：接口契约（Interface Contract）

回答：模块之间如何对话？是前后端的"宪法"。

```yaml
spec:
  endpoints:
    - id: "login"
      path: "/api/auth/login"
      method: "POST"
      request:
        schema:
          type: object
          required: ["email", "password"]
          properties:
            email:    { type: string, format: email }
            password: { type: string, minLength: 8 }
      response:
        success:
          status: 200
          schema:
            type: object
            required: ["token", "expires_in", "user_id"]
  binding:
    producer: "role.coder_backend"
    consumers: ["role.coder_frontend"]
  change_policy:
    requires_approval: ["role.architect", "human"]
    on_change: "suspend_dependent_tasks"
```

#### 类型 IV：行为契约（Behavior Contract）

回答：代码跑起来，必须表现出什么行为？

```yaml
spec:
  test_suite:
    runner: "pytest"
    entry: "tests/backend/test_user_auth.py"
    command: "pytest -q tests/backend/test_user_auth.py"   # v0.1 强制必填
  mandatory_cases:
    - id: "TC001"
      description: "正确凭证返回 JWT token"
      must_pass: true
  coverage:
    minimum_percent: 80    # v0.1 可选
```

硬规则：Behavior 的 created_by 必须为 `role.qa` 或 `human`，否则 L1 打回。

#### 类型 V：边界契约（Boundary Contract）

回答：什么是绝对禁区？触发后果是终止，不是打回。

```yaml
spec:
  sacred_files:
    - "capsule.yaml"
    - "contracts/schemas/**"
    - "contracts/boundaries/**"
    - ".env*"
    - "state/**"
  rules:
    - id: "no_sacred_write"
      check_method: "git_diff_scan"
      violation_action: "immediate_halt"
    - id: "no_forbidden_exec"
      check_method: "command_audit"
      violation_action: "immediate_halt"
  on_violation:
    notify: "human"
    log_path: "state/audit/boundary_violations.log"
```

L3 触发即终止，不允许重试。

### 7.3 三类事件契约（运行事实）

#### GateReport（门禁报告）

```yaml
spec:
  gate_id: "INPUT_GATE" | "OUTPUT_GATE"
  level: 0|1|2|3
  result: "pass" | "fail" | "halt" | "human"
  failed_contract_ref: { id: "...", version: "..." }
  diagnostics:
    summary: "..."
    details: {}
  resolved_refs:
    - { id: "behavior.user_auth", version: "1.0.3" }
  timestamp: "..."
```

#### ExecutionEvidence（执行证据包）

```yaml
spec:
  run_id: "20260303-101530-ab12cd"
  role_id: "role.coder_backend"
  task_ref: { id: "task.user_auth.login_api", version: "1.0.0" }
  contract_snapshot:
    refs:
      - { id: "interface.user_auth", version: "1.0.0" }
      - { id: "behavior.user_auth", version: "1.0.0" }
  changes:
    modified_files: ["src/backend/auth/login.py"]
    diff_stat: { files: 1, insertions: 40, deletions: 3 }
  commands:
    ran:
      - { cmd: "pytest -q ...", exit_code: 0, duration_ms: 1200 }
  tests:
    ran:
      - { cmd: "pytest -q ...", summary: "12 passed" }
    summary: "pass" | "fail"
  self_report:
    confidence: 0.82
    risks: ["..."]
    notes: "..."
```

#### HumanDecision（人类决策记录）

```yaml
spec:
  decision_id: "HD-20260303-001"
  trigger: "retry_exceeded" | "boundary_violation" | "review_required"
  context_refs:
    - { id: "evidence.run.20260303-...", version: "1.0.0" }
  options_presented: ["approve", "amend_contract", "pause", "abort"]
  selected_option: "amend_contract"
  rationale: "..."
  actions:
    next: "resume" | "abort" | "pause"
  timestamp: "..."
  made_by: "human"
```

---

## 第八部分：门禁系统（Gate System）

### 8.1 验证流水线总览

```
Agent 产出
    │
  INPUT GATE：前置条件检查 + 约束注入 + 引用锁定
    │ 通过
  AGENT EXECUTION：执行引擎沙盒执行
    │
  OUTPUT GATE：
    L0 格式校验      →  JSON Schema, <100ms
    L1 结构一致性    →  跨契约引用检查、created_by 合规、scope 匹配
    L2 行为验证      →  运行测试套件（pytest/jest）
    L3 边界审计      →  Git Diff 扫描 + 命令审计
    │
    ├── 全通过 → 进入下一节点 + 提取新约束
    ├── L0-L2 失败 → 携带诊断打回，Agent 重试
    └── L3 触发 → 立即终止，通知人类
```

### 8.2 INPUT GATE 详细检查顺序

1. **I0 契约可加载（L0）**：Task/Role/Boundary/Behavior/Interface 均必须加载成功并通过 schema 校验
2. **I1 依赖存在与引用锁定（L1）**：解析 task 中所有 ref → 锁定精确版本 → 写入 state
3. **I2 Scope 与 Role 权限预检（L1）**：task.scope 必须是 role.capabilities.write 的子集
4. **产物**：生成 INPUT GateReport

### 8.3 OUTPUT GATE 详细检查顺序

1. **O0 Evidence 格式校验（L0）**：evidence 必须符合 schema；缺字段直接 fail
2. **O1 结构一致性（L1）**：evidence.task_ref 必须等于 state.current_task_ref；refs 精确；created_by 合规
3. **O2 行为验证（L2）**：按 behavior.spec.test_suite.command 执行（由系统执行，非 agent 自说自话）
4. **O3 边界审计（L3）**：git diff 扫描 sacred_files + 命令审计 → 匹配即 halt

### 8.4 打回协议（Rejection Protocol）

结构化打回必须包含：
- rejection_id
- target_role / task_ref
- retry_count / max_retries
- failed_gate / failed_level / failed_contract_ref
- failure_details（命令/退出码/用例摘要/建议修复方向）

### 8.5 断路器

触发条件：`retry_count >= max_retries` 或 token_budget 超限

触发动作：
- 生成 HumanDecision 请求
- 将待处理事项加入 `state.human_queue`

人类选项：
1. 修改需求，重新设计契约
2. 手动修复后继续
3. 调整契约验证标准
4. 暂存此任务，先做其他模块

---

## 第九部分：角色系统

### 9.1 设计原则

角色是配置，不是代码。新增角色只需新增 yaml 文件。

### 9.2 MVP 三个内置角色

**🧠 Architect（架构师）**
- 职责：需求形式化、技术设计、契约生成、最终语义审查
- 特权：唯一可以创建和修改契约文件的 Agent
- Human Review：完成后必须等待人类审核

**🕵️ QA（质量保障）**
- 职责：在开发开始前生成行为契约（测试套件）
- 约束：不参与编码，只负责测试规格定义
- 产出：behavior.contract.yaml

**👨‍💻 Coder（编码者）**
- 职责：严格基于接口契约和行为契约实现代码
- 约束：权限被锁定在自己的沙盒目录内；不被允许"重新定义意图"
- 实例：可以有多个（coder_backend, coder_frontend）

### 9.3 权威层级（Authority Order）

1. **Intent / 人类决策**（最高）
2. **Boundary Contract（安全/禁区宪法）**
3. **Active Contracts（Interface/Behavior/Role/Task 的生效版本）**
4. **Artifacts/Evidence（过程证据）**
5. **对话与 Prompt（最低权威，只能生成候选工件）**

任何东西与上层冲突，即使测试全绿，也必须走修订流程或回滚实现。

---

## 第十部分：工作流系统

### 10.1 设计原则

工作流是有向图。节点是角色，边是流转条件。由 yaml 配置驱动，支持条件路由和自循环（失败打回）。v0.1 仅需支持串行。

### 10.2 内置工作流（MVP）

```yaml
workflow.standard:
  flow: architect → qa → coder_backend → architect(review)
  human_review_nodes: [architect, architect(review)]
```

### 10.3 编排内核接口（Orchestration Port）

Capsule 只依赖一个编排端口：
- 输入：当前 State + 当前 Node 输出的 Evidence/GateReport
- 输出：下一节点、要调用的角色、要执行的任务契约、是否进入 human gate

v0.1 实现 Lean Orchestrator（串行 + 重试 + 断路器 + human 挂起）。后续可接入 LangGraph。

---

## 第十一部分：状态系统

### 11.1 核心原则

Agent 是无状态的函数。每次调用 Agent，都携带从状态系统提取的完整约束集快照，不依赖聊天历史。

### 11.2 PROJECT_STATE.json 最小结构

```json
{
  "project_id": "my-saas-app",
  "current_workflow_id": "workflow.standard",
  "current_node_id": "coding",
  "current_task_ref": { "id": "task.user_auth.login_api", "version": "1.0.0" },
  "phase": "development",
  "status": "in_progress",
  "locked_refs": [],
  "run_history": [
    {
      "run_id": "...",
      "task_ref": {},
      "role_id": "...",
      "last_gate_report_ref": "...",
      "evidence_ref": "...",
      "status": "..."
    }
  ],
  "checkpoints": [],
  "human_queue": [],
  "constraint_count": 42,
  "global_conventions": {
    "api_prefix": "/api/v1",
    "auth_method": "JWT",
    "db_orm": "SQLAlchemy",
    "test_runner": "pytest"
  }
}
```

### 11.3 断点续跑

系统在任何节点都可以中断，下次启动时从状态文件恢复现场，携带上次失败的诊断信息继续执行。

---

## 第十二部分：执行层

### 12.1 执行端口抽象（Executor Port）

**ExecutionRequest（最小包含）：**
- role_id
- working_dir
- task_ref（精确版本）
- injected_context（只读快照：相关契约内容 + state 关键字段）
- policy（允许写入 glob、允许执行命令前缀）

**ExecutionResult / ExecutionEvidence（最小包含）：**
- modified_files（从 VCS diff 得出）
- commands ran + exit codes
- tests ran + summary
- agent report（结构化）
- raw logs pointer（可选）

### 12.2 Codex CLI 适配器（v0.1）

- 将 request 转换为 `codex exec` 调用
- 解析输出为 ExecutionEvidence
- 执行前后 git diff 收集 modified_files
- 异常（非 0 退出、json 解析失败）转为结构化 rejection/error evidence
- 禁止把长日志直接塞入 evidence（截断 + 结构化）

### 12.3 执行沙盒原则

- 工作目录：锁定为 role.capabilities.write 的授权路径
- 文件审计：Git Diff 后置扫描（L3）
- 命令白名单：来自 role.capabilities.exec
- 退出码非 0：直接触发打回协议

---

## 第十三部分：人机交互

### 13.1 触发时机

**主动触发（系统固定等待）：**
- 契约从 DRAFT 进入 ACTIVE 之前
- 工作流中标记 human_review 的节点完成后
- 重要架构决策（新增模块、修改接口契约）

**被动触发（异常升级）：**
- 断路器触发（重试次数耗尽）
- 边界契约违规（立即终止）
- Agent 自评置信度低于阈值

### 13.2 交互设计原则

呈现给人类的永远是：
- ✅ 结构化摘要，不是原始日志
- ✅ 明确选项，不是开放式问题
- ✅ 足够上下文，能做出决策
- ✅ 影响范围说明，知道自己在决定什么

人类的选择必须记录为 HumanDecision 写入 state，保证可回放、可恢复运行。

### 13.3 CLI 最小指令集（v0.1）

- `capsule validate`：校验 contracts 与 state（离线）
- `capsule run`：从 state 当前节点开始跑到下一个 human gate 或结束
- `capsule resume`：从 checkpoint/run_id 恢复
- `capsule review`：输出结构化摘要（给人类看）
- `capsule decide --option ...`：写入 HumanDecision 并继续

---

## 第十四部分：意图结晶系统（高级概念，待进一步实现）

> 这一部分代表设计认知的最新状态。v0.1 不要求完整实现，但概念必须理解，因为它决定了 Capsule 的长期方向与扩展架构。

### 14.1 核心思想

"边做边约束，边做边知道自己要做什么"：允许前期模糊探索，但探索产物必须被结构化记录；当信息足够时，系统推动结晶并冻结。冻结后所有任务必须对齐。

### 14.2 GPT 架构师方案：三态模型

- **Liquid（液态）**：探索中的意图/假设，还不确定。允许频繁改。必须记录。
- **Gel（凝胶态）**：已基本明确，变更需要影响分析与理由。
- **Crystal（结晶态）**：冻结为硬约束。默认不可修改，只能新版本替代 + 显式破冰。

冻结强度分级：
- F1 Hard Preference：不符合触发 human review，可放行
- F2 Hard Requirement：不符合即打回
- F3 Hard Prohibition：触发即 halt

### 14.3 Claude 方案：四态光谱

```
☁️ Nebula → 💧 Hypothesis → 💎 Decision → 🔒 Contract
（星云）     （假说）         （决策）       （契约）
```

关键区分：Decision ≠ Contract。Decision 是因，Contract 是果。系统应追踪决策的因果关系，以便知道为什么当初这么写。

### 14.4 融合方向（待定稿）

无论采用哪种具体模型，核心机制一致：
- 从每次交互中提取约束
- 约束有从模糊到硬的演进路径
- 结晶后的约束具备门禁执行力
- 修改结晶约束需要显式"破冰"流程

### 14.5 L4 Intent Alignment Gate（概念预留）

任何可流转产物都应附带 Alignment Report：
1. 引用了哪些结晶条款？
2. 满足了它们的哪些验收点？证据是什么？
3. 做了哪些取舍？是否触碰 F2/F3？
4. 不确定性/风险？是否需要人类决策？

v0.1 可先做结构预留（schema 支持但不强制执行），后续再加严。

### 14.6 触发结晶的高价值时刻（系统应主动推动）

1. 重复失败：同类 rejection 出现 ≥ N 次
2. 出现争议：architect 与 coder/qa 对实现方向冲突
3. 接口/架构定型：模块边界、API、数据模型一旦被多个任务依赖

### 14.7 破冰机制（Thaw Protocol）

修改结晶约束必须产出 Thaw Request：
- 为什么必须改
- 影响范围
- 替代方案（至少两个）
- 推荐方案
- 决策结果写回 HumanDecision

---

## 第十五部分：项目目录结构

```
capsule/
│
├── capsule.yaml                    # 项目总配置
├── CAPSULE.md                      # 项目说明（注入给所有 Agent）
├── capsule_lead.md                 # 架构师技术指导
│
├── roles/                          # 角色定义（可扩展）
│   ├── architect.contract.yaml
│   ├── qa.contract.yaml
│   ├── coder_backend.contract.yaml
│   └── coder_frontend.contract.yaml
│
├── workflows/                      # 工作流定义（可扩展）
│   ├── standard.yaml
│   └── hotfix.yaml
│
├── contracts/
│   ├── schemas/                    # 元契约 JSON Schema（边界保护）
│   │   ├── contract.envelope.schema.json
│   │   ├── contract.ref.schema.json
│   │   ├── role.contract.schema.json
│   │   ├── task.contract.schema.json
│   │   ├── interface.contract.schema.json
│   │   ├── behavior.contract.schema.json
│   │   ├── boundary.contract.schema.json
│   │   ├── gate_report.schema.json
│   │   ├── evidence.schema.json
│   │   └── human_decision.schema.json
│   │
│   ├── boundaries/                 # 边界契约实例（全局生效）
│   │   └── global.boundary.yaml
│   │
│   └── instances/                  # 运行时生成的具体契约
│       └── {module_name}/
│           ├── task.contract.yaml
│           ├── interface.contract.yaml
│           └── behavior.contract.yaml
│
├── state/
│   ├── PROJECT_STATE.json          # 全局状态机（核心）
│   ├── runs/                       # 每次运行的证据链
│   │   └── {run_id}/
│   │       ├── evidence.json
│   │       ├── gate_reports/
│   │       │   ├── input.json
│   │       │   └── output.json
│   │       ├── rejections/
│   │       └── human_decisions/
│   ├── checkpoints/                # 断点快照
│   └── audit/
│       └── boundary_violations.log # 追加式，不可删除
│
├── prompts/                        # Agent System Prompt 模板
│   ├── architect.md
│   ├── qa.md
│   └── coder.md
│
└── core/                           # 系统核心代码
    ├── cli.py                      # 用户入口
    ├── registry.py                 # Contract Registry
    ├── validator.py                # Gate + 校验器
    ├── state_manager.py            # 状态持久化
    ├── orchestrator.py             # Lean Orchestrator
    ├── executor/
    │   ├── port.py                 # Executor Port（抽象）
    │   └── codex_cli.py            # Codex 适配器
    └── human_loop.py               # Human-in-the-loop 交互
```

---

## 第十六部分：实现策略（Hard Spine + Thin Slice）

### 16.1 策略选择

不是"先全面设计再实现"，也不是"先做空骨架"。而是：**先把不可变的"硬脊柱"一次性定好并实现成可运行的纵切片，其余能力用插件化接口预留，逐步加严与扩展。**

### 16.2 硬脊柱（必须一开始就定死）

1. 元契约 Envelope + Ref + SemVer + 引用锁定机制
2. Contract Registry / Loader / L0 校验
3. State（PROJECT_STATE）最小稳定结构
4. Evidence / GateReport / HumanDecision 三类事件的最小 schema
5. Boundary L3 最小可执行审计（git diff）
6. Executor Port（执行端口抽象）

### 16.3 可演进层（先能跑，再变强）

- L1 结构一致性规则的完整集
- L2 行为验证的丰富度
- 多工作流、多角色
- LangGraph 适配器、并行执行
- 更强的审计（hash 链、不可变存储）
- 意图结晶的完整实现

### 16.4 实现顺序（按依赖）

1. Contract Envelope + Ref + 基础五类 schema
2. Contract Registry（扫描、加载、索引、L0 校验）
3. State Manager（最小 state + runs + checkpoint）
4. Validator（INPUT/OUTPUT gate：L0 + 锁定 + L3 骨架）
5. Executor Port + Codex adapter（能跑一次并产出 evidence）
6. OUTPUT GATE L2（按 behavior.command 跑测试）
7. Lean Orchestrator（workflow 串行、重试、断路器）
8. Human loop（review/decide/resume）

### 16.5 判断准则

- 凡是影响"可回放/可审计/可恢复"的格式 → 必须先定
- 凡是影响"安全边界"的东西 → 必须先定
- 凡是纯粹"能力增强"的东西 → 允许后置

---

## 第十七部分：Contract Registry 行为规范与算法

### 17.1 注册表职责

- 扫描 `contracts/boundaries/`, `roles/`, `contracts/instances/**`
- 解析 Envelope（YAML/JSON）
- L0：按 `contract.meta.validation.schema` 执行 JSON Schema 校验
- 建索引：`by_id[id] -> list[contract]`（按 version 排序）；`by_id_version[(id, version)] -> contract`

### 17.2 版本解析与锁定算法

输入：`ContractRef(id, version)`

规则：
1. 若 version 为精确 SemVer → 必须存在该版本，否则 L1 fail
2. 若 version 为 `MAJOR.x` → 从 registry 取所有该 id 版本 → 过滤 MAJOR 匹配 → 过滤 status=active → 选最高版本
3. 锁定写入：`PROJECT_STATE.locked_refs` + `GateReport.resolved_refs` + `ExecutionEvidence.contract_snapshot.refs`

---

## 第十八部分：MVP 范围与验收标准

### 18.1 MVP 必须实现

- ✅ architect → qa → coder_backend 串行完整流程
- ✅ 五种契约类型的 YAML 定义和解析
- ✅ L0-L3 四级验证流水线
- ✅ 结构化打回协议（携带诊断信息）
- ✅ 断路器 + Human-in-the-loop 出口
- ✅ PROJECT_STATE.json 持久化与断点续跑
- ✅ Codex CLI 作为执行引擎（通过端口抽象）
- ✅ 工作流和角色由 YAML 配置驱动（不硬编码）

### 18.2 MVP 不做

- ❌ Web UI
- ❌ 多 Agent 并行
- ❌ Frontend Coder（MVP 后加入）
- ❌ DevOps 角色
- ❌ 云端同步
- ❌ 完整意图结晶系统（v0.1 预留结构）
- ❌ LangGraph 深度集成

### 18.3 MVP 验收标准

> 用 Capsule 自身，完成一个「用户注册登录模块」的端到端开发。
> 全程不超过 2 次人类介入（不含最终验收批准），最终所有自动化测试通过。

具体验收条件：
1. 任意契约文件缺字段或类型错误 → L0 必须拒绝加载并给出明确诊断
2. task 引用 `behavior@1.x` → INPUT GATE 必须解析为精确版本并写入 state/evidence/gate_report
3. 执行一次 coder_backend → 必须产出 ExecutionEvidence（即便失败）
4. L2 必须按 behavior.command 运行测试并记录结果
5. L3 若触达 sacred_files → 必须 immediate halt 并进入 human gate
6. `capsule review` 输出结构化摘要；`capsule decide` 可写回并 `resume`
7. 断点续跑：中断后再次运行，能够从 state 恢复并继续

---

## 第十九部分：最高风险点与规避建议

1. **规约维护成本 > 它省下的人力成本**：如果写 contract/gate/schema 的时间比直接写代码还多，系统变成"形式主义税"。规避：保持契约简约，只约束"必须约束的"。

2. **门禁太硬但证据生成太弱 → 全在打回重试**：Agent 总是差一点点过门禁，retry 消耗巨大。规避：确保 Executor Adapter 能产生高质量 evidence；确保打回诊断足够具体。

3. **可验证 ≠ 你真正想要的价值**：测试绿了、schema 过了，但实现方向不对（语义偏差）。规避：这是 L4/Intent 要解决的；v0.1 至少在 human_review 节点人工审查方向。

4. **过早追求强并行与复杂编排**：会拖慢 v0.1。先串行闭环。

5. **执行引擎耦合**：Evidence 必须抽象，否则未来替换执行引擎会重构核心。

6. **人类出口不结构化**：会导致"人类变调试者"，违背产品哲学。

7. **契约演进缺乏版本纪律**：没有 SemVer 与 ref 锁定就无法回放与暂停依赖任务。

---

## 第二十部分：当前状态与下一步

### 20.1 当前状态

```
阶段：     产品设计阶段（概念与架构设计基本完成，尚未开始编码）
已完成：   
  - 完整产品定位与市场分析
  - 核心洞察确立（约束累积 = 第一性原理）
  - 系统架构设计（五层 + 两平面）
  - 契约体系设计（元契约 + 五类原子 + 三类事件）
  - 门禁系统设计（L0-L3 + 预留 L4）
  - 状态/证据/人类出口设计
  - 实现策略确定（Hard Spine + Thin Slice）
  - 技术选型确定（Python/CLI/JSON Schema/Pydantic/Git/Codex CLI）
  
待完成：
  - 约束的最小数据结构最终定稿
  - 用"约束审计"视角重新审视所有设计（标注哪里产生约束、执行约束、约束可能丢失）
  - 契约 JSON Schema 编写
  - 第一个可运行的 MVP 原型
```

### 20.2 建议的下一步

**最紧急：** 定义"约束"的最小数据结构（三个字段），然后回顾全部设计，用这个结构标注：哪些地方在产生约束、哪些地方在执行约束、哪些地方约束会丢失。丢失的地方，就是系统会"不 work"的地方。补上它，Capsule 就成立。

**然后：** 按 16.4 的实现顺序开始编码。

### 20.3 工作模式（发起人与架构师约定）

- 架构师给每一步的设计
- 发起人提建议，架构师修改
- OK 后架构师出技术指导
- 发起人让 coder 实现
- 实现后发起人提设计建议
- 架构师再修改
- 循环往复

架构师不关心实际代码，只关心设计与约束。

---

## 附录 A：Codex CLI 关键能力（执行引擎参考）

Capsule v0.1 的执行引擎是 Codex CLI。以下是与 Capsule 设计相关的关键能力：

- **`codex exec`**：非交互执行入口，进度写 stderr，结果写 stdout
- **`--json`**：运行事件以 JSON Lines 输出（事件类型包括 thread/turn/item/command/file_change 等）
- **`--output-schema`**：强制最终输出满足 JSON Schema
- **权限策略**：默认 read-only sandbox；`--full-auto` 允许编辑；`--sandbox danger-full-access` 最高权限
- **Approval modes**：Auto / Read-only / Full Access
- **Multi-agents（实验特性）**：通过 `[agents.<name>]` 定义角色
- **AGENTS.md**：全局/仓库/子目录分层约束
- **Rules**：Starlark `.rules` 文件控制命令越权策略

> 重要：Capsule 不直接依赖这些特性。Codex 通过 Executor Adapter 接入，内核只消费 Evidence。

---

## 附录 B：术语表

| 术语 | 定义 |
|------|------|
| Constraint（约束） | 对解空间的一次收窄：什么不可以/什么必须 + 为什么 + 违反后果 |
| Contract（契约） | 已结晶的约束集合，形式化为可验证的 YAML/JSON 工件 |
| Artifact（工件） | 一次步骤的产物，可被验证、可被引用、可被回放 |
| Evidence（证据） | 证明"做了什么、做成没有"的结构化材料 |
| Decision（决策） | 人类或系统对"是否流转/如何修订"的结构化裁定 |
| Gate（门禁） | 约束的执行点，判定通过/失败/终止/升级 |
| GateReport | 门禁的结构化输出（判定结果 + 诊断 + 锁定 refs） |
| Work Unit（WU） | 工作流中的一个节点：Typed I/O + Verifiers + Failure Policy |
| Rejection | L0-L2 失败时的结构化打回（携带诊断与重试信息） |
| Boundary | 安全禁区宪法，违规即终止（L3） |
| Intent | 产品/工程方向性约束（长期，高权威） |
| Crystallization（结晶） | 约束从模糊到硬的演进过程 |
| Thaw（破冰） | 修改已结晶约束的正式流程 |
| Governance Plane | 治理平面：Registry + Gate + State + Decision Log |
| Execution Plane | 执行平面：Executor Adapter + Tooling |
| Hard Spine | 不可变的核心结构，必须一开始就定好 |
| Thin Slice | 纵向切片，最小可运行闭环 |
| Lean Orchestrator | v0.1 的极简串行编排器 |
| Executor Port | 执行引擎的抽象接口，保证可替换 |
| ContractRef | 契约的引用格式（id + version） |
| SemVer | 语义化版本（MAJOR.MINOR.PATCH） |
| Sacred Files | 受 Boundary 保护的不可触碰文件 |

---

## 附录 C：与其他 AI 架构师的协作说明

本项目发起人同时与多个 AI 架构师（GPT / Claude 等）交互。各方贡献的关键洞察：

- **GPT 架构师（本文作者）**：契约体系详细设计、门禁分层、Pragmatic 严格度策略、Hard Spine + Thin Slice 实现策略、约束累积作为第一性原理
- **Claude 架构师**：四态光谱模型（Nebula→Hypothesis→Decision→Contract）、"Decision 是因 Contract 是果"的因果追踪洞察
- **发起人核心判断**："不够本质"的审美标准推动认知从"契约框架"升级到"约束累积系统"

---

**文档结束。**

**交接建议：** 阅读本文档后，建议专家首先理解第二部分（问题本质与认知演进）和第三部分（约束核心模型），这两部分决定了所有设计决策的"为什么"。技术细节（第七至第十七部分）是"怎么做"，应在理解"为什么"之后再细读。

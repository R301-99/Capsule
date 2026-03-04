
# Capsule v0.1 技术方案（重写版）

> 基于核心洞察：Capsule 不是多 Agent 编排框架，而是一套**治理原语系统**。  
> 它解决的根本问题是：工程开发需要"可执行的价值函数 + 可追溯的因果链 + 闭环纠偏"，而现有 agent 只提供生成能力，没有治理能力。

---

## 第一部分：系统本体

### 1. Capsule 是什么（重新定义）

Capsule 是一个**治理原语驱动的 AI 软件工程系统**。

它由三本账和一个编译器构成：

```
┌─────────────────────────────────────────────────┐
│              Governance Plane（治理平面）          │
│                                                   │
│   Decision Ledger    ←→    Constraint Compiler    │
│   （决策账本）               （约束编译器）          │
│        │                        ↑ ↓               │
│        ▼                                          │
│   Contract Registry  ←→    Evidence Ledger        │
│   （契约注册表）             （证据账本）            │
│                                                   │
├─────────────────────────────────────────────────┤
│              Execution Plane（执行平面）           │
│                                                   │
│   Orchestrator → Executor → Gate → Evidence       │
│   （可替换：Codex CLI / 未来其他引擎）              │
└─────────────────────────────────────────────────┘
```

**治理平面**是 Capsule 的核心价值，不可替换。  
**执行平面**是可替换的工具层。

### 2. 四个系统原语（Capsule 的全部基础）

整个系统只有四种一等公民。任何功能、角色、流程都是这四种原语的组合与派生：

**原语 1：Decision（决策）**  
人类（或系统推荐 + 人类确认）做出的选择。  
是 Contract 的因，是系统方向感的来源。  
没有 Decision 的 Contract 是无根之木。

**原语 2：Contract（契约）**  
Decision 的形式化、可执行表达。  
是 Gate 的弹药，是 Agent 行为的边界。  
没有 Contract 的 Decision 是空话。

**原语 3：Evidence（证据）**  
每次执行的传感器读数：改了什么、测了什么、结果如何。  
是 Gate 判定的依据，是 Compiler 反向推理的输入。  
没有 Evidence 的执行等于没发生。

**原语 4：Gate（门禁）**  
拿 Contract 做标尺、拿 Evidence 做证据、做出"通过/打回/终止/升级人类"的确定性判定。  
是系统确定性的执行机构。  
没有 Gate 的 Contract 是建议。

> 四句话总结：  
> Decision 说"为什么"。Contract 说"必须怎样"。Evidence 说"实际怎样"。Gate 说"能不能过"。

### 3. Constraint Compiler（约束编译器）——质变组件

编译器不是 Agent，不是 LLM，是确定性的系统组件（可含少量 LLM 辅助但判定必须确定性）。

它做两个方向的编译：

**Forward Compile（正向编译）：Decision → Contract**
- 输入：一组 active decisions
- 输出：对应的 contract 条款（interface schema / behavior cases / boundary rules / role permissions）
- 人类审核后激活

**Backward Compile（反向编译）：Evidence → Hypothesis**
- 输入：重复失败的 evidence、rejection 模式、边界冲突
- 输出：待人类确认的 hypothesis（"是否应该结晶一条新 decision？"）
- 人类确认后进入 Decision Ledger

> 正向编译让"意图变成牢笼"。反向编译让"失败变成认知"。两者合一，系统才不只是重试器，而是学习器。

---

## 第二部分：数据模型（四个原语的精确定义）

### 4. Decision（决策对象）

#### 4.1 Decision 的最小字段集

```yaml
decision:
  meta:
    id: "decision.auth.token_strategy"
    version: "1.0.0"
    status: "active"          # draft | active | superseded | withdrawn
    created_by: "human"
    created_at: "2026-03-04T10:00:00Z"
    supersedes: null           # 若存在，引用被替代的旧 decision
    superseded_by: null        # 若被替代，指向新 decision

  spec:
    what: "用户认证采用 JWT，算法 HS256，secret 从环境变量读取，有效期 24h"
    why: "JWT 无状态，适合单体后端；HS256 实现简单；env 读取避免硬编码"
    alternatives:
      - option: "Session-based auth"
        rejected_because: "需要服务端状态存储，增加复杂度"
      - option: "RS256"
        rejected_because: "需要密钥对管理，当前规模不需要"
    scope:
      affects_modules: ["user_auth"]
      affects_contracts: []     # 激活后由 compiler 填充
    freeze_level: "F2"          # F1=强偏好 / F2=硬要求 / F3=硬禁止

  extensions: {}
```

#### 4.2 Decision 状态机

```
DRAFT → ACTIVE → SUPERSEDED
                → WITHDRAWN

规则：
  DRAFT → ACTIVE：必须经过 Human Gate
  ACTIVE → SUPERSEDED：必须先有新 Decision（ACTIVE），旧的自动 superseded
  ACTIVE → WITHDRAWN：必须经过 Human Gate + 影响分析
  SUPERSEDED/WITHDRAWN：不可变，永久存档
```

#### 4.3 Decision 的三种冻结强度（Freeze Level）

- **F1（Hard Preference）**：不符合触发 human review，但可放行
- **F2（Hard Requirement）**：不符合即打回，人类可在 review 中降级或放行
- **F3（Hard Prohibition）**：触发即 halt，等同边界违规

#### 4.4 Decision 的硬规则
- 任何 Decision 的 `what` 必须是可判定的陈述（不允许模糊表达如"尽量""大概"）
- 任何 Decision 必须有 `why`（一句话也行，但不能空）
- 任何 Decision 必须有 `scope`（哪怕只写一个模块名）

---

### 5. Contract（契约对象）

#### 5.1 Contract 与 Decision 的因果绑定（铁律）

**铁律 1：任何 ACTIVE Contract 必须引用至少一个 ACTIVE Decision**

```yaml
contract:
  meta:
    # ...existing fields...
    decision_refs:                    # 必填，不可为空（对 ACTIVE 状态）
      - { id: "decision.auth.token_strategy", version: "1.0.0" }
```

这条规则保证：
- 任何契约都可追溯到"为什么这么定"
- 未来修改契约时，必须先找到要废止/替代的 decision

**铁律 2：任何修改 ACTIVE Contract 的行为，必须先产生 Supersede Decision**

流程：
1) 提出新 Decision（draft）
2) Human Gate 确认（新 decision → active，旧 decision → superseded）
3) Compiler 正向编译：生成新版本 Contract
4) 新 Contract 进入 pending_review → Human Gate → active
5) 旧 Contract → deprecated

> 这让"契约变更"从"直接改文件"变成"先拍板为什么改，再编译出怎么改"。

#### 5.2 Contract Envelope（与前版一致，增加 decision_refs）

```yaml
contract:
  meta:
    type: "role | task | interface | behavior | boundary"
    id: "..."
    version: "X.Y.Z"
    status: "draft | pending_review | active | amending | deprecated"
    created_by: "..."
    created_at: "..."
    decision_refs: [...]          # 新增：因果链
    dependencies: [...]
    validation:
      schema: "contracts/schemas/..."
      checks: []
    on_failure:
      action: "retry | halt | human_escalation"
      max_retries: 3
      severity: "low | mid | high"
  spec: { ... }
  extensions: {}
```

#### 5.3 五类原子契约（spec 定义，与前版一致但更精炼）

**Role Contract**
```yaml
spec:
  display_name: "Backend Coder"
  capabilities:
    read: [glob]
    write: [glob]
    exec: [command_prefix]
  prohibitions:
    write: [glob]
    exec: [command_prefix]
  retry_policy:
    max_retries: 3
  confidence_threshold: 0.7
```

硬规则：默认拒绝。不在 capabilities 中即禁止。

**Task Contract**
```yaml
spec:
  assigned_to: "role.coder_backend"
  scope:
    include: [glob]
    exclude: [glob]
    create_allowed: [glob]
  acceptance:
    behavior_ref: { id: "...", version: "..." }
    interface_refs: [...]
    max_new_files: N
  token_budget: N
```

**Interface Contract**
```yaml
spec:
  endpoints:
    - id: "login"
      path: "/api/auth/login"
      method: "POST"
      request: { schema: {...} }
      response: { success: { status: 200, schema: {...} } }
  binding:
    producer: "role.coder_backend"
    consumers: ["role.coder_frontend"]
  change_policy:
    requires_approval: ["role.architect", "human"]
```

**Behavior Contract**
```yaml
spec:
  test_suite:
    runner: "pytest"
    entry: "tests/backend/test_user_auth.py"
    command: "pytest -q tests/backend/test_user_auth.py"   # 必填
  mandatory_cases:
    - { id: "TC001", description: "...", must_pass: true }
  coverage:
    minimum_percent: 80    # 可选
```

硬规则：created_by 必须为 role.qa 或 human。

**Boundary Contract**
```yaml
spec:
  sacred_files: [glob]
  rules:
    - id: "no_sacred_write"
      check_method: "git_diff_scan"
      violation_action: "immediate_halt"
  on_violation:
    notify: "human"
    log_path: "state/audit/boundary_violations.log"
```

硬规则：violation_action=immediate_halt 不可降级。

---

### 6. Evidence（证据对象）

#### 6.1 Execution Evidence（每次执行必产出）

```yaml
evidence:
  meta:
    type: "evidence"
    id: "evidence.run.20260304-103000-ab12"
    version: "1.0.0"
    status: "active"
    created_by: "system"
    created_at: "..."
    decision_refs: []              # evidence 不直接引用 decision（通过 task→decision 间接追溯）
    dependencies:
      - { id: "task.user_auth.login_api", version: "1.0.0" }

  spec:
    run_id: "20260304-103000-ab12"
    role_id: "role.coder_backend"
    task_ref: { id: "task.user_auth.login_api", version: "1.0.0" }
    contract_snapshot:
      refs:
        - { id: "interface.user_auth", version: "1.0.0" }
        - { id: "behavior.user_auth", version: "1.0.0" }
    changes:
      modified_files: ["src/backend/auth/login.py"]
      created_files: []
      diff_stat: { files: 1, insertions: 40, deletions: 3 }
    commands:
      ran:
        - { cmd: "pytest -q ...", exit_code: 0, duration_ms: 1200 }
    tests:
      summary: "pass"
      details:
        - { case_id: "TC001", result: "pass" }
    self_report:
      confidence: 0.82
      risks: []
      notes: "..."

  extensions: {}
```

#### 6.2 Gate Report（门禁报告，每次门禁必产出）

```yaml
gate_report:
  meta:
    type: "gate_report"
    id: "gate.run.20260304-103000-ab12.output"
    version: "1.0.0"
    status: "active"
    created_by: "system"
    created_at: "..."
    decision_refs: []
    dependencies:
      - { id: "evidence.run.20260304-103000-ab12", version: "1.0.0" }

  spec:
    gate_type: "INPUT_GATE | OUTPUT_GATE"
    levels_checked:
      L0: { result: "pass", details: null }
      L1: { result: "pass", details: null }
      L2: { result: "fail", details: { failed_case: "TC003", trace: "..." } }
      L3: { result: "pass", details: null }
      L4: { result: "skip", details: null }    # 意图对齐（v0.1 可选）
    overall_result: "fail"
    resolved_refs:
      - { id: "behavior.user_auth", version: "1.0.0" }
    rejection:                                  # 若 fail
      retry_count: 1
      max_retries: 3
      failed_contract_ref: { id: "behavior.user_auth", version: "1.0.0" }
      diagnostics:
        summary: "TC003 failed: token 缺少第三段 signature"
        hint: "检查 jwt.py 签名逻辑"
    timestamp: "..."

  extensions: {}
```

#### 6.3 Human Decision（人类裁决，每次人类介入必产出）

```yaml
human_decision:
  meta:
    type: "human_decision"
    id: "hd.20260304-110000-001"
    version: "1.0.0"
    status: "active"
    created_by: "human"
    created_at: "..."
    decision_refs: []             # 若此次人类介入同时产生了新 Decision，在此引用
    dependencies:
      - { id: "gate.run.20260304-103000-ab12.output", version: "1.0.0" }

  spec:
    trigger: "retry_exceeded | boundary_violation | review_required | hypothesis_proposed"
    context_refs:
      - { id: "evidence.run.20260304-103000-ab12", version: "1.0.0" }
    options_presented:
      - { key: "approve", description: "接受当前产出" }
      - { key: "retry", description: "打回重试" }
      - { key: "amend", description: "修改契约后重试" }
      - { key: "crystallize", description: "将此次教训结晶为新 Decision" }
      - { key: "abort", description: "终止此任务" }
    selected_option: "crystallize"
    rationale: "重复失败说明缺少对 JWT 签名算法的硬约束"
    actions:
      new_decision_draft: "decision.auth.jwt_signing"    # 若选择 crystallize
      next: "pause_and_compile"

  extensions: {}
```

---

### 7. Hypothesis（假说——Backward Compile 的中间产物）

Hypothesis 不是独立原语，而是 Decision 的前态（status=draft 的 Decision + 特殊 trigger 标记）。

```yaml
decision:
  meta:
    id: "decision.auth.jwt_signing"
    version: "0.1.0"                   # 0.x 表示 draft/hypothesis
    status: "draft"
    created_by: "system"               # 由 compiler backward 生成
    created_at: "..."
    supersedes: null

  spec:
    what: "JWT 签名必须使用 HS256 算法，禁止 none 算法"
    why: "连续 2 次 rejection 均因 token 签名缺失/格式错误导致"
    alternatives: []                    # 系统生成时可为空，等人类补充
    scope:
      affects_modules: ["user_auth"]
    freeze_level: "F2"
    trigger:                            # hypothesis 专属字段
      source: "backward_compile"
      evidence_refs:
        - "evidence.run.20260304-103000-ab12"
        - "evidence.run.20260304-113000-cd34"
      pattern: "同类 TC003 失败 ≥ 2 次"

  extensions: {}
```

人类通过 Human Gate 决定：
- 接受 → status 升级为 active（结晶）
- 修改 → 人类改写 what/why/freeze_level 后 active
- 拒绝 → status 设为 withdrawn

---

## 第三部分：系统行为（流程与门禁）

### 8. Gate System（五级门禁）

#### 8.1 INPUT GATE（执行前）

检查顺序（固定）：
1. **I-L0：契约可加载**——task/role/boundary/behavior/interface 全部 schema 校验通过
2. **I-L1：依赖解析与版本锁定**——所有 ref 解析为精确版本；依赖的 contract 必须 active
3. **I-L1b：因果链完整**——task 引用的 contract 必须有 active decision_refs（铁律 1）
4. **I-L1c：scope 与 role 权限一致性**——task.scope ⊆ role.capabilities
5. 产出 INPUT GateReport

#### 8.2 OUTPUT GATE（执行后）

检查顺序（固定）：
1. **O-L0：Evidence schema 校验**——必填字段齐全、类型正确
2. **O-L1：结构一致性**——evidence.task_ref 与 state 当前任务匹配；refs 精确；created_by 合规
3. **O-L2：行为验证**——按 behavior.command 运行测试（系统执行，非 agent 自报）
4. **O-L3：边界审计**——git diff 扫描 sacred_files；命令审计越权
5. **O-L4：意图对齐**（v0.1 先做结构检查）——evidence 中是否引用了对应 decisions 的 scope
6. 产出 OUTPUT GateReport

#### 8.3 门禁判定后果（固定）

```
L0/L1/L2 fail → Rejection（可重试，按 on_failure.max_retries）
L3 fail       → Immediate Halt（不可重试，直接 Human Gate）
L4 fail       → Human Review（v0.1：仅提醒，不阻断；v0.2 可升级为阻断）

retry_count ≥ max_retries → 断路器 → Backward Compile → Human Gate
```

### 9. Constraint Compiler（约束编译器）

#### 9.1 Forward Compile（正向：Decision → Contract）

触发条件：新 Decision 进入 active

流程：
1. 读取 decision.spec.scope.affects_modules  
2. 查找该模块下已有的 contracts  
3. 生成"契约变更建议"（新增/修改哪些 contract 的哪些字段）  
4. 产出 draft contracts（status=draft，decision_refs 已填充）  
5. 进入 Human Gate：人类审核 → pending_review → active

v0.1 实现建议：  
- Forward compile 先做"提示 + 模板生成"：系统根据 decision 类型与 scope 生成 contract 骨架（字段预填充），人类/architect 补全细节。  
- 不需要 LLM 自动完成整个编译过程（保持确定性）。

#### 9.2 Backward Compile（反向：Evidence pattern → Hypothesis）

触发条件：同类 rejection 连续出现 N 次（N 可配，建议默认 2）

"同类"判定规则（v0.1 简约版）：
- 同一 task_ref + 同一 failed_contract_ref + 同一 failed level
- 或同一 behavior case_id 连续失败

流程：
1. 从 Evidence Ledger 中提取失败模式  
2. 生成 Hypothesis（draft Decision），附带 trigger.evidence_refs 与 trigger.pattern  
3. 放入 human_queue  
4. 人类决策：结晶 / 修改后结晶 / 拒绝

v0.1 实现建议：  
- Backward compile 先做"模式匹配 + 模板生成"：系统检测重复失败模式，生成 hypothesis 骨架（what 预填"建议约束 X"，why 预填失败摘要）。  
- 人类负责确认/修改 what 与 freeze_level。

#### 9.3 Compiler 不做什么（边界）
- 不做"自动判定 decision 是否正确"（这是人类的事）
- 不做"自动合并冲突的 decisions"（冲突必须升级人类）
- 不做"跨模块的隐式推理"（只在 scope 范围内编译）

---

### 10. Orchestrator（编排器，v0.1 串行）

#### 10.1 工作流 YAML（最小结构）

```yaml
workflow:
  id: "workflow.standard"
  nodes:
    - id: "architect"
      role: "role.architect"
      action: "produce_contracts"
      human_review: true
    - id: "qa"
      role: "role.qa"
      action: "produce_behavior"
    - id: "coder"
      role: "role.coder_backend"
      action: "implement"
    - id: "review"
      role: "role.architect"
      action: "review"
      human_review: true
  transitions:
    on_pass: "next"
    on_fail: "retry_or_escalate"
    on_halt: "human_gate"
```

#### 10.2 编排器核心循环（伪逻辑）

```
loop:
  1. 读取 state → 当前 node、当前 task
  2. INPUT GATE（含引用锁定、因果链校验）
     - fail → rejection / human_gate
  3. 构建 ExecutionRequest → 调用 Executor
  4. 收集 ExecutionEvidence
  5. OUTPUT GATE（L0→L1→L2→L3→L4）
     - fail(L0-L2) → rejection → 重试或断路器
     - fail(L3) → halt → human_gate
     - fail(L4) → human_review
  6. pass → 更新 state → 前进到下一 node
  7. 若 node.human_review=true → 挂起等待 HumanDecision
  8. 断路器触发 → backward_compile → hypothesis → human_gate
```

---

### 11. Executor Port（执行端口）

#### 11.1 抽象接口（不绑定 Codex）

**ExecutionRequest**
- role_id
- working_dir（由 role.capabilities 派生）
- task_ref（精确版本）
- injected_context（只读：相关 contracts + active decisions + state 摘要）
- policy（写入 glob 白名单、命令前缀白名单）

**ExecutionResult**
- exit_status
- evidence（必须产出，失败也要）
- raw_log_pointer（可选，不进入核心数据流）

#### 11.2 Codex CLI Adapter（v0.1 唯一实现）
- 将 request 翻译为 `codex exec` 调用
- 执行前后做 git diff（为 L3 提供数据）
- 解析输出为 evidence（系统生成，不信任 agent 自报的结构）
- 若 Codex 退出码非 0：仍产出 error evidence（不可静默丢失）

#### 11.3 可替换保证
- 治理平面只消费 Evidence 与 GateReport
- 不依赖 Codex 专有字段、事件格式、日志结构

---

### 12. State Manager（状态管理）

#### 12.1 PROJECT_STATE 结构（v0.1 最小稳定集）

```json
{
  "project_id": "my-project",
  "current_workflow_id": "workflow.standard",
  "current_node_id": "coder",
  "current_task_ref": { "id": "task.user_auth.login_api", "version": "1.0.0" },
  "phase": "development",
  "status": "in_progress",

  "locked_refs": [
    { "id": "interface.user_auth", "version": "1.0.0" },
    { "id": "behavior.user_auth", "version": "1.0.0" }
  ],

  "active_decisions": [
    "decision.auth.token_strategy@1.0.0",
    "decision.auth.jwt_signing@1.0.0"
  ],

  "run_history": [
    {
      "run_id": "20260304-103000-ab12",
      "task_ref": "task.user_auth.login_api@1.0.0",
      "role_id": "role.coder_backend",
      "evidence_ref": "evidence.run.20260304-103000-ab12@1.0.0",
      "gate_result": "fail",
      "status": "rejected"
    }
  ],

  "human_queue": [
    {
      "type": "hypothesis",
      "ref": "decision.auth.jwt_signing@0.1.0",
      "priority": "high"
    }
  ],

  "checkpoints": []
}
```

#### 12.2 持久化与恢复规则
- 任何状态变更必须先写 state 再执行下一步
- 断点续跑：读取 state → 恢复到 current_node + 最后一次 gate_result → 继续
- 任何 run 必须落 evidence（哪怕是 error evidence）

---

### 13. Human-in-the-loop（人类交互）

#### 13.1 触发类型

```
主动触发（系统固定等待）：
  - Decision 从 draft → active（结晶确认）
  - Contract 从 draft → active（激活审核）
  - 工作流 node 标记 human_review=true

被动触发（异常升级）：
  - 断路器（重试次数耗尽）
  - 边界违规（L3 halt）
  - 低置信度（evidence.self_report.confidence < threshold）
  - Backward compile 产出 hypothesis
```

#### 13.2 结构化输出（给人类看的永远是选择题 + 摘要）

```
┌─ Capsule Human Gate ──────────────────────────────┐
│                                                     │
│  触发原因：重试次数耗尽（TC003 连续 2 次失败）        │
│                                                     │
│  影响范围：task.user_auth.login_api                  │
│  失败摘要：JWT token 缺少第三段 signature              │
│  相关决策：decision.auth.token_strategy@1.0.0        │
│                                                     │
│  系统建议：结晶新 Decision（JWT 签名必须 HS256）       │
│                                                     │
│  选项：                                              │
│  [1] 接受建议，结晶新 Decision                        │
│  [2] 手动修改建议后结晶                               │
│  [3] 打回重试（不结晶）                               │
│  [4] 修改现有 Contract 后重试                         │
│  [5] 暂停此任务                                      │
│                                                     │
└─────────────────────────────────────────────────────┘
```

#### 13.3 决策写回
人类选择后 → 产出 HumanDecision 工件 → 写入 state  
若选择结晶 → 触发 Decision 激活流程 → 触发 Forward Compile

---

## 第四部分：文件系统与落盘

### 14. 目录结构

```
capsule/
├── capsule.yaml                         # 项目配置
├── CAPSULE.md                           # 上下文注入文档
│
├── decisions/                           # Decision Ledger
│   ├── auth/
│   │   ├── token_strategy.decision.yaml
│   │   └── jwt_signing.decision.yaml
│   └── ...
│
├── contracts/
│   ├── schemas/                         # JSON Schema（sacred）
│   ├── boundaries/                      # Boundary 实例（sacred）
│   └── instances/                       # 按模块
│       └── user_auth/
│           ├── task.login_api.contract.yaml
│           ├── interface.user_auth.contract.yaml
│           └── behavior.user_auth.contract.yaml
│
├── roles/
│   ├── architect.role.yaml
│   ├── qa.role.yaml
│   └── coder_backend.role.yaml
│
├── workflows/
│   └── standard.workflow.yaml
│
├── state/
│   ├── PROJECT_STATE.json
│   ├── runs/
│   │   └── <run_id>/
│   │       ├── evidence.yaml
│   │       ├── input_gate.yaml
│   │       ├── output_gate.yaml
│   │       └── human_decision.yaml      # 若有
│   └── audit/
│       └── boundary_violations.log
│
└── core/                                # 系统实现
    ├── cli.py
    ├── registry.py                      # Contract + Decision Registry
    ├── compiler.py                      # Constraint Compiler（forward + backward）
    ├── validator.py                     # Gate Engine
    ├── state_manager.py
    ├── orchestrator.py
    ├── executor/
    │   ├── port.py
    │   └── codex_cli.py
    └── human_loop.py
```

---

## 第五部分：Authority Order（权威顺序，系统铁律）

写死为系统规则，任何冲突按此顺序裁决：

```
1. Active Decisions（freeze_level=F3）       ← 最高权威
2. Boundary Contracts
3. Active Decisions（freeze_level=F2）
4. Active Contracts（interface/behavior/role/task）
5. Active Decisions（freeze_level=F1）
6. Evidence / GateReports
7. Prompts / 对话                            ← 最低权威（只是工具）
```

> 当 Gate 判定出现冲突时（例如测试通过但违反 F2 decision），以权威顺序为准。

---

## 第六部分：CLI（v0.1 最小指令集）

```
capsule init              # 初始化项目结构
capsule validate          # 离线校验所有 contracts + decisions（L0/L1 + 因果链）
capsule run               # 从当前 state 开始执行到下一个 human gate 或结束
capsule resume <run_id>   # 从断点恢复
capsule review            # 输出当前 human_queue 的结构化摘要与选项
capsule decide <option>   # 写入 HumanDecision 并继续
capsule crystallize       # 将 draft decision 激活（触发 forward compile）
capsule status            # 输出当前 state 摘要
```

---

## 第七部分：三条系统铁律（Gate 必须硬编码执行，不可配置绕过）

**铁律 1：任何 ACTIVE Contract 必须引用至少一个 ACTIVE Decision**  
无根之木不允许存在。INPUT GATE I-L1b 强制检查。

**铁律 2：任何修改 ACTIVE Contract，必须先 Supersede Decision**  
先有新因，才有新果。变更流程强制执行。

**铁律 3：当同类 Rejection ≥ N 次，系统必须触发 Backward Compile**  
失败不允许被静默重试；必须升级为认知（hypothesis），让人类决定是否结晶。

---

## 第八部分：实现顺序（最小返工路线图）

```
Step 1：Decision + Contract 数据模型与 Schema
        - decision.schema.json
        - contract envelope + 5 类 spec schema
        - evidence / gate_report / human_decision schema
        - 含 decision_refs 因果链字段

Step 2：Registry（Decision + Contract 统一注册表）
        - 扫描、加载、索引
        - L0 schema 校验
        - 版本解析与锁定
        - 因果链校验（铁律 1）

Step 3：Gate Engine（INPUT + OUTPUT，L0-L3）
        - 含 rejection 产出
        - 含 boundary L3 halt

Step 4：State Manager
        - PROJECT_STATE 读写
        - run_history / human_queue
        - checkpoint / resume

Step 5：Executor Port + Codex Adapter
        - 产出 evidence
        - git diff 收集

Step 6：Compiler
        - Forward：decision → contract draft（模板生成）
        - Backward：rejection pattern → hypothesis

Step 7：Orchestrator（串行 workflow）
        - 完整循环：input gate → execute → output gate → next/retry/human

Step 8：CLI + Human Loop
        - run / review / decide / crystallize / resume

Step 9：端到端验收
        - user_auth 模块完整跑通
        - 至少产出 1 个 backward compile hypothesis
        - 人类介入 ≤ 2 次
```

---

## 第九部分：v0.1 验收标准（Definition of Done）

1. 任意契约缺 decision_refs 且 status=active → INPUT GATE 必须拒绝（铁律 1）
2. 修改 active contract 未先 supersede decision → 系统必须阻断（铁律 2）
3. 同类 rejection ≥ 2 → 系统必须产出 hypothesis 并进入 human_queue（铁律 3）
4. 边界违规（sacred_files 触达）→ immediate halt + human gate
5. evidence schema 不合格 → L0 打回
6. `capsule crystallize` → forward compile → draft contract 产出
7. `capsule review` → 结构化摘要 + 选项；`capsule decide` → 写回 + 可 resume
8. 端到端：user_auth 从 decision → contract → implement → test → review 全链路闭环

---

这套技术方案的全部重心已经从"如何编排 Agent"转移到"如何建立治理原语"。你审阅后告诉我哪里需要修改、哪里需要继续深入，我们再迭代。

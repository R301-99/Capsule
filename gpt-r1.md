以下为 **Capsule v0.1（第一轮设计）对应的详细技术方案**。它的定位是：直接交给“什么都不知道的工程实现者”，使其能够按统一架构实现一个可运行的 MVP 内核闭环。文档不包含具体代码，但包含**接口契约、数据结构、校验算法、流程状态机、文件落盘规范、验收标准与实现顺序**。

---

# Capsule v0.1 详细技术方案（Implementation Spec）

## 1. 范围与交付目标（v0.1 必须做到什么）

### 1.1 v0.1 目标（强制）
实现一个“契约驱动”的纵向闭环，使得以下链条成立：

1) 读取契约（contracts）与工作流（workflows）  
2) 进入 INPUT GATE：引用解析 + 版本锁定 + 权限/范围预检  
3) 调用执行引擎（v0.1：Codex CLI 适配器）产生 ExecutionEvidence  
4) 进入 OUTPUT GATE：L0/L1/L2/L3 逐级验证并产出 GateReport  
5) 失败则按 on_failure 形成 Rejection / 重试 / 断路器升级  
6) 必要时进入 Human-in-the-loop：输出结构化摘要与选项，并写回 HumanDecision  
7) 所有过程写入 PROJECT_STATE 与 runs 证据链，可断点续跑

### 1.2 v0.1 非目标（明确不做）
- 并行多 Agent、复杂 DAG 编排  
- Web UI、云服务  
- 高级不可篡改审计（hash 链可预留但不强制）  
- 全套 LangGraph 深度集成（仅预留适配点）

---

## 2. 关键架构原则（工程实现必须遵守）

1) **核心严格，外围宽松**  
   - `contract.meta` 严格：禁止未知字段  
   - 扩展只允许进入 `contract.extensions`（唯一扩展口）

2) **引用可写范围，但运行前必须锁定精确版本**  
   - 配置可写 `1.x`；进入执行态前必须解析为 `1.2.3` 并写入 state + gate_report + evidence

3) **ACTIVE 契约不可原地修改**  
   - 修改走新版本（copy-on-write）；旧版本 deprecated/冻结

4) **执行引擎可替换**  
   - 内核只消费 `ExecutionEvidence` 与 `GateReport`，不得依赖 Codex 专有日志结构

---

## 3. 文件系统与落盘规范（可审计、可恢复）

### 3.1 建议目录（v0.1 固定）
```
contracts/
  schemas/                      # JSON Schema（边界保护）
  boundaries/                   # boundary 实例（全局）
  instances/<module>/           # task/interface/behavior 实例（按模块）

roles/                          # role 合同（YAML）
workflows/                      # workflow 定义（YAML）

state/
  PROJECT_STATE.json
  runs/<run_id>/
    evidence.json
    gate_reports/
      input.json
      output.json
    rejections/<rej_id>.json    # 可选
    human_decisions/<id>.json   # 可选（也可集中到 state）
    artifacts/                  # 可选：测试报告、命令输出摘要等
  audit/
    boundary_violations.log     # 追加式
```

### 3.2 Run ID 规则（建议）
- `run_id = YYYYMMDD-HHMMSS-<shortuuid>`  
用于定位一次执行的所有证据文件。

---

## 4. 元契约（Meta-Contract）规范（v0.1 详尽定义）

### 4.1 Contract Envelope（所有契约统一结构）
所有契约文件均为 YAML（或 JSON），顶层结构固定为：

```yaml
contract:
  meta: {...}
  spec: {...}
  extensions: {}   # 可选；若存在则允许任意结构
```

#### 4.1.1 `meta` 字段（additionalProperties=false）
必填字段：
- `type`: enum  
  `role | task | interface | behavior | boundary | gate_report | evidence | human_decision`
- `id`: string（分层命名）  
  推荐：`<type>.<domain>.<name>`
- `version`: string（SemVer，regex `^\d+\.\d+\.\d+$`）
- `status`: enum  
  `draft | pending_review | active | amending | deprecated`
- `created_by`: enum（最小集合，后续可扩）  
  `role.architect | role.qa | role.coder_backend | role.coder_frontend | human | system`
- `created_at`: string（ISO 8601）
- `dependencies`: array of `ContractRef`（允许空数组）
- `validation`: object（见 4.3）
- `on_failure`: object（见 4.4）

可选字段（但建议 v0.1 也纳入 schema）：
- `description`: string
- `tags`: string[]

#### 4.1.2 `extensions`（唯一扩展口）
- `extensions` 允许任意结构（additionalProperties=true）  
- 约定：必须命名空间化，例如 `extensions.org_x.feature_y`

### 4.2 ContractRef（引用对象）
统一使用对象引用（禁止自由文本路径引用作为依赖）：

```yaml
ref:
  id: "behavior.user_auth"
  version: "1.x"     # 允许范围表达（仅在未锁定阶段）
```

> **锁定规则（硬）**：任何将要执行的 task，其依赖 ref 必须被解析为精确版本 `1.2.3`，并写入 state 与 gate_report/evidence（见第 7 节算法）。

### 4.3 `validation`（契约自描述验证方式）
v0.1 采用最简但可扩展结构：

```yaml
validation:
  schema: "contracts/schemas/task.contract.schema.json"
  checks: []
```

- `schema` 必填：指向用于 L0 校验的 schema 文件路径（相对仓库根）
- `checks` 可选：预留未来脚本/命令型校验声明（v0.1 可不执行，但结构要可解析）

### 4.4 `on_failure`（失败策略）
```yaml
on_failure:
  action: "retry" | "halt" | "human_escalation"
  max_retries: 0..N
  severity: "low" | "mid" | "high"
```

---

## 5. 五类原子契约：最小字段集与关键约束（v0.1）

> 目标：字段“足够门禁化”，不追求完整业务表达。

### 5.1 Role Contract（role.*）
`spec` 最小字段：

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

**执行期硬规则：**
- 任何写入路径若不在 capabilities.write → 视为越权（L3/halt）
- 任何命令若不在 capabilities.exec 或命中 prohibitions.exec → 视为越权（L3/halt）

### 5.2 Task Contract（task.*）
`spec` 最小字段：

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

### 5.3 Interface Contract（interface.*）
建议要求 `behavior` 与 `interface` 不强耦，但 `task` 可引用 `interface_refs`。

`spec` 最小字段：
- `endpoints[]`: `id/path/method/request.schema/response.*.schema`
- `binding`: `producer`/`consumers[]`
- `change_policy`: `requires_approval[]`

### 5.4 Behavior Contract（behavior.*）
**v0.1 强烈建议 `command` 必填**，避免推断 runner/entry：

```yaml
spec:
  test_suite:
    runner: "pytest"
    entry: "tests/backend/test_user_auth.py"
    command: "pytest -q tests/backend/test_user_auth.py"
  mandatory_cases: []
```

**created_by 规则（L1）：**
- behavior.created_by 必须是 `role.qa` 或 `human`，否则打回（可重试，不 halt）

### 5.5 Boundary Contract（boundary.*）
v0.1 必须启用至少一个 global boundary。

```yaml
spec:
  sacred_files:
    - "capsule.yaml"
    - "contracts/schemas/**"
    - "state/**"
    - ".env*"
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

---

## 6. 三类事件契约（运行事实）：GateReport / ExecutionEvidence / HumanDecision

> 这三者是“证据链”和“人类出口标准化”的基础。v0.1 建议直接纳入 schema 与落盘。

### 6.1 GateReport（gate_report.* 或作为 evidence 子文件）
`spec` 最小字段：

```yaml
spec:
  gate_id: "INPUT_GATE" | "OUTPUT_GATE"
  level: 0|1|2|3
  result: "pass" | "fail" | "halt" | "human"
  failed_contract_ref: { id: "...", version: "..." } # 可选
  diagnostics:
    summary: "..."
    details: {}          # 结构化，可扩展
  resolved_refs:         # 关键：锁定后的精确引用
    - { id: "behavior.user_auth", version: "1.0.3" }
  timestamp: "..."
```

### 6.2 ExecutionEvidence（evidence.*）
`spec` 最小字段：

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

### 6.3 HumanDecision（human_decision.*）
`spec` 最小字段：

```yaml
spec:
  decision_id: "HD-20260303-001"
  trigger: "retry_exceeded" | "boundary_violation" | "review_required"
  context_refs:
    - { id: "evidence.run.20260303-...", version: "1.0.0" }  # 或用路径指针
  options_presented: ["approve", "amend_contract", "pause", "abort"]
  selected_option: "amend_contract"
  rationale: "..."
  actions:
    next: "resume" | "abort" | "pause"
  timestamp: "..."
  made_by: "human"
```

---

## 7. Contract Registry（契约注册表）：行为规范与算法（必须详尽）

### 7.1 注册表职责
- 扫描 `contracts/boundaries/`, `roles/`, `contracts/instances/**`  
- 解析 Envelope（YAML/JSON）
- L0：按 `contract.meta.validation.schema` 执行 JSON Schema 校验（任何失败即拒绝加载）
- 建索引：
  - `by_id[id] -> list[contract]`（按 version 排序）
  - `by_id_version[(id, version)] -> contract`

### 7.2 版本解析与锁定（核心算法）
输入：`ContractRef(id, version)`，其中 version 可能是 `1.x` 或精确 `1.2.3`

输出：精确版本 ref

规则：
1) 若 version 为精确 SemVer：必须存在该版本，否则 L1 fail  
2) 若 version 为范围（仅支持 `MAJOR.x`，v0.1 不支持更复杂范围）：
   - 从 registry 中取 `id` 对应的所有版本
   - 过滤出 `MAJOR == requested_major`
   - 过滤出 `status == active`（若无 active，可接受 pending_review？建议不接受，避免不确定）
   - 选最高版本（按 SemVer 比较）
   - 输出精确 ref

锁定写入点（INPUT GATE 内完成）：
- 写入 `PROJECT_STATE.locked_refs`（或 `state.locked_refs`）
- 写入 `GateReport.spec.resolved_refs`
- 写入 `ExecutionEvidence.spec.contract_snapshot.refs`

---

## 8. Gate System：L0/L1/L2/L3 的确定性验证细则（必须详尽）

### 8.1 INPUT GATE（执行前）
输入：task_ref（可能含范围引用）、当前 state、registry、role contract、boundary contract  
输出：GateReport +（若 pass）锁定后的精确 refs 集合

检查顺序（固定）：

**I0：契约可加载（L0）**
- task/role/boundary/behavior/interface（若 task 引用）均必须加载成功

**I1：依赖存在与引用锁定（L1）**
- 解析 task.acceptance.behavior_ref、task.acceptance.interface_refs 等
- 锁定为精确版本，写入 state

**I2：Scope 与 Role 权限预检（L1）**
- task.scope.include/exclude/create_allowed 必须是 role.capabilities.write 的子集（或可由系统容忍 include 更窄，但不得更宽）
- task.scope.exclude 不能与 include 冲突
- 发现越权风险：result=fail（可打回）或 result=human（若需人类裁决）

产物：
- `state.current_task_ref` 必须变为精确版本
- 生成 `input_gate_report.json`

### 8.2 OUTPUT GATE（执行后）
输入：ExecutionEvidence、registry、boundary、role、task、behavior  
输出：output GateReport（pass/fail/halt/human）

**O0：Evidence 格式校验（L0）**
- evidence 必须符合 schema；缺字段直接 fail
- evidence.task_ref 必须与 state.current_task_ref 匹配（L1）

**O1：结构一致性（L1）**
- evidence.contract_snapshot.refs 必须包含 task/behavior/interface 的精确 refs
- behavior.created_by 合规
- evidence.modified_files 必须落在 role.write 且不触达 boundary.sacred_files（此处可在 L3 再判，但建议此处先做预检以减少无效 L2）

**O2：行为验证（L2）**
- 从 behavior.spec.test_suite.command 获取命令执行（由系统执行，非 agent 自说自话）
- 失败则 fail，形成 rejection，并将失败用例/摘要写入 diagnostics

**O3：边界审计（L3）**
- 基于 git diff（推荐）扫描 modified_files：
  - 任一匹配 boundary.sacred_files → immediate halt
- 基于命令审计（若 evidence 中记录命令，或由系统 wrapper 记录）：
  - 命中 role.prohibitions.exec 或不在 role.capabilities.exec → immediate halt
- 产出 boundary violation 记录写入 `state/audit/boundary_violations.log`（追加式）

---

## 9. Rejection Protocol 与断路器（重试/升级机制）

### 9.1 Rejection（结构化打回）
当 L0–L2 fail（非 L3）时生成：

- `rejection_id`
- `target_role`
- `task_ref`
- `retry_count` / `max_retries`
- `failed_gate` / `failed_level`
- `failed_contract_ref`
- `failure_details`（结构化：命令、退出码、用例摘要、建议）

### 9.2 重试策略来源
优先级（从高到低）：
1) task.meta.on_failure（若存在角色特定覆盖）  
2) role.spec.retry_policy  
3) 系统默认（例如 max_retries=2）

### 9.3 断路器
触发条件：`retry_count >= max_retries` 或 `token_budget` 超限（v0.1 可先记录不强制）  
触发动作：
- 生成 `HumanDecision` 请求（trigger=retry_exceeded）
- 将待处理事项加入 `state.human_queue`

---

## 10. Orchestrator（v0.1：Lean 串行，工作流 YAML 规范）

### 10.1 Workflow YAML（最简可用）
建议结构（示例）：

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
    - id: "coder_backend"
      role: "role.coder_backend"
      action: "implement"
    - id: "architect_review"
      role: "role.architect"
      action: "review"
      human_review: true
  transitions:
    on_pass: "next"
    on_fail: "retry_or_escalate"
    on_halt: "human_gate"
```

v0.1 只需支持：
- `next` 串行
- `retry_or_escalate`（按 rejection 与断路器）
- `human_gate` 挂起等待决策

### 10.2 编排状态
`PROJECT_STATE` 至少包含：
- current_workflow_id
- current_node_id
- current_task_ref（精确）
- run_history（run_id 与 gate/evidence 指针）
- human_queue（待决策项）

---

## 11. Executor Port（执行端口）与 Codex CLI 适配器（实现约束）

### 11.1 Executor Port（必须抽象）
定义两个对象概念（实现者可用 Pydantic/Dataclass）：

**ExecutionRequest**
- role_id
- working_dir
- task_ref（精确）
- injected_context（只读快照：相关契约内容投影 + state 关键字段）
- policy（允许写入 glob、允许执行命令前缀）

**ExecutionResult**
- success/failure（执行层是否成功）
- raw logs pointer（可选）
- evidence（必须产出；失败也要产出 error evidence）

### 11.2 Codex CLI Adapter（v0.1）
要求：
- 由 wrapper 负责记录：
  - 实际运行命令（至少包含测试命令）
  - 退出码与耗时
- 由 wrapper 负责产生 evidence 的结构化字段（而非让 agent 自己胡写）
- 由 wrapper 负责收集 modified_files：
  - 推荐：执行前后 git diff 或文件快照对比（与 L3 共用机制）
- Codex 的输出仅作为 self_report.notes 的来源之一，必须截断与结构化，禁止把长日志直接塞入 evidence（防止状态膨胀）

---

## 12. Human-in-the-loop（挂起/决策/恢复）

### 12.1 人类出口输出（CLI 层）
`capsule review` 输出必须包括：
- 触发原因（trigger）
- 影响范围（改了哪些文件、哪些契约、哪些测试失败）
- 推荐选项（系统或 architect）
- 可选项列表（固定枚举）

### 12.2 决策落盘
`capsule decide --option X --rationale "..."`
- 写入 `state/runs/<run_id>/human_decisions/<id>.json`
- 并写入 `PROJECT_STATE.last_human_decision`
- orchestrator 读取 decision 后：
  - `resume`：继续从当前 node 或指定 node
  - `amend_contract`：将任务标记为 “needs_contract_update”，阻塞后续直到契约更新完成（v0.1 可简化为进入 architect node）

---

## 13. JSON Schema 与 Pydantic 的推荐用法（工程实现指导）

### 13.1 真相源：JSON Schema 文件
- `contracts/schemas/*.schema.json` 是正式规范  
- Validator(L0) 使用 jsonschema 校验

### 13.2 开发便利：Pydantic（建议）
- 使用 Pydantic 模型承载 Contract / Evidence / GateReport / State
- 推荐路线：**Model-first + 导出 schema 固化**  
  - 由 CI 导出 schema 到 `contracts/schemas/`
  - schema 变更受 boundary + human_review 保护

> 注意：Pydantic AI 可用于“语义层生成契约草案”，但不应成为契约层与门禁层的依赖。

---

## 14. 实现顺序（最小返工路线图）

按依赖顺序（强烈建议遵循）：

1) 定稿 Contract Envelope / Ref / 三类事件（schema 与样例）  
2) Contract Registry（扫描、加载、索引、L0 校验）  
3) State Manager（最小 state + runs 落盘 + checkpoint）  
4) Validator（INPUT/OUTPUT gate：先做 L0+锁定+L3 diff 扫描骨架）  
5) Executor Port + Codex adapter（先能跑一次并产出 evidence）  
6) OUTPUT GATE 的 L2（按 behavior.command 跑测试）  
7) Lean Orchestrator（workflow 串行、重试、断路器）  
8) Human loop（review/decide/resume）

---

## 15. v0.1 验收标准（Definition of Done）

满足以下全部条件才算 v0.1 通过：

1) 任意契约文件缺字段或类型错误 → L0 必须拒绝加载并给出明确诊断  
2) task 引用 `behavior@1.x` → INPUT GATE 必须解析为精确版本并写入 state/evidence/gate_report  
3) 执行一次 coder_backend：
   - 必须产出 ExecutionEvidence（即便失败）  
4) OUTPUT GATE：
   - L2 必须按 behavior.command 运行测试并记录结果  
   - L3 若触达 sacred_files 或越权命令 → 必须 immediate halt，并进入 human gate  
5) `capsule review` 输出结构化摘要与选项；`capsule decide` 可写回并 `resume`  
6) 断点续跑：中断后再次运行，能够从 state 恢复并继续

---

# 需要你（产品发起人）在本方案上确认的 3 个“定盘星”

为确保 coder 不会在实现时反复猜测，我建议你直接回复“同意/修改”以下三点（我默认按建议执行）：

1) **强制 git 作为差异与边界审计基础**（推荐同意）  
2) **behavior.test_suite.command 在 v0.1 中必填**（推荐同意）  
3) **范围引用仅支持 `MAJOR.x`（如 1.x），不支持更复杂 semver range**（v0.1 推荐同意，后续再扩展）

你确认后，我将把本方案压缩为两份“交付给 coder 的工作包”：
- 《Schema & Data Spec Pack》（含所有契约/事件/state 的样例文件与字段解释）
- 《Gate & Orchestration DoD Pack》（含输入/输出门禁检查清单、错误码/诊断规范、验收用例）

并按你的工作模式进入下一轮：你提改动点，我更新方案与指导文档。

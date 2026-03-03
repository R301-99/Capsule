下面给出 **Capsule 第一版设计草案（v0.1-architecture draft）**。这版遵循你的要求：

- **整体全面而宽泛**：把产品长期“牢笼”结构先定出来，保证扩展性与可替换性。
- **局部尽可能详尽**：对“马上要实现”的内核（契约元结构、注册表、验证门禁、状态/证据、人类出口、执行端口与 Codex 适配器、最小编排）给出可直接落地的技术指导级细节。
- **不涉及实际代码**：但会给到工程实现者足够明确的字段、约束、流程与 DoD。

你可以把它当作：你我作为架构师的第一轮“设计合同”。你提修改意见后，我再迭代成第二版并补充“给 coder 的技术指导”。

---

# Capsule v0.1 设计草案（第一版）

## 1. 总体边界与不变性（Global Invariants）

### 1.1 Capsule 内核只做三件事（必须长期保持克制）
1) **Contract**：读取/校验/引用解析/版本锁定/生命周期管理  
2) **Gate**：输入门禁、输出门禁、边界审计、失败打回/终止/升级  
3) **State + Evidence + Human Decision**：可回放、可恢复、可审计的事实链

> 任何“智能”只允许存在于语义层（architect/qa 的生成与澄清），但**判定与流转**必须在内核以确定性规则完成。

### 1.2 执行引擎可替换（从第一天开始贯彻）
Capsule 内核不依赖 Codex 的任何专有对象；只依赖以下抽象输出：
- `ExecutionEvidence`（结构化证据包）
- `GateReport`（门禁结论）
- `HumanDecision`（人类裁决）

Codex CLI 仅是第一版 `ExecutorAdapter`。

---

## 2. 目录与模块边界（建议固定，降低沟通成本）

建议在仓库内保持如下结构（你已有雏形，v0.1 进一步明确边界）：

```
capsule/
├── capsule.yaml                 # 项目级配置（角色/工作流/策略开关）
├── CAPSULE.md                   # 上下文注入文档（你已完成）
├── capsule_lead.md              # 架构师技术指导（你已落库）
│
├── contracts/
│   ├── schemas/                 # 元契约：JSON Schema（必须受边界保护）
│   ├── boundaries/              # Boundary 合同实例（全局生效）
│   └── instances/               # 运行时具体合同（按模块划分）
│
├── roles/                       # Role 合同（YAML）
├── workflows/                   # 工作流定义（YAML）
├── prompts/                     # prompt 模板（可换，可多实现）
│
├── state/
│   ├── PROJECT_STATE.json       # 单一真相源（核心）
│   ├── runs/                    # 每次运行的证据链（建议按 run_id 目录）
│   └── audit/                   # 边界违规、关键审计（追加式）
│
└── core/
    ├── cli.py
    ├── registry.py              # Contract Registry（必须）
    ├── validator.py             # Gate + 校验器（必须）
    ├── state_manager.py         # 状态机与持久化（必须）
    ├── orchestrator.py          # Lean Orchestrator（必须，先串行）
    ├── executor/
    │   ├── port.py              # Executor Port（必须）
    │   └── codex_cli.py         # Codex 适配器（必须）
    └── human_loop.py            # Human gate（必须）
```

**边界保护建议（立即落地）**
- `contracts/schemas/**`、`capsule.yaml`、`state/**`、`.env*` 属于 Sacred Files（L3 触发即 halt）

---

## 3. 元契约（Meta-Contract）规范（v0.1 必须实现，字段级详尽）

> 这是“牢笼的钢筋”。先把 Envelope、Ref、生命周期与扩展口定死，后续新增契约类型才不乱。

### 3.1 Contract Envelope（统一信封）

所有契约文件统一为：

```yaml
contract:
  meta: ...
  spec: ...
  extensions: {}   # 可选，但这是唯一扩展口
```

#### 3.1.1 `meta`（核心严格，additionalProperties=false）
- `type`：枚举  
  `role | task | interface | behavior | boundary | gate_report | evidence | human_decision`
- `id`：分层字符串（方案 A）  
  格式建议：`<type>.<domain>.<name>`（例如 `interface.user_auth.login` 也可接受）
- `version`：SemVer 字符串，强制 `^\d+\.\d+\.\d+$`
- `status`：枚举  
  `draft | pending_review | active | amending | deprecated`
- `created_by`：枚举（最小集合）  
  `role.architect | role.qa | role.coder_backend | role.coder_frontend | human | system`
- `created_at`：ISO 8601 时间戳字符串（建议强制存在）
- `dependencies`：`ContractRef[]`（允许空数组）
- `validation`：验证声明（见 3.3）
- `on_failure`：失败策略（见 3.4)

> 说明：你要“商用扩展性但简约”。这套 meta 字段在长期不会后悔：它们是可回放与可治理的最小集合。

#### 3.1.2 `extensions`（外围宽松，允许开放）
- `extensions` 允许 `additionalProperties=true`
- 但建议所有扩展必须命名空间化：`extensions.<vendor_or_team>.<feature>`，避免污染。

### 3.2 ContractRef（引用规范：允许范围，但运行前必须锁定）

```yaml
ref:
  id: "interface.user_auth"
  version: "1.x"     # 允许范围表达，仅用于草案/配置
  # 或
  version: "1.0.3"   # 锁定后的精确版本
```

**硬规则（由系统在 INPUT GATE 执行）：**
- 若某 Task 将进入执行态（或从 `pending_review`→`active`），其所有 dependencies 必须被解析为精确版本，并写入：
  - `PROJECT_STATE.locked_refs`
  - 本次 `GateReport.resolved_refs`
  - 本次 `ExecutionEvidence.contract_snapshot`

这条规则保证“扩展性（写 1.x）”与“确定性（跑时 1.0.3）”同时成立。

### 3.3 `validation`（契约自描述验收方式）

v0.1 定义一个足够简约但可扩展的结构：

```yaml
validation:
  schema: "contracts/schemas/task.contract.schema.json"   # 必填：本契约应使用哪个 schema
  checks:                                                  # 可选：附加确定性检查声明
    - kind: "script"
      id: "check.created_by_policy"
    - kind: "command"
      run: "pytest -q"
```

**设计意图：**
- `schema` 使 L0 校验自描述（减少硬编码映射）
- `checks` 为未来扩展（如自定义脚本、命令、门禁策略）预留

### 3.4 `on_failure`（失败策略）

```yaml
on_failure:
  action: "retry" | "halt" | "human_escalation"
  max_retries: 3            # 对 retry 有意义
  severity: "low"|"mid"|"high"   # 用于人类出口优先级排序
```

---

## 4. 五类原子契约（v0.1：结构定死，字段先做“最小充分”）

> 这里要“全面但不臃肿”：先把必须可验收的字段落地，后续再加更细粒度。

### 4.1 Role Contract（必须支持）
`spec` 最小字段建议：
- `display_name`
- `capabilities`
  - `read: [glob]`
  - `write: [glob]`
  - `exec: [command_prefix]`（建议前缀匹配）
- `prohibitions`
  - `write: [glob]`
  - `exec: [command_prefix]`
- `retry_policy`（可覆盖 meta.on_failure）
- `confidence_threshold`（触发 human gate）

**硬规则：默认拒绝**
- 任何写入不在 `capabilities.write` → L3 直接 halt（越界）
- 任何命令不在 `capabilities.exec` → L3 直接 halt

### 4.2 Task Contract（必须支持）
`spec` 最小字段建议：
- `assigned_to`（role id）
- `scope`
  - `include`（允许修改/关注）
  - `exclude`（禁止触达）
  - `create_allowed`（允许新增目录）
- `acceptance`
  - `behavior_ref`（Behavior Contract ref）
  - `interface_refs`（可选，用于联动）
  - `max_new_files`
- `token_budget`（断路器之一：可先记录不强 enforcement）

### 4.3 Interface Contract（必须支持）
`spec` 最小字段建议（先满足“前后端宪法”）：
- `endpoints[]`
  - `id, path, method`
  - `request.schema`（JSON schema 子集）
  - `response.*.schema`
- `binding`
  - `producer`（role）
  - `consumers[]`
- `change_policy`
  - `requires_approval[]`（包含 human/architect）

### 4.4 Behavior Contract（必须支持）
`spec` 最小字段建议：
- `test_suite`
  - `runner`（pytest/jest 等）
  - `entry`（测试入口）
  - `command`（可选：直接给完整命令，v0.1 建议必填，减少推断）
- `mandatory_cases[]`（可选，但建议有）
- `coverage`（v0.1 可选）

**硬规则：created_by 合规**
- Behavior 必须 `created_by in {role.qa, human}`，否则 L1 打回（可重试，不视为安全越界）。

### 4.5 Boundary Contract（必须支持，且立即启用）
`spec` 最小字段建议：
- `sacred_files[]`（glob）
- `rules[]`
  - `id`
  - `check_method: git_diff_scan | command_audit`
  - `violation_action: immediate_halt`
- `on_violation`
  - `notify: human`
  - `log_path`

**硬规则：L3 触发即终止**
- Boundary 违规 = 安全越界，不允许重试。

---

## 5. 三类“事件契约”（v0.1 建议立即实现，保证出口与证据链）

> 你可以把它们看作“运行时合同”，它们让 Capsule 成为工程系统，而不是脚本拼装。

### 5.1 GateReport（必须）
最小字段（建议在 `spec`）：
- `gate_id`：例如 `INPUT_GATE` / `OUTPUT_GATE`
- `level`：`0|1|2|3`
- `result`：`pass|fail|halt|human`
- `failed_contract_ref`（可选）
- `diagnostics`：结构化诊断对象（短摘要 + 可定位信息）
- `resolved_refs[]`：本次锁定后的精确引用列表（关键）
- `timestamp`

### 5.2 ExecutionEvidence（必须）
最小字段（建议在 `spec`）：
- `run_id`（全局唯一）
- `role_id`
- `task_ref`（精确版本）
- `contract_snapshot`
  - `refs[]`（此次执行涉及的所有精确 ref）
  - （可选）`content_hashes`（后续可升级）
- `changes`
  - `modified_files[]`
  - `diff_stat`（行数统计）
- `commands`
  - `ran[]`（命令+退出码+耗时）
- `tests`
  - `ran[]`（命令/runner+摘要）
  - `summary`（pass/fail）
- `self_report`
  - `confidence`（0~1）
  - `risks[]`
  - `notes`（短文本，禁止长日志）

### 5.3 HumanDecision（必须）
最小字段（建议在 `spec`）：
- `decision_id`
- `trigger`（为何进入 human gate：retry_exceeded/boundary_violation/review_required 等）
- `context_refs[]`（涉及哪些契约/证据）
- `options_presented[]`（系统给了哪些选项）
- `selected_option`
- `rationale`（简短）
- `actions`
  - `resume|abort|amend_contract|pause_task` 等
- `timestamp`
- `made_by`（human）

---

## 6. PROJECT_STATE（v0.1：必须稳定，可恢复、可追溯）

建议 state 至少包含：

- `project_id`
- `current_workflow_id`
- `current_node_id`
- `current_task_ref`（精确版本）
- `phase` / `status`
- `locked_refs[]`（全局/本轮锁定 ref）
- `run_history[]`
  - `{run_id, task_ref, role_id, last_gate_report_ref, evidence_ref, status}`
- `checkpoints[]`（断点续跑指针）
- `human_queue[]`（待人类决策的事项列表）

**硬要求：**
- 任何一次执行（无论成功失败）都必须落一个 run 记录与 evidence（或 error evidence）
- 任何一次 gate 结论必须落 GateReport 并被 state 引用

---

## 7. Gate System（v0.1 需要详尽实现，流程级明确）

### 7.1 INPUT GATE（执行前）
检查顺序（建议固定，便于诊断一致）：
1) 契约加载与 L0（Task/Role/Boundary/Behavior/Interface）  
2) 依赖存在性与引用解析  
3) 引用锁定（把范围 ref 解析为精确 ref）  
4) scope 与 role 权限一致性（include/exclude/create_allowed vs role.write）  
5) 生成 INPUT GateReport（pass/fail/human）

失败策略：
- L0/L1/L2 类失败：打回（retry 或 human escalation，按 on_failure）
- 若发现 scope 明显越界且无法修复：human escalation（不是 halt；halt 留给 L3）

### 7.2 OUTPUT GATE（执行后）
顺序：
- L0：Evidence/GateReport 的 schema 校验（必须快速失败）
- L1：一致性校验（evidence 中的 task_ref 必须等于 state 当前任务；refs 必须是精确版本；created_by 合规；等）
- L2：行为验证（按 Behavior Contract command 执行）
- L3：边界审计（git diff + command audit）

结果：
- L0-L2 fail：产生 Rejection（可重试/升级）
- L3 hit：立即 halt + HumanDecision（强制）入口

---

## 8. Orchestrator（v0.1：Lean 串行实现，LangGraph 作为可选适配器后置）

### 8.1 工作流定义（YAML）
v0.1 仅需支持：
- 节点按序执行
- 失败回边（打回重试）
- 断路器到 human gate

建议工作流节点类型：
- `produce_contracts`（architect）
- `produce_behavior`（qa）
- `implement`（coder_backend）
- `review`（architect + 人类可选）

### 8.2 编排内核接口（对执行器/门禁器解耦）
编排只做：
- 读取 state
- 决定下一节点
- 形成 ExecutionRequest（交给 executor）
- 接收 evidence + gate_report，更新 state
- 若触发 human gate：挂起等待 HumanDecision

---

## 9. CLI（v0.1 只需最小指令集，避免做成平台）

建议 v0.1 CLI 最小集合：
- `capsule validate`：校验 contracts 与 state（离线）
- `capsule run`：从 state 当前节点开始跑到下一个 human gate 或结束
- `capsule resume`：从 checkpoint/run_id 恢复
- `capsule review`：输出结构化摘要（给人类看）
- `capsule decide --option ...`：写入 HumanDecision 并继续

> v0.1 暂不做复杂交互 UI；先用结构化 JSON/YAML 输出即可。

---

# 10. v0.1 “马上要实现”的详尽 DoD（给 coder 的第一阶段任务边界）

为了保证你说的“这一版局部详尽”，这里明确 v0.1 第一阶段必须交付的“硬脊柱闭环”，且不要求从最小 demo 起步——可以直接以“用户认证模块（user_auth）”作为目标，但实现顺序仍按内核依赖推进。

## 10.1 第一阶段必须完成（不可裁剪）
1) Contract Envelope + Ref + 基础五类 schema（字段至少覆盖本草案最小字段）
2) Contract Registry（加载、索引、按 ref 取精确版本）
3) Validator：
   - L0 schema 校验
   - 引用解析与锁定（范围→精确）
   - created_by 合规（Behavior）
4) State Manager（最小 PROJECT_STATE + run_history + checkpoint）
5) GateReport / ExecutionEvidence / HumanDecision 的 schema 与落盘
6) Boundary L3（git diff 扫描 sacred_files + 越权写）
7) Executor Port + Codex CLI Adapter（输出 evidence；失败也要 evidence）
8) Lean Orchestrator（串行 workflow，支持重试、断路器、人类挂起）

## 10.2 第一阶段验收标准（可操作）
- 能从 `workflow.standard` 跑到：
  - architect 产出 contracts（哪怕先由人类手写 contracts 也可，但系统必须能读/验）
  - qa 产出 behavior（或人类提供）
  - coder_backend 执行一次实现并产出 evidence
  - gate 能跑完 L0/L1/L2/L3 并给出一致的 GateReport
- 任意触达 sacred_files → 必须立即 halt 并进入 human gate
- evidence 缺字段/不合 schema → 必须在 L0 被打回
- 人类通过 `capsule decide` 写回 decision 后能 `resume` 继续跑

---

# 11. 本草案的“已定”与“待你确认”的极少数点（便于你提修改）

为避免你审阅成本过高，我把真正需要你拍板/提意见的点压缩到 4 项：

1) **范围引用的解析策略**：  
   我已定为“配置可写 1.x，但执行前锁定精确版本”。你是否接受？  
2) **Behavior 的执行命令**：  
   v0.1 是否强制 `behavior.spec.test_suite.command` 必填（推荐），以减少推断？  
3) **Boundary 的 L3 严格度**：  
   我已定为 L3 命中即 halt。你是否希望对某些规则降级为 human_escalation（不 halt）？（我倾向不降级）  
4) **Evidence 的最小字段集**：  
   你是否希望加入 `content_hashes`（增强审计，但实现复杂度略升）？我建议 v0.1 先不强制，只预留字段。

---

## 你下一步给我反馈的方式（建议）
你可以直接在这四点上逐条批注“同意/修改为…/补充…”。我收到后，会输出：

1) **Capsule v0.1 设计定稿版（第二版）**：将上述草案固化成“不可变规范 + 立即实现细则”。  
2) **给 coder 的技术指导（Implementation Guide v0.1）**：按模块拆解任务、给出数据文件样例（不写代码但给样例 JSON/YAML），并附上验收清单。

你希望我们第一阶段直接以哪个真实模块作为目标来驱动（不是 demo，而是可用功能）？
- A) `user_auth`（注册/登录/JWT）  
- B) `crud`（通用资源增删改查）  
- C) 你已有更具体的业务模块名称与范围（你指定）

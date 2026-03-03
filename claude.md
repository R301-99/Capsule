
# Capsule 第一版设计 — 讨论稿

---

## 一、第一版的边界在哪

先对齐范围。我把系统拆成 **六个能力块**，标注哪些在第一版做、做到什么程度：

| 能力块 | 第一版 | 说明 |
|--------|--------|------|
| **A. 契约体系** | ✅ 全做 | 五种 Model 已设计完，全部落地。这是地基，不分期。 |
| **B. 验证流水线** | ✅ 全做 | L0-L3 四级全实现。这是系统心脏，没有它一切都是软的。 |
| **C. 执行层** | ✅ 全做 | Executor Protocol + CodexExecutor。不大，但必须从第一天就抽象好。 |
| **D. 单角色执行闭环** | ✅ 详细做 | Coder 接收手写契约 → 执行 → 验证 → 打回/通过。这是第一版的核心场景。 |
| **E. 多角色编排** | 🔲 架构预留 | 定义好节点接口和状态结构，但不实际接入 pydantic-graph。第一版用线性脚本驱动。 |
| **F. 智能角色（Architect/QA Agent）** | 🔲 架构预留 | 定义好 Agent 工厂接口，但第一版中契约由人类手写，不由 Agent 生成。 |

**第一版的一句话定义：**

> 人类手写契约 → Capsule 调度 Coder Agent 执行 → 自动四级验证 → 失败自动打回重试 → 超限断路器通知人类 → 通过则持久化结果。

为什么不从 Architect Agent 开始？因为 **契约质量决定系统质量**。第一版让人类写契约，能保证输入端是干净的，从而纯粹地测试"验证-打回-执行"闭环。等闭环可靠了，再让 Agent 接管契约生成——那时候我们对"好的契约长什么样"已经有了第一手经验。

---

## 二、全局架构图（宽泛层，标注第一版实现范围）

```
┌─────────────────────────────────────────────────────────────────┐
│   Layer 5: CLI / Human Interface                                │
│   ┌───────────────────┐  ┌──────────────┐  ┌───────────────┐   │
│   │ capsule run ✅     │  │ capsule      │  │ capsule       │   │
│   │ capsule status ✅  │  │ review  🔲   │  │ init    🔲    │   │
│   └───────────────────┘  └──────────────┘  └───────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│   Layer 4: Agent / Semantic Layer                               │
│   ┌──────────────┐  ┌──────────┐  ┌──────────────────────┐     │
│   │ Architect 🔲  │  │ QA  🔲   │  │ Prompt Builder  ✅   │     │
│   └──────────────┘  └──────────┘  └──────────────────────┘     │
├─────────────────────────────────────────────────────────────────┤
│   Layer 3: Orchestration                                        │
│   ┌───────────────────────────┐  ┌───────────────────────┐     │
│   │ pydantic-graph  🔲        │  │ Linear Runner  ✅      │     │
│   │ (接口预留)                │  │ (第一版实际驱动器)     │     │
│   └───────────────────────────┘  └───────────────────────┘     │
├─────────────────────────────────────────────────────────────────┤
│   Layer 2: Contract + Validation                  ← 全部 ✅     │
│   ┌──────────────────┐  ┌──────────────────────────────────┐   │
│   │ 5 Contract Models │  │ Validation Pipeline (L0-L3)     │   │
│   │ Contract I/O      │  │ Rejection Protocol              │   │
│   │ Contract Registry │  │ Circuit Breaker                 │   │
│   └──────────────────┘  └──────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────┤
│   Layer 1: State + Persistence                                  │
│   ┌───────────────────────┐  ┌───────────────────────────┐     │
│   │ PROJECT_STATE.json ✅  │  │ FileStatePersistence 🔲   │     │
│   │ (简化版)               │  │ (pydantic-graph 配套)     │     │
│   └───────────────────────┘  └───────────────────────────┘     │
├─────────────────────────────────────────────────────────────────┤
│   Layer 0: Execution                                ← 全部 ✅   │
│   ┌────────────────────┐  ┌───────────────────────────────┐    │
│   │ Executor Protocol   │  │ CodexExecutor                 │    │
│   └────────────────────┘  └───────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、第一版详细设计

以下是**要实现的部分**，尽可能详尽。

### 3.1 核心执行流程（Linear Runner）

这是第一版的主干。不用状态机，就是一个 async 函数：

```
输入：
  task.contract.yaml        （人类手写）
  interface.contract.yaml   （人类手写，如有）
  behavior.contract.yaml    （人类手写，如有）
  roles/coder_backend.role.yaml （人类手写）
  contracts/boundaries/global.boundary.yaml （人类手写）

流程：

  ┌─ PHASE 1: LOAD & INPUT GATE ──────────────────────────┐
  │                                                        │
  │  1. 加载所有契约 YAML → model_validate()（L0 前置）     │
  │  2. 检查 preconditions：引用的契约是否都存在且 active    │
  │  3. 检查 assigned_to 角色契约是否存在                    │
  │  4. 任一失败 → 报错退出（这是配置错误，不是 Agent 错误）  │
  │                                                        │
  └────────────────────────────────────────────────────────┘
                          │ 通过
                          ▼
  ┌─ PHASE 2: PROMPT ASSEMBLY ────────────────────────────┐
  │                                                        │
  │  组装完整 prompt：                                      │
  │    · 角色身份 + 权限边界（from RoleContract）            │
  │    · 项目约定（from PROJECT_STATE.json）                │
  │    · 接口契约全文（from InterfaceContract）             │
  │    · 任务描述 + 验收标准 + 禁止行为（from TaskContract）│
  │    · 必须通过的测试清单（from BehaviorContract）        │
  │    · 打回历史（如果是重试轮次）                         │
  │                                                        │
  └────────────────────────────────────────────────────────┘
                          │
                          ▼
  ┌─ PHASE 3: EXECUTE ────────────────────────────────────┐
  │                                                        │
  │  1. Git snapshot（记录执行前状态）                      │
  │  2. CodexExecutor.execute(prompt, working_dir, ...)    │
  │  3. 收集 ExecutionResult                               │
  │  4. 如果 exit_code != 0 → 视为执行失败，进入打回       │
  │                                                        │
  └────────────────────────────────────────────────────────┘
                          │
                          ▼
  ┌─ PHASE 4: OUTPUT GATE ────────────────────────────────┐
  │                                                        │
  │  L0: 格式校验（Agent 产出结构）                         │
  │    │ 失败 → reject                                     │
  │  L1: 结构一致性                                        │
  │    │ · modified_files 都在 scope.include 内？           │
  │    │ · 没触碰 scope.exclude？                          │
  │    │ · 没违反 forbidden_actions？                       │
  │    │ · 新文件数 <= max_new_files？                     │
  │    │ 失败 → reject                                     │
  │  L2: 行为验证                                          │
  │    │ · 运行 behavior_contract.test_suite               │
  │    │ · 逐条检查 mandatory_cases                        │
  │    │ · 检查覆盖率                                      │
  │    │ 失败 → reject                                     │
  │  L3: 边界审计                                          │
  │    │ · Git diff vs sacred_files                        │
  │    │ · Git diff vs prohibited_paths                    │
  │    │ 失败 → HALT                                       │
  │                                                        │
  └────────────────────────────────────────────────────────┘
                          │
                ┌─────────┼─────────┐
                │         │         │
              reject    halt     全部通过
                │         │         │
                ▼         ▼         ▼
  ┌─ PHASE 5a ──┐ ┌─ 5b ────┐ ┌─ 5c ──────────────────┐
  │ 打回协议     │ │ 立即终止 │ │ 成功                   │
  │              │ │ 通知人类 │ │ · 更新 PROJECT_STATE   │
  │ retry++      │ │ 写审计  │ │ · Git commit           │
  │ 生成         │ │ 日志    │ │ · 打印摘要             │
  │ Rejection    │ │ 退出    │ │ · 退出                 │
  │ Report       │ └────────┘ └────────────────────────┘
  │              │
  │ retry < max? │
  │  yes → 回到  │
  │  PHASE 2     │
  │  (带打回历史)│
  │              │
  │  no → 断路器 │
  │  打印诊断    │
  │  退出        │
  └──────────────┘
```

### 3.2 契约 I/O 设计

契约在磁盘上是 YAML，在运行时是 Pydantic Model 实例。需要一个薄的 I/O 层。

**设计要点：**

```python
"""capsule/contracts/io.py"""

import yaml
from pathlib import Path
from .models import parse_contract  # 通用入口


def load_contract(path: str | Path):
    """
    加载一份契约 YAML，返回对应的 Pydantic Model 实例。
    失败抛出 ValidationError 或 FileNotFoundError。
    """
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return parse_contract(raw)


def save_contract(contract, path: str | Path):
    """
    将契约 Model 实例序列化为 YAML 并写入文件。
    用于 Agent 生成契约后的持久化（第二版场景）。
    第一版中主要用于测试。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = contract.model_dump(mode="json")  # datetime → string
    path.write_text(
        yaml.dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def load_all_contracts(directory: str | Path) -> list:
    """递归加载目录下所有 .yaml/.yml 契约文件。"""
    directory = Path(directory)
    contracts = []
    for p in directory.rglob("*.yaml"):
        try:
            contracts.append(load_contract(p))
        except Exception:
            # 非契约 YAML 文件（如 workflow 定义），静默跳过
            # 正式版应该有更好的区分策略，第一版先宽容
            pass
    return contracts
```

**YAML 约定：**

- 每个契约文件必须有 `type` 字段作为第一级键
- 文件命名：`{name}.{type}.yaml`，如 `coder_backend.role.yaml`、`user_auth.interface.yaml`
- 目录位置遵循 capsule_lead.md 中定义的目录结构

### 3.3 验证流水线详细设计

```python
"""capsule/validation/pipeline.py"""

# ═══════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════

@dataclass
class GateResult:
    level: int                  # 0, 1, 2, 3
    passed: bool
    details: list[CheckDetail]  # 每条检查的结果


@dataclass
class CheckDetail:
    check_name: str             # 如 "scope_include_check"
    passed: bool
    expected: str               # 人类可读：期望什么
    actual: str                 # 人类可读：实际是什么
    hint: str                   # 给 Agent 的修复建议


@dataclass
class ValidationResult:
    passed: bool
    halted: bool                # L3 触发 = True
    failed_level: int | None    # 第一个失败的层级
    gate_results: list[GateResult]  # 每层的详细结果

    def to_rejection_report(self, task_id: str, retry_count: int) -> dict:
        """转为可注入 prompt 的打回报告"""
        ...


# ═══════════════════════════════════════════════════════
# L0: 格式校验
# ═══════════════════════════════════════════════════════

"""capsule/validation/l0_structural.py"""

# 这一层在第一版中有两个触发点：
#
# 触发点 A：加载契约 YAML 时（INPUT GATE）
#   → load_contract() 内部的 model_validate() 已经做了
#   → 如果契约 YAML 格式不对，在流程启动前就会报错
#   → 这是"配置错误"，不进入打回循环，直接报错退出
#
# 触发点 B：Agent 产出校验（OUTPUT GATE）
#   → Agent 通过 Codex CLI 执行后，我们需要检查它的产出
#   → 但 Codex CLI 的产出不是"契约"，而是代码文件 + 执行结果
#   → 所以 OUTPUT GATE 的 L0 校验的是 ExecutionResult 的结构
#   → 以及 Agent 产出的文件是否符合预期
#
# 具体检查项：
#   · CodexExecutor 返回的 ExecutionResult 是否完整
#   · exit_code 是否为 0
#   · modified_files 列表是否非空（Agent 确实做了什么）


# ═══════════════════════════════════════════════════════
# L1: 结构一致性
# ═══════════════════════════════════════════════════════

"""capsule/validation/l1_consistency.py"""

# 输入：ExecutionResult + TaskContract + RoleContract
# 检查项（每条独立，全部执行，汇总结果）：

# CHECK 1: scope_include
#   modified_files 中的每个文件，是否匹配 task.scope.include 的某个 glob？
#   不匹配 → fail, hint: "文件 X 不在任务允许范围内"

# CHECK 2: scope_exclude
#   modified_files 中是否有文件匹配 task.scope.exclude？
#   匹配 → fail, hint: "文件 X 被明确排除"

# CHECK 3: role_write_permission
#   modified_files 中的每个文件，是否匹配 role.file_permissions.write 的某个 glob？
#   不匹配 → fail, hint: "角色无权写入文件 X"

# CHECK 4: max_new_files
#   新创建的文件数 <= task.acceptance.max_new_files？
#   git diff --name-only --diff-filter=A 获取新增文件列表

# CHECK 5: prohibited_paths
#   modified_files 中是否有文件匹配 role.prohibited_paths？
#   匹配 → fail（注意这和 L3 的区别：L1 是角色级禁区，L3 是全局圣域）

# 工具函数需求：
#   fnmatch_any(filepath, glob_list) → bool
#   git_modified_files(repo_path) → list[str]
#   git_new_files(repo_path) → list[str]


# ═══════════════════════════════════════════════════════
# L2: 行为验证
# ═══════════════════════════════════════════════════════

"""capsule/validation/l2_behavioral.py"""

# 前提：TaskContract 关联了一个 BehaviorContract
# 如果没有关联（behavior_contract_ref 为空），L2 跳过，直接 pass

# 步骤：
#   1. 加载 BehaviorContract
#   2. 如果有 test_suite.setup_cmd，先执行它
#   3. 执行 test_suite.runner + test_suite.entry
#      如: subprocess.run(["pytest", "tests/backend/test_user_auth.py", "-v", "--tb=short"])
#   4. 解析退出码：0 = 全部通过，非 0 = 有失败
#   5. 解析 pytest 输出，匹配 mandatory_cases 的通过情况
#      （简化版：第一版只看退出码 + stdout 中的 PASSED/FAILED 关键词）
#      （正式版可用 pytest --json-report 或 pytest-json-report 插件）
#   6. 覆盖率检查（如需要）：
#      pytest --cov=src/backend --cov-report=json
#      解析 coverage.json 中的 totals.percent_covered

# 返回：
#   每个 mandatory_case 的通过/失败状态
#   覆盖率数值
#   原始 stdout/stderr（截断到合理长度，用于注入 prompt）


# ═══════════════════════════════════════════════════════
# L3: 边界审计
# ═══════════════════════════════════════════════════════

"""capsule/validation/l3_boundary.py"""

# 这是最严厉的一层。失败 = HALT，不是 reject。

# 输入：modified_files + 所有 active 的 BoundaryContract
# 检查项：

# CHECK 1: sacred_files
#   对每个 BoundaryContract 的 sacred_files 列表：
#   modified_files 中是否有文件匹配任何 sacred glob？
#   匹配 → HALT

# CHECK 2: audit_rules
#   逐条执行 audit_rules：
#   · check_method = "git_diff_scan"：
#     扫描 diff 内容，检查是否有可疑操作（第一版只做文件级检查，不做内容级）
#   · 未来可扩展其他 check_method

# HALT 处理：
#   写入 state/audit/boundary_violations.log（追加，不可覆盖）
#   日志格式：
#   {timestamp} | HALT | {boundary_contract_id} | {violated_rule} | {file} | {detail}

# 关键实现细节：
#   boundary_violations.log 必须是 append-only
#   即使进程被 kill，已写入的记录也不会丢失
#   使用 open(path, "a") 逐行写入，每行写完 flush
```

### 3.4 CodexExecutor 详细设计

```python
"""capsule/execution/codex_executor.py"""

# ═══════════════════════════════════════════════════════
# 调用方式
# ═══════════════════════════════════════════════════════

# 基础命令：
# codex exec \
#   --full-auto \
#   --sandbox workspace-write \
#   --json \
#   --cd {working_dir} \
#   "{prompt}"

# 关于 --json：
#   Codex CLI 的 --json 输出格式我们尚未完全确认。
#   第一版的策略：
#     1. 先跑一次裸 codex exec --json，记录实际输出结构
#     2. 在 CodexExecutor 中做宽松解析（try/except，记录 raw）
#     3. 核心依赖放在 git diff，不放在 --json 的特定字段
#
# 这是"观察对手"策略——先看 Codex 实际给我们什么，再决定怎么用。

# ═══════════════════════════════════════════════════════
# 执行流程
# ═══════════════════════════════════════════════════════

# Step 1: 执行前快照
#   git_snapshot_before = git_get_head_hash(working_dir)
#   确保工作区干净（git status --porcelain 为空）
#   如果不干净 → 报错：工作区有未提交变更

# Step 2: 调用 Codex CLI
#   使用 asyncio.create_subprocess_exec
#   捕获 stdout, stderr
#   设置 timeout（来自 TaskContract.token_budget 换算或固定值）

# Step 3: 解析输出
#   尝试 json.loads(stdout) → 存入 raw_output
#   如果不是 JSON → raw_output = {"raw_stdout": stdout}

# Step 4: 收集变更
#   modified_files = git_diff_names(working_dir, git_snapshot_before)
#   new_files = git_diff_names(working_dir, git_snapshot_before, filter="A")
#   deleted_files = git_diff_names(working_dir, git_snapshot_before, filter="D")

# Step 5: 组装 ExecutionResult
#   success = (exit_code == 0)
#   返回 ExecutionResult(...)

# ═══════════════════════════════════════════════════════
# Git 工具函数
# ═══════════════════════════════════════════════════════

# 这些函数独立出来，因为 L1 和 L3 验证也需要用。
# 建议放在 capsule/utils/git.py

# git_get_head_hash(repo_path) → str
# git_is_clean(repo_path) → bool
# git_diff_names(repo_path, from_hash, filter=None) → list[str]
# git_diff_content(repo_path, from_hash) → str  （L3 审计可能需要）
# git_commit(repo_path, message) → str  （成功后自动提交）
# git_rollback(repo_path, to_hash) → None  （HALT 时回滚）
```

**关键设计决策：git rollback on HALT**

当 L3 边界审计发现违规时，Agent 对文件的修改必须被回滚。因为违规意味着不可信——我们无法确定 Agent 还偷偷做了什么其他事。

```
L3 HALT 时：
  1. git_rollback(to=snapshot_before)  ← 所有 Agent 变更被撤销
  2. 写审计日志
  3. 通知人类
```

### 3.5 Prompt Builder 详细设计

```python
"""capsule/agents/prompt_builder.py"""

# ═══════════════════════════════════════════════════════
# Prompt 结构（固定分区，每区有明确职责）
# ═══════════════════════════════════════════════════════

# Section 1: ROLE IDENTITY
# ────────────────────────
# 告诉 Agent 它是谁。
# 来源：RoleContract
# 内容：display_name, description
# 这一段要短，但要明确。

# Section 2: HARD CONSTRAINTS（硬约束区）
# ────────────────────────
# 这是整个 prompt 中最重要的部分。
# 用醒目的格式标注，不与其他内容混淆。
# 来源：RoleContract + TaskContract + BoundaryContract
# 内容：
#   · 可写路径（白名单）
#   · 禁止路径（黑名单）
#   · 禁止行为
#   · 不可修改的文件
# 格式建议：
#   用 ``` 围栏 + ⛔ 标记，让 LLM 明确知道这不是建议

# Section 3: PROJECT CONTEXT（项目上下文）
# ────────────────────────
# 来源：PROJECT_STATE.json → global_conventions
# 内容：技术栈、命名规范、API 前缀等
# 这些是 Agent 需要遵守的"软约定"（不被自动验证，但期望遵守）

# Section 4: INTERFACE CONTRACT（接口契约原文）
# ────────────────────────
# 来源：InterfaceContract（YAML 原文直接注入）
# 这里不做任何改写。原文注入，让 Agent 自己读懂。
# 理由：改写会丢失精度。契约本身就是 Agent 可读的格式。

# Section 5: TASK SPECIFICATION（任务规格）
# ────────────────────────
# 来源：TaskContract
# 内容：
#   · task description
#   · acceptance_criteria
#   · scope（哪些文件可以动）

# Section 6: TEST SPECIFICATION（测试规格）
# ────────────────────────
# 来源：BehaviorContract
# 内容：mandatory_cases 列表，每条的 id + description
# 明确告诉 Agent："你的代码必须让以下测试通过"

# Section 7: REJECTION HISTORY（打回历史，仅重试时存在）
# ────────────────────────
# 来源：RejectionReport 列表
# 内容：每次打回的失败层级、失败详情、修复建议
# 格式：按时间顺序排列，最新的在最前面
# 这一段的目的是让 Agent 精确知道上次哪里错了

# Section 8: OUTPUT INSTRUCTION（输出格式指令）
# ────────────────────────
# 告诉 Agent 完成后需要做什么：
#   · 确保所有修改的文件已保存
#   · 不要修改上述禁止的文件
#   · 任务结束后不要做额外的事情

# ═══════════════════════════════════════════════════════
# 关于 Prompt 模板 vs 代码生成
# ═══════════════════════════════════════════════════════

# 第一版使用代码拼接（f-string / str.join）
# 不使用 Jinja2 等模板引擎
# 理由：
#   · Prompt 结构目前还不稳定，我们需要快速迭代
#   · 代码拼接更容易调试（能 print 出完整 prompt 看效果）
#   · 等 prompt 结构稳定后，再考虑提取为模板文件

# 但有一个关键设计：
# build_prompt() 返回的 prompt 必须同时写入日志文件
# 路径：state/prompts/{task_id}_attempt_{n}.md
# 这样人类可以审查每次发给 Agent 的完整 prompt
# 这是调试 Agent 行为最重要的工具
```

### 3.6 打回协议详细设计

```python
"""capsule/validation/rejection.py"""

@dataclass
class RejectionReport:
    rejection_id: str           # "REJ-{YYYYMMDD}-{seq}"
    task_id: str
    target_role: str            # 角色 ID
    retry_count: int            # 当前第几次重试
    max_retries: int
    timestamp: str              # ISO8601

    failed_level: int           # 0, 1, 2
    failed_checks: list[CheckDetail]  # 所有失败的检查项

    def to_prompt_section(self) -> str:
        """
        将打回报告格式化为可注入 prompt 的文本段。

        格式示例：
        ─────────────────────────────────
        ⚠️ PREVIOUS ATTEMPT FAILED (attempt 2/3)

        Failed checks:
        1. [L1] scope_include_check: FAILED
           Expected: 修改的文件应在 src/backend/** 范围内
           Actual:   修改了 src/frontend/utils.ts
           Fix hint: 不要修改前端文件，你的任务只涉及后端

        2. [L2] test_TC001: FAILED
           Expected: 正确凭证返回 JWT token
           Actual:   测试抛出 KeyError: 'token'
           Fix hint: 确保返回的 JSON 包含 'token' 字段
           Trace:    AssertionError at test_user_auth.py:23
        ─────────────────────────────────

        关键设计：
          · hint 是验证层自动生成的，不是人写的
          · hint 的质量直接影响 Agent 的修复成功率
          · 第一版的 hint 可以简单直接
          · 后续可以引入 LLM 辅助生成更精准的 hint
        """
        ...
```

### 3.7 PROJECT_STATE.json 第一版设计

第一版简化。不需要完整的模块追踪，只需要：

```json
{
  "project_id": "string — 项目标识",
  "capsule_version": "0.1.0",

  "global_conventions": {
    "// 注释": "技术栈和命名约定，注入每次 prompt",
    "language": "python",
    "framework": "fastapi",
    "test_runner": "pytest",
    "api_prefix": "/api/v1"
  },

  "execution_history": [
    {
      "task_id": "task.user_auth.login_api",
      "role": "role.coder_backend",
      "attempts": 2,
      "final_result": "passed",
      "timestamp": "2026-03-03T12:00:00Z"
    }
  ]
}
```

`execution_history` 是追加式的。每次任务完成（无论成功或断路器终止）都追加一条记录。

### 3.8 CLI 设计（第一版）

```
capsule run <task_contract_path>
  [--project-dir PATH]       默认当前目录
  [--conventions PATH]       PROJECT_STATE.json 路径
  [--dry-run]                只生成 prompt，不执行
  [--verbose]                打印完整验证日志

capsule validate <contract_path>
  验证一份契约文件是否合法（纯 L0 检查）
  用于人类手写契约后的自检

capsule status
  打印当前项目状态和执行历史
```

`capsule run` 是主命令。它做的事情就是 3.1 中的完整流程。

`--dry-run` 很重要：它让你看到完整的 prompt 输出，但不实际调用 Codex CLI。这是调试 prompt 的核心工具。

---

## 四、架构预留点（第一版不实现，但接口已定义）

### 4.1 Orchestrator 接口预留

```python
"""capsule/orchestration/protocol.py"""

class Orchestrator(Protocol):
    """编排器抽象。第一版用 LinearRunner，第二版换 GraphOrchestrator。"""

    async def run(
        self,
        task_contract: TaskContract,
        context: dict,
    ) -> OrchestratorResult:
        ...
```

第一版的 `LinearRunner` 实现这个接口。第二版的 `GraphOrchestrator`（基于 pydantic-graph）也实现这个接口。上层 CLI 代码不需要改。

### 4.2 Agent 工厂接口预留

```python
"""capsule/agents/protocol.py"""

class AgentRole(Protocol):
    """Agent 角色抽象。第一版只有 CoderRole，第二版加 ArchitectRole、QARole。"""

    role_contract: RoleContract

    async def execute(
        self,
        prompt: str,
        output_type: type,
    ) -> Any:
        ...
```

第一版的 `CoderRole` 内部调用 `CodexExecutor`。
第二版的 `ArchitectRole` 内部调用 `PydanticAI Agent`（不走 Codex，直接做 LLM 推理）。

---

## 五、需要你拍板的问题

### Q1：行为契约谁写？

第一版中，BehaviorContract（测试规格）也是人类手写。但问题是：**测试代码本身谁写？**

- **选项 A：** 人类手写测试代码，BehaviorContract 只是对这些测试的"注册"。Agent 只负责让已有测试通过。
- **选项 B：** BehaviorContract 只写测试规格（TC001: 描述），测试代码由 Coder Agent 一并实现。

我倾向 **A**。理由：第一版要测试的是"契约-验证-打回"闭环是否可靠。如果测试代码也让 Agent 写，失败原因就不清晰了——到底是实现代码有问题，还是测试代码有问题？先把测试代码作为"已知正确的锚点"。

### Q2：Git 操作策略

Agent 每次执行后的 git 策略：

- **选项 A：** 验证通过后自动 `git commit`，失败则 `git reset --hard`（完全回滚）
- **选项 B：** 验证通过后自动 `git commit`，失败则保留变更（不回滚），打回重试时 Agent 在上次修改基础上继续
- **选项 C：** 都不自动，由人类决定

我倾向 **B**。理由：Agent 第一次可能做对了 80%，只差一点。如果全部回滚，第二次要从零开始，很浪费。保留变更让 Agent 可以"增量修复"。但 L3 HALT 时必须回滚（因为不可信）。

### Q3：Codex CLI 不可用时的降级方案

如果开发者本机没有 Codex CLI（比如 API key 问题），第一版是否需要一个 Mock Executor？

我建议是：**需要。** 一个简单的 `MockExecutor`，读取预设目录里的文件作为 Agent "产出"。这样验证流水线可以独立测试，不依赖 Codex CLI 的可用性。

---

你看看整体范围和详细程度是否合适，以及三个问题怎么选。

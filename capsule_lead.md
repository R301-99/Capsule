
---

# Capsule — 完整技术指导文档

**文档版本：** v1.0
**目标读者：** 负责实现 Capsule MVP 的开发者
**前提假设：** 读者对 Python、Pydantic 有基础了解，但对 Capsule 项目、PydanticAI、Codex CLI 可能完全陌生

---

## 第一部分：项目全貌

### 1.1 Capsule 是什么

Capsule 是一个**契约驱动的 AI 软件工程编排系统**。它让技术型独立开发者能指挥一支角色明确、行为可验证的 AI 开发团队，完成中大型项目的持续迭代。

**一句话本质：** 用确定的工程系统（契约、状态机、验证流水线）包裹不确定的大模型（Agent）。

### 1.2 Capsule 不是什么

```
❌ 不是 AI 编辑器（不替代 Cursor / Copilot）
❌ 不是全自主 Agent（不追求无人值守）
❌ 不是通用 Agent 框架（不是 LangGraph / CrewAI 的竞品）
❌ 不是代码生成服务
```

### 1.3 Capsule 是什么

```
✅ 本地运行的 CLI 工具
✅ 多 Agent 编排和验证系统
✅ 以契约为骨架的开发流程管理器
✅ 个人开发者的"AI 开发团队操作系统"
✅ Codex CLI 等 AI 编码工具的调度层
```

### 1.4 核心问题域

发起人在实际使用多 Agent 开发时遭遇的系统性失败：

| 失败类型 | 表现 |
|----------|------|
| 契约不够硬 | Agent 不按规定格式开发，产出不可验收，擅自修改不该改的东西 |
| 上下文溢出 | 架构师 Agent 在复杂任务中丢失旧共识，早期规范被遗忘 |
| 根因 | 大模型是概率系统，用自然语言管理概率机器，结果必然失控 |

### 1.5 四条设计信条

这四条信条是所有设计决策的最终裁判。当你对实现方案犹豫时，用它们做判断：

1. **契约是门卫，不是建议。** 每一步的输入输出，必须通过形式化验证才能流转。没有"大概对"。
2. **规则写在契约里，不写在 Prompt 里。** Prompt 可以被遗忘和曲解，契约不会。Agent 的行为边界由契约定义。
3. **Agent 是无状态的函数，状态由系统管理。** 不依赖聊天历史传递上下文。每次调用 Agent，都携带完整的状态快照。
4. **人类是决策者，不是调试者。** 系统自动处理所有可自动化的验证和重试。只在真正需要判断时，呼叫人类。

---

## 第二部分：技术栈与选型理由

### 2.1 技术栈总览

```
┌────────────────────────────────────────────┐
│        PydanticAI (Agent Framework)         │
│  · Agent 定义 + 结构化输出 = 契约门卫        │
│  · Human-in-the-loop 原生支持               │
│  · 依赖注入 = 状态快照注入                   │
├────────────────────────────────────────────┤
│     pydantic-graph V1 API (State Machine)   │
│  · 工作流编排 = 有向图状态机                 │
│  · FileStatePersistence = 断点续跑           │
│  · 类型提示定义边 = 流转路径可验证            │
├────────────────────────────────────────────┤
│        Pydantic BaseModel (Contracts)       │
│  · 五种契约类型 = 五组 Pydantic Model        │
│  · model_validate() = L0 验证一行搞定        │
│  · 可导出 JSON Schema（如需外部消费）        │
├────────────────────────────────────────────┤
│        Executor Protocol (抽象执行层)        │
│  · CodexExecutor（MVP 实现）                │
│  · 未来可替换为任何 CLI Agent                │
└────────────────────────────────────────────┘
```

### 2.2 为什么选 PydanticAI 而非 LangGraph

PydanticAI 已于 2025 年 9 月达到 V1 版本，承诺 API 稳定性：在 V2 之前不会引入破坏性变更。 ([Upgrade Guide - Pydantic AI](https://ai.pydantic.dev/changelog/))

选择 PydanticAI 的核心理由：

**① 结构化输出验证（天然契约门卫）**

Agent 类构造器接受 `output_type` 参数，支持简单标量类型、list 和 dict 类型（包括 TypedDict）、dataclass 和 Pydantic model，以及类型联合——基本上 Pydantic model 中支持的所有类型提示。 ([Output - Pydantic AI](https://ai.pydantic.dev/output/)) Pydantic model 用于约束 Agent 返回的结构化数据。从这个简单定义出发，Pydantic 构建 JSON Schema 告知 LLM 如何返回数据，并执行验证以保证运行结束时数据的正确性。 ([Pydantic AI - Pydantic AI](https://ai.pydantic.dev/))

这意味着我们的契约 Model 可以直接作为 Agent 的 `output_type`，不符合则自动重试——这几乎就是 L0 验证的原生实现。

**② Human-in-the-loop 原生支持**

PydanticAI 支持持久化执行（Durable Execution），能在 API 失败或应用重启后保留进度，处理长时间运行、异步和 human-in-the-loop 工作流，具备生产级可靠性。 ([Pydantic AI - Pydantic AI](https://ai.pydantic.dev/))

**③ pydantic-graph 提供轻量状态机**

pydantic-graph 是作为 PydanticAI 一部分开发的异步图和状态机库，但它不依赖 pydantic-ai，可以被视为一个纯粹的图状态机库。无论你是否使用 PydanticAI 或构建 GenAI 应用，都可能觉得它有用。 ([Overview - Pydantic AI](https://ai.pydantic.dev/graph/))

**④ 弃 LangGraph 的理由**

LangGraph 对 Capsule 而言过重。一个人维护的项目不需要 LangChain 生态的复杂性。pydantic-graph 的类型安全和轻量设计更契合本项目。

### 2.3 pydantic-graph：关键 API 速览

**必须使用 V1 API（BaseNode 类继承模式），不使用 Beta API。** 理由：V1 Graph 拥有完整的持久化支持（BaseStatePersistence、iter_from_persistence()、snapshots），而 Beta Graph 目前没有持久化能力。 ([Does Temporal handle Beta Graph resumability, or is native persistence still planned? · Issue #3697 · pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai/issues/3697))

核心概念：

- `BaseNode` 的子类定义图中待执行的节点。节点通常是 dataclass，包含：调用节点时所需的参数字段、run 方法中的业务逻辑、run 方法的返回类型注解（pydantic-graph 据此确定节点的出边）。 ([Overview - Pydantic AI](https://ai.pydantic.dev/graph/))
- `End` 是返回值，用于指示图运行应该结束。`End` 对图的返回类型 `RunEndT` 是泛型的。 ([Overview - Pydantic AI](https://ai.pydantic.dev/graph/))
- FSM 图的最大好处之一是简化中断执行的处理。状态机逻辑可能需要暂停——例如等待用户输入，或执行时间过长无法在单次连续运行中完成。 ([Graph](https://ai.pydantic.dev/graph/))

**持久化（断点续跑的关键）：**

pydantic-graph 提供 `FileStatePersistence`——基于文件的状态持久化，将快照保存到 JSON 文件。 ([Graph](https://ai.pydantic.dev/graph/)) 在生产应用中，开发者应通过子类化 `BaseStatePersistence` 抽象基类来实现自己的状态持久化。 ([Graph](https://ai.pydantic.dev/graph/))

MVP 阶段直接使用 `FileStatePersistence`，后续如需可自定义。

`graph.iter_from_persistence()` 可用于根据持久化中存储的状态运行图。 ([Graph](https://ai.pydantic.dev/graph/)) 这就是我们断点续跑的底层实现。

### 2.4 Codex CLI：执行引擎

Codex CLI 是 OpenAI 的编码 Agent，在本地计算机上运行。 ([GitHub - openai/codex: Lightweight coding agent that runs in your terminal](https://github.com/openai/codex))

**非交互模式（核心调用方式）：**

非交互模式允许你从脚本运行 Codex（例如 CI 任务），无需打开交互式 TUI。通过 `codex exec` 调用。 ([Non-interactive mode](https://developers.openai.com/codex/noninteractive/))

exec 子命令可以自动化工作流或将 Codex 接入现有脚本。它以非交互方式运行 Codex，将最终计划和结果输出到 stdout。 ([Codex CLI features](https://developers.openai.com/codex/cli/features/))

关键命令模式：

```bash
codex exec \
  --full-auto \                    # 全自动，无需人工确认
  --sandbox workspace-write \      # 沙盒：可写工作区
  --json \                         # 结构化 JSON 输出
  --cd {working_dir} \             # 指定工作目录
  "{task_prompt}"                  # 任务 prompt
```

应设置 `--full-auto` 用于无人值守的本地工作，但避免将其与 `--dangerously-bypass-approvals-and-sandbox` 组合，除非在专用沙盒 VM 内。 ([Command line options](https://developers.openai.com/codex/cli/reference/))

配合 `--json` 和 `--output-last-message` 可在 CI 中捕获机器可读的进度和最终自然语言摘要。 ([Command line options](https://developers.openai.com/codex/cli/reference/))

**Session 续跑能力（可能有用）：**

如需继续前一次运行（例如两阶段流水线），可使用 resume 子命令：`codex exec resume --last "fix the race conditions you found"`。 ([Non-interactive mode](https://developers.openai.com/codex/noninteractive/))

**安全约束：**

Codex 要求命令在 Git 仓库内运行，以防止破坏性更改。 ([Non-interactive mode](https://developers.openai.com/codex/noninteractive/))

**模型选择：**

对于 Codex 中的大多数编码任务，首选 `gpt-5.3-codex`。 ([Codex Models](https://developers.openai.com/codex/models/))

### 2.5 执行层抽象设计

Codex CLI 是 MVP 的执行引擎，但 Capsule 设计上必须允许未来替换。实现方式：定义一个 `Executor` Protocol。

```python
"""capsule/core/executor.py"""

from typing import Protocol, Any
from pydantic import BaseModel


class ExecutionResult(BaseModel):
    """执行器的统一返回结构"""
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    modified_files: list[str]   # Git diff 检测到的变更文件
    raw_output: dict[str, Any]  # 执行器原始输出（如 --json 的完整内容）


class Executor(Protocol):
    """执行层抽象协议。任何 AI 编码工具只需实现此协议即可接入。"""

    async def execute(
        self,
        prompt: str,
        working_dir: str,
        allowed_paths: list[str],
        timeout_seconds: int = 300,
    ) -> ExecutionResult:
        """
        执行一次编码任务。

        Args:
            prompt: 完整的任务 prompt（由契约 + 状态快照生成）
            working_dir: 工作目录（沙盒根）
            allowed_paths: 允许写入的路径 glob 列表
            timeout_seconds: 超时时间
        """
        ...
```

`CodexExecutor` 是第一个实现，内部调用 `subprocess` 封装 `codex exec`。

---

## 第三部分：系统架构

### 3.1 五层架构

```
┌──────────────────────────────────────────────────────────────────┐
│   Layer 5: 人机交互层 (Human-in-the-loop Layer)                  │
│   CLI 界面 · Human Review 出口 · 断路器通知 · 进度报告            │
├──────────────────────────────────────────────────────────────────┤
│   Layer 4: 语义层 (Semantic Layer)                               │
│   需求形式化 · 对话式澄清 · 任务拆解 · 契约生成                   │
├──────────────────────────────────────────────────────────────────┤
│   Layer 3: 编排层 (Orchestration Layer)                          │
│   pydantic-graph 状态机 · 角色调度 · 条件路由                     │
├──────────────────────────────────────────────────────────────────┤
│   Layer 2: 契约层 (Contract Layer)          ← 系统心脏           │
│   五种契约 Pydantic Model · 四级验证流水线 · 打回协议 · 断路器      │
├──────────────────────────────────────────────────────────────────┤
│   Layer 1: 状态层 (State Layer)                                  │
│   PROJECT_STATE.json · FileStatePersistence · 审计日志             │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    执行层（外部工具）
                    Codex CLI · 测试运行器 · Git
```

### 3.2 数据流全景

```
人类（自然语言需求）
        │
        ▼
  语义层：Architect Agent 需求澄清 → 形式化 → 生成契约
        │
        ▼
  编排层：pydantic-graph 选择工作流节点 → 分发给角色
        │
        ▼
  契约层：INPUT GATE 验证 → Codex CLI 执行 → OUTPUT GATE 验证
        │                                        │
        │ 全部通过                              失败
        ▼                                        ▼
  状态层：持久化到 PROJECT_STATE       打回协议（携带诊断）→ 重试
        │                                        │
        ▼                                    超过重试上限
  下一节点 或 里程碑节点                          │
        │                                        ▼
        ▼                                   断路器 → Human
  Human Review 节点 → 人类决策 → 继续
```

### 3.3 目录结构

```
capsule/
│
├── pyproject.toml                  # 项目配置
├── capsule.yaml                    # 项目总配置（模型、默认参数等）
├── CAPSULE.md                      # 项目说明（注入给所有 Agent）
│
├── roles/                          # 角色契约定义（YAML，可扩展）
│   ├── architect.role.yaml
│   ├── qa.role.yaml
│   └── coder_backend.role.yaml
│
├── workflows/                      # 工作流定义（YAML，可扩展）
│   ├── standard.yaml
│   └── hotfix.yaml
│
├── contracts/
│   ├── boundaries/                 # 边界契约（全局生效，人类维护）
│   │   └── global.boundary.yaml
│   │
│   └── instances/                  # 运行时生成的具体契约
│       └── {module_name}/
│           ├── task.contract.yaml
│           ├── interface.contract.yaml
│           └── behavior.contract.yaml
│
├── state/
│   ├── PROJECT_STATE.json          # 全局项目状态
│   ├── graph_persistence/          # pydantic-graph FileStatePersistence
│   │   └── {workflow_run_id}.json
│   ├── checkpoints/                # 断点快照
│   └── audit/
│       └── boundary_violations.log # 不可删除的审计日志
│
├── prompts/                        # Agent System Prompt 模板
│   ├── architect.md
│   ├── qa.md
│   └── coder.md
│
└── capsule/                        # Python 包：系统核心代码
    ├── __init__.py
    ├── cli.py                      # 用户入口（typer 或 click）
    ├── contracts/
    │   ├── __init__.py
    │   └── models/                 # 五种契约的 Pydantic Model
    │       ├── __init__.py         # 含 CONTRACT_REGISTRY + parse_contract()
    │       ├── enums.py
    │       ├── role_contract.py
    │       ├── task_contract.py
    │       ├── interface_contract.py
    │       ├── behavior_contract.py
    │       └── boundary_contract.py
    ├── validation/
    │   ├── __init__.py
    │   ├── pipeline.py             # L0-L3 四级验证流水线
    │   ├── l0_structural.py        # L0: model_validate()
    │   ├── l1_consistency.py       # L1: 跨契约引用、权限校验
    │   ├── l2_behavioral.py        # L2: 运行测试套件
    │   └── l3_boundary.py          # L3: Git Diff 边界审计
    ├── orchestration/
    │   ├── __init__.py
    │   ├── graph.py                # pydantic-graph 工作流定义
    │   ├── nodes.py                # 图节点（ArchitectNode, QANode, CoderNode...）
    │   └── state.py                # 图状态定义（ProjectState dataclass）
    ├── agents/
    │   ├── __init__.py
    │   ├── factory.py              # Agent 工厂：从角色契约创建 PydanticAI Agent
    │   └── prompt_builder.py       # Prompt 组装器：契约 + 状态快照 → prompt
    ├── execution/
    │   ├── __init__.py
    │   ├── protocol.py             # Executor Protocol 定义
    │   └── codex_executor.py       # Codex CLI subprocess 封装
    ├── state/
    │   ├── __init__.py
    │   ├── project_state.py        # PROJECT_STATE.json 的读写管理
    │   └── audit.py                # 审计日志写入
    └── human_loop/
        ├── __init__.py
        └── handler.py              # Human-in-the-loop 交互处理
```

---

## 第四部分：契约体系（系统心脏）

### 4.1 设计决策备忘

| 决策点 | 结论 | 理由 |
|--------|------|------|
| 公共骨架 | 各 Model 独立声明所有字段，不用继承/mixin | 打开任何一个文件即完整，零心智跟踪 |
| 严格度 | `ConfigDict(extra="forbid")` + 显式 `extensions: dict` | 核心字段锁死，extensions 口袋供自由扩展 |
| 引用格式 | 纯字符串 ID（如 `"interface.user_auth"`），validator.py 负责解析 | MVP 轻量，未来可加版本号 |
| 验证分界 | Pydantic Model 管"形状"，validator.py 管"关系" | Model 做字段验证；跨契约一致性、状态流转在代码层 |

### 4.2 枚举定义

```python
"""capsule/contracts/models/enums.py"""

from enum import StrEnum


class ContractType(StrEnum):
    ROLE = "role"
    TASK = "task"
    INTERFACE = "interface"
    BEHAVIOR = "behavior"
    BOUNDARY = "boundary"


class ContractStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    AMENDING = "amending"
    DEPRECATED = "deprecated"


class ViolationAction(StrEnum):
    RETRY = "retry"
    HUMAN_ESCALATION = "human_escalation"
    IMMEDIATE_HALT = "immediate_halt"


class HttpMethod(StrEnum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
```

### 4.3 类型 I：角色契约（RoleContract）

**职责：** 定义一个 Agent 的身份、能力边界和行为规则。
**回答三个问题：** 你是谁？你能做什么？你不能碰什么？

```python
"""capsule/contracts/models/role_contract.py"""

from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from .enums import ContractType, ContractStatus, ViolationAction


class FilePermissions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    read:  list[str] = Field(default_factory=list, description="可读路径 glob")
    write: list[str] = Field(default_factory=list, description="可写路径 glob")


class ExecPermissions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allow: list[str] = Field(default_factory=list, description="允许的命令前缀")
    deny:  list[str] = Field(default_factory=list, description="禁止的命令前缀")


class OutputSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required_fields: list[str] = Field(..., min_length=1)


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_retries: int = Field(default=3, ge=1, le=10)
    on_exceed: ViolationAction = Field(default=ViolationAction.HUMAN_ESCALATION)


class RoleContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # ── Identity ──
    id:           str = Field(..., pattern=r"^role\.[a-z_]+$")
    version:      str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    type:         ContractType = Field(default=ContractType.ROLE, frozen=True)
    status:       ContractStatus = Field(default=ContractStatus.DRAFT)
    created_by:   str = Field(default="human")
    created_at:   datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    display_name: str = Field(..., min_length=1)
    description:  str = Field(default="")

    # ── Capabilities ──
    file_permissions: FilePermissions
    exec_permissions: ExecPermissions

    # ── Prohibitions ──
    prohibited_paths: list[str] = Field(
        default_factory=list,
        description="绝对禁写路径，优先级高于 file_permissions.write"
    )

    # ── Output Spec ──
    output_spec: OutputSpec

    # ── Retry ──
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)

    # ── Confidence Threshold ──
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)

    # ── Extensions ──
    extensions: dict[str, Any] = Field(default_factory=dict)
```

**YAML 实例示例（`roles/coder_backend.role.yaml`）：**

```yaml
id: "role.coder_backend"
version: "1.0.0"
type: "role"
status: "active"
created_by: "human"
display_name: "Backend Coder"
description: "负责后端代码实现，严格基于接口契约和行为契约工作"

file_permissions:
  read:  ["src/backend/**", "contracts/**", "CAPSULE.md"]
  write: ["src/backend/**", "tests/backend/**"]

exec_permissions:
  allow: ["pytest", "pip install", "python"]
  deny:  ["git push", "git reset", "rm -rf"]

prohibited_paths:
  - "src/frontend/**"
  - "contracts/boundaries/**"
  - ".env*"

output_spec:
  required_fields:
    - "task_id"
    - "modified_files"
    - "test_result"
    - "confidence_score"

retry_policy:
  max_retries: 3
  on_exceed: "human_escalation"

confidence_threshold: 0.7
```

### 4.4 类型 II：任务契约（TaskContract）

**职责：** 一次具体开发任务的完整规格。
**回答：** 这件事的规格是什么？谁来做？怎么算做完？

```python
"""capsule/contracts/models/task_contract.py"""

from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from .enums import ContractType, ContractStatus, ViolationAction


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    include:        list[str] = Field(..., min_length=1)
    create_allowed: list[str] = Field(default_factory=list)
    exclude:        list[str] = Field(default_factory=list)


class AcceptanceCriteria(BaseModel):
    model_config = ConfigDict(extra="forbid")
    behavior_contract_ref: str = Field(default="")
    max_new_files:         int = Field(default=20, ge=0)
    custom_criteria:       list[str] = Field(default_factory=list)


class TaskContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # ── Identity ──
    id:          str = Field(..., pattern=r"^task\.[a-z_.]+$")
    version:     str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    type:        ContractType = Field(default=ContractType.TASK, frozen=True)
    status:      ContractStatus = Field(default=ContractStatus.DRAFT)
    created_by:  str = Field(...)
    created_at:  datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    description: str = Field(..., min_length=1)

    # ── Assignment ──
    assigned_to: str = Field(...)

    # ── Preconditions ──
    preconditions: list[str] = Field(default_factory=list)

    # ── Scope ──
    scope: Scope

    # ── Acceptance ──
    acceptance: AcceptanceCriteria = Field(default_factory=AcceptanceCriteria)

    # ── Forbidden Actions ──
    forbidden_actions: list[str] = Field(default_factory=list)

    # ── Budget ──
    token_budget: int = Field(default=16000, ge=1000)

    # ── Retry ──
    max_retries:        int = Field(default=3, ge=1, le=10)
    on_retries_exceeded: ViolationAction = Field(default=ViolationAction.HUMAN_ESCALATION)

    # ── Context Refs ──
    context_refs: list[str] = Field(default_factory=list)

    # ── Extensions ──
    extensions: dict[str, Any] = Field(default_factory=dict)
```

### 4.5 类型 III：接口契约（InterfaceContract）

**职责：** 模块之间的通信协议。前后端之间的"宪法"。

```python
"""capsule/contracts/models/interface_contract.py"""

from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from .enums import ContractType, ContractStatus, HttpMethod


class SchemaSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type:       str = Field(default="object")
    required:   list[str] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)


class ResponseSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    success_status: int = Field(default=200, ge=100, le=599)
    success_schema: SchemaSpec = Field(default_factory=SchemaSpec)
    error_statuses: list[int] = Field(default_factory=lambda: [400, 401, 500])


class Endpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id:          str = Field(..., min_length=1)
    path:        str = Field(..., pattern=r"^/")
    method:      HttpMethod
    request:     SchemaSpec = Field(default_factory=SchemaSpec)
    response:    ResponseSpec = Field(default_factory=ResponseSpec)
    description: str = Field(default="")


class Binding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    producer:  str = Field(...)
    consumers: list[str] = Field(default_factory=list)


class ChangePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requires_approval: list[str] = Field(default_factory=lambda: ["role.architect"])
    on_change:         str = Field(default="suspend_dependent_tasks")


class InterfaceContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id:          str = Field(..., pattern=r"^interface\.[a-z_.]+$")
    version:     str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    type:        ContractType = Field(default=ContractType.INTERFACE, frozen=True)
    status:      ContractStatus = Field(default=ContractStatus.DRAFT)
    created_by:  str = Field(default="role.architect")
    created_at:  datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    description: str = Field(default="")

    endpoints:     list[Endpoint] = Field(..., min_length=1)
    binding:       Binding
    change_policy: ChangePolicy = Field(default_factory=ChangePolicy)
    extensions:    dict[str, Any] = Field(default_factory=dict)
```

### 4.6 类型 IV：行为契约（BehaviorContract）

**职责：** 代码跑起来必须表现出什么行为。**只能由 QA Agent 创建。**

```python
"""capsule/contracts/models/behavior_contract.py"""

from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from .enums import ContractType, ContractStatus


class TestCase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id:          str = Field(..., pattern=r"^TC\d{3,}$")
    description: str = Field(..., min_length=1)
    must_pass:   bool = Field(default=True)


class CoverageRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minimum_percent: int = Field(default=80, ge=0, le=100)


class TestSuite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runner:    str = Field(...)
    entry:     str = Field(...)
    setup_cmd: str = Field(default="")


class BehaviorContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id:          str = Field(..., pattern=r"^behavior\.[a-z_.]+$")
    version:     str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    type:        ContractType = Field(default=ContractType.BEHAVIOR, frozen=True)
    status:      ContractStatus = Field(default=ContractStatus.DRAFT)
    created_by:  str = Field(default="role.qa")
    created_at:  datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    description: str = Field(default="")

    test_suite:      TestSuite
    mandatory_cases: list[TestCase] = Field(..., min_length=1)
    coverage:        CoverageRequirement = Field(default_factory=CoverageRequirement)
    extensions:      dict[str, Any] = Field(default_factory=dict)
```

### 4.7 类型 V：边界契约（BoundaryContract）

**职责：** 绝对禁区。触发后果是**终止**，不是打回。

```python
"""capsule/contracts/models/boundary_contract.py"""

from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from .enums import ContractType, ContractStatus, ViolationAction


class AuditRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id:               str = Field(..., min_length=1)
    description:      str = Field(default="")
    check_method:     str = Field(...)
    violation_action: ViolationAction = Field(default=ViolationAction.IMMEDIATE_HALT)


class BoundaryContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id:          str = Field(..., pattern=r"^boundary\.[a-z_.]+$")
    version:     str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    type:        ContractType = Field(default=ContractType.BOUNDARY, frozen=True)
    status:      ContractStatus = Field(default=ContractStatus.ACTIVE)
    created_by:  str = Field(default="human")
    created_at:  datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    description: str = Field(default="")

    scope:        str = Field(default="global")
    sacred_files: list[str] = Field(..., min_length=1)
    audit_rules:  list[AuditRule] = Field(..., min_length=1)
    on_violation: ViolationAction = Field(default=ViolationAction.IMMEDIATE_HALT)
    notify:       str = Field(default="human")
    log_path:     str = Field(default="state/audit/boundary_violations.log")
    extensions:   dict[str, Any] = Field(default_factory=dict)
```

### 4.8 契约注册表

```python
"""capsule/contracts/models/__init__.py"""

from .enums import ContractType, ContractStatus, ViolationAction
from .role_contract import RoleContract
from .task_contract import TaskContract
from .interface_contract import InterfaceContract
from .behavior_contract import BehaviorContract
from .boundary_contract import BoundaryContract

CONTRACT_REGISTRY: dict[ContractType, type] = {
    ContractType.ROLE:      RoleContract,
    ContractType.TASK:      TaskContract,
    ContractType.INTERFACE: InterfaceContract,
    ContractType.BEHAVIOR:  BehaviorContract,
    ContractType.BOUNDARY:  BoundaryContract,
}


def parse_contract(data: dict):
    """
    通用契约解析入口。
    根据 data["type"] 选择正确的 Model 验证。
    不合法则抛出 ValidationError —— 这就是 L0 门卫。
    """
    contract_type = data.get("type")
    if contract_type not in CONTRACT_REGISTRY:
        raise ValueError(f"Unknown contract type: {contract_type}")
    model_class = CONTRACT_REGISTRY[ContractType(contract_type)]
    return model_class.model_validate(data)
```

### 4.9 契约生命周期

```
DRAFT → PENDING_REVIEW → ACTIVE → AMENDING → DEPRECATED

规则：
  ACTIVE 状态的契约，修改必须先转为 AMENDING，重走审批
  AMENDING 期间，依赖此契约的所有任务自动暂停
  DEPRECATED 永久存档，不可删除
  状态流转的合法性在 validator.py 中校验，不在 Model 层
```

---

## 第五部分：验证流水线（Gate System）

### 5.1 四级验证架构

```
Agent 产出
    │
  INPUT GATE：前置条件检查 + 依赖契约存在性检查
    │ 通过
  AGENT EXECUTION：Codex CLI 沙盒执行
    │
  OUTPUT GATE：
    │
    ├── L0 格式校验
    │   方法：contract_model.model_validate(output)
    │   耗时：<100ms
    │   失败：直接 reject，不进入下一层
    │
    ├── L1 结构一致性
    │   方法：自定义 Python 校验逻辑
    │   内容：
    │     - 引用的契约 ID 是否真实存在？
    │     - 引用的契约状态是否为 active？
    │     - Agent 角色权限是否匹配文件路径？
    │     - forbidden_actions 是否被违反？
    │   失败：reject + 标注违规条款
    │
    ├── L2 行为验证
    │   方法：运行测试套件（pytest / jest）
    │   内容：
    │     - 逐条检查 behavior_contract 的 mandatory_cases
    │     - 检查覆盖率
    │   失败：reject + 附带测试输出
    │
    └── L3 边界审计
        方法：Git Diff 扫描
        内容：
          - 变更文件是否在 scope.include 范围内？
          - 是否触碰了 sacred_files？
          - 是否写入了 prohibited_paths？
        失败：IMMEDIATE_HALT，不打回，直接终止，通知人类
```

### 5.2 验证流水线实现指引

```python
"""capsule/validation/pipeline.py — 概念结构"""

from dataclasses import dataclass
from enum import StrEnum


class GateVerdict(StrEnum):
    PASSED = "passed"
    REJECTED = "rejected"
    HALTED = "halted"          # L3 触发，不可重试


@dataclass
class ValidationResult:
    verdict: GateVerdict
    failed_level: int | None   # 0-3，None if passed
    failed_contract: str       # 失败关联的契约 ID
    details: str               # 人类可读的失败描述
    trace: str                 # 技术堆栈/日志
    hint: str                  # 给 Agent 的修复建议


async def run_output_gate(
    artifact: dict,            # Agent 的原始产出
    task_contract,             # 关联的 TaskContract 实例
    role_contract,             # Agent 的 RoleContract 实例
    boundary_contracts: list,  # 所有 active 的 BoundaryContract
    behavior_contract=None,    # 关联的 BehaviorContract（可选）
) -> ValidationResult:
    """
    四级验证流水线。短路逻辑：任一级失败即停止。
    L0-L2 失败 = reject（可重试）
    L3 失败 = halt（不可重试，通知人类）
    """
    # L0: 格式校验
    # L1: 结构一致性
    # L2: 行为验证
    # L3: 边界审计
    ...
```

### 5.3 打回协议（Rejection Protocol）

当 L0-L2 验证失败时，系统生成结构化打回信息重新注入 Agent：

```python
@dataclass
class RejectionReport:
    rejection_id: str          # "REJ-{timestamp}-{seq}"
    target_agent: str          # 角色 ID
    task_id: str
    retry_count: int           # 当前第几次
    max_retries: int
    failed_gate: str           # "OUTPUT_GATE"
    failed_level: int          # 0, 1, or 2
    failed_contract: str       # 失败关联的契约 ID
    failure_details: dict      # 包含 expected, actual, trace, hint
```

这份报告会被序列化后注入到下一轮 Agent 调用的 prompt 中，让 Agent 精确知道哪里出了问题。

### 5.4 断路器

```
retry_count >= max_retries
    │
  生成诊断报告（所有失败记录汇总 + 差异对比）
    │
  触发 Human-in-the-loop
    │
  人类选择：
    [1] 修改需求，重新设计契约
    [2] 手动修复后继续
    [3] 调整契约验证标准（放宽/收紧）
    [4] 暂存此任务，先做其他模块
    [5] 终止
```

---

## 第六部分：编排层（pydantic-graph 实现）

### 6.1 图状态定义

```python
"""capsule/orchestration/state.py"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CapsuleGraphState:
    """pydantic-graph 的状态对象，贯穿整个工作流执行。"""

    # 当前任务上下文
    project_id: str = ""
    current_module: str = ""
    current_task_id: str = ""

    # 契约引用（已加载的契约实例缓存为 dict）
    active_contracts: dict[str, dict[str, Any]] = field(default_factory=dict)

    # 执行跟踪
    retry_count: int = 0
    rejection_history: list[dict] = field(default_factory=list)

    # 产出暂存
    latest_artifact: dict[str, Any] | None = None

    # 人类决策记录
    human_decisions: list[dict] = field(default_factory=list)

    # 标志位
    needs_human_review: bool = False
    is_halted: bool = False
    halt_reason: str = ""
```

### 6.2 图节点设计

每个节点是一个 `BaseNode` 子类。节点的 `run` 方法返回下一个节点类型，pydantic-graph 据此确定流转路径。

```python
"""capsule/orchestration/nodes.py — 概念结构"""

from dataclasses import dataclass
from pydantic_graph import BaseNode, End, GraphRunContext

# 类型别名
State = CapsuleGraphState
Deps = None                    # MVP 暂无依赖注入
Result = str                   # 图最终返回值类型


@dataclass
class ArchitectDesignNode(BaseNode[State, Deps, Result]):
    """架构师节点：需求分析 → 生成契约包"""

    async def run(self, ctx: GraphRunContext[State, Deps]) -> "HumanReviewDesignNode":
        # 1. 加载项目状态和现有共识
        # 2. 调用 Architect Agent（PydanticAI Agent，output_type=契约包模型）
        # 3. Agent 产出契约（接口契约 + 任务契约草案）
        # 4. L0 验证契约格式
        # 5. 写入 contracts/instances/
        # 6. 更新 state
        # 7. 流转到人类审查节点
        return HumanReviewDesignNode()


@dataclass
class HumanReviewDesignNode(BaseNode[State, Deps, Result]):
    """人类审查设计节点：系统暂停，等待人类确认"""

    async def run(self, ctx: GraphRunContext[State, Deps]) -> "QADesignNode":
        # 1. 将设计摘要呈现给人类（CLI 输出）
        # 2. 等待人类输入（approve / reject / modify）
        # 3. 如 reject，回到 ArchitectDesignNode（需要条件路由）
        # 4. 如 approve，记录决策，流转到 QA
        return QADesignNode()


@dataclass
class QADesignNode(BaseNode[State, Deps, Result]):
    """QA 节点：生成行为契约（测试规格）"""

    async def run(self, ctx: GraphRunContext[State, Deps]) -> "CoderNode":
        # 1. 加载接口契约
        # 2. 调用 QA Agent（output_type=BehaviorContract 模型）
        # 3. L0 验证
        # 4. 写入 behavior.contract.yaml
        # 5. 流转到 Coder
        return CoderNode()


@dataclass
class CoderNode(BaseNode[State, Deps, Result]):
    """Coder 节点：执行编码任务"""

    async def run(
        self, ctx: GraphRunContext[State, Deps]
    ) -> "ValidationNode":
        # 1. 从状态中获取 task_contract, role_contract
        # 2. 组装 prompt（契约 + 共识 + 打回历史）
        # 3. 调用 Codex CLI（通过 Executor Protocol）
        # 4. 收集产出
        # 5. 流转到验证节点
        return ValidationNode()


@dataclass
class ValidationNode(BaseNode[State, Deps, Result]):
    """验证节点：运行四级验证流水线"""

    async def run(
        self, ctx: GraphRunContext[State, Deps]
    ) -> "CoderNode | HumanEscalationNode | ArchitectReviewNode":
        # 1. 运行 OUTPUT GATE（L0-L3）
        # 2. 如 L3 触发 → HumanEscalationNode
        # 3. 如 L0-L2 失败 且 retry < max → 回到 CoderNode
        # 4. 如 L0-L2 失败 且 retry >= max → HumanEscalationNode
        # 5. 如全部通过 → ArchitectReviewNode
        ...


@dataclass
class HumanEscalationNode(BaseNode[State, Deps, Result]):
    """断路器触发，等待人类决策"""

    async def run(
        self, ctx: GraphRunContext[State, Deps]
    ) -> "CoderNode | ArchitectDesignNode | End[Result]":
        # 1. 汇总诊断信息
        # 2. 呈现给人类
        # 3. 根据人类选择路由
        ...


@dataclass
class ArchitectReviewNode(BaseNode[State, Deps, Result]):
    """架构师最终审查 → 完成"""

    async def run(
        self, ctx: GraphRunContext[State, Deps]
    ) -> "HumanReviewResultNode":
        # 架构师做最终语义审查
        return HumanReviewResultNode()


@dataclass
class HumanReviewResultNode(BaseNode[State, Deps, Result]):
    """最终人类验收"""

    async def run(self, ctx: GraphRunContext[State, Deps]) -> End[Result]:
        # 人类最终确认
        return End("completed")
```

### 6.3 图定义与运行

```python
"""capsule/orchestration/graph.py — 概念结构"""

from pydantic_graph import Graph
from pydantic_graph.persistence.file import FileStatePersistence
from .nodes import *
from .state import CapsuleGraphState


# 注册所有节点，pydantic-graph 通过返回类型注解自动推导边
capsule_workflow = Graph(
    nodes=[
        ArchitectDesignNode,
        HumanReviewDesignNode,
        QADesignNode,
        CoderNode,
        ValidationNode,
        HumanEscalationNode,
        ArchitectReviewNode,
        HumanReviewResultNode,
    ]
)


async def run_workflow(project_id: str, module_name: str):
    """启动或恢复一次工作流执行。"""
    persistence_path = f"state/graph_persistence/{project_id}_{module_name}.json"
    persistence = FileStatePersistence(persistence_path)

    state = CapsuleGraphState(
        project_id=project_id,
        current_module=module_name,
    )

    # 尝试从持久化恢复
    persistence.set_graph_types(capsule_workflow)
    snapshot = await persistence.load_next()

    if snapshot:
        # 断点续跑
        async with capsule_workflow.iter_from_persistence(
            persistence=persistence
        ) as run:
            async for node in run:
                pass  # 图会自动驱动到完成或暂停
    else:
        # 全新启动
        async with capsule_workflow.iter(
            start_node=ArchitectDesignNode(),
            state=state,
            persistence=persistence,
        ) as run:
            async for node in run:
                pass
```

**关键实现细节：**

- 如果之前运行过图，`load_next` 会返回下一个待运行节点的快照，可以使用该快照中的状态，创建新节点继续。如果图之前未运行，则创建新状态从初始节点开始。 ([Graph](https://ai.pydantic.dev/graph/))
- FSM 图的最大好处之一是简化中断执行的处理。状态机逻辑可能需要暂停——例如等待用户输入，或者执行时间太长无法在单次连续运行中完成。 ([Graphs - PydanticAI](https://ai-pydantic-dev.translate.goog/graph/?_x_tr_sl=en&_x_tr_tl=es&_x_tr_hl=es&_x_tr_pto=tc))

这正是 Capsule 的 Human-in-the-loop 节点的底层实现：图运行到 Human 节点时，将状态快照到文件，进程退出。人类做出决策后，下次启动从持久化恢复，继续执行。

---

## 第七部分：Agent 工厂与 Prompt 组装

### 7.1 Agent 工厂

每个角色对应一个 PydanticAI Agent 实例。Agent 的 `output_type` 绑定为对应的契约 Model 或自定义产出 Model。

```python
"""capsule/agents/factory.py — 概念结构"""

from pydantic_ai import Agent
from pydantic import BaseModel


class CoderOutput(BaseModel):
    """Coder Agent 的结构化输出"""
    task_id: str
    modified_files: list[dict]  # [{path, action, summary}]
    test_result: str            # "passed" | "failed" | "not_run"
    confidence_score: float     # 0.0 - 1.0
    notes: str


def create_coder_agent(
    model: str = "openai:gpt-4o",
    system_prompt: str = "",
) -> Agent[None, CoderOutput]:
    """
    创建 Coder Agent。
    output_type=CoderOutput 确保 Agent 产出必须符合结构。
    """
    return Agent(
        model,
        output_type=CoderOutput,
        instructions=system_prompt,
        output_retries=2,  # 输出格式不对时自动重试
    )
```

验证错误（包括函数工具参数验证和结构化输出验证）可以被传回模型并请求重试。你也可以从工具或输出函数中抛出 `ModelRetry` 来告诉模型它应该重试生成响应。默认重试次数为 1，但可以为整个 Agent、特定工具或输出分别调整。 ([Agents - Pydantic AI](https://ai.pydantic.dev/agent/))

这意味着 L0 验证（格式校验）在 PydanticAI 层面就已经有了第一道防线。Agent 产出不符合 `output_type` 时，PydanticAI 会自动要求模型重试。

### 7.2 Prompt 组装器

Prompt 不是静态模板，而是由**契约 + 状态快照 + 打回历史**动态组装：

```python
"""capsule/agents/prompt_builder.py — 概念结构"""


def build_coder_prompt(
    task_contract: dict,
    interface_contract: dict,
    behavior_contract: dict,
    role_contract: dict,
    project_conventions: dict,
    rejection_history: list[dict] | None = None,
) -> str:
    """
    组装注入给 Coder Agent 的完整 prompt。

    核心原则：Agent 是无状态函数。
    每次调用都携带完整上下文，不依赖聊天历史。
    """
    sections = []

    # 1. 角色身份
    sections.append(f"## 你的角色\n你是 {role_contract['display_name']}。")

    # 2. 权限边界（从角色契约提取）
    sections.append(f"## 权限边界\n可写路径: {role_contract['file_permissions']['write']}")
    sections.append(f"禁止路径: {role_contract['prohibited_paths']}")

    # 3. 项目约定（从 PROJECT_STATE 提取）
    sections.append(f"## 项目约定\n{project_conventions}")

    # 4. 接口契约（原文注入）
    sections.append(f"## 接口契约（必须严格遵守）\n{interface_contract}")

    # 5. 任务规格
    sections.append(f"## 任务\n{task_contract['description']}")
    sections.append(f"## 验收标准\n{task_contract['acceptance']}")
    sections.append(f"## 禁止行为\n{task_contract['forbidden_actions']}")

    # 6. 行为契约（测试用例清单）
    sections.append(f"## 必须通过的测试\n{behavior_contract['mandatory_cases']}")

    # 7. 打回历史（如果有）
    if rejection_history:
        sections.append("## ⚠️ 前次失败记录（请修复以下问题）")
        for r in rejection_history:
            sections.append(f"- L{r['failed_level']} 失败: {r['failure_details']}")

    return "\n\n".join(sections)
```

---

## 第八部分：Human-in-the-loop 设计

### 8.1 触发时机

```
主动触发（系统预设的固定等待点）：
  - 契约从 DRAFT 进入 ACTIVE 之前（架构师设计审查）
  - 工作流中标记 human_review: true 的节点完成后
  - 最终验收

被动触发（异常升级）：
  - 断路器触发（重试次数耗尽）
  - L3 边界契约违规（立即终止）
  - Agent 自评置信度低于阈值
```

### 8.2 交互设计原则

```
呈现给人类的，永远是：
  ✅ 结构化摘要，不是原始日志
  ✅ 有限选项列表，不是开放式问题
  ✅ 足够做出决策的上下文
  ✅ 影响范围说明（这个决定会影响什么）
```

### 8.3 实现机制

在 pydantic-graph 中，Human 节点的实现模式：

1. 图运行到 HumanReviewNode
2. 节点将需要人类审查的信息写入状态
3. 节点将状态快照持久化到 JSON 文件
4. **进程挂起等待 CLI 输入（交互模式）或退出（批处理模式）**
5. 人类通过 CLI 做出决策
6. 决策写入状态
7. 图从持久化恢复，继续执行

---

## 第九部分：项目状态管理

### 9.1 PROJECT_STATE.json

```json
{
  "project_id": "my-saas-app",
  "current_workflow": "standard",
  "phase": "development",

  "modules": {
    "user_auth": {
      "status": "in_progress",
      "design": "complete",
      "test_design": "complete",
      "coding": "in_progress",
      "review": "pending"
    }
  },

  "active_contracts": [
    "interface.user_auth",
    "behavior.user_auth",
    "task.user_auth.login_api"
  ],

  "global_conventions": {
    "api_prefix": "/api/v1",
    "auth_method": "JWT",
    "db_orm": "SQLAlchemy",
    "test_runner": "pytest"
  },

  "history": []
}
```

### 9.2 与 pydantic-graph 持久化的关系

两套持久化并存，职责不同：

| 持久化 | 存储位置 | 职责 |
|--------|---------|------|
| `PROJECT_STATE.json` | `state/PROJECT_STATE.json` | 项目级元数据：模块进度、全局约定、契约清单 |
| `FileStatePersistence` | `state/graph_persistence/{id}.json` | 图运行级：当前节点、图状态、执行历史 |

`PROJECT_STATE.json` 由 Capsule 代码直接读写。
`FileStatePersistence` 由 pydantic-graph 自动管理。

---

## 第十部分：MVP 范围

### 10.1 必须实现

```
✅ 架构师 → QA → Backend Coder 串行完整流程
✅ 五种契约类型的 Pydantic Model + YAML 序列化/反序列化
✅ L0-L3 四级验证流水线
✅ 结构化打回协议（携带诊断信息注入 Agent prompt）
✅ 断路器 + Human-in-the-loop CLI 交互
✅ pydantic-graph 状态机 + FileStatePersistence 断点续跑
✅ Codex CLI 作为执行引擎（通过 Executor Protocol 抽象）
✅ 工作流和角色由 YAML 配置驱动（不硬编码）
✅ PROJECT_STATE.json 持久化
```

### 10.2 不做

```
❌ Web UI
❌ 多 Agent 并行执行
❌ Frontend Coder 角色（MVP 后加入）
❌ DevOps / 运维角色
❌ 云端同步
❌ pydantic-graph Beta API（使用 V1 API）
```

### 10.3 MVP 验收标准

> 用 Capsule 自身，完成一个「用户注册登录 API 模块」的端到端开发。
> 全程不超过 **2 次** 人类介入，最终所有自动化测试通过。

---

## 第十一部分：实现路线图

### Phase 1：地基层（预计 2-3 天）

```
Step 1.1  项目脚手架
          pyproject.toml, 目录结构, 依赖安装
          依赖: pydantic, pydantic-ai, pydantic-graph, pyyaml, typer

Step 1.2  五种契约 Pydantic Model
          完整实现 enums.py + 5 个 contract model + __init__.py
          单元测试: 正确 YAML 能 parse，错误 YAML 抛 ValidationError

Step 1.3  契约 YAML I/O
          load_contract(path) → Contract Model instance
          save_contract(instance, path) → YAML file
          使用 pyyaml + model.model_dump() / model_validate()
```

### Phase 2：验证层（预计 2-3 天）

```
Step 2.1  L0 格式校验
          直接调用 model_validate()，捕获 ValidationError

Step 2.2  L1 结构一致性
          检查引用的契约 ID 是否存在
          检查角色权限与文件路径的匹配
          检查 forbidden_actions

Step 2.3  L3 边界审计
          Git diff 扫描封装
          sacred_files 触碰检测

Step 2.4  L2 行为验证（简化版）
          subprocess 调用 pytest/jest
          解析退出码和输出

Step 2.5  验证流水线串联
          run_output_gate() 串联 L0 → L1 → L2 → L3
          短路逻辑
          打回协议生成
```

### Phase 3：执行层（预计 1-2 天）

```
Step 3.1  Executor Protocol 定义
Step 3.2  CodexExecutor 实现
          subprocess 调用 codex exec
          --json 输出解析
          Git diff 采集（调用前后对比）
Step 3.3  Prompt Builder 实现
```

### Phase 4：编排层（预计 3-4 天）

```
Step 4.1  CapsuleGraphState 定义
Step 4.2  图节点实现（8 个节点）
Step 4.3  图定义 + FileStatePersistence 集成
Step 4.4  Human-in-the-loop 节点实现（CLI 交互）
Step 4.5  断点续跑测试
```

### Phase 5：Agent 集成（预计 2-3 天）

```
Step 5.1  Architect Agent（PydanticAI Agent, output_type=契约包）
Step 5.2  QA Agent（output_type=BehaviorContract）
Step 5.3  Coder Agent 集成（Prompt Builder + CodexExecutor）
Step 5.4  Agent 工厂：从角色 YAML 动态创建 Agent
```

### Phase 6：CLI 入口 + 端到端联调（预计 2-3 天）

```
Step 6.1  CLI 命令设计（typer）
          capsule init          # 初始化项目
          capsule run           # 启动/恢复工作流
          capsule status        # 查看项目状态
          capsule review        # 进入 Human Review
Step 6.2  端到端 Demo：用户注册登录 API
Step 6.3  修 Bug，调 Prompt，直到 MVP 验收通过
```

---

## 第十二部分：关键注意事项

### 12.1 PydanticAI API 注意事项

`result_type` 参数已从 Agent 类中移除，应使用 `output_type` 替代。 ([Upgrade Guide - Pydantic AI](https://ai.pydantic.dev/changelog/))

`FinalResult` 类的 `data` 属性已移除，应使用 `output` 替代。 ([Upgrade Guide - Pydantic AI](https://ai.pydantic.dev/changelog/))

`Graph` 类的 `next` 方法已移除，应使用 `async with graph.iter(...) as run: run.next()` 替代。 ([Upgrade Guide - Pydantic AI](https://ai.pydantic.dev/changelog/))

### 12.2 pydantic-graph V1 vs Beta

**务必使用 V1 API（BaseNode 类继承模式）。** V1 Graph 拥有完整持久化支持，而 Beta Graph 目前无持久化能力。官方尚未明确 Temporal 是否是 Beta Graph 持久化的替代方案。 ([Does Temporal handle Beta Graph resumability, or is native persistence still planned? · Issue #3697 · pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai/issues/3697))

原始的 Graph API 仍然可用（并且可与新的 Beta API 互操作），文档在主 graph 文档页面。 ([Getting Started - Pydantic AI](https://ai.pydantic.dev/graph/beta/))

### 12.3 Codex CLI 安全

当需要授予 Codex 更多目录的写入权限时，优先使用 `--add-dir` 而非强制 `--sandbox danger-full-access`。 ([Command line options](https://developers.openai.com/codex/cli/reference/))

### 12.4 最重要的一条

**契约是这个系统的核心，不是技术实现。** 当你在做任何设计决策时，问自己：

> "这个决策让系统更确定了，还是更模糊了？"

"大概对"不是对。"基本符合"不是符合。通过就是通过，不通过就是不通过。

---

**文档版本：** v1.0
**日期：** 2026-03-03
**状态：** 可交付开发者实施

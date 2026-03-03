
# Capsule 第一版 — 完整技术实施方案

**文档版本：** v1.0
**目标读者：** 负责实现的开发者
**前置阅读：** `capsule_lead.md`（项目全局设计与技术指导）
**状态：** 可实施

---

## 〇、实施前须知

### 0.1 第一版做什么

> 人类手写契约 → Capsule 调度 Coder Agent 执行 → 自动四级验证 → 失败自动打回重试 → 超限断路器通知人类 → 通过则持久化结果。

Architect Agent 和 QA Agent 不在第一版范围内。第一版中所有契约由人类手写。Capsule 只负责"执行-验证-打回"闭环。

### 0.2 已锁定的设计决策

| 决策 | 结论 |
|------|------|
| 行为契约 | 人类手写测试代码，BehaviorContract 是对已有测试的"注册"。Agent 只负责让这些测试通过。 |
| Git 策略 | 验证通过 → 自动 commit；L0-L2 失败 → 保留变更不回滚，Agent 增量修复；L3 HALT → 强制回滚。 |
| Mock 执行器 | 提供 MockExecutor，验证流水线可独立测试，不依赖 Codex CLI。 |
| 编排方式 | 线性脚本（LinearRunner），不引入 pydantic-graph。 |
| Prompt 方式 | 代码拼接，不用模板引擎。每次 prompt 写入日志文件。 |

### 0.3 依赖清单

```toml
[project]
name = "capsule"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.10,<3.0",
    "pyyaml>=6.0,<7.0",
    "typer>=0.15,<1.0",
    "rich>=13.0,<14.0",        # CLI 美化输出
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=6.0",
]

[project.scripts]
capsule = "capsule.cli:app"
```

注意：第一版不依赖 `pydantic-ai` 和 `pydantic-graph`。这两个库在第二版引入。第一版只用 `pydantic` 核心库做契约验证。

---

## 一、目录结构

```
capsule/                            # 仓库根目录
│
├── capsule_lead.md                 # 项目全局设计文档（已存在）
├── pyproject.toml
│
├── roles/                          # 角色契约（人类手写）
│   └── coder_backend.role.yaml
│
├── workflows/                      # 第一版为空，结构预留
│
├── contracts/
│   ├── boundaries/
│   │   └── global.boundary.yaml    # 边界契约（人类手写）
│   └── instances/                  # 运行时契约存放目录
│       └── .gitkeep
│
├── state/
│   ├── PROJECT_STATE.json
│   ├── prompts/                    # prompt 日志（自动生成）
│   │   └── .gitkeep
│   └── audit/
│       └── .gitkeep
│
├── prompts/                        # Agent System Prompt 模板（第一版预留）
│
├── tests/                          # Capsule 自身的测试
│   ├── __init__.py
│   ├── conftest.py                 # pytest fixtures
│   ├── test_contracts.py           # 契约 Model 测试
│   ├── test_validation.py          # 验证流水线测试
│   ├── test_executor.py            # 执行器测试
│   ├── test_runner.py              # LinearRunner 测试
│   └── fixtures/                   # 测试用 YAML 契约样本
│       ├── valid/
│       └── invalid/
│
└── capsule/                        # Python 包
    ├── __init__.py
    ├── cli.py
    │
    ├── contracts/
    │   ├── __init__.py
    │   ├── io.py                   # YAML 读写
    │   └── models/
    │       ├── __init__.py         # CONTRACT_REGISTRY + parse_contract()
    │       ├── enums.py
    │       ├── role_contract.py
    │       ├── task_contract.py
    │       ├── interface_contract.py
    │       ├── behavior_contract.py
    │       └── boundary_contract.py
    │
    ├── validation/
    │   ├── __init__.py
    │   ├── pipeline.py             # 串联入口 + 数据结构
    │   ├── l0_structural.py
    │   ├── l1_consistency.py
    │   ├── l2_behavioral.py
    │   └── l3_boundary.py
    │
    ├── execution/
    │   ├── __init__.py
    │   ├── protocol.py             # Executor Protocol + ExecutionResult
    │   ├── codex_executor.py
    │   └── mock_executor.py
    │
    ├── agents/
    │   ├── __init__.py
    │   └── prompt_builder.py
    │
    ├── orchestration/
    │   ├── __init__.py
    │   ├── protocol.py             # Orchestrator Protocol（接口预留）
    │   └── linear_runner.py        # 第一版主驱动
    │
    ├── state/
    │   ├── __init__.py
    │   └── project_state.py
    │
    └── utils/
        ├── __init__.py
        └── git.py                  # Git 操作封装
```

---

## 二、完整代码规格

### 2.1 `capsule/contracts/models/enums.py`

```python
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
```

无 `TaskStatus` 枚举——第一版不追踪任务状态机，只记录执行历史。

---

### 2.2 五种契约 Model

每个 Model 的详细字段定义已在 `capsule_lead.md` 中给出。以下仅标注**实施时需要注意的补充规格**，不重复完整字段。

#### `role_contract.py` 补充规格

- `id` 的 pattern：`^role\.[a-z][a-z0-9_]*$`（必须以字母开头）
- `file_permissions.read` 和 `file_permissions.write`：元素为 glob 字符串，运行时用 `fnmatch` 匹配
- `prohibited_paths`：优先级高于 `file_permissions.write`。即使某路径匹配 write glob，如果同时匹配 prohibited glob，则禁写
- `confidence_threshold`：第一版保留字段但不在验证流水线中使用（因为第一版 Coder 通过 Codex CLI 执行，不直接返回 confidence_score）

#### `task_contract.py` 补充规格

- `id` 的 pattern：`^task\.[a-z][a-z0-9_.]*$`（允许多级点分，如 `task.user_auth.login_api`）
- `preconditions`：字符串列表，每项是一个契约 ID。INPUT GATE 检查这些 ID 对应的 YAML 文件是否存在且可解析
- `acceptance.behavior_contract_ref`：如为空字符串，L2 验证跳过
- `acceptance.custom_criteria`：第一版不做自动验证（需要 LLM 判断），仅注入 prompt 供 Agent 参考
- `context_refs`：字符串列表，引用的契约 ID。Prompt Builder 会加载这些契约并注入 prompt

#### `interface_contract.py` 补充规格

- `endpoints[].request.properties` 和 `endpoints[].response.success_schema.properties`：值是简化的类型描述字典，如 `{"email": {"type": "string", "format": "email"}}`。这不是完整的 JSON Schema，只是 Agent 可读的类型提示。系统不对这些做深度验证，仅原文注入 prompt。

#### `behavior_contract.py` 补充规格

- `mandatory_cases[].id` pattern：`^TC\d{3,}$`（如 TC001, TC0001）
- `test_suite.runner`：第一版支持 `pytest` 和 `jest`。其他值不报错但 L2 会跳过（输出 warning）
- `test_suite.entry`：相对于项目根目录的路径
- `coverage.minimum_percent`：第一版仅在 runner 为 `pytest` 时检查（通过 `pytest-cov`）

#### `boundary_contract.py` 补充规格

- `status` 默认 `active`，边界契约创建即生效
- `audit_rules[].check_method`：第一版只实现 `git_diff_scan`。其他值静默跳过 + warning
- `sacred_files`：glob 列表，匹配用 `fnmatch`
- `log_path`：相对于项目根目录，默认 `state/audit/boundary_violations.log`

---

### 2.3 `capsule/contracts/models/__init__.py`

```python
from .enums import ContractType, ContractStatus, ViolationAction, HttpMethod
from .role_contract import RoleContract
from .task_contract import TaskContract
from .interface_contract import InterfaceContract
from .behavior_contract import BehaviorContract
from .boundary_contract import BoundaryContract

CONTRACT_REGISTRY: dict[str, type] = {
    ContractType.ROLE:      RoleContract,
    ContractType.TASK:      TaskContract,
    ContractType.INTERFACE: InterfaceContract,
    ContractType.BEHAVIOR:  BehaviorContract,
    ContractType.BOUNDARY:  BoundaryContract,
}


def parse_contract(data: dict):
    """
    通用契约解析入口。

    Args:
        data: 从 YAML 加载的原始字典

    Returns:
        对应类型的 Pydantic Model 实例

    Raises:
        ValueError: type 字段缺失或未知
        pydantic.ValidationError: 字段校验失败
    """
    contract_type = data.get("type")
    if contract_type is None:
        raise ValueError("Contract missing required field: 'type'")
    if contract_type not in CONTRACT_REGISTRY:
        raise ValueError(
            f"Unknown contract type: '{contract_type}'. "
            f"Valid types: {list(CONTRACT_REGISTRY.keys())}"
        )
    model_class = CONTRACT_REGISTRY[contract_type]
    return model_class.model_validate(data)
```

---

### 2.4 `capsule/contracts/io.py`

```python
"""
契约文件的 YAML 读写。

约定：
  · 契约文件扩展名：.yaml（不用 .yml）
  · 文件命名：{name}.{type}.yaml，如 coder_backend.role.yaml
  · 文件必须包含 type 字段作为顶级键
  · 编码：UTF-8
"""

import yaml
from pathlib import Path
from .models import parse_contract


def load_contract(path: str | Path):
    """
    加载单份契约文件。

    Returns: 对应的 Pydantic Model 实例
    Raises:
        FileNotFoundError: 文件不存在
        yaml.YAMLError: YAML 格式错误
        ValueError: type 字段缺失或未知
        pydantic.ValidationError: 字段校验失败
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Contract file not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Contract file must be a YAML mapping, got {type(raw).__name__}: {path}")
    return parse_contract(raw)


def save_contract(contract, path: str | Path) -> Path:
    """
    将契约实例序列化为 YAML 文件。

    Args:
        contract: Pydantic Model 实例
        path: 目标文件路径

    Returns: 写入的绝对路径
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = contract.model_dump(mode="json")
    path.write_text(
        yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return path.resolve()


def load_contracts_from_dir(directory: str | Path) -> dict[str, object]:
    """
    递归加载目录下所有契约文件。

    Returns: {contract_id: contract_instance} 字典
    Raises: 不抛异常。无法解析的文件静默跳过，错误记录在返回值的 _errors 键中。
    """
    directory = Path(directory)
    contracts = {}
    errors = []

    for p in sorted(directory.rglob("*.yaml")):
        try:
            c = load_contract(p)
            contracts[c.id] = c
        except Exception as e:
            errors.append({"path": str(p), "error": str(e)})

    if errors:
        contracts["_load_errors"] = errors

    return contracts


def resolve_contract_path(contract_id: str, search_dirs: list[str | Path]) -> Path | None:
    """
    根据契约 ID 在搜索目录中查找对应文件。

    查找策略：
      1. 遍历 search_dirs 中所有 .yaml 文件
      2. 尝试 load，检查 id 是否匹配
      3. 返回第一个匹配的路径

    这是一个 O(n) 的扫描。第一版可接受。
    第二版可用索引文件加速。
    """
    for d in search_dirs:
        d = Path(d)
        if not d.exists():
            continue
        for p in d.rglob("*.yaml"):
            try:
                raw = yaml.safe_load(p.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and raw.get("id") == contract_id:
                    return p
            except Exception:
                continue
    return None
```

---

### 2.5 `capsule/utils/git.py`

```python
"""
Git 操作封装。

所有函数接收 repo_path 参数，不依赖全局状态。
使用 subprocess 调用 git 命令。
"""

import subprocess
from pathlib import Path


class GitError(Exception):
    """Git 操作失败"""
    pass


def _run_git(repo_path: str | Path, *args: str) -> str:
    """
    底层 git 命令执行器。

    Returns: stdout 文本（stripped）
    Raises: GitError
    """
    cmd = ["git", "-C", str(repo_path)] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise GitError(f"Git command timed out: {' '.join(cmd)}")

    if result.returncode != 0:
        raise GitError(
            f"Git command failed (exit {result.returncode}): {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def get_head_hash(repo_path: str | Path) -> str:
    """获取当前 HEAD 的 commit hash。"""
    return _run_git(repo_path, "rev-parse", "HEAD")


def is_clean(repo_path: str | Path) -> bool:
    """工作区是否干净（无未提交变更）。"""
    output = _run_git(repo_path, "status", "--porcelain")
    return output == ""


def stage_all(repo_path: str | Path) -> None:
    """暂存所有变更（git add -A）。"""
    _run_git(repo_path, "add", "-A")


def diff_names_from(
    repo_path: str | Path,
    from_hash: str,
    diff_filter: str | None = None,
) -> list[str]:
    """
    获取从 from_hash 到当前工作区的变更文件列表。

    Args:
        from_hash: 基准 commit hash
        diff_filter: 可选过滤器，如 "A"(新增), "M"(修改), "D"(删除)

    Returns: 相对于 repo 根目录的文件路径列表
    """
    args = ["diff", "--name-only", from_hash]
    if diff_filter:
        args.append(f"--diff-filter={diff_filter}")
    output = _run_git(repo_path, *args)
    if not output:
        return []
    return output.split("\n")


def diff_names_staged(repo_path: str | Path) -> list[str]:
    """获取已暂存的变更文件列表。"""
    output = _run_git(repo_path, "diff", "--cached", "--name-only")
    if not output:
        return []
    return output.split("\n")


def commit(repo_path: str | Path, message: str) -> str:
    """
    提交当前暂存区。

    Returns: 新 commit 的 hash
    """
    _run_git(repo_path, "commit", "-m", message)
    return get_head_hash(repo_path)


def rollback_to(repo_path: str | Path, target_hash: str) -> None:
    """
    硬回滚到指定 commit。

    ⚠️ 破坏性操作。仅在 L3 HALT 时使用。
    """
    _run_git(repo_path, "reset", "--hard", target_hash)
    _run_git(repo_path, "clean", "-fd")  # 删除未跟踪文件


def ensure_repo(repo_path: str | Path) -> None:
    """确保路径是一个 Git 仓库。不是则报错。"""
    repo = Path(repo_path)
    if not (repo / ".git").is_dir():
        raise GitError(f"Not a git repository: {repo_path}")
```

---

### 2.6 `capsule/execution/protocol.py`

```python
"""
执行层抽象协议。

核心原则：Capsule 不直接与任何特定 AI 编码工具耦合。
CodexExecutor 是第一个实现，未来可替换。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ExecutionResult:
    """执行器的统一返回结构。"""

    success: bool                           # exit_code == 0
    exit_code: int
    stdout: str
    stderr: str
    modified_files: list[str] = field(default_factory=list)
    new_files: list[str] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)
    raw_output: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0


class Executor(Protocol):
    """
    执行层协议。

    任何 AI 编码工具只需实现此协议即可接入 Capsule。
    """

    async def execute(
        self,
        prompt: str,
        working_dir: str,
        timeout_seconds: int = 300,
    ) -> ExecutionResult:
        """
        执行一次编码任务。

        Args:
            prompt: 完整任务 prompt
            working_dir: 工作目录（所有文件操作相对于此目录）
            timeout_seconds: 超时时间

        Returns: ExecutionResult

        不应抛出异常。执行失败通过 ExecutionResult.success=False 表达。
        """
        ...
```

---

### 2.7 `capsule/execution/codex_executor.py`

```python
"""
Codex CLI 执行器。

调用方式：
  codex exec --full-auto --json "{prompt}"

工作流：
  1. 确认工作目录是 git repo 且工作区干净
  2. 记录 HEAD hash 作为快照
  3. subprocess 调用 codex exec
  4. 收集 stdout/stderr
  5. 通过 git diff 获取实际文件变更
  6. 组装 ExecutionResult

注意事项：
  · Codex CLI 要求在 git 仓库内运行
  · --json 输出的具体结构可能因版本变化，解析需宽容
  · 不使用 --dangerously-bypass-approvals-and-sandbox
"""

import asyncio
import json
import time
from pathlib import Path

from ..utils.git import (
    ensure_repo,
    is_clean,
    get_head_hash,
    diff_names_from,
    stage_all,
)
from .protocol import ExecutionResult


class CodexExecutor:
    """Codex CLI subprocess 封装。"""

    def __init__(
        self,
        codex_binary: str = "codex",
        model: str | None = None,      # 默认使用 Codex CLI 自身默认模型
        sandbox_mode: str = "workspace-write",
    ):
        self.codex_binary = codex_binary
        self.model = model
        self.sandbox_mode = sandbox_mode

    async def execute(
        self,
        prompt: str,
        working_dir: str,
        timeout_seconds: int = 300,
    ) -> ExecutionResult:

        repo_path = Path(working_dir).resolve()
        ensure_repo(repo_path)

        # ── Step 1: 记录执行前快照 ──
        snapshot_hash = get_head_hash(repo_path)

        # ── Step 2: 构建命令 ──
        cmd = [
            self.codex_binary, "exec",
            "--full-auto",
            "--sandbox", self.sandbox_mode,
            "--json",
            prompt,
        ]
        if self.model:
            cmd.insert(2, f"--model={self.model}")

        # ── Step 3: 执行 ──
        start_time = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_seconds,
            )
            exit_code = proc.returncode or 0
        except asyncio.TimeoutError:
            # 超时：尝试终止进程
            try:
                proc.terminate()
                await asyncio.sleep(2)
                proc.kill()
            except Exception:
                pass
            return ExecutionResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr="TIMEOUT: Codex CLI exceeded time limit",
                duration_seconds=timeout_seconds,
            )
        except FileNotFoundError:
            return ExecutionResult(
                success=False,
                exit_code=-2,
                stdout="",
                stderr=f"Codex CLI binary not found: {self.codex_binary}",
                duration_seconds=0.0,
            )

        duration = time.monotonic() - start_time
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        # ── Step 4: 解析 JSON 输出 ──
        raw_output = {}
        try:
            raw_output = json.loads(stdout)
        except (json.JSONDecodeError, ValueError):
            raw_output = {"_raw_stdout": stdout}

        # ── Step 5: 暂存变更并收集文件列表 ──
        stage_all(repo_path)
        modified = diff_names_from(repo_path, snapshot_hash, diff_filter="M")
        new = diff_names_from(repo_path, snapshot_hash, diff_filter="A")
        deleted = diff_names_from(repo_path, snapshot_hash, diff_filter="D")

        # 注意：此处只 stage，不 commit。
        # commit 由 LinearRunner 在验证通过后执行。
        # 如果验证失败，变更保留在工作区（L0-L2 策略）。

        return ExecutionResult(
            success=(exit_code == 0),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            modified_files=modified,
            new_files=new,
            deleted_files=deleted,
            raw_output=raw_output,
            duration_seconds=round(duration, 2),
        )
```

**实现时注意：** `stage_all` 后再做 `diff_names_from(snapshot_hash)` 能捕获到所有变更（包括新增文件）。但 `diff_names_from` 实际比较的是 `snapshot_hash` 和当前暂存区的差异。需要确保 `diff_names_from` 的实现使用 `git diff --cached` 或者 `git diff {hash} --staged`，或者直接 `git diff {hash}` 在 stage_all 之后两者等价。建议实现时用 `git diff {hash} HEAD` 不行（因为没 commit），应该用 `git diff {hash} --cached --name-only --diff-filter=X`。

**修正：** `_run_git(repo_path, "diff", "--cached", "--name-only", "--diff-filter="+filter, snapshot_hash)` 这样在 stage_all 之后可以正确获取相对于 snapshot_hash 的暂存变更。请在 `git.py` 中新增一个函数或修改 `diff_names_from` 使其支持 `--cached` 模式。

---

### 2.8 `capsule/execution/mock_executor.py`

```python
"""
Mock 执行器。

用途：
  1. Capsule 自身的测试（不依赖 Codex CLI）
  2. 开发者调试验证流水线

工作方式：
  · 不调用任何 AI
  · 将 mock_dir 中的文件复制到 working_dir
  · 模拟 Agent "产出"了这些文件
"""

import shutil
import time
from pathlib import Path

from ..utils.git import get_head_hash, diff_names_from, stage_all, ensure_repo
from .protocol import ExecutionResult


class MockExecutor:
    """
    模拟执行器。

    Args:
        mock_source_dir: 包含预设"产出"文件的目录。
                         执行时将此目录内容复制到 working_dir 对应位置。
        simulate_failure: 如果为 True，返回 exit_code=1
    """

    def __init__(
        self,
        mock_source_dir: str | Path,
        simulate_failure: bool = False,
    ):
        self.mock_source_dir = Path(mock_source_dir)
        self.simulate_failure = simulate_failure

    async def execute(
        self,
        prompt: str,
        working_dir: str,
        timeout_seconds: int = 300,
    ) -> ExecutionResult:

        repo_path = Path(working_dir).resolve()
        ensure_repo(repo_path)
        snapshot_hash = get_head_hash(repo_path)

        start_time = time.monotonic()

        # 复制 mock 文件到工作目录
        if self.mock_source_dir.exists():
            for src_file in self.mock_source_dir.rglob("*"):
                if src_file.is_file():
                    rel = src_file.relative_to(self.mock_source_dir)
                    dst = repo_path / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst)

        duration = time.monotonic() - start_time

        # 收集变更
        stage_all(repo_path)
        modified = diff_names_from(repo_path, snapshot_hash, diff_filter="M")
        new = diff_names_from(repo_path, snapshot_hash, diff_filter="A")

        exit_code = 1 if self.simulate_failure else 0

        return ExecutionResult(
            success=(exit_code == 0),
            exit_code=exit_code,
            stdout='{"mock": true}',
            stderr="",
            modified_files=modified,
            new_files=new,
            deleted_files=[],
            raw_output={"mock": True, "prompt_received": prompt[:200]},
            duration_seconds=round(duration, 2),
        )
```

---

### 2.9 `capsule/validation/pipeline.py`

```python
"""
验证流水线：数据结构 + 串联入口。

短路规则：
  L0 失败 → 停止，返回 reject
  L1 失败 → 停止，返回 reject
  L2 失败 → 停止，返回 reject
  L3 失败 → 停止，返回 HALT

每一层内部所有检查项全部执行（不短路），汇总后判断该层是否通过。
层与层之间短路。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import StrEnum
from datetime import datetime, timezone


class GateVerdict(StrEnum):
    PASSED = "passed"
    REJECTED = "rejected"           # L0-L2，可重试
    HALTED = "halted"               # L3，不可重试


@dataclass
class CheckDetail:
    """单条检查的结果。"""
    check_id: str                   # 如 "l1.scope_include"
    passed: bool
    expected: str                   # 人类可读
    actual: str                     # 人类可读
    hint: str                       # 给 Agent 的修复建议

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "passed": self.passed,
            "expected": self.expected,
            "actual": self.actual,
            "hint": self.hint,
        }


@dataclass
class LevelResult:
    """单个验证层的结果。"""
    level: int                      # 0, 1, 2, 3
    passed: bool
    checks: list[CheckDetail] = field(default_factory=list)

    @property
    def failed_checks(self) -> list[CheckDetail]:
        return [c for c in self.checks if not c.passed]


@dataclass
class ValidationResult:
    """完整验证流水线的结果。"""
    verdict: GateVerdict
    level_results: list[LevelResult] = field(default_factory=list)
    halted: bool = False
    failed_level: int | None = None
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def all_failed_checks(self) -> list[CheckDetail]:
        result = []
        for lr in self.level_results:
            result.extend(lr.failed_checks)
        return result


@dataclass
class RejectionReport:
    """
    打回报告。

    由 ValidationResult 生成，用于注入下一轮 Agent prompt。
    """
    rejection_id: str               # "REJ-{YYYYMMDD-HHmmss}-{retry_count}"
    task_id: str
    target_role: str
    retry_count: int
    max_retries: int
    failed_level: int
    failed_checks: list[dict]       # CheckDetail.to_dict() 列表
    timestamp: str

    def to_prompt_section(self) -> str:
        """
        格式化为可注入 prompt 的文本。

        输出格式：

        ⚠️ PREVIOUS ATTEMPT FAILED (attempt {n}/{max})

        Failed checks:
        1. [{level}] {check_id}: FAILED
           Expected: ...
           Actual:   ...
           Fix hint: ...

        2. ...
        """
        lines = [
            f"⚠️ PREVIOUS ATTEMPT FAILED (attempt {self.retry_count}/{self.max_retries})",
            "",
            "Failed checks:",
        ]
        for i, check in enumerate(self.failed_checks, 1):
            lines.append(f"{i}. [L{self.failed_level}] {check['check_id']}: FAILED")
            lines.append(f"   Expected: {check['expected']}")
            lines.append(f"   Actual:   {check['actual']}")
            lines.append(f"   Fix hint: {check['hint']}")
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def from_validation_result(
        vr: ValidationResult,
        task_id: str,
        target_role: str,
        retry_count: int,
        max_retries: int,
    ) -> "RejectionReport":
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return RejectionReport(
            rejection_id=f"REJ-{ts}-{retry_count}",
            task_id=task_id,
            target_role=target_role,
            retry_count=retry_count,
            max_retries=max_retries,
            failed_level=vr.failed_level or 0,
            failed_checks=[c.to_dict() for c in vr.all_failed_checks],
            timestamp=vr.timestamp,
        )
```

---

### 2.10 `capsule/validation/l0_structural.py`

```python
"""
L0: 格式校验。

在 OUTPUT GATE 中，L0 检查的是 Agent 执行的基本完整性，不是契约格式。
（契约格式在 INPUT GATE 的 load_contract 阶段已经检查过了。）

检查项：
  1. ExecutionResult.success 是否为 True（exit_code == 0）
  2. 变更文件列表是否非空（Agent 确实做了什么）
"""

from .pipeline import LevelResult, CheckDetail
from ..execution.protocol import ExecutionResult


def run_l0(execution_result: ExecutionResult) -> LevelResult:
    checks = []

    # CHECK 1: 执行成功
    checks.append(CheckDetail(
        check_id="l0.exit_code",
        passed=execution_result.success,
        expected="exit_code == 0",
        actual=f"exit_code == {execution_result.exit_code}",
        hint=(
            "Codex CLI 执行失败。检查 stderr 获取详细信息。"
            if not execution_result.success else ""
        ),
    ))

    # CHECK 2: 有文件变更
    all_changes = (
        execution_result.modified_files
        + execution_result.new_files
    )
    has_changes = len(all_changes) > 0
    checks.append(CheckDetail(
        check_id="l0.has_changes",
        passed=has_changes,
        expected="至少修改或创建一个文件",
        actual=f"变更文件数: {len(all_changes)}",
        hint="Agent 未做出任何文件变更。请检查任务描述是否足够明确。",
    ))

    return LevelResult(
        level=0,
        passed=all(c.passed for c in checks),
        checks=checks,
    )
```

---

### 2.11 `capsule/validation/l1_consistency.py`

```python
"""
L1: 结构一致性。

检查 Agent 的文件变更是否在授权范围内。
所有检查基于 git diff 得到的文件列表，不检查文件内容。

检查项：
  1. scope_include: 所有变更文件在 task.scope.include 范围内
  2. scope_exclude: 无变更文件匹配 task.scope.exclude
  3. role_write_permission: 所有变更文件在 role.file_permissions.write 范围内
  4. max_new_files: 新增文件数不超过上限
  5. prohibited_paths: 无变更文件匹配 role.prohibited_paths
"""

from fnmatch import fnmatch
from .pipeline import LevelResult, CheckDetail
from ..execution.protocol import ExecutionResult


def _matches_any(filepath: str, patterns: list[str]) -> bool:
    """文件路径是否匹配任一 glob 模式。"""
    return any(fnmatch(filepath, p) for p in patterns)


def _find_violations(files: list[str], patterns: list[str], should_match: bool) -> list[str]:
    """
    Args:
        should_match: True = 文件应该匹配至少一个 pattern（白名单模式）
                      False = 文件不应匹配任何 pattern（黑名单模式）
    Returns: 违规文件列表
    """
    violations = []
    for f in files:
        matched = _matches_any(f, patterns)
        if should_match and not matched:
            violations.append(f)
        elif not should_match and matched:
            violations.append(f)
    return violations


def run_l1(
    execution_result: ExecutionResult,
    task_contract,          # TaskContract 实例
    role_contract,          # RoleContract 实例
) -> LevelResult:
    checks = []
    all_changed = execution_result.modified_files + execution_result.new_files

    # CHECK 1: scope_include
    if task_contract.scope.include:
        violations = _find_violations(all_changed, task_contract.scope.include, should_match=True)
        checks.append(CheckDetail(
            check_id="l1.scope_include",
            passed=len(violations) == 0,
            expected=f"所有变更文件应匹配: {task_contract.scope.include}",
            actual=f"超出范围的文件: {violations}" if violations else "全部在范围内",
            hint=f"以下文件不在任务允许范围内，请勿修改: {violations}",
        ))

    # CHECK 2: scope_exclude
    if task_contract.scope.exclude:
        violations = _find_violations(all_changed, task_contract.scope.exclude, should_match=False)
        checks.append(CheckDetail(
            check_id="l1.scope_exclude",
            passed=len(violations) == 0,
            expected=f"无文件应匹配排除规则: {task_contract.scope.exclude}",
            actual=f"触碰了排除文件: {violations}" if violations else "未触碰排除文件",
            hint=f"以下文件被明确排除，不得修改: {violations}",
        ))

    # CHECK 3: role_write_permission
    write_perms = role_contract.file_permissions.write
    if write_perms:
        violations = _find_violations(all_changed, write_perms, should_match=True)
        checks.append(CheckDetail(
            check_id="l1.role_write_permission",
            passed=len(violations) == 0,
            expected=f"所有变更文件应在角色可写范围: {write_perms}",
            actual=f"越权写入: {violations}" if violations else "全部在授权范围内",
            hint=f"你无权写入以下文件: {violations}",
        ))

    # CHECK 4: max_new_files
    new_count = len(execution_result.new_files)
    max_new = task_contract.acceptance.max_new_files
    checks.append(CheckDetail(
        check_id="l1.max_new_files",
        passed=new_count <= max_new,
        expected=f"新增文件数 <= {max_new}",
        actual=f"新增文件数: {new_count}",
        hint=f"新增文件过多（{new_count} > {max_new}），请精简实现。",
    ))

    # CHECK 5: prohibited_paths
    if role_contract.prohibited_paths:
        violations = _find_violations(
            all_changed, role_contract.prohibited_paths, should_match=False
        )
        checks.append(CheckDetail(
            check_id="l1.prohibited_paths",
            passed=len(violations) == 0,
            expected=f"无文件应匹配禁止路径: {role_contract.prohibited_paths}",
            actual=f"触碰禁止路径: {violations}" if violations else "未触碰禁止路径",
            hint=f"以下路径被角色契约禁止写入: {violations}",
        ))

    return LevelResult(
        level=1,
        passed=all(c.passed for c in checks),
        checks=checks,
    )
```

---

### 2.12 `capsule/validation/l2_behavioral.py`

```python
"""
L2: 行为验证。

运行测试套件，检查 mandatory_cases 是否通过。

第一版实现策略：
  · 支持 pytest（主要）和 jest（基础支持）
  · 通过 subprocess 执行测试命令
  · 解析退出码：0 = 全通过，非 0 = 有失败
  · pytest: 使用 --tb=short -v 获取可读输出
  · 匹配 mandatory_cases：从 pytest -v 输出中查找每个 test case id
  · 覆盖率：可选，使用 pytest-cov

如果 task_contract.acceptance.behavior_contract_ref 为空，L2 直接 PASS。
"""

import subprocess
from pathlib import Path
from .pipeline import LevelResult, CheckDetail


def run_l2(
    working_dir: str,
    behavior_contract=None,     # BehaviorContract 实例，可为 None
) -> LevelResult:
    # 无行为契约绑定 → 跳过
    if behavior_contract is None:
        return LevelResult(
            level=2,
            passed=True,
            checks=[CheckDetail(
                check_id="l2.skipped",
                passed=True,
                expected="No behavior contract bound",
                actual="L2 skipped",
                hint="",
            )],
        )

    checks = []
    suite = behavior_contract.test_suite

    # ── Step 1: Setup（如有）──
    if suite.setup_cmd:
        setup_result = subprocess.run(
            suite.setup_cmd,
            shell=True,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if setup_result.returncode != 0:
            checks.append(CheckDetail(
                check_id="l2.setup",
                passed=False,
                expected="测试环境搭建成功 (exit 0)",
                actual=f"setup_cmd 失败 (exit {setup_result.returncode}): {setup_result.stderr[:500]}",
                hint=f"测试前置命令失败: {suite.setup_cmd}",
            ))
            return LevelResult(level=2, passed=False, checks=checks)

    # ── Step 2: 运行测试 ──
    test_entry = str(Path(working_dir) / suite.entry)

    if suite.runner == "pytest":
        cmd = [
            "python", "-m", "pytest",
            test_entry,
            "-v",
            "--tb=short",
            "--no-header",
        ]
        # 覆盖率（如配置了）
        cov_target = str(Path(suite.entry).parent)
        if behavior_contract.coverage.minimum_percent > 0:
            cmd.extend([
                f"--cov={cov_target}",
                "--cov-report=term-missing",
            ])
    elif suite.runner == "jest":
        cmd = ["npx", "jest", test_entry, "--verbose"]
    else:
        checks.append(CheckDetail(
            check_id="l2.unsupported_runner",
            passed=True,    # 不阻断，只警告
            expected=f"Runner '{suite.runner}' supported",
            actual=f"Runner '{suite.runner}' not supported in v1, L2 skipped",
            hint="",
        ))
        return LevelResult(level=2, passed=True, checks=checks)

    try:
        test_result = subprocess.run(
            cmd,
            cwd=working_dir,
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        checks.append(CheckDetail(
            check_id="l2.timeout",
            passed=False,
            expected="测试在 180 秒内完成",
            actual="测试超时",
            hint="测试执行超时，检查是否有死循环或长时间阻塞。",
        ))
        return LevelResult(level=2, passed=False, checks=checks)

    test_output = test_result.stdout + "\n" + test_result.stderr

    # ── Step 3: 逐条检查 mandatory_cases ──
    for tc in behavior_contract.mandatory_cases:
        # 在 pytest -v 输出中查找 test case
        # pytest -v 输出格式: "test_file.py::test_function_name PASSED/FAILED"
        # 我们用 tc.id 或 tc.description 的关键词在输出中匹配
        # 这是简化策略，第二版可用 pytest-json-report 做精确匹配
        tc_found = tc.id.lower() in test_output.lower() or tc.description.lower() in test_output.lower()

        if not tc_found and test_result.returncode == 0:
            # 测试全部通过但没找到特定 case —— 可能命名不匹配
            # 第一版宽容处理：如果整体通过，不单独判定
            checks.append(CheckDetail(
                check_id=f"l2.case.{tc.id}",
                passed=True,
                expected=f"{tc.id}: {tc.description}",
                actual="整体测试通过（未精确匹配到此 case）",
                hint="",
            ))
        elif not tc_found and test_result.returncode != 0:
            checks.append(CheckDetail(
                check_id=f"l2.case.{tc.id}",
                passed=False if tc.must_pass else True,
                expected=f"{tc.id}: {tc.description} — PASSED",
                actual="测试失败且未精确匹配到此 case",
                hint=f"请确保实现满足: {tc.description}",
            ))
        else:
            # 找到了，检查是 PASSED 还是 FAILED
            is_passed = f"{tc.id}" in test_output and "PASSED" in test_output
            # 简化判断：如果整体 exit_code == 0，视为全 passed
            is_passed = is_passed or test_result.returncode == 0
            checks.append(CheckDetail(
                check_id=f"l2.case.{tc.id}",
                passed=is_passed if tc.must_pass else True,
                expected=f"{tc.id}: {tc.description} — PASSED",
                actual="PASSED" if is_passed else "FAILED",
                hint="" if is_passed else f"测试未通过: {tc.description}",
            ))

    # ── Step 4: 整体退出码检查 ──
    checks.append(CheckDetail(
        check_id="l2.overall",
        passed=test_result.returncode == 0,
        expected="所有测试通过 (exit 0)",
        actual=f"exit code: {test_result.returncode}",
        hint=f"测试输出（截断）:\n{test_output[:1500]}" if test_result.returncode != 0 else "",
    ))

    return LevelResult(
        level=2,
        passed=all(c.passed for c in checks),
        checks=checks,
    )
```

---

### 2.13 `capsule/validation/l3_boundary.py`

```python
"""
L3: 边界审计。

最严厉的验证层。失败 = HALT（立即终止，不可重试）。

检查 Agent 的文件变更是否触碰了任何边界契约中的 sacred_files。

执行后果：
  · 写入不可变审计日志
  · 调用方负责 git rollback
"""

from fnmatch import fnmatch
from datetime import datetime, timezone
from pathlib import Path

from .pipeline import LevelResult, CheckDetail
from ..execution.protocol import ExecutionResult


def _append_audit_log(log_path: str, entry: str) -> None:
    """追加写入审计日志。逐行 flush，保证原子性。"""
    p = Path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(entry + "\n")
        f.flush()


def run_l3(
    execution_result: ExecutionResult,
    boundary_contracts: list,       # list[BoundaryContract]
    audit_log_path: str = "state/audit/boundary_violations.log",
) -> LevelResult:
    checks = []
    all_changed = (
        execution_result.modified_files
        + execution_result.new_files
        + execution_result.deleted_files
    )

    for bc in boundary_contracts:
        for filepath in all_changed:
            for sacred_pattern in bc.sacred_files:
                if fnmatch(filepath, sacred_pattern):
                    # ── VIOLATION ──
                    timestamp = datetime.now(timezone.utc).isoformat()
                    log_entry = (
                        f"{timestamp} | HALT | {bc.id} | "
                        f"sacred_file_violated | {filepath} | "
                        f"matched pattern: {sacred_pattern}"
                    )
                    _append_audit_log(audit_log_path, log_entry)

                    checks.append(CheckDetail(
                        check_id=f"l3.sacred.{bc.id}",
                        passed=False,
                        expected=f"文件 {filepath} 不得被修改（sacred pattern: {sacred_pattern}）",
                        actual=f"文件 {filepath} 被修改",
                        hint="BOUNDARY VIOLATION: 此文件受边界契约保护，不可修改。系统将回滚所有变更。",
                    ))

    # 如无违规
    if not checks:
        checks.append(CheckDetail(
            check_id="l3.clean",
            passed=True,
            expected="无边界违规",
            actual="无边界违规",
            hint="",
        ))

    return LevelResult(
        level=3,
        passed=all(c.passed for c in checks),
        checks=checks,
    )
```

---

### 2.14 验证流水线串联

在 `pipeline.py` 中增加串联函数：

```python
# ═══════════════════════════════════════════════════════
# 在 pipeline.py 末尾添加
# ═══════════════════════════════════════════════════════

from .l0_structural import run_l0
from .l1_consistency import run_l1
from .l2_behavioral import run_l2
from .l3_boundary import run_l3


def run_output_gate(
    execution_result,           # ExecutionResult
    task_contract,              # TaskContract
    role_contract,              # RoleContract
    boundary_contracts: list,   # list[BoundaryContract]
    behavior_contract=None,     # BehaviorContract | None
    working_dir: str = ".",
    audit_log_path: str = "state/audit/boundary_violations.log",
) -> ValidationResult:
    """
    四级验证流水线。层间短路，层内全跑。

    Returns: ValidationResult
    """
    level_results = []

    # ── L0 ──
    l0 = run_l0(execution_result)
    level_results.append(l0)
    if not l0.passed:
        return ValidationResult(
            verdict=GateVerdict.REJECTED,
            level_results=level_results,
            failed_level=0,
        )

    # ── L1 ──
    l1 = run_l1(execution_result, task_contract, role_contract)
    level_results.append(l1)
    if not l1.passed:
        return ValidationResult(
            verdict=GateVerdict.REJECTED,
            level_results=level_results,
            failed_level=1,
        )

    # ── L2 ──
    l2 = run_l2(working_dir, behavior_contract)
    level_results.append(l2)
    if not l2.passed:
        return ValidationResult(
            verdict=GateVerdict.REJECTED,
            level_results=level_results,
            failed_level=2,
        )

    # ── L3 ──
    l3 = run_l3(execution_result, boundary_contracts, audit_log_path)
    level_results.append(l3)
    if not l3.passed:
        return ValidationResult(
            verdict=GateVerdict.HALTED,
            level_results=level_results,
            halted=True,
            failed_level=3,
        )

    # ── ALL PASSED ──
    return ValidationResult(
        verdict=GateVerdict.PASSED,
        level_results=level_results,
    )
```

---

### 2.15 `capsule/agents/prompt_builder.py`

```python
"""
Prompt 组装器。

原则：
  · Agent 是无状态函数，每次调用携带完整上下文
  · Prompt 按固定分区组织，每区职责明确
  · 每次生成的 prompt 写入日志文件，可审计
  · 第一版使用代码拼接（f-string），不用模板引擎

分区结构：
  Section 1: ROLE IDENTITY
  Section 2: HARD CONSTRAINTS
  Section 3: PROJECT CONTEXT
  Section 4: INTERFACE CONTRACT
  Section 5: TASK SPECIFICATION
  Section 6: TEST SPECIFICATION
  Section 7: REJECTION HISTORY（仅重试时）
  Section 8: OUTPUT INSTRUCTION
"""

from pathlib import Path
from datetime import datetime, timezone
import yaml


def build_coder_prompt(
    task_contract,                          # TaskContract 实例
    role_contract,                          # RoleContract 实例
    interface_contract=None,                # InterfaceContract 实例 | None
    behavior_contract=None,                 # BehaviorContract 实例 | None
    project_conventions: dict | None = None,
    context_contracts: list | None = None,  # context_refs 解析后的契约实例列表
    rejection_history: list | None = None,  # list[RejectionReport]
) -> str:

    sections = []

    # ── Section 1: ROLE IDENTITY ──
    sections.append(
        f"# Role: {role_contract.display_name}\n\n"
        f"{role_contract.description}\n"
    )

    # ── Section 2: HARD CONSTRAINTS ──
    constraints = [
        "# ⛔ HARD CONSTRAINTS — MUST NOT VIOLATE",
        "",
        "## Writable paths (ONLY these paths may be created or modified):",
    ]
    for p in role_contract.file_permissions.write:
        constraints.append(f"  - {p}")

    constraints.append("")
    constraints.append("## Prohibited paths (NEVER touch these):")
    for p in role_contract.prohibited_paths:
        constraints.append(f"  - ⛔ {p}")

    if task_contract.scope.exclude:
        constraints.append("")
        constraints.append("## Excluded from this task:")
        for p in task_contract.scope.exclude:
            constraints.append(f"  - {p}")

    if task_contract.forbidden_actions:
        constraints.append("")
        constraints.append("## Forbidden actions:")
        for a in task_contract.forbidden_actions:
            constraints.append(f"  - ⛔ {a}")

    constraints.append("")
    constraints.append(f"## Max new files allowed: {task_contract.acceptance.max_new_files}")

    sections.append("\n".join(constraints))

    # ── Section 3: PROJECT CONTEXT ──
    if project_conventions:
        ctx_lines = ["# Project Conventions", ""]
        for k, v in project_conventions.items():
            ctx_lines.append(f"- {k}: {v}")
        sections.append("\n".join(ctx_lines))

    # ── Section 4: INTERFACE CONTRACT ──
    if interface_contract:
        ic_dump = interface_contract.model_dump(mode="json", exclude={"extensions", "created_at"})
        ic_yaml = yaml.dump(ic_dump, allow_unicode=True, sort_keys=False, default_flow_style=False)
        sections.append(
            "# Interface Contract (MUST comply strictly)\n\n"
            f"```yaml\n{ic_yaml}```"
        )

    # ── Section 5: TASK SPECIFICATION ──
    task_lines = [
        "# Task Specification",
        "",
        f"**Task ID:** {task_contract.id}",
        f"**Description:** {task_contract.description}",
        "",
        "## Scope (files you should work on):",
    ]
    for p in task_contract.scope.include:
        task_lines.append(f"  - {p}")
    if task_contract.scope.create_allowed:
        task_lines.append("")
        task_lines.append("## Directories where you may create new files:")
        for p in task_contract.scope.create_allowed:
            task_lines.append(f"  - {p}")
    if task_contract.acceptance.custom_criteria:
        task_lines.append("")
        task_lines.append("## Additional acceptance criteria:")
        for c in task_contract.acceptance.custom_criteria:
            task_lines.append(f"  - {c}")
    sections.append("\n".join(task_lines))

    # ── Section 6: TEST SPECIFICATION ──
    if behavior_contract:
        test_lines = [
            "# Tests Your Code Must Pass",
            "",
            f"Test runner: {behavior_contract.test_suite.runner}",
            f"Test file: {behavior_contract.test_suite.entry}",
            "",
            "## Mandatory test cases:",
        ]
        for tc in behavior_contract.mandatory_cases:
            marker = "🔴 MUST PASS" if tc.must_pass else "🟡 optional"
            test_lines.append(f"  - [{tc.id}] {tc.description} ({marker})")

        test_lines.append("")
        test_lines.append(
            f"Minimum coverage: {behavior_contract.coverage.minimum_percent}%"
        )
        sections.append("\n".join(test_lines))

    # ── Section 6.5: CONTEXT CONTRACTS ──
    if context_contracts:
        for cc in context_contracts:
            cc_dump = cc.model_dump(mode="json", exclude={"extensions", "created_at"})
            cc_yaml = yaml.dump(cc_dump, allow_unicode=True, sort_keys=False, default_flow_style=False)
            sections.append(
                f"# Reference: {cc.id}\n\n"
                f"```yaml\n{cc_yaml}```"
            )

    # ── Section 7: REJECTION HISTORY ──
    if rejection_history:
        sections.append("# ⚠️ Previous Attempt Results\n")
        for rr in rejection_history:
            sections.append(rr.to_prompt_section())

    # ── Section 8: OUTPUT INSTRUCTION ──
    sections.append(
        "# Output Instructions\n\n"
        "1. Implement the task as specified above.\n"
        "2. Ensure all modified files are saved.\n"
        "3. Do NOT modify any files outside the writable paths.\n"
        "4. Do NOT perform any actions listed as forbidden.\n"
        "5. When finished, stop. Do not add extra features or refactoring.\n"
    )

    return "\n\n---\n\n".join(sections)


def save_prompt_log(
    prompt: str,
    task_id: str,
    attempt: int,
    log_dir: str = "state/prompts",
) -> Path:
    """
    将 prompt 写入日志文件。

    路径: {log_dir}/{task_id}_attempt_{n}.md
    """
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    filename = f"{task_id}_attempt_{attempt}.md"
    filepath = log_path / filename
    filepath.write_text(prompt, encoding="utf-8")
    return filepath
```

---

### 2.16 `capsule/state/project_state.py`

```python
"""
PROJECT_STATE.json 管理。

第一版简化版：只维护全局约定和执行历史。
不追踪模块状态机（第二版做）。
"""

import json
from pathlib import Path
from datetime import datetime, timezone


DEFAULT_STATE = {
    "project_id": "",
    "capsule_version": "0.1.0",
    "global_conventions": {},
    "execution_history": [],
}


class ProjectState:
    def __init__(self, state_path: str = "state/PROJECT_STATE.json"):
        self.path = Path(state_path)
        self._data: dict = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self._data = DEFAULT_STATE.copy()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @property
    def conventions(self) -> dict:
        return self._data.get("global_conventions", {})

    def append_execution(
        self,
        task_id: str,
        role: str,
        attempts: int,
        result: str,        # "passed" | "rejected" | "halted" | "circuit_break"
    ) -> None:
        self._data.setdefault("execution_history", []).append({
            "task_id": task_id,
            "role": role,
            "attempts": attempts,
            "final_result": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self.save()
```

---

### 2.17 `capsule/orchestration/linear_runner.py`

这是第一版的核心驱动器。

```python
"""
LinearRunner: 第一版的直线型编排器。

流程：
  INPUT GATE → [PROMPT → EXECUTE → OUTPUT GATE → (retry?)] → RESULT

不使用 pydantic-graph。纯 async 函数。
"""

import asyncio
from pathlib import Path
from datetime import datetime, timezone

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..contracts.io import load_contract, resolve_contract_path
from ..contracts.models.enums import ContractType, ViolationAction
from ..execution.protocol import Executor, ExecutionResult
from ..validation.pipeline import (
    run_output_gate,
    ValidationResult,
    GateVerdict,
    RejectionReport,
)
from ..agents.prompt_builder import build_coder_prompt, save_prompt_log
from ..state.project_state import ProjectState
from ..utils.git import (
    ensure_repo,
    is_clean,
    get_head_hash,
    commit,
    rollback_to,
    stage_all,
)

console = Console()


async def run_task(
    task_contract_path: str,
    executor: Executor,
    project_dir: str = ".",
    state_path: str = "state/PROJECT_STATE.json",
    dry_run: bool = False,
    verbose: bool = False,
) -> None:
    """
    执行单个任务的完整闭环。

    Args:
        task_contract_path: 任务契约 YAML 文件路径
        executor: 执行器实例（CodexExecutor 或 MockExecutor）
        project_dir: 项目根目录
        state_path: PROJECT_STATE.json 路径
        dry_run: 只生成 prompt，不执行
        verbose: 详细输出
    """

    project_dir = str(Path(project_dir).resolve())
    state = ProjectState(state_path)

    # ═══════════════════════════════════════════
    # PHASE 1: LOAD & INPUT GATE
    # ═══════════════════════════════════════════

    console.print("\n[bold blue]═══ PHASE 1: INPUT GATE ═══[/bold blue]\n")

    # 1.1 加载任务契约
    task_contract = load_contract(task_contract_path)
    assert task_contract.type == ContractType.TASK, (
        f"Expected task contract, got {task_contract.type}"
    )
    console.print(f"  ✅ Task contract loaded: [bold]{task_contract.id}[/bold]")

    # 1.2 搜索目录配置
    search_dirs = [
        Path(project_dir) / "roles",
        Path(project_dir) / "contracts" / "boundaries",
        Path(project_dir) / "contracts" / "instances",
    ]

    # 1.3 加载角色契约
    role_path = resolve_contract_path(task_contract.assigned_to, search_dirs)
    if role_path is None:
        console.print(f"  ❌ Role contract not found: {task_contract.assigned_to}")
        return
    role_contract = load_contract(role_path)
    console.print(f"  ✅ Role contract loaded: [bold]{role_contract.id}[/bold]")

    # 1.4 加载边界契约
    boundary_dir = Path(project_dir) / "contracts" / "boundaries"
    boundary_contracts = []
    if boundary_dir.exists():
        for bp in boundary_dir.rglob("*.yaml"):
            try:
                bc = load_contract(bp)
                if bc.type == ContractType.BOUNDARY:
                    boundary_contracts.append(bc)
            except Exception:
                pass
    console.print(f"  ✅ Boundary contracts loaded: {len(boundary_contracts)}")

    # 1.5 加载接口契约（如引用）
    interface_contract = None
    behavior_contract = None

    # 从 preconditions 和 context_refs 中查找
    for ref_id in task_contract.preconditions + task_contract.context_refs:
        ref_path = resolve_contract_path(ref_id, search_dirs)
        if ref_path:
            ref_contract = load_contract(ref_path)
            if ref_contract.type == ContractType.INTERFACE:
                interface_contract = ref_contract
            elif ref_contract.type == ContractType.BEHAVIOR:
                behavior_contract = ref_contract
        else:
            console.print(f"  ⚠️  Referenced contract not found: {ref_id}")

    # 1.6 通过 acceptance.behavior_contract_ref 加载行为契约
    if (
        behavior_contract is None
        and task_contract.acceptance.behavior_contract_ref
    ):
        ref_path = resolve_contract_path(
            task_contract.acceptance.behavior_contract_ref,
            search_dirs,
        )
        if ref_path:
            behavior_contract = load_contract(ref_path)
            console.print(f"  ✅ Behavior contract loaded: [bold]{behavior_contract.id}[/bold]")
        else:
            console.print(
                f"  ⚠️  Behavior contract not found: "
                f"{task_contract.acceptance.behavior_contract_ref}"
            )

    # 1.7 加载 context_refs 中的其他契约（注入 prompt 用）
    context_contracts = []
    for ref_id in task_contract.context_refs:
        ref_path = resolve_contract_path(ref_id, search_dirs)
        if ref_path:
            try:
                cc = load_contract(ref_path)
                context_contracts.append(cc)
            except Exception:
                pass

    # 1.8 Git 检查
    ensure_repo(project_dir)

    console.print("\n  [green]INPUT GATE PASSED[/green]\n")

    # ═══════════════════════════════════════════
    # RETRY LOOP
    # ═══════════════════════════════════════════

    max_retries = task_contract.max_retries
    rejection_history: list[RejectionReport] = []

    for attempt in range(1, max_retries + 1):

        console.print(f"\n[bold blue]═══ ATTEMPT {attempt}/{max_retries} ═══[/bold blue]\n")

        # ═══════════════════════════════════════
        # PHASE 2: PROMPT ASSEMBLY
        # ═══════════════════════════════════════

        prompt = build_coder_prompt(
            task_contract=task_contract,
            role_contract=role_contract,
            interface_contract=interface_contract,
            behavior_contract=behavior_contract,
            project_conventions=state.conventions,
            context_contracts=context_contracts,
            rejection_history=rejection_history if rejection_history else None,
        )

        log_file = save_prompt_log(prompt, task_contract.id, attempt)
        console.print(f"  📝 Prompt saved: {log_file}")

        if dry_run:
            console.print("\n  [yellow]DRY RUN — prompt generated, execution skipped[/yellow]")
            return

        # ═══════════════════════════════════════
        # PHASE 3: EXECUTE
        # ═══════════════════════════════════════

        console.print("  🚀 Executing via Codex CLI...")

        snapshot_hash = get_head_hash(project_dir)

        exec_result: ExecutionResult = await executor.execute(
            prompt=prompt,
            working_dir=project_dir,
            timeout_seconds=task_contract.token_budget // 10,  # 粗略换算
        )

        console.print(f"  Exit code: {exec_result.exit_code}")
        console.print(f"  Duration: {exec_result.duration_seconds}s")
        console.print(f"  Modified: {exec_result.modified_files}")
        console.print(f"  New: {exec_result.new_files}")

        if verbose:
            console.print(f"  Stdout: {exec_result.stdout[:500]}")

        # ═══════════════════════════════════════
        # PHASE 4: OUTPUT GATE
        # ═══════════════════════════════════════

        console.print("\n  🔍 Running validation pipeline...")

        audit_log = str(Path(project_dir) / "state" / "audit" / "boundary_violations.log")

        validation: ValidationResult = run_output_gate(
            execution_result=exec_result,
            task_contract=task_contract,
            role_contract=role_contract,
            boundary_contracts=boundary_contracts,
            behavior_contract=behavior_contract,
            working_dir=project_dir,
            audit_log_path=audit_log,
        )

        # 打印验证结果
        _print_validation(validation, verbose)

        # ═══════════════════════════════════════
        # PHASE 5: DECISION
        # ═══════════════════════════════════════

        if validation.verdict == GateVerdict.PASSED:
            # ── 5c: 成功 ──
            console.print("\n  [bold green]✅ ALL GATES PASSED[/bold green]\n")
            stage_all(project_dir)
            commit_hash = commit(
                project_dir,
                f"capsule: {task_contract.id} completed (attempt {attempt})",
            )
            console.print(f"  Git commit: {commit_hash[:8]}")
            state.append_execution(
                task_id=task_contract.id,
                role=task_contract.assigned_to,
                attempts=attempt,
                result="passed",
            )
            console.print("\n  [bold green]🎉 Task completed successfully.[/bold green]\n")
            return

        elif validation.verdict == GateVerdict.HALTED:
            # ── 5b: L3 HALT ──
            console.print("\n  [bold red]🛑 BOUNDARY VIOLATION — HALT[/bold red]\n")
            rollback_to(project_dir, snapshot_hash)
            console.print(f"  Git rolled back to: {snapshot_hash[:8]}")
            state.append_execution(
                task_id=task_contract.id,
                role=task_contract.assigned_to,
                attempts=attempt,
                result="halted",
            )
            console.print("  ⚠️  All changes have been reverted. Check audit log.")
            return

        else:
            # ── 5a: REJECTED ──
            console.print(f"\n  [yellow]❌ REJECTED at L{validation.failed_level}[/yellow]")

            rejection = RejectionReport.from_validation_result(
                vr=validation,
                task_id=task_contract.id,
                target_role=task_contract.assigned_to,
                retry_count=attempt,
                max_retries=max_retries,
            )
            rejection_history.append(rejection)

            if attempt < max_retries:
                console.print(f"  Retrying... ({attempt}/{max_retries})")
                # 不回滚，保留变更，Agent 增量修复
                continue
            else:
                # ── 断路器 ──
                console.print("\n  [bold red]🔌 CIRCUIT BREAKER — max retries exceeded[/bold red]\n")
                _print_circuit_breaker_report(rejection_history)
                state.append_execution(
                    task_id=task_contract.id,
                    role=task_contract.assigned_to,
                    attempts=attempt,
                    result="circuit_break",
                )
                return


def _print_validation(vr: ValidationResult, verbose: bool) -> None:
    """打印验证结果摘要。"""
    table = Table(title="Validation Results")
    table.add_column("Level", style="bold")
    table.add_column("Status")
    table.add_column("Details")

    for lr in vr.level_results:
        status = "[green]PASSED[/green]" if lr.passed else "[red]FAILED[/red]"
        details = ""
        if not lr.passed:
            failed = lr.failed_checks
            details = "; ".join(f"{c.check_id}: {c.actual}" for c in failed[:3])
        table.add_row(f"L{lr.level}", status, details)

    console.print(table)


def _print_circuit_breaker_report(history: list[RejectionReport]) -> None:
    """断路器触发时的诊断报告。"""
    console.print(Panel(
        "\n".join([
            "[bold]Circuit Breaker Diagnostic Report[/bold]",
            "",
            f"Total attempts: {len(history)}",
            "",
            "Failure summary:",
            *[
                f"  Attempt {r.retry_count}: L{r.failed_level} — "
                + ", ".join(c["check_id"] for c in r.failed_checks[:3])
                for r in history
            ],
            "",
            "Recommended actions:",
            "  [1] Review the rejection details above",
            "  [2] Adjust the task contract or acceptance criteria",
            "  [3] Manually fix the code and re-run",
            "  [4] Simplify the task scope",
        ]),
        title="🔌 Circuit Breaker",
        border_style="red",
    ))
```

---

### 2.18 `capsule/cli.py`

```python
"""
Capsule CLI 入口。

第一版命令：
  capsule run <task_contract_path> [options]
  capsule validate <contract_path>
  capsule status
"""

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(
    name="capsule",
    help="Contract-driven AI software engineering orchestrator.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def run(
    task_contract: str = typer.Argument(
        ..., help="Path to the task contract YAML file"
    ),
    project_dir: str = typer.Option(
        ".", "--project-dir", "-p", help="Project root directory"
    ),
    state_path: str = typer.Option(
        "state/PROJECT_STATE.json", "--state", help="PROJECT_STATE.json path"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Generate prompt only, skip execution"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Verbose output"
    ),
    mock: Optional[str] = typer.Option(
        None, "--mock", help="Path to mock source dir (use MockExecutor instead of Codex)"
    ),
    codex_binary: str = typer.Option(
        "codex", "--codex-binary", help="Path to codex CLI binary"
    ),
):
    """Run a task through the Capsule pipeline."""
    from .orchestration.linear_runner import run_task

    if mock:
        from .execution.mock_executor import MockExecutor
        executor = MockExecutor(mock_source_dir=mock)
    else:
        from .execution.codex_executor import CodexExecutor
        executor = CodexExecutor(codex_binary=codex_binary)

    asyncio.run(run_task(
        task_contract_path=task_contract,
        executor=executor,
        project_dir=project_dir,
        state_path=state_path,
        dry_run=dry_run,
        verbose=verbose,
    ))


@app.command()
def validate(
    contract_path: str = typer.Argument(
        ..., help="Path to a contract YAML file to validate"
    ),
):
    """Validate a single contract file (L0 schema check)."""
    from .contracts.io import load_contract

    try:
        contract = load_contract(contract_path)
        console.print(f"[green]✅ Valid[/green] — {contract.type} contract: {contract.id}")
    except FileNotFoundError:
        console.print(f"[red]❌ File not found:[/red] {contract_path}")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]❌ Validation failed:[/red]\n{e}")
        raise typer.Exit(code=1)


@app.command()
def status(
    state_path: str = typer.Option(
        "state/PROJECT_STATE.json", "--state", help="PROJECT_STATE.json path"
    ),
):
    """Show project status and execution history."""
    from rich.table import Table
    from .state.project_state import ProjectState

    state = ProjectState(state_path)

    # Conventions
    if state.conventions:
        console.print("\n[bold]Project Conventions:[/bold]")
        for k, v in state.conventions.items():
            console.print(f"  {k}: {v}")

    # History
    history = state._data.get("execution_history", [])
    if history:
        table = Table(title="\nExecution History")
        table.add_column("Task ID")
        table.add_column("Role")
        table.add_column("Attempts")
        table.add_column("Result")
        table.add_column("Time")
        for h in history[-20:]:  # 最近 20 条
            result_style = {
                "passed": "green",
                "circuit_break": "red",
                "halted": "bold red",
            }.get(h["final_result"], "yellow")
            table.add_row(
                h["task_id"],
                h["role"],
                str(h["attempts"]),
                f"[{result_style}]{h['final_result']}[/{result_style}]",
                h.get("timestamp", "")[:19],
            )
        console.print(table)
    else:
        console.print("\n  No execution history yet.\n")
```

---

## 三、测试策略

### 3.1 测试优先级

| 优先级 | 测试目标 | 方法 |
|--------|---------|------|
| P0 | 五种契约 Model 的 validate/reject | 单元测试：正确 YAML pass，错误 YAML 抛 ValidationError |
| P0 | L0-L3 验证流水线 | 单元测试：构造 ExecutionResult + 契约实例，断言 verdict |
| P0 | 流水线串联短路逻辑 | 单元测试：L1 失败时不应执行 L2 |
| P1 | MockExecutor | 集成测试：复制文件 + git diff 收集 |
| P1 | LinearRunner + MockExecutor | 端到端测试：完整闭环跑通 |
| P2 | CodexExecutor | 手动测试（依赖 Codex CLI 环境） |
| P2 | CLI 命令 | 手动测试 + 少量 typer 测试 |

### 3.2 测试 Fixtures

在 `tests/fixtures/` 中提供：

```
tests/fixtures/
├── valid/
│   ├── coder_backend.role.yaml
│   ├── user_auth.task.yaml
│   ├── user_auth.interface.yaml
│   ├── user_auth.behavior.yaml
│   └── global.boundary.yaml
├── invalid/
│   ├── missing_type.yaml           # 无 type 字段
│   ├── bad_role_id.yaml            # id 不符合 pattern
│   ├── missing_required.yaml       # 缺少必填字段
│   └── extra_fields.yaml           # 有 extra 字段（应被 forbid）
└── mock_outputs/
    └── user_auth/                  # MockExecutor 用的预设产出
        └── src/
            └── backend/
                └── auth/
                    └── login.py
```

### 3.3 `tests/conftest.py` 关键 Fixture

```python
import pytest
import tempfile
import subprocess
from pathlib import Path


@pytest.fixture
def tmp_git_repo(tmp_path):
    """创建一个临时 git 仓库。"""
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "--allow-empty", "-m", "init"],
        check=True,
        capture_output=True,
    )
    return tmp_path


@pytest.fixture
def sample_role_contract():
    """返回一个有效的 RoleContract 实例。"""
    from capsule.contracts.models.role_contract import RoleContract
    return RoleContract(
        id="role.coder_backend",
        display_name="Backend Coder",
        file_permissions={"read": ["src/**"], "write": ["src/backend/**"]},
        exec_permissions={"allow": ["pytest"], "deny": ["rm -rf"]},
        prohibited_paths=["src/frontend/**"],
        output_spec={"required_fields": ["task_id"]},
    )


@pytest.fixture
def sample_task_contract():
    """返回一个有效的 TaskContract 实例。"""
    from capsule.contracts.models.task_contract import TaskContract
    return TaskContract(
        id="task.test.example",
        created_by="role.architect",
        description="Test task",
        assigned_to="role.coder_backend",
        scope={"include": ["src/backend/**"], "create_allowed": ["src/backend/"]},
    )
```

---

## 四、第一版完成后的验收场景

### 场景描述

用 Capsule 执行一个**极简任务**：实现一个返回 `{"status": "ok"}` 的 health check 端点。

### 所需契约文件（人类手写）

**`roles/coder_backend.role.yaml`：**

```yaml
id: "role.coder_backend"
type: "role"
status: "active"
display_name: "Backend Coder"
description: "实现后端 API 端点"
file_permissions:
  read: ["src/**", "contracts/**", "tests/**"]
  write: ["src/backend/**", "tests/backend/**"]
exec_permissions:
  allow: ["pytest", "python"]
  deny: ["git push", "rm -rf"]
prohibited_paths:
  - "src/frontend/**"
  - ".env*"
output_spec:
  required_fields: ["task_id"]
retry_policy:
  max_retries: 3
  on_exceed: "human_escalation"
```

**`contracts/instances/health/health.task.yaml`：**

```yaml
id: "task.health.endpoint"
type: "task"
status: "active"
created_by: "human"
description: |
  创建一个 health check API 端点。
  路径: GET /api/v1/health
  返回: {"status": "ok"}
  使用 FastAPI 实现。
assigned_to: "role.coder_backend"
scope:
  include: ["src/backend/**"]
  create_allowed: ["src/backend/"]
acceptance:
  behavior_contract_ref: "behavior.health"
  max_new_files: 3
forbidden_actions:
  - "不得修改已有文件，只能新建"
  - "不得安装新的 pip 依赖"
max_retries: 3
context_refs: []
```

**`contracts/instances/health/health.behavior.yaml`：**

```yaml
id: "behavior.health"
type: "behavior"
status: "active"
created_by: "human"
description: "health check 端点的行为验证"
test_suite:
  runner: "pytest"
  entry: "tests/backend/test_health.py"
  setup_cmd: ""
mandatory_cases:
  - id: "TC001"
    description: "GET /api/v1/health 返回 200"
    must_pass: true
  - id: "TC002"
    description: "响应体包含 status: ok"
    must_pass: true
coverage:
  minimum_percent: 0
```

**`contracts/boundaries/global.boundary.yaml`：**

```yaml
id: "boundary.global"
type: "boundary"
status: "active"
created_by: "human"
description: "全局边界契约"
scope: "global"
sacred_files:
  - "capsule.yaml"
  - "contracts/boundaries/**"
  - ".env*"
  - "state/audit/**"
audit_rules:
  - id: "no_sacred_touch"
    description: "不得修改受保护文件"
    check_method: "git_diff_scan"
    violation_action: "immediate_halt"
on_violation: "immediate_halt"
notify: "human"
```

**人类预写的测试文件 `tests/backend/test_health.py`：**

```python
"""由人类预写，Agent 的代码必须让这些测试通过。"""
from fastapi.testclient import TestClient


def test_health_returns_200():  # TC001
    from src.backend.main import app
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_health_returns_ok():  # TC002
    from src.backend.main import app
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.json()["status"] == "ok"
```

### 执行命令

```bash
capsule run contracts/instances/health/health.task.yaml --verbose
```

### 预期行为

```
═══ PHASE 1: INPUT GATE ═══
  ✅ Task contract loaded: task.health.endpoint
  ✅ Role contract loaded: role.coder_backend
  ✅ Boundary contracts loaded: 1
  ✅ Behavior contract loaded: behavior.health

  INPUT GATE PASSED

═══ ATTEMPT 1/3 ═══
  📝 Prompt saved: state/prompts/task.health.endpoint_attempt_1.md
  🚀 Executing via Codex CLI...
  Exit code: 0
  Duration: 45.2s
  Modified: []
  New: ['src/backend/main.py']

  🔍 Running validation pipeline...
  ┌─────────────────────────────┐
  │ Level │ Status  │ Details   │
  ├───────┼─────────┼───────────┤
  │ L0    │ PASSED  │           │
  │ L1    │ PASSED  │           │
  │ L2    │ PASSED  │           │
  │ L3    │ PASSED  │           │
  └─────────────────────────────┘

  ✅ ALL GATES PASSED

  Git commit: a1b2c3d4
  🎉 Task completed successfully.
```

---

## 五、实施顺序建议

```
Day 1-2:  enums.py → 五种 Model → __init__.py → io.py → tests/test_contracts.py
Day 2-3:  git.py → protocol.py → mock_executor.py → tests/test_executor.py
Day 3-5:  l0 → l1 → l2 → l3 → pipeline.py (串联) → tests/test_validation.py
Day 5-6:  prompt_builder.py → project_state.py
Day 6-8:  linear_runner.py → cli.py → 端到端联调
Day 8:    codex_executor.py → 真实 Codex CLI 测试
```

每完成一个模块，跑通该模块的单元测试再进入下一个。不要一次性写完再测。

---

**文档结束。** 如实施过程中遇到设计层面的歧义或需要架构决策，请上报，不要自行假设。

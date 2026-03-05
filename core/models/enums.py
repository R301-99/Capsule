from enum import Enum, IntEnum


class ContractType(str, Enum):
    ROLE = "role"
    TASK = "task"
    INTERFACE = "interface"
    BEHAVIOR = "behavior"
    BOUNDARY = "boundary"
    GATE_REPORT = "gate_report"
    EVIDENCE = "evidence"
    HUMAN_DECISION = "human_decision"


class ContractStatus(str, Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    ACTIVE = "active"
    AMENDING = "amending"
    DEPRECATED = "deprecated"
    draft = DRAFT
    pending_review = PENDING_REVIEW
    active = ACTIVE
    amending = AMENDING
    deprecated = DEPRECATED


class CreatedBy(str, Enum):
    ARCHITECT = "role.architect"
    QA = "role.qa"
    CODER_BACKEND = "role.coder_backend"
    CODER_FRONTEND = "role.coder_frontend"
    HUMAN = "human"
    SYSTEM = "system"


class FailureAction(str, Enum):
    RETRY = "retry"
    HALT = "halt"
    HUMAN_ESCALATION = "human_escalation"


class Severity(str, Enum):
    LOW = "low"
    MID = "mid"
    HIGH = "high"


class GateId(str, Enum):
    INPUT_GATE = "INPUT_GATE"
    OUTPUT_GATE = "OUTPUT_GATE"


class GateResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    HALT = "halt"
    HUMAN = "human"


class GateLevel(IntEnum):
    L0 = 0
    L1 = 1
    L2 = 2
    L3 = 3


class TestSummary(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class HumanTrigger(str, Enum):
    RETRY_EXCEEDED = "retry_exceeded"
    BOUNDARY_VIOLATION = "boundary_violation"
    REVIEW_REQUIRED = "review_required"
    LOW_CONFIDENCE = "low_confidence"


class HumanAction(str, Enum):
    RESUME = "resume"
    ABORT = "abort"
    PAUSE = "pause"
    AMEND_CONTRACT = "amend_contract"


class ViolationAction(str, Enum):
    IMMEDIATE_HALT = "immediate_halt"


class CheckMethod(str, Enum):
    GIT_DIFF_SCAN = "git_diff_scan"
    COMMAND_AUDIT = "command_audit"

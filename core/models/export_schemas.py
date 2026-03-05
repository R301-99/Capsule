from __future__ import annotations

import json
from pathlib import Path
from typing import Type

from pydantic import BaseModel

from .base import ContractEnvelope, ContractRef
from .behavior import BehaviorContract
from .boundary import BoundaryContract
from .evidence import EvidenceContract
from .gate_report import GateReportContract
from .human_decision import HumanDecisionContract
from .interface import InterfaceContract
from .role import RoleContract
from .task import TaskContract

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "contracts" / "schemas"

MODEL_TO_FILE: dict[Type[BaseModel], str] = {
    ContractEnvelope: "contract.envelope.schema.json",
    ContractRef: "contract.ref.schema.json",
    RoleContract: "role.contract.schema.json",
    TaskContract: "task.contract.schema.json",
    InterfaceContract: "interface.contract.schema.json",
    BehaviorContract: "behavior.contract.schema.json",
    BoundaryContract: "boundary.contract.schema.json",
    GateReportContract: "gate_report.schema.json",
    EvidenceContract: "evidence.schema.json",
    HumanDecisionContract: "human_decision.schema.json",
}


def export_schemas(schema_dir: Path = SCHEMA_DIR) -> list[Path]:
    schema_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for model, filename in MODEL_TO_FILE.items():
        path = schema_dir / filename
        schema = model.model_json_schema()
        path.write_text(json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)

    return written


if __name__ == "__main__":
    paths = export_schemas()
    print(f"Exported {len(paths)} schemas:")
    for p in paths:
        print(f"- {p}")

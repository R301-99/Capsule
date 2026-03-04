from __future__ import annotations

import json
from pathlib import Path

from .base import GenericContractEnvelope
from .behavior import BehaviorContract
from .boundary import BoundaryContract
from .evidence import EvidenceContract
from .gate_report import GateReportContract
from .human_decision import HumanDecisionContract
from .interface import InterfaceContract
from .role import RoleContract
from .task import TaskContract

SCHEMAS: dict[str, type] = {
    "contract.envelope.schema.json": GenericContractEnvelope,
    "role.contract.schema.json": RoleContract,
    "task.contract.schema.json": TaskContract,
    "interface.contract.schema.json": InterfaceContract,
    "behavior.contract.schema.json": BehaviorContract,
    "boundary.contract.schema.json": BoundaryContract,
    "gate_report.schema.json": GateReportContract,
    "evidence.schema.json": EvidenceContract,
    "human_decision.schema.json": HumanDecisionContract,
}


def export_schemas(output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for filename, model in SCHEMAS.items():
        schema = model.model_json_schema()
        path = output_dir / filename
        path.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(path)

    return written


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    out_dir = repo_root / "contracts" / "schemas"
    written = export_schemas(out_dir)
    print("Exported schemas:")
    for item in written:
        print(f"- {item.relative_to(repo_root)}")


if __name__ == "__main__":
    main()

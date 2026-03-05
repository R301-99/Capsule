from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models.enums import HumanAction, HumanTrigger
from .models.state import HumanQueueItem, ProjectState
from .state_manager import HumanQueueItemNotFoundError, RunNotFoundError, StateManager


@dataclass(frozen=True)
class ReviewSummary:
    item_id: str
    trigger: str
    run_id: str
    summary: str
    details: list[str]
    options: list[str]
    recommended: str | None


class HumanLoop:
    def __init__(self, state_manager: StateManager):
        self.sm = state_manager

    def get_pending_reviews(self, state: ProjectState) -> list[ReviewSummary]:
        return [self._to_review_summary(item) for item in self.sm.pending_human_items(state)]

    def format_review(self, summary: ReviewSummary) -> str:
        lines = [
            "HUMAN REVIEW REQUIRED",
            f"Item: {summary.item_id}",
            f"Trigger: {summary.trigger}",
            f"Run: {summary.run_id}",
            "",
            "SUMMARY",
            summary.summary,
            "",
            "DETAILS",
        ]
        if summary.details:
            lines.extend([f"- {detail}" for detail in summary.details])
        else:
            lines.append("- (no extra details)")
        lines.extend(["", "OPTIONS"])
        for index, option in enumerate(summary.options, start=1):
            marker = " (recommended)" if summary.recommended == option else ""
            lines.append(f"[{index}] {option}{marker}")
        return "\n".join(lines)

    def apply_decision(
        self, state: ProjectState, item_id: str, selected_option: str, rationale: str = ""
    ) -> ProjectState:
        item = self._find_item(state, item_id)
        if item is None:
            raise HumanQueueItemNotFoundError(f"Human queue item not found: {item_id}")
        if item.resolved:
            raise ValueError(f"Human queue item already resolved: {item_id}")
        normalized_option = self._normalize_option(selected_option, item.options)
        if normalized_option not in item.options:
            raise ValueError(f"Invalid option '{selected_option}' for {item_id}")

        decision_id = f"hd-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
        decision_payload = self._build_decision_payload(
            item=item,
            decision_id=decision_id,
            selected_option=normalized_option,
            rationale=rationale,
            state=state,
        )
        try:
            self.sm.write_human_decision(item.run_id, decision_payload)
        except RunNotFoundError:
            # If run directory no longer exists, still keep decision in state by resolving queue item.
            pass

        return self.sm.resolve_human(state, item_id, decision_id)

    @staticmethod
    def _normalize_option(selected_option: str, options: list[str]) -> str:
        text = selected_option.strip()
        if text.isdigit():
            index = int(text)
            if index < 1 or index > len(options):
                return text
            return options[index - 1]
        return text

    @staticmethod
    def _find_item(state: ProjectState, item_id: str) -> HumanQueueItem | None:
        for item in state.human_queue:
            if item.item_id == item_id:
                return item
        return None

    def _to_review_summary(self, item: HumanQueueItem) -> ReviewSummary:
        trigger = item.trigger.value if hasattr(item.trigger, "value") else str(item.trigger)
        details = self._build_details(item)
        recommended = self._recommended_option(item.trigger, item.options)
        return ReviewSummary(
            item_id=item.item_id,
            trigger=trigger,
            run_id=item.run_id,
            summary=item.summary,
            details=details,
            options=list(item.options),
            recommended=recommended,
        )

    @staticmethod
    def _recommended_option(trigger: HumanTrigger, options: list[str]) -> str | None:
        default_map = {
            HumanTrigger.RETRY_EXCEEDED: "amend_contract",
            HumanTrigger.BOUNDARY_VIOLATION: "abort",
            HumanTrigger.REVIEW_REQUIRED: "approve",
            HumanTrigger.LOW_CONFIDENCE: "pause",
        }
        preferred = default_map.get(trigger)
        if preferred in options:
            return preferred
        return options[0] if options else None

    @staticmethod
    def _build_details(item: HumanQueueItem) -> list[str]:
        trigger = item.trigger.value if hasattr(item.trigger, "value") else str(item.trigger)
        details = [f"Queue trigger: {trigger}"]
        if item.summary:
            details.append(item.summary)
        if item.options:
            details.append(f"Options: {', '.join(item.options)}")
        return details

    @staticmethod
    def _build_decision_payload(
        *,
        item: HumanQueueItem,
        decision_id: str,
        selected_option: str,
        rationale: str,
        state: ProjectState,
    ) -> dict[str, Any]:
        option_map = {
            "approve": HumanAction.RESUME.value,
            "abort": HumanAction.ABORT.value,
            "pause": HumanAction.PAUSE.value,
            "amend_contract": HumanAction.AMEND_CONTRACT.value,
        }
        action = option_map.get(selected_option, HumanAction.RESUME.value)
        task_ref = state.current_task_ref.model_dump(mode="json") if state.current_task_ref is not None else None
        refs = [task_ref] if task_ref is not None else []
        return {
            "decision_id": decision_id,
            "item_id": item.item_id,
            "run_id": item.run_id,
            "trigger": item.trigger.value if hasattr(item.trigger, "value") else str(item.trigger),
            "context_refs": refs,
            "options_presented": list(item.options),
            "selected_option": selected_option,
            "rationale": rationale or "",
            "actions": {"next": action},
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "made_by": "human",
        }

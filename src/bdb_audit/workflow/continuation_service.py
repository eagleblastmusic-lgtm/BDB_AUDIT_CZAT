"""History-derived Continuation Service (B02 / §100).

Derives workflow status and next legitimate action exclusively from the
verified accepted history cut of the campaign store.
"""
from __future__ import annotations

from typing import Any

from ..core.errors import ValidationError
from ..history.store import TransactionalHistoryStore
from .read_models import campaign_status, current_accepted_cut


_STAGE_SEQUENCE = ("E1", "E2", "E3", "E4", "E5")


class ContinuationService:
    """Evaluates campaign progression from immutable accepted records."""

    @staticmethod
    def evaluate_continuation(store: TransactionalHistoryStore) -> dict[str, Any]:
        head = store.head()
        if head is None:
            raise ValidationError("EMPTY_STORE", "Store has no accepted commits")

        # Use the same verified, fully typed accepted-history cut as every other
        # operational read model.  A shorthand {campaign_id, commit_seq, commit_hash}
        # is not an authority-bearing HistoryCut and must never be passed to
        # accepted_records/resolve_accepted.
        cut = current_accepted_cut(store)

        # Query accepted records
        status = campaign_status(store, lambda s: s.upper() if isinstance(s, str) else str(s))
        prepared_stages = list(status["stages_prepared"])
        completed_stages = list(status["stages_completed"])
        termination_state = status.get("termination_state", "OPEN")
        finalization = status["finalization_progress"]
        common = {
            "campaign_id": head.campaign_id,
            "stages_prepared": prepared_stages,
            "stages_completed": completed_stages,
            "accepted_head_seq": head.commit_seq,
            "termination_state": termination_state,
            "finalization_progress": finalization,
            "workflow_finished": status["workflow_finished"],
        }

        if termination_state in {"COMPLETED", "COMPLETED_LIMITED"}:
            if finalization["state"] == "BLOCKED":
                return {
                    **common,
                    "current_stage": "FINALIZATION",
                    "continuation_state": "FINALIZATION_BLOCKED",
                    "next_action": "REVIEW_FINALIZATION_CHAIN",
                }
            if finalization["state"] != "COMPLETE":
                return {
                    **common,
                    "current_stage": "FINALIZATION",
                    "continuation_state": "FINALIZATION_INCOMPLETE",
                    "next_action": "RESUME_FINALIZATION",
                }
            return {
                **common,
                "current_stage": (
                    "CONCLUDED_LIMITED"
                    if termination_state == "COMPLETED_LIMITED"
                    else "CONCLUDED"
                ),
                "continuation_state": termination_state,
                "next_action": (
                    "CAMPAIGN_TERMINATED_LIMITED"
                    if termination_state == "COMPLETED_LIMITED"
                    else "CAMPAIGN_FINISHED"
                ),
            }

        # Check for STOP evaluations
        stop_records = sorted(
            store.accepted_records("stop_evaluation", cut),
            key=lambda row: row["accepted_seq"],
        )
        if stop_records:
            latest_stop = stop_records[-1]["body"]
            decision = latest_stop.get("continuation_decision")
            if decision == "PASS":
                return {
                    **common,
                    "current_stage": "STOP",
                    "continuation_state": "READY_FOR_CONCLUSION",
                    "next_action": "CONCLUDE_CAMPAIGN",
                }
            elif decision == "E6_REQUIRED":
                if "E6" in completed_stages:
                    return {
                        **common,
                        "current_stage": "STOP",
                        "continuation_state": "READY_FOR_STOP_REEVALUATION",
                        "next_action": "EVALUATE_STOP_GATE",
                    }
                if "E6" in prepared_stages:
                    return {
                        **common,
                        "current_stage": "E6",
                        "continuation_state": "E6_EXECUTION_UNAVAILABLE",
                        "next_action": "E6_RUNTIME_UNAVAILABLE",
                    }
                return {
                    **common,
                    "current_stage": "E6",
                    "continuation_state": "E6_REQUIRED",
                    "next_action": "PREPARE_STAGE_E6",
                }
            elif decision == "BLOCKED":
                return {
                    **common,
                    "current_stage": "STOP",
                    "continuation_state": "BLOCKED",
                    "next_action": "CONCLUDE_LIMITED_OR_BLOCK",
                }

        # Check stage progression across E1..E5
        for stage in _STAGE_SEQUENCE:
            if stage not in completed_stages:
                if stage not in prepared_stages:
                    return {
                        **common,
                        "current_stage": stage,
                        "continuation_state": "NOT_PREPARED",
                        "next_action": f"PREPARE_STAGE_{stage}",
                    }
                else:
                    # Prepared but not completed
                    return {
                        **common,
                        "current_stage": stage,
                        "continuation_state": "RUNNING",
                        "next_action": f"QUALIFY_STAGE_{stage}",
                    }

        # All E1..E5 completed, STOP not yet evaluated
        return {
            **common,
            "current_stage": "STOP",
            "continuation_state": "READY_FOR_STOP_EVALUATION",
            "next_action": "EVALUATE_STOP_GATE",
        }

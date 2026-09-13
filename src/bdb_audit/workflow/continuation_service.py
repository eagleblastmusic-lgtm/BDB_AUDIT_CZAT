"""History-derived Continuation Service (B02 / §100).

Derives workflow status and next legitimate action exclusively from the
verified accepted history cut of the campaign store.
"""
from __future__ import annotations

from typing import Any

from ..core.errors import ValidationError
from ..history.store import TransactionalHistoryStore
from .read_models import campaign_status


_STAGE_SEQUENCE = ("E1", "E2", "E3", "E4", "E5")


class ContinuationService:
    """Evaluates campaign progression from immutable accepted records."""

    @staticmethod
    def evaluate_continuation(store: TransactionalHistoryStore) -> dict[str, Any]:
        head = store.head()
        if head is None:
            raise ValidationError("EMPTY_STORE", "Store has no accepted commits")

        cut = {
            "campaign_id": head.campaign_id,
            "commit_seq": head.commit_seq,
            "commit_hash": head.commit_hash,
        }

        # Query accepted records
        status = campaign_status(store, lambda s: s.upper() if isinstance(s, str) else str(s))
        prepared_stages = list(status["stages_prepared"])
        completed_stages = list(status["stages_completed"])
        termination_state = status.get("termination_state", "OPEN")

        if termination_state == "COMPLETED":
            return {
                "campaign_id": head.campaign_id,
                "current_stage": "CONCLUDED",
                "continuation_state": "COMPLETED",
                "next_action": "CAMPAIGN_FINISHED",
                "stages_prepared": prepared_stages,
                "stages_completed": completed_stages,
                "accepted_head_seq": head.commit_seq,
            }

        if termination_state == "COMPLETED_LIMITED":
            return {
                "campaign_id": head.campaign_id,
                "current_stage": "CONCLUDED_LIMITED",
                "continuation_state": "COMPLETED_LIMITED",
                "next_action": "CAMPAIGN_TERMINATED_LIMITED",
                "stages_prepared": prepared_stages,
                "stages_completed": completed_stages,
                "accepted_head_seq": head.commit_seq,
            }

        # Check for STOP evaluations
        stop_records = store.accepted_records("stop_evaluation", cut)
        if stop_records:
            latest_stop = stop_records[-1]["body"]
            decision = latest_stop.get("continuation_decision")
            if decision == "PASS":
                return {
                    "campaign_id": head.campaign_id,
                    "current_stage": "STOP",
                    "continuation_state": "READY_FOR_CONCLUSION",
                    "next_action": "CONCLUDE_CAMPAIGN",
                    "stages_prepared": prepared_stages,
                    "stages_completed": completed_stages,
                    "accepted_head_seq": head.commit_seq,
                }
            elif decision == "E6_REQUIRED":
                return {
                    "campaign_id": head.campaign_id,
                    "current_stage": "E6",
                    "continuation_state": "E6_REQUIRED",
                    "next_action": "PREPARE_STAGE_E6",
                    "stages_prepared": prepared_stages,
                    "stages_completed": completed_stages,
                    "accepted_head_seq": head.commit_seq,
                }
            elif decision == "BLOCKED":
                return {
                    "campaign_id": head.campaign_id,
                    "current_stage": "STOP",
                    "continuation_state": "BLOCKED",
                    "next_action": "CONCLUDE_LIMITED_OR_BLOCK",
                    "stages_prepared": prepared_stages,
                    "stages_completed": completed_stages,
                    "accepted_head_seq": head.commit_seq,
                }

        # Check stage progression across E1..E5
        for stage in _STAGE_SEQUENCE:
            if stage not in completed_stages:
                if stage not in prepared_stages:
                    return {
                        "campaign_id": head.campaign_id,
                        "current_stage": stage,
                        "continuation_state": "PREPARED" if stage in prepared_stages else "NOT_PREPARED",
                        "next_action": f"PREPARE_STAGE_{stage}",
                        "stages_prepared": prepared_stages,
                        "stages_completed": completed_stages,
                        "accepted_head_seq": head.commit_seq,
                    }
                else:
                    # Prepared but not completed
                    return {
                        "campaign_id": head.campaign_id,
                        "current_stage": stage,
                        "continuation_state": "RUNNING",
                        "next_action": f"QUALIFY_STAGE_{stage}",
                        "stages_prepared": prepared_stages,
                        "stages_completed": completed_stages,
                        "accepted_head_seq": head.commit_seq,
                    }

        # All E1..E5 completed, STOP not yet evaluated
        return {
            "campaign_id": head.campaign_id,
            "current_stage": "STOP",
            "continuation_state": "READY_FOR_STOP_EVALUATION",
            "next_action": "EVALUATE_STOP_GATE",
            "stages_prepared": prepared_stages,
            "stages_completed": completed_stages,
            "accepted_head_seq": head.commit_seq,
        }

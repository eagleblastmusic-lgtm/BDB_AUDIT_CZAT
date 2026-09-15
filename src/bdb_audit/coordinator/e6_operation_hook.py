"""Install the M45-aware E6 preparation and continuation paths.

The pre-M45 facade constructed E6 like an ordinary baseline StageSpec, which
produced ``stop_e6_relationship='NONE'`` and was correctly rejected by the M45
history authority validator.  This adapter keeps E1-E5 behavior untouched while
routing E6 through ``AdaptiveE6Generator.generate_e6_spec_from_store`` and
ensuring a prepared E6 revision must complete before control returns to STOP.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..core.errors import ValidationError
from ..history.objects import CommandEnvelope
from ..history.store import TransactionalHistoryStore
from ..stop.e6 import AdaptiveE6Generator


def install_adaptive_e6_prepare_stage() -> None:
    from . import Coordinator
    from . import operations as operations_module

    api_cls = operations_module.AuditOperationApi
    if getattr(api_cls, "_bdb_m45_prepare_stage_installed", False):
        return

    original_prepare_stage = api_cls.prepare_stage
    original_continue_campaign = api_cls.continue_campaign

    def prepare_stage(self, store_path, stage_id, stage_spec_revision="1"):
        stage_key = operations_module._canonical_stage_key(stage_id)
        if stage_key != "E6":
            return original_prepare_stage(self, store_path, stage_id, stage_spec_revision)

        from ..workflow.read_models import current_accepted_cut

        path = Path(store_path).resolve()
        status = self.get_campaign_status(path)
        if status.get("termination_state", "OPEN") != "OPEN":
            raise ValidationError(
                "CAMPAIGN_ALREADY_TERMINATED",
                "Cannot prepare a stage after campaign conclusion",
            )
        if "E5" not in status["stages_completed"]:
            raise ValidationError(
                "PREDECESSOR_STAGE_NOT_COMPLETED",
                "Stage E5 must be completed before preparing E6",
            )

        if "E6" in status["stages_prepared"] and "E6" not in status["stages_completed"]:
            raise ValidationError("STAGE_ALREADY_PREPARED", "Stage E6 is already prepared")

        store = TransactionalHistoryStore(path, registry=self.registry)
        coordinator = Coordinator(store)
        head = store.head()
        if head is None:
            raise ValidationError("CAMPAIGN_NOT_FOUND", "Campaign contains no accepted head")

        cut = current_accepted_cut(store)
        stop_rows = store.accepted_records("stop_evaluation", cut)
        if not stop_rows:
            raise ValidationError("E6_ACCEPTED_STOP_REQUIRED")
        latest_stop = max(stop_rows, key=lambda row: int(row.get("accepted_seq", 0)))

        existing_e6 = [
            row
            for row in store.accepted_records("stage_spec", cut)
            if row["body"].get("stage_key") == "E6"
        ]
        requested_revision = str(stage_spec_revision)
        existing_revisions = {
            str(row["body"].get("stage_spec_revision")) for row in existing_e6
        }
        if requested_revision in existing_revisions:
            if requested_revision == "1":
                requested_revision = f"1.{len(existing_e6) + 1}"
            else:
                raise ValidationError("STAGE_SPEC_REVISION_REBIND")

        adaptive = AdaptiveE6Generator.generate_e6_spec_from_store(
            store,
            spec_id=requested_revision,
            stop_evaluation_ref=latest_stop["ref"],
        )
        spec_obj = adaptive.as_object()

        parent_head_ref = {"tag": "ACCEPTED_HEAD_REF", **head.as_dict()}
        conn = store._connect()
        try:
            row = conn.execute(
                "SELECT body FROM commits WHERE commit_hash=?", (head.commit_hash,)
            ).fetchone()
            if row is None:
                raise ValidationError("ACCEPTED_HEAD_COMMIT_MISSING")
            prior_commit = json.loads(row[0])
        finally:
            conn.close()

        cmd = CommandEnvelope(
            command_id=operations_module._command_id(
                f"stage_prep_E6_{head.commit_seq + 1}_{requested_revision}"
            ),
            command_kind="RECORD_FOUNDATION_FACT",
            actor_ref=prior_commit.get("actor_ref", "installation-owner"),
            expected_parent_head=parent_head_ref,
            governing_policy_ref=prior_commit.get(
                "governing_policy_ref", "pin:initial_governing_policy_ref"
            ),
            governing_spec_refs=tuple(
                prior_commit.get(
                    "governing_spec_refs", ("pin:initial_transition_profile_ref",)
                )
            ),
            idempotency_scope=f"stage_prep_E6_{spec_obj.digest[:16]}",
            campaign_ref=head.campaign_id,
        )

        result = coordinator.accept(cmd, immutable_objects=[spec_obj])
        return {
            "status": "SUCCESS",
            "stage_id": stage_id,
            "stage_key": "E6",
            "stage_spec_revision": requested_revision,
            "stage_spec_digest": spec_obj.digest,
            "commit_seq": result.head.commit_seq,
            "commit_hash": result.head.commit_hash,
        }

    def continue_campaign(self, store_path):
        status = self.get_campaign_status(store_path)
        if (
            status.get("termination_state", "OPEN") == "OPEN"
            and "E6" in status.get("stages_prepared", ())
            and "E6" not in status.get("stages_completed", ())
        ):
            return {
                "status": "SUCCESS",
                "campaign_id": status["campaign_id"],
                "current_stage": "E6",
                "continuation_state": "AWAITING_STAGE_COMPLETION",
                "next_action": "AWAITING_STAGE_COMPLETION",
                "head_seq": status["accepted_head_seq"],
            }
        # Once the latest E6 revision is complete, the baseline continuation
        # logic sees E1-E5 complete and correctly returns EVALUATE_STOP_GATE.
        return original_continue_campaign(self, store_path)

    setattr(api_cls, "prepare_stage", prepare_stage)
    setattr(api_cls, "continue_campaign", continue_campaign)
    setattr(api_cls, "_bdb_m45_prepare_stage_installed", True)

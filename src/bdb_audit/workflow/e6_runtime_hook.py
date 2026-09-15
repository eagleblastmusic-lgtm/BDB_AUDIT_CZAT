"""Recursive E6 read-model and completion integration for M45.

Baseline E1-E5 remain single-revision stages.  E6 is different: POST_E6 may
return E6_REQUIRED again, so accepted history can contain multiple immutable E6
StageSpec revisions and one StageCompletion per revision.  Operational status
must therefore project the latest E6 revision rather than treating any duplicate
stage key as corruption.
"""
from __future__ import annotations

from typing import Any

from ..core.errors import ValidationError


def install_recursive_e6_runtime_support() -> None:
    from . import read_models as rm
    from . import stage_service as ss

    model_cls = rm.VerifiedCampaignReadModel
    if not getattr(model_cls, "_bdb_recursive_e6_projection_installed", False):
        def project_status(self) -> dict[str, Any]:
            cut = self.cut
            head = self.head

            stage_rows = tuple(sorted(
                self.store.accepted_records("stage_spec", cut),
                key=lambda row: (int(row.get("accepted_seq", 0)), row["ref"]["revision_digest"]),
            ))
            selected_by_stage: dict[str, dict[str, Any]] = {}
            e6_revision_digests: dict[str, str] = {}

            for index, row in enumerate(stage_rows, start=1):
                doc = row["body"]
                stage_key = doc.get("stage_key") or doc.get("stage_id") or doc.get("key")
                if stage_key is None:
                    raise ValidationError("STAGE_SPEC_PROJECTION_INVALID", "stage_spec missing stage_key")
                try:
                    canonical_key = self.canonical_stage(str(stage_key))
                except ValidationError as exc:
                    raise ValidationError("STAGE_SPEC_PROJECTION_INVALID", str(exc)) from exc

                if canonical_key != "E6" and canonical_key in selected_by_stage:
                    raise ValidationError(
                        "STAGE_SPEC_PROJECTION_INVALID",
                        f"Duplicate accepted stage key {canonical_key}",
                    )

                if canonical_key == "E6":
                    revision = str(doc.get("stage_spec_revision", ""))
                    prior_digest = e6_revision_digests.get(revision)
                    current_digest = row["ref"]["revision_digest"]
                    if prior_digest is not None and prior_digest != current_digest:
                        raise ValidationError("STAGE_SPEC_REVISION_REBIND", revision)
                    e6_revision_digests[revision] = current_digest

                # E6 intentionally overwrites with the newest accepted revision.
                selected_by_stage[canonical_key] = row

            stage_records: list[tuple[int, str, dict[str, Any]]] = []
            for canonical_key, row in selected_by_stage.items():
                ordinal = row["body"].get("stage_ordinal")
                if type(ordinal) is not int or ordinal < 1:
                    ordinal = int(row.get("accepted_seq", 0)) or 1
                stage_records.append((ordinal, canonical_key, row))
            stage_records.sort(key=lambda item: (item[0], item[1]))
            stages_prepared = [stage_key for _, stage_key, _ in stage_records]

            lane_rows = self.store.accepted_records("lane_spec", cut)
            lanes_prepared: list[str] = []
            for row in lane_rows:
                doc = row["body"]
                lane_key = doc.get("lane_key") or doc.get("lane_id") or doc.get("slot")
                if not lane_key:
                    raise ValidationError("LANE_SPEC_PROJECTION_INVALID", "lane_spec missing lane_key")
                lanes_prepared.append(str(lane_key))
            lanes_prepared.sort()
            # Recursive E6 may legitimately reuse an operational lane key in a
            # new immutable lane-spec revision.  Baseline duplicate keys remain
            # invalid; collapse only E6 lane keys by their accepted revisions.
            non_e6_keys = [key for key in lanes_prepared if not key.lower().startswith("lane_e6")]
            if len(non_e6_keys) != len(set(non_e6_keys)):
                raise ValidationError("LANE_SPEC_PROJECTION_INVALID", "Duplicate accepted lane key")
            lanes_prepared = list(dict.fromkeys(lanes_prepared))

            completion_rows = tuple(sorted(
                self.store.accepted_records("stage_completion", cut),
                key=lambda row: (int(row.get("accepted_seq", 0)), row["ref"]["revision_digest"]),
            ))
            baseline_completed: dict[str, str] = {}
            e6_completion_by_spec: dict[str, str] = {}

            for row in completion_rows:
                doc = row["body"]
                if doc.get("completion_predicate_result") != "STAGE_COMPLETED":
                    continue
                spec_ref = doc.get("stage_spec_ref")
                if not isinstance(spec_ref, dict):
                    raise ValidationError(
                        "STAGE_COMPLETION_PROJECTION_INVALID",
                        "Missing stage_spec_ref in stage_completion",
                    )
                spec_record = self.store.resolve_accepted(spec_ref, cut)
                spec_body = spec_record["body"]
                raw_key = spec_body.get("stage_key") or spec_body.get("stage_id")
                if not raw_key:
                    raise ValidationError(
                        "STAGE_COMPLETION_PROJECTION_INVALID",
                        "stage_spec has no stage_key",
                    )
                canonical_key = self.canonical_stage(str(raw_key))
                completion_digest = row["ref"]["revision_digest"]
                spec_digest = spec_ref.get("revision_digest")

                if canonical_key == "E6":
                    existing = e6_completion_by_spec.get(str(spec_digest))
                    if existing is not None and existing != completion_digest:
                        raise ValidationError(
                            "MULTIPLE_STAGE_COMPLETIONS",
                            "Ambiguous conflicting completions for E6 revision",
                        )
                    e6_completion_by_spec[str(spec_digest)] = completion_digest
                    continue

                existing = baseline_completed.get(canonical_key)
                if existing is not None and existing != completion_digest:
                    raise ValidationError(
                        "MULTIPLE_STAGE_COMPLETIONS",
                        f"Ambiguous conflicting completions for stage {canonical_key}",
                    )
                baseline_completed[canonical_key] = completion_digest

            completed_stages = list(baseline_completed)
            latest_e6 = selected_by_stage.get("E6")
            if latest_e6 is not None:
                latest_e6_digest = latest_e6["ref"]["revision_digest"]
                if latest_e6_digest in e6_completion_by_spec:
                    completed_stages.append("E6")

            stage_order = {stage_key: index for index, stage_key in enumerate(stages_prepared)}
            try:
                completed_stages.sort(key=stage_order.__getitem__)
            except KeyError as exc:
                raise ValidationError(
                    "STAGE_COMPLETION_PROJECTION_INVALID",
                    f"Completion references unprojected accepted stage {exc.args[0]}",
                ) from exc

            stop_rows = self.store.accepted_records("stop_evaluation", cut)
            conclusion_rows = tuple(sorted(
                self.store.accepted_records("campaign_conclusion", cut),
                key=lambda row: row["accepted_seq"],
            ))
            latest_conclusion = conclusion_rows[-1]["body"] if conclusion_rows else None
            termination_state = latest_conclusion.get("termination_state") if latest_conclusion else "OPEN"
            if termination_state not in {"OPEN", "COMPLETED", "COMPLETED_LIMITED"}:
                raise ValidationError("CAMPAIGN_CONCLUSION_PROJECTION_INVALID", str(termination_state))

            current_stage = "GENESIS"
            completed_set = set(completed_stages)
            for stage_key in stages_prepared:
                if stage_key not in completed_set:
                    current_stage = stage_key
                    break
            else:
                if stages_prepared:
                    current_stage = stages_prepared[-1]

            source = rm.campaign_source_identity(self.store, cut)
            return {
                "status": "SUCCESS",
                "campaign_id": head.campaign_id,
                "accepted_head_seq": head.commit_seq,
                "accepted_head_hash": head.commit_hash,
                "current_stage": current_stage,
                "stages_prepared": stages_prepared,
                "stages_completed": completed_stages,
                "lanes_prepared": lanes_prepared,
                "stage_completions_count": len(completion_rows),
                "stop_evaluations_count": len(stop_rows),
                "campaign_conclusions_count": len(conclusion_rows),
                "termination_state": termination_state,
                "campaign_completed": termination_state in {"COMPLETED", "COMPLETED_LIMITED"},
                "total_objects_count": rm._accepted_object_count(self.store, cut),
                "source_generation_id": source.get("source_generation_id"),
            }

        model_cls.project_status = project_status
        model_cls._bdb_recursive_e6_projection_installed = True

    service_cls = ss.StageService
    if getattr(service_cls, "_bdb_recursive_e6_completion_installed", False):
        return

    original_qualify = service_cls.qualify_and_complete_stage

    def qualify_and_complete_stage(self, stage_key, *args, **kwargs):
        if str(stage_key).upper() != "E6":
            return original_qualify(self, stage_key, *args, **kwargs)

        cut = ss.current_accepted_cut(self.store)
        e6_specs = [
            row for row in self.store.accepted_records("stage_spec", cut)
            if row["body"].get("stage_key") == "E6"
        ]
        if not e6_specs:
            raise ValidationError("STAGE_SPEC_NOT_FOUND", "No accepted StageSpec found for E6")
        latest_e6 = max(e6_specs, key=lambda row: int(row.get("accepted_seq", 0)))
        latest_revision = str(latest_e6["body"].get("stage_spec_revision"))

        original_records = self.store.accepted_records
        original_lane_spec = ss.LaneSpec

        def chronological_records(kind, selected_cut):
            rows = original_records(kind, selected_cut)
            return tuple(sorted(
                rows,
                key=lambda row: (int(row.get("accepted_seq", 0)), row["ref"]["revision_digest"]),
            ))

        def e6_lane_spec(*lane_args, **lane_kwargs):
            lane_kwargs["stage_spec_revision"] = latest_revision
            return original_lane_spec(*lane_args, **lane_kwargs)

        self.store.accepted_records = chronological_records
        ss.LaneSpec = e6_lane_spec
        try:
            return original_qualify(self, "E6", *args, **kwargs)
        finally:
            self.store.accepted_records = original_records
            ss.LaneSpec = original_lane_spec

    service_cls.qualify_and_complete_stage = qualify_and_complete_stage
    service_cls._bdb_recursive_e6_completion_installed = True

"""Reference durable history adapter (Data Contracts §§14.6–15.5).

SQLite is used as a simple durable profile. Objects, commit, receipt, and the
single accepted-head pointer are written inside one explicit transaction. A
caller can supply named test-only crash hooks; hooks never exist as production
authority or recovery state.
"""
from dataclasses import dataclass
import json
import sqlite3
from pathlib import Path
from typing import Callable, Iterable

from ..core.canonical_json import canonical_bytes, parse
from ..core.errors import ValidationError
from ..core.hashing import object_digest
from ..core.registry import ContractRegistry, canonical_reference_set
from ..schemas.foundation import F2_KINDS, F3_KINDS, M5_KINDS, foundation_schema_bindings
from .closure import canonical_order, ClosureNode
from .objects import (
    EMPTY_HISTORY, ACCEPTED_HEAD_REF, AcceptedHead, CanonicalObject, CommandEnvelope,
    CommitBody, CommandReceipt, HistoryCut, InstallationBootstrapProfile,
)


class InjectedCrash(RuntimeError):
    """Named deterministic test-only persistence-boundary fault."""


TARGET_CLASS_MEMBERS = {
    "materiality_subject_ref": {"surface_record", "surface_key", "invariant_revision", "materiality_subject_ref"},
    "typed_scope_ref": {"surface_record", "surface_key", "invariant_revision", "finding_claim_revision", "scope_state_record", "typed_scope_ref"},
    "finding_or_risk_ref": {"finding_claim_revision", "finding_adjudication_decision", "residual_risk", "finding_or_risk_ref"},
    "limited_conclusion_basis_ref": {"stage_completion", "stop_evaluation", "residual_risk", "limited_conclusion_basis_ref"},
    "control_ref": {"raw_artifact_ref", "external_profile_ref", "control_ref"},
    "residual_risk_ref": {"residual_risk", "residual_risk_ref"},
    "coverage_obligation_summary_ref": {"coverage_obligation_summary_ref", "coverage_obligation_qualification"},
}


@dataclass(frozen=True)
class AcceptanceResult:
    commit: CommitBody
    receipt: CommandReceipt
    head: AcceptedHead
    already_accepted: bool = False


class TransactionalHistoryStore:
    """One Coordinator/Authority writer over one canonical history database."""
    HOOKS = (
        "before_object_durability", "after_object_durability",
        "before_commit_durability", "after_commit_before_receipt",
        "after_receipt_before_head", "after_head_durability",
        "after_commit_durability_before_ack",
    )

    def __init__(self, path, *, schema_bindings=None, registry=None, crash_hook=None):
        self.path = str(path)
        self.registry = registry or ContractRegistry()
        # Bind every foundation kind up front.  This is still a prerequisite
        # substrate (M10 qualification is separate), but no accepted closure
        # can reach an unbound registered dependency.
        self.schemas = schema_bindings or foundation_schema_bindings(kinds=tuple(F3_KINDS))
        self.crash_hook = crash_hook
        if crash_hook is not None and not callable(crash_hook):
            raise TypeError("crash_hook must be callable")
        self._initialize()

    def _connect(self):
        con = sqlite3.connect(self.path, isolation_level=None, timeout=30)
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA journal_mode=DELETE")
        con.execute("PRAGMA synchronous=FULL")
        return con

    def _initialize(self):
        con = self._connect()
        try:
            con.executescript("""
            CREATE TABLE IF NOT EXISTS immutable_objects(
              digest TEXT PRIMARY KEY, kind TEXT NOT NULL, version TEXT NOT NULL,
              schema_ref TEXT NOT NULL, logical_id TEXT, body BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS commits(
              seq INTEGER PRIMARY KEY, commit_hash TEXT NOT NULL UNIQUE,
              campaign_id TEXT NOT NULL, body BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS receipts(
              command_id TEXT PRIMARY KEY, command_digest TEXT NOT NULL,
              receipt_digest TEXT NOT NULL UNIQUE, body BLOB NOT NULL);
            CREATE TABLE IF NOT EXISTS accepted_head(
              singleton INTEGER PRIMARY KEY CHECK(singleton=1), campaign_id TEXT NOT NULL,
              seq INTEGER NOT NULL, commit_hash TEXT NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS command_index(
              command_id TEXT PRIMARY KEY, command_digest TEXT NOT NULL,
              receipt_digest TEXT NOT NULL);
            """)
        finally:
            con.close()

    def _hook(self, name):
        if name not in self.HOOKS:
            raise ValueError("unknown persistence boundary")
        if self.crash_hook is not None:
            result = self.crash_hook(name)
            if result is True or result == name:
                raise InjectedCrash(name)

    def head(self):
        con = self._connect()
        try:
            row = con.execute("SELECT campaign_id,seq,commit_hash FROM accepted_head WHERE singleton=1").fetchone()
            return AcceptedHead(*row) if row else None
        finally:
            con.close()

    def receipt(self, command_id):
        con = self._connect()
        try:
            row = con.execute("SELECT body FROM receipts WHERE command_id=?", (command_id,)).fetchone()
            if not row:
                return None
            return _receipt_from_body(json.loads(row[0]))
        finally:
            con.close()

    def commits(self):
        con = self._connect()
        try:
            return [json.loads(row[0]) for row in con.execute("SELECT body FROM commits ORDER BY seq")]
        finally:
            con.close()

    def object_record(self, digest):
        con = self._connect()
        try:
            row = con.execute("SELECT kind,version,schema_ref,logical_id,body FROM immutable_objects WHERE digest=?", (digest,)).fetchone()
            if not row:
                return None
            return {"kind": row[0], "version": row[1], "schema_revision_ref": row[2],
                    "logical_id": row[3], "revision_digest": digest, "body": json.loads(row[4])}
        finally:
            con.close()

    def resolve_accepted(self, ref, cut, *, require_current=False):
        """Resolve exact closure membership on a verified accepted cut.

        Object-table presence alone is never acceptance evidence. Validate the
        commit chain, cut context and complete typed identity before returning.
        This read creates no grant or other authority.
        """
        from .objects import ObjectRef
        ref = ref.as_dict() if isinstance(ref, ObjectRef) else ref
        typed = ObjectRef.from_dict(ref)
        cut = cut.as_dict() if isinstance(cut, HistoryCut) else cut
        if not isinstance(cut, dict) or cut.get("variant") != "ACCEPTED_HISTORY_CUT":
            raise ValidationError("ACCEPTED_HISTORY_CUT_REQUIRED")
        con = self._connect()
        try:
            con.execute("BEGIN")
            head_row = con.execute("SELECT campaign_id,seq,commit_hash FROM accepted_head WHERE singleton=1").fetchone()
            if head_row is None:
                raise ValidationError("ACCEPTED_HISTORY_CUT_NOT_FOUND")
            head = AcceptedHead(*head_row)
            seq = cut.get("accepted_head_seq")
            if type(seq) is not int or seq < 1 or seq > head.commit_seq:
                raise ValidationError("ACCEPTED_HISTORY_CUT_NOT_FOUND")
            if require_current and (seq != head.commit_seq or cut.get("accepted_head_hash") != head.commit_hash):
                raise ValidationError("STALE_HISTORY_CUT")
            previous = EMPTY_HISTORY
            found = None
            for stored_seq, digest, raw in con.execute("SELECT seq,commit_hash,body FROM commits WHERE seq<=? ORDER BY seq", (seq,)):
                body = json.loads(raw)
                commit = _commit_from_body(body)
                if commit.digest != digest or body["commit_seq"] != stored_seq or body["prev_history_ref"] != previous:
                    raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
                if body["campaign_id"] != head.campaign_id:
                    raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
                previous = {"tag": ACCEPTED_HEAD_REF, "campaign_id": head.campaign_id,
                            "commit_seq": stored_seq, "commit_hash": digest}
                if any(r.get("revision_digest") == typed.revision_digest and r.get("kind") == typed.kind
                       and r.get("schema_revision_ref") == typed.schema_revision_ref
                       and r.get("logical_id") == typed.logical_id for r in body["immutable_object_refs"]):
                    found = found or stored_seq
                if stored_seq == seq:
                    expected = HistoryCut.accepted(AcceptedHead(head.campaign_id, seq, digest),
                                                  body["governing_policy_ref"], body["governing_spec_refs"]).as_dict()
                    if cut != expected:
                        raise ValidationError("HISTORY_CUT_INPUT_MISMATCH")
            if found is None:
                raise ValidationError("OBJECT_NOT_ACCEPTED_AT_CUT")
            row = con.execute("SELECT kind,version,schema_ref,logical_id,body FROM immutable_objects WHERE digest=?", (typed.revision_digest,)).fetchone()
            if row is None:
                raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
            obj = CanonicalObject(row[0], json.loads(row[4]), row[2], row[3], row[1])
            if obj.digest != typed.revision_digest or obj.schema_revision_ref != typed.schema_revision_ref:
                raise ValidationError("ACCEPTED_HISTORY_INTEGRITY_FAILURE")
            return {"body": obj.body, "accepted_seq": found, "ref": obj.ref.as_dict()}
        finally:
            con.close()

    def accepted_records(self, kind, cut):
        """Rebuild kind membership from closure refs, never cached indices."""
        refs = {}
        for commit in self.commits():
            if commit["commit_seq"] > cut.get("accepted_head_seq", 0):
                break
            for ref in commit["immutable_object_refs"]:
                if ref["kind"] == kind:
                    refs[ref["revision_digest"]] = ref
        # Validate the cut even when this particular kind has no members.
        commits = self.commits()
        if not commits:
            raise ValidationError("ACCEPTED_HISTORY_CUT_NOT_FOUND")
        self.resolve_accepted(commits[0]["command_ref"], cut)
        return tuple(self.resolve_accepted(ref, cut) for _, ref in sorted(refs.items()))

    def _expected(self, expected_head, current):
        if expected_head is None:
            expected_head = EMPTY_HISTORY if current is None else current.as_dict()
        if expected_head == EMPTY_HISTORY:
            if current is not None:
                raise ValidationError("EMPTY_HISTORY_AFTER_INITIALIZATION")
            return 1, EMPTY_HISTORY
        expected = expected_head.as_dict() if isinstance(expected_head, AcceptedHead) else expected_head
        if type(expected) is not dict or expected.get("tag") not in (None, ACCEPTED_HEAD_REF):
            raise ValidationError("EXPECTED_HEAD_INVALID")
        canonical_current = {"tag": ACCEPTED_HEAD_REF, **current.as_dict()} if current is not None else None
        if expected.get("tag") == ACCEPTED_HEAD_REF:
            expected = {k: expected[k] for k in ("campaign_id", "commit_seq", "commit_hash") if k in expected}
        if current is None or expected != current.as_dict():
            raise ValidationError("EXPECTED_HEAD_CONFLICT")
        return current.commit_seq + 1, canonical_current

    def _check_schema_bindings(self, objects, command):
        # This check is intentionally before any persistence boundary.
        kinds = {"command_envelope", "commit_body", "command_receipt", *M5_KINDS}
        kinds.update(o.kind for o in objects)
        for kind in kinds:
            key = self.registry.contract(kind)["schema_ref"]
            self.schemas.require_bound(key)

    def _validate_object_schemas(self, objects):
        for obj in objects:
            self.schemas.validate_schema(obj.kind, canonical_bytes(obj.body), obj.version)

    @staticmethod
    def _ref_tokens(value):
        """Return identity spellings that can be used by an authority pin.

        History context fields are intentionally scalar pins in the current
        foundation contracts, while prepared objects use typed reference
        dictionaries.  Keeping the comparison at this boundary avoids
        treating a same-commit object as effective merely because its digest
        appears somewhere in a command body.
        """
        if isinstance(value, str):
            return {value}
        if isinstance(value, dict):
            return {v for v in (value.get("revision_digest"), value.get("logical_id"))
                    if isinstance(v, str)}
        return set()

    def _validate_semantic_authority(self, objects, command, profile, current, con):
        """Enforce input-cut authority and prohibit semantic self-upgrades.

        Policy/spec/actor/source authority are context bindings.  They may be
        pinned by the installation profile for the EMPTY_HISTORY bootstrap,
        or must match the already accepted parent commit for a normal command.
        A prepared object in the accepting closure can therefore never make
        itself effective by naming its own digest/logical id in one of these
        fields.  This check is deliberately independent from the content DAG:
        an order-only edge cannot satisfy authority or provenance.
        """
        same_commit_tokens = set()
        for obj in objects:
            same_commit_tokens.update({obj.digest})
            if obj.logical_id:
                same_commit_tokens.add(obj.logical_id)

        # Explicit semantic self-authorization markers are rejected for every
        # acceptance path, including bootstrap.  These fields are diagnostic
        # witnesses used by the pinned negative vectors; they cannot turn a
        # prepared object into an authority source.
        for obj in objects:
            body = obj.body
            if body.get("source_authority_created_in_same_commit"):
                raise ValidationError("SOURCE_AUTHORITY_NOT_PREESTABLISHED")
            if body.get("actor_identity_created_in_same_commit") or body.get("role_grant_created_in_same_commit"):
                raise ValidationError("ACTOR_AUTHORITY_NOT_PREESTABLISHED")
            if body.get("owner_operator_authority_same_commit"):
                raise ValidationError("GENESIS_CONTEXT_SELF_AUTHORIZATION")

        command_context = {
            command.governing_policy_ref,
            *command.governing_spec_refs,
        }
        if command_context & same_commit_tokens:
            raise ValidationError("SEMANTIC_CONTEXT_NOT_EFFECTIVE_AT_INPUT_HISTORY")
        if command.actor_ref in same_commit_tokens:
            raise ValidationError("ACTOR_AUTHORITY_NOT_EFFECTIVE_AT_INPUT_HISTORY")

        if current is None:
            # EMPTY_HISTORY has no accepted commit to consult.  The exact
            # installation profile is the only context authority allowed.
            if profile is None:
                raise ValidationError("BOOTSTRAP_PROFILE_REQUIRED")
            if command.governing_policy_ref != profile.pins["initial_governing_policy_ref"]:
                raise ValidationError("SEMANTIC_CONTEXT_NOT_EFFECTIVE_AT_INPUT_HISTORY")
            if tuple(command.governing_spec_refs) != (profile.pins["initial_transition_profile_ref"],):
                raise ValidationError("SEMANTIC_CONTEXT_NOT_EFFECTIVE_AT_INPUT_HISTORY")
            # The installation owner/trust root is represented by an external
            # scalar pin in the bootstrap profile; arbitrary same-commit actor
            # objects were already rejected above.  Keep the boundary explicit
            # without inventing a new actor object kind.
            if command.actor_ref.startswith("workspace/"):
                raise ValidationError("ACTOR_AUTHORITY_NOT_PREESTABLISHED")
            return

        row = con.execute("SELECT body FROM commits WHERE commit_hash=?", (current.commit_hash,)).fetchone()
        if row is None:
            raise ValidationError("ACCEPTED_HEAD_COMMIT_MISSING")
        prior = json.loads(row[0])
        if command.governing_policy_ref != prior.get("governing_policy_ref") or \
                tuple(command.governing_spec_refs) != tuple(prior.get("governing_spec_refs", ())):
            raise ValidationError("SEMANTIC_CONTEXT_NOT_EFFECTIVE_AT_INPUT_HISTORY")
        prior_actor = prior.get("actor_ref")
        if command.actor_ref != prior_actor:
            # This minimal foundation has no separate accepted actor-grant
            # family yet.  Until one is introduced by a later contract, only
            # an actor already recorded by the accepted parent is effective.
            raise ValidationError("ACTOR_AUTHORITY_NOT_EFFECTIVE_AT_INPUT_HISTORY")

    def _validate_history_cuts(self, objects, *, seq, current, profile, con):
        """Validate every tagged history input before content ordering.

        A history cut is context, never a same-commit content dependency.  The
        sole EMPTY_HISTORY_CUT values are initialization inputs bound to the
        installation profile; once a head exists all input cuts must bind the
        exact prior accepted head.  This recursive walk intentionally follows
        field names from the wire contract rather than treating arbitrary
        dictionaries as history cuts.
        """
        expected_empty = profile.empty_cut().as_dict() if profile is not None else None
        expected_accepted = None
        if current is not None:
            commit_row = con.execute(
                "SELECT body FROM commits WHERE commit_hash=?", (current.commit_hash,)
            ).fetchone()
            if commit_row is None:
                raise ValidationError("ACCEPTED_HEAD_COMMIT_MISSING")
            prior = json.loads(commit_row[0])
            expected_accepted = {
                "variant": "ACCEPTED_HISTORY_CUT",
                "campaign_id": current.campaign_id,
                "accepted_head_seq": current.commit_seq,
                "accepted_head_hash": current.commit_hash,
                "governing_policy_ref": prior.get("governing_policy_ref"),
                "governing_spec_refs": list(prior.get("governing_spec_refs", ())),
            }

        def walk(value, field_name=""):
            if isinstance(value, dict):
                if "variant" in value and field_name.endswith("history_cut"):
                    variant = value.get("variant")
                    if seq == 1:
                        if variant != "EMPTY_HISTORY_CUT":
                            raise ValidationError("HISTORY_INPUT_SAME_COMMIT_FORBIDDEN")
                        if expected_empty is not None and value != expected_empty:
                            raise ValidationError("HISTORY_CUT_PROFILE_BINDING_MISMATCH")
                    else:
                        if variant != "ACCEPTED_HISTORY_CUT":
                            raise ValidationError("HISTORY_INPUT_MUST_PREEXIST")
                        if expected_accepted is not None and value != expected_accepted:
                            raise ValidationError("HISTORY_CUT_INPUT_MISMATCH")
                    return
                for key, child in value.items():
                    walk(child, str(key))
            elif isinstance(value, list):
                for child in value:
                    walk(child, field_name)

        for obj in objects:
            walk(obj.body)

    def _validate_content_refs(self, objects, con):
        """Validate typed refs independently of order-only precedence.

        A CONTENT_OBJECT target must be in this closure. A CONTENT_OR_PRIOR
        target may be in the closure or an immutable object already persisted.
        History/context/sidecar refs are deliberately excluded from the content
        dependency graph and are validated by their owning object contract.
        """
        by_digest = {obj.digest: obj for obj in objects}
        if len(by_digest) != len(objects):
            raise ValidationError("DUPLICATE_CONTENT_REFERENCE")
        for obj in objects:
            for ref in obj.content_refs:
                if ref.ref_class not in {"CONTENT_OBJECT", "CONTENT_OR_PRIOR"}:
                    continue
                target = by_digest.get(ref.revision_digest)
                if target is not None and target.kind != ref.kind:
                    raise ValidationError("TYPED_REF_TARGET_MISMATCH")
                if ref.ref_class == "CONTENT_OBJECT" and target is None:
                    raise ValidationError("DANGLING_CONTENT_REF", ref.revision_digest)
                if target is None:
                    if ref.kind in self.registry.document.get("reference_target_classes", {}):
                        # Registry target classes (for example a pinned
                        # application-generation identity) may be external
                        # immutable locators rather than object rows.
                        continue
                    row = con.execute(
                        "SELECT kind,schema_ref FROM immutable_objects WHERE digest=?",
                        (ref.revision_digest,),
                    ).fetchone()
                    if row is None:
                        raise ValidationError("DANGLING_CONTENT_REF", ref.revision_digest)
                    if row[0] != ref.kind or row[1] != ref.schema_revision_ref:
                        raise ValidationError("TYPED_REF_TARGET_MISMATCH")

    def _validate_material_ref_contracts(self, obj):
        """Check exact field/class/allowed-kind/cardinality for inline refs.

        Structural executable schemas intentionally stay small; this layer is
        where the pinned Registry's explicit reference contract is enforced.
        """
        row = self.registry.contract(obj.kind, obj.version)
        body = obj.body
        semantics = self.registry.document["reference_class_semantics"]
        for spec in row.get("material_refs", ()):
            field = spec["field"]
            value = body.get(field)
            if value is None:
                count = 0
                values = []
            elif isinstance(value, list):
                count = len(value)
                values = value
            else:
                count = 1
                values = [value]
            card = spec.get("cardinality", "")
            required = card == "1" or card.startswith("1;") or card.startswith("1 for") or card.startswith("1..")
            if required and count < 1:
                raise ValidationError("REFERENCE_CARDINALITY_MISMATCH", field)
            if card.startswith("0..1") and count > 1:
                raise ValidationError("REFERENCE_CARDINALITY_MISMATCH", field)
            if isinstance(value, list) and value and all(
                    isinstance(item, dict) and {"kind", "revision_digest", "digest_profile", "schema_revision_ref"}.issubset(item)
                    for item in value):
                ordering = row.get("ordering_rules", {})
                has_override = field == "immutable_object_refs" or any(
                    "CANONICAL_TOPOLOGICAL" in str(rule) for rule in ordering.values()
                )
                if not has_override and value != canonical_reference_set(value):
                    raise ValidationError("ORDERING_RULE_DEFECT", field)
            for value_item in values:
                if not isinstance(value_item, dict) or not {"kind", "revision_digest", "digest_profile", "schema_revision_ref"}.issubset(value_item):
                    # Scalar refs (policy/actor/history strings) are allowed
                    # only where the exact reference class is a scalar wire
                    # binding. Content and profile refs must be typed objects.
                    if isinstance(value_item, str) and spec["ref_class"] in {
                            "AUTHORIZED_ACTOR_REF", "HISTORY_CONTEXT_BINDING",
                            "PINNED_INSTALLATION_REF", "PRIOR_ACCEPTED_ONLY"}:
                        continue
                    if field in {"expected_parent_head", "prev_history_ref", "accepted_head"} or "variant" in value_item:
                        continue
                    raise ValidationError("TYPED_REF_INCOMPLETE", field)
                if value_item.get("ref_class") != spec["ref_class"]:
                    raise ValidationError("REFERENCE_CLASS_MISMATCH", field)
                allowed_kinds = set(spec.get("allowed", ()))
                for a in list(allowed_kinds):
                    if a in TARGET_CLASS_MEMBERS:
                        allowed_kinds.update(TARGET_CLASS_MEMBERS[a])
                if value_item.get("kind") not in allowed_kinds and "registered_immutable_object" not in allowed_kinds:
                    raise ValidationError("TYPED_REF_TARGET_MISMATCH", field)
                if value_item.get("ref_class") not in semantics:
                    raise ValidationError("UNREGISTERED_REFERENCE_CLASS")

    def _validate_stop_snapshot_binding(self, obj, objects, con):
        snap_ref = obj.body.get("stop_input_snapshot_ref")
        if not isinstance(snap_ref, dict) or "revision_digest" not in snap_ref:
            return
        target_digest = snap_ref["revision_digest"]
        snap_obj = next((o for o in objects if o.digest == target_digest), None)
        if snap_obj is not None:
            snap_body = snap_obj.body
        else:
            row = con.execute("SELECT body FROM immutable_objects WHERE digest=?", (target_digest,)).fetchone()
            if row is None:
                return
            snap_body = json.loads(row[0])
        from ..stop.evaluator import validate_stop_snapshot_binding
        validate_stop_snapshot_binding(obj.body, snap_body)


    def _validate_bootstrap_closure(self, objects, profile):
        required = {
            "command_envelope", "source_generation", "legacy_raw_ref",
            "legacy_mechanical_validation_assessment", "source_reconciliation_assessment",
            "lineage_admission_assessment", "trusted_predecessor_selection_decision",
            "bootstrap_admission_decision", "campaign_genesis",
        }
        kinds = {o.kind for o in objects}
        missing = required - kinds
        if missing:
            raise ValidationError("BOOTSTRAP_CLOSURE_INCOMPLETE", ",".join(sorted(missing)))
        by_kind = {o.kind: o for o in objects}
        admission = by_kind["bootstrap_admission_decision"]
        if admission.body.get("result") == "BLOCKED_CANONICAL_ADMISSION":
            raise ValidationError("BLOCKED_ADMISSION_CANNOT_EMIT_GENESIS")
        genesis = by_kind["campaign_genesis"]
        admission_ref = genesis.body.get("bootstrap_admission_decision_ref")
        if not isinstance(admission_ref, dict) or admission_ref.get("revision_digest") != admission.digest:
            raise ValidationError("GENESIS_ADMISSION_BINDING_MISMATCH")
        # Order-only edges do not satisfy refs, authority, or provenance. Check
        # required refs independently through each object's typed body graph.
        if any(o.body.get("source_authority_created_in_same_commit") for o in objects):
            raise ValidationError("SOURCE_AUTHORITY_NOT_PREESTABLISHED")
        if any(o.body.get("owner_operator_authority_same_commit") for o in objects):
            raise ValidationError("GENESIS_CONTEXT_SELF_AUTHORIZATION")
        for obj in objects:
            pin = obj.body.get("predecessor_pin_ref", "")
            if isinstance(pin, str) and pin.startswith("workspace/"):
                raise ValidationError("UNTRUSTED_PREDECESSOR_PIN")
        # The exact bootstrap profile is an external trust root. Object body
        # fields must bind to its pins; same-commit replacements are not a
        # semantic upgrade.
        genesis = by_kind["campaign_genesis"]
        trust_ref = genesis.body.get("trust_profile_ref", {})
        trust_pin = profile.pins.get("initial_trust_profile_ref")
        if isinstance(trust_ref, dict) and isinstance(trust_pin, str):
            # A profile may pin an exact digest or an installation locator.
            # Compare the digest when the pin is digest-shaped; otherwise the
            # external installation locator remains the authority boundary.
            if len(trust_pin) == 64 and trust_ref.get("revision_digest") != trust_pin:
                raise ValidationError("GENESIS_TRUST_PROFILE_PIN_MISMATCH")
        if genesis.body.get("owner_operator_authority_same_commit"):
            raise ValidationError("GENESIS_CONTEXT_SELF_AUTHORIZATION")
        if genesis.body.get("input_history_cut", {}).get("variant") != "EMPTY_HISTORY_CUT":
            raise ValidationError("NORMAL_GENESIS_REQUIRES_EMPTY_HISTORY")
        selection = by_kind["trusted_predecessor_selection_decision"]
        predecessor_pin = selection.body.get("predecessor_pin_ref")
        allowed_pin_strings = {
            profile.pins.get("initial_trust_profile_ref"),
            profile.pins.get("allowed_history_namespace_ref"),
            "INSTALLATION_BOOTSTRAP_PROFILE_V1",
        }
        if isinstance(predecessor_pin, dict):
            if predecessor_pin.get("ref_class") != "PINNED_INSTALLATION_REF":
                raise ValidationError("UNTRUSTED_PREDECESSOR_PIN")
        elif predecessor_pin not in allowed_pin_strings:
            raise ValidationError("UNTRUSTED_PREDECESSOR_PIN")

    def _object_rows(self, objects):
        rows = []
        for obj in objects:
            if not isinstance(obj, CanonicalObject):
                raise ValidationError("OBJECT_REQUIRED")
            rows.append((obj.digest, obj.kind, obj.version, obj.schema_revision_ref,
                         obj.logical_id, canonical_bytes(obj.body)))
        return rows

    def accept(self, command: CommandEnvelope, expected_head=None, *, immutable_objects=(),
               ordered_events=(), bootstrap_profile=None, expected_closure=None):
        if not isinstance(command, CommandEnvelope):
            raise ValidationError("COMMAND_REQUIRED")
        objects = list(immutable_objects)
        if any(not isinstance(o, CanonicalObject) for o in objects):
            raise ValidationError("OBJECT_REQUIRED")
        command_obj = command.as_object()
        if not any(isinstance(o, CanonicalObject) and o.digest == command_obj.digest for o in objects):
            objects.insert(0, command_obj)
        self._check_schema_bindings(objects, command)
        self._validate_object_schemas(objects)
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            row = con.execute("SELECT command_digest,receipt_digest FROM command_index WHERE command_id=?", (command.command_id,)).fetchone()
            if row:
                if row[0] != command.digest:
                    raise ValidationError("ID_REUSE_CONFLICT")
                receipt_row = con.execute("SELECT body FROM receipts WHERE command_id=?", (command.command_id,)).fetchone()
                if receipt_row is None:
                    raise ValidationError("RECEIPT_MISSING_FOR_INDEX")
                receipt = _receipt_from_body(json.loads(receipt_row[0]))
                commit_body = json.loads(con.execute("SELECT body FROM commits WHERE commit_hash=?", (receipt.accepted_head.commit_hash,)).fetchone()[0])
                commit = _commit_from_body(commit_body)
                con.rollback()
                return AcceptanceResult(commit, receipt, receipt.accepted_head, True)

            current_row = con.execute("SELECT campaign_id,seq,commit_hash FROM accepted_head WHERE singleton=1").fetchone()
            current = AcceptedHead(*current_row) if current_row else None
            seq, parent = self._expected(expected_head, current)
            self._validate_semantic_authority(objects, command, bootstrap_profile, current, con)
            if command.command_kind == "INITIALIZE_CAMPAIGN_FROM_LEGACY":
                if seq != 1 or parent != EMPTY_HISTORY:
                    raise ValidationError("INITIALIZATION_ALREADY_COMPLETED")
                if bootstrap_profile is None:
                    raise ValidationError("BOOTSTRAP_PROFILE_REQUIRED")
                if command.bootstrap_profile_ref != bootstrap_profile.profile_ref:
                    raise ValidationError("BOOTSTRAP_PROFILE_BINDING_MISMATCH")
                self._validate_bootstrap_closure(objects, bootstrap_profile)
            elif seq == 1:
                raise ValidationError("INITIALIZATION_REQUIRED")
            if command.expected_parent_head != parent:
                raise ValidationError("COMMAND_BINDING_CONFLICT")
            if current is not None and command.campaign_ref != current.campaign_id:
                raise ValidationError("CAMPAIGN_NOT_PRIOR_ACCEPTED")
            self._validate_history_cuts(objects, seq=seq, current=current,
                                        profile=bootstrap_profile, con=con)
            campaign_id = command.proposed_campaign_id if seq == 1 else command.campaign_ref
            if not campaign_id:
                raise ValidationError("CAMPAIGN_ID_REQUIRED")
            self._validate_content_refs(objects, con)
            for obj in objects:
                self._validate_material_ref_contracts(obj)
                if obj.kind == "stop_input":
                    self._validate_stop_snapshot_binding(obj, objects, con)
            from ..orchestration.fsm import project_states
            prior_events = [event for (raw,) in con.execute("SELECT body FROM commits ORDER BY seq")
                            for event in json.loads(raw)["ordered_event_bodies"]]
            transition_events = [event for event in prior_events + list(ordered_events)
                                 if isinstance(event, dict) and any(key in event for key in ("aggregate", "from_state", "to_state"))]
            project_states(transition_events)
            closure_nodes = [ClosureNode.from_object(o, node_id=o.digest) for o in objects]
            ordered_ids = canonical_order(
                closure_nodes, command_kind=command.command_kind, commit_seq=seq,
                expected_parent="EMPTY_HISTORY" if parent == EMPTY_HISTORY else ACCEPTED_HEAD_REF,
                expected=expected_closure, registry=self.registry)
            ordered_refs = tuple(next(o.as_ref(ref_class="CONTENT_OBJECT") for o in objects if o.digest == d) for d in ordered_ids)
            if command_obj.digest not in ordered_ids:
                raise ValidationError("COMMAND_NOT_IN_CLOSURE")
            if seq == 1 and ordered_ids.index(command_obj.digest) != 0:
                raise ValidationError("COMMAND_MUST_PRECEDE_DOMAIN_OBJECTS")
            commit = CommitBody(
                campaign_id=campaign_id, commit_seq=seq,
                prev_history_ref=parent, command_ref=command_obj.as_ref(ref_class="CONTENT_OBJECT"),
                command_digest=command.digest, actor_ref=command.actor_ref,
                expected_parent_head=parent,
                governing_policy_ref=command.governing_policy_ref,
                governing_spec_refs=tuple(command.governing_spec_refs),
                ordered_event_bodies=tuple(ordered_events), immutable_object_refs=ordered_refs)
            commit_digest = commit.digest
            head = AcceptedHead(campaign_id, seq, commit_digest)
            receipt = CommandReceipt(command.command_id, command_obj.as_ref(ref_class="CONTENT_OBJECT"), ordered_refs,
                                     {"kind": "commit_body", "revision_digest": commit_digest,
                                      "digest_profile": "BDB-OBJECT-DIGEST-1",
                                     "schema_revision_ref": self.registry.contract("commit_body")["schema_ref"],
                                      "ref_class": "POST_ACCEPTANCE_SIDECAR"}, head)
            self.schemas.validate_schema("commit_body", canonical_bytes(commit.body()))
            self.schemas.validate_schema("command_receipt", canonical_bytes(receipt.body()))
            self._hook("before_object_durability")
            for row in self._object_rows(objects):
                con.execute("INSERT OR IGNORE INTO immutable_objects(digest,kind,version,schema_ref,logical_id,body) VALUES(?,?,?,?,?,?)", row)
            self._hook("after_object_durability")
            self._hook("before_commit_durability")
            con.execute("INSERT INTO commits(seq,commit_hash,campaign_id,body) VALUES(?,?,?,?)",
                        (seq, commit_digest, campaign_id, canonical_bytes(commit.body())))
            self._hook("after_commit_before_receipt")
            receipt_digest = receipt.digest
            con.execute("INSERT INTO receipts(command_id,command_digest,receipt_digest,body) VALUES(?,?,?,?)",
                        (command.command_id, command.digest, receipt_digest, canonical_bytes(receipt.body())))
            con.execute("INSERT INTO command_index(command_id,command_digest,receipt_digest) VALUES(?,?,?)",
                        (command.command_id, command.digest, receipt_digest))
            self._hook("after_receipt_before_head")
            if current is None:
                con.execute("INSERT INTO accepted_head(singleton,campaign_id,seq,commit_hash) VALUES(1,?,?,?)",
                            (campaign_id, seq, commit_digest))
            else:
                updated = con.execute(
                    "UPDATE accepted_head SET campaign_id=?,seq=?,commit_hash=? "
                    "WHERE singleton=1 AND campaign_id=? AND seq=? AND commit_hash=?",
                    (campaign_id, seq, commit_digest, current.campaign_id,
                     current.commit_seq, current.commit_hash),
                ).rowcount
                if updated != 1:
                    raise ValidationError("EXPECTED_HEAD_CONFLICT")
            self._hook("after_head_durability")
            con.commit()
            self._hook("after_commit_durability_before_ack")
            return AcceptanceResult(commit, receipt, head)
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def rebuild_projection(self):
        """Rebuild a derived sequence solely from canonical commits."""
        result = {"campaign_id": None, "state": "CREATED", "events": []}
        for body in self.commits():
            if result["campaign_id"] is None:
                result["campaign_id"] = body["campaign_id"]
            result["events"].extend(body["ordered_event_bodies"])
            for event in body["ordered_event_bodies"]:
                if event.get("aggregate") == "Campaign" and event.get("to_state"):
                    result["state"] = event["to_state"]
        return result


def _ref_from_body(value):
    from .objects import ObjectRef
    return ObjectRef.from_dict(value)


def _commit_from_body(body):
    return CommitBody(body["campaign_id"], body["commit_seq"], body["prev_history_ref"],
                      _ref_from_body(body["command_ref"]), body["command_digest"], body["actor_ref"],
                      body["expected_parent_head"], body["governing_policy_ref"],
                      tuple(body["governing_spec_refs"]), tuple(body["ordered_event_bodies"]),
                      tuple(_ref_from_body(r) for r in body["immutable_object_refs"]))


def _receipt_from_body(body):
    return CommandReceipt(body["command_id"], _ref_from_body(body["command_ref"]),
                          tuple(_ref_from_body(r) for r in body["result_object_refs"]),
                          body["accepted_commit_ref"], AcceptedHead.from_dict(body["accepted_head"]),
                          body["receipt_status"])

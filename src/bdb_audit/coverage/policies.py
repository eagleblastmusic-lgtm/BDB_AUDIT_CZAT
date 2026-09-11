"""Production Coverage Obligation Policy Library (F4 Domain Expansion / M16).

Defines production policy rules mapping surfaces and invariants to mandatory/auxiliary
CoverageObligations with stable CoverageObligationKeys, strict qualification semantics,
and full breadth/depth derivations.
"""
from dataclasses import dataclass, field
import hashlib
from typing import Any, Mapping, Sequence, Set

from ..core.canonical_json import canonical_bytes
from ..core.errors import ValidationError
from ..core.ids import new_id, validate_id, deterministic_id
from ..history.objects import CanonicalObject, ObjectRef
from .models import (
    CoverageObligationKey,
    CoverageObligation,
    CoverageObligationQualification,
    ObligationApplicabilityDecision,
    ApprovalDecision,
    MaterialityAssessment,
    QUALIFICATION_STATUSES,
    SUBSTANTIVE_OUTCOMES,
    APPLICABILITY_RESULTS,
    _ref_dict,
)


@dataclass(frozen=True)
class PolicyObligationRule:
    policy_rule_id: str
    scenario_class: str
    required_techniques: Sequence[str]
    is_mandatory: bool = True
    falsifier_requirements: Sequence[str] = ()


class ObligationPolicyLibrary:
    """Library of production obligation policy rules."""

    def __init__(self):
        self._rules_by_category: dict[str, list[PolicyObligationRule]] = {
            "HTTP_ROUTE": [
                PolicyObligationRule("rule_http_schema", "STATIC_SCHEMA", ["AST_ANALYZER"], is_mandatory=True),
                PolicyObligationRule("rule_http_fuzz", "FUZZ_INPUT", ["DYNAMIC_FUZZER"], is_mandatory=True),
                PolicyObligationRule("rule_http_auth", "AUTHORIZATION_BYPASS", ["SECURITY_PROBER"], is_mandatory=True),
            ],
            "PERSISTENCE": [
                PolicyObligationRule("rule_db_durability", "CRASH_RECOVERY", ["FAULT_INJECTOR"], is_mandatory=True),
                PolicyObligationRule("rule_db_concurrency", "TRANSACTION_ISOLATION", ["CONCURRENCY_TESTER"], is_mandatory=True),
            ],
            "PARSER": [
                PolicyObligationRule("rule_parser_differential", "MALFORMED_INPUT", ["DIFFERENTIAL_PARSER"], is_mandatory=True),
                PolicyObligationRule("rule_parser_resource", "RESOURCE_LIMIT", ["MEMORY_LIMITER"], is_mandatory=False),
            ],
            "CONCURRENCY": [
                PolicyObligationRule("rule_concurrency_race", "RACE_CONDITION", ["THREAD_SANITIZER"], is_mandatory=True),
                PolicyObligationRule("rule_concurrency_deadlock", "DEADLOCK_DETECTION", ["LOCK_ORDER_GRAPH"], is_mandatory=True),
            ],
            "AUTHORITY": [
                PolicyObligationRule("rule_auth_privilege", "PRIVILEGE_ESCALATION", ["CAPABILITY_AUDITOR"], is_mandatory=True),
                PolicyObligationRule("rule_auth_tamper", "DIGEST_INTEGRITY", ["TAMPER_SIMULATOR"], is_mandatory=True),
            ],
        }

    def get_rules_for_category(self, surface_category: str) -> list[PolicyObligationRule]:
        return list(self._rules_by_category.get(surface_category, [
            PolicyObligationRule("rule_generic_unit", "FUNCTIONAL_UNIT", ["UNIT_HARNESS"], is_mandatory=True),
        ]))

    def generate_obligations(
        self,
        surface_ref: Any,
        surface_category: str,
        invariant_ref: Any,
        invariant_logical_id: str,
        materiality_assessment_ref: Any,
        source_generation_ref: Any,
        history_cut: dict,
        environment_profile_ref: Any,
        governing_policy_ref: Any,
    ) -> list[CoverageObligation]:
        """Generate mandatory and auxiliary CoverageObligations according to pinned policy."""
        rules = self.get_rules_for_category(surface_category)
        obligations = []

        surf_key_str = (
            surface_ref.get("revision_digest")
            if isinstance(surface_ref, dict)
            else (surface_ref.digest if hasattr(surface_ref, "digest") else str(surface_ref))
        )

        for rule in rules:
            policy_ob_key = f"{rule.policy_rule_id}:{rule.scenario_class}"
            ob_key = CoverageObligationKey(
                source_generation_ref=source_generation_ref,
                target_scope_or_surface_ref=surface_ref,
                invariant_logical_id=invariant_logical_id,
                scenario_class=rule.scenario_class,
                environment_profile_ref=environment_profile_ref,
                policy_obligation_key=policy_ob_key,
            )

            # Deterministic obligation ID derived from key
            ob_id = deterministic_id("coverage_obligation", ob_key.digest)

            ob = CoverageObligation(
                obligation_id=ob_id,
                obligation_revision="1",
                obligation_input_history_cut=history_cut,
                source_generation_ref=source_generation_ref,
                target_scope_or_surface_ref=surface_ref,
                invariant_revision_ref=invariant_ref,
                scenario_class=rule.scenario_class,
                environment_profile_ref=environment_profile_ref,
                materiality_assessment_ref=materiality_assessment_ref,
                required_oracle_independence_predicate_ref={
                    "kind": "predicate",
                    "revision_digest": hashlib.sha256(b"independent_oracle").hexdigest(),
                    "digest_profile": "BDB-OBJECT-DIGEST-1",
                    "schema_revision_ref": "BDB_SCHEMA_REGISTRY::predicate/1",
                    "ref_class": "CONTENT_OR_PRIOR",
                },
                acceptance_predicate_ref={
                    "kind": "predicate",
                    "revision_digest": hashlib.sha256(b"no_violation").hexdigest(),
                    "digest_profile": "BDB-OBJECT-DIGEST-1",
                    "schema_revision_ref": "BDB_SCHEMA_REGISTRY::predicate/1",
                    "ref_class": "CONTENT_OR_PRIOR",
                },
                applicability_predicate_ref={
                    "kind": "predicate",
                    "revision_digest": hashlib.sha256(b"applicable_to_surface").hexdigest(),
                    "digest_profile": "BDB-OBJECT-DIGEST-1",
                    "schema_revision_ref": "BDB_SCHEMA_REGISTRY::predicate/1",
                    "ref_class": "CONTENT_OR_PRIOR",
                },
                policy_obligation_key=policy_ob_key,
                governing_policy_ref=governing_policy_ref,
                origin_ref=surface_ref,
                required_technique_or_capability_refs=[
                    {
                        "kind": "capability",
                        "revision_digest": hashlib.sha256(tech.encode()).hexdigest(),
                        "digest_profile": "BDB-OBJECT-DIGEST-1",
                        "schema_revision_ref": "BDB_SCHEMA_REGISTRY::capability/1",
                        "ref_class": "CONTENT_OR_PRIOR",
                    }
                    for tech in rule.required_techniques
                ],
                falsifier_or_control_requirements=[
                    {
                        "falsifier": fals,
                    }
                    for fals in rule.falsifier_requirements
                ],
            )
            obligations.append(ob)

        return obligations


def compute_breadth_summary(
    inventory_revision_ref: Any,
    obligation_set_revision: str,
    evaluations: Sequence[dict],
    scope_states: Sequence[Any] = (),
) -> dict:
    """Compute normative breadth summary as_of_head according to Contract §36."""
    mandatory_count = 0
    qualified_count = 0
    qualified_no_violation_count = 0
    qualified_violation_count = 0
    qualified_inconclusive_count = 0
    blocked_count = 0
    stale_count = 0
    waived_count = 0
    not_applicable_count = 0

    surface_depth_evals: dict[str, list[dict]] = {}

    for ev in evaluations:
        mandatory_count += 1
        status = ev.get("effective_status")
        substantive = ev.get("substantive_outcome")
        target = ev.get("target_ref") or "default_target"
        surface_depth_evals.setdefault(str(target), []).append(ev)

        if ev.get("is_not_applicable"):
            not_applicable_count += 1
        elif ev.get("is_waived"):
            waived_count += 1
        elif status == "QUALIFIED":
            qualified_count += 1
            if substantive == "NO_VIOLATION_OBSERVED":
                qualified_no_violation_count += 1
            elif substantive == "VIOLATION_CONFIRMED":
                qualified_violation_count += 1
            elif substantive == "INCONCLUSIVE":
                qualified_inconclusive_count += 1
        elif status == "BLOCKED":
            blocked_count += 1
        elif status == "STALE":
            stale_count += 1

    # Depth distribution per surface
    depth_distribution: dict[str, int] = {"D0": 0, "D1": 0, "D2": 0, "D3": 0, "D4": 0, "D5": 0}
    for tgt, ev_list in surface_depth_evals.items():
        # count satisfied
        sat = sum(1 for e in ev_list if e.get("satisfies_completion"))
        ratio = sat / len(ev_list) if ev_list else 0.0
        if sat == 0:
            d = "D0"
        elif ratio < 0.5:
            d = "D1"
        elif ratio < 0.8:
            d = "D2"
        elif ratio < 1.0:
            d = "D3"
        else:
            d = "D4"
        depth_distribution[d] += 1

    # Scope counts from scope states
    known_unobserved = sum(1 for s in scope_states if (s.state if hasattr(s, "state") else s.get("state")) == "KNOWN_UNOBSERVED_SCOPE")
    unsupported = sum(1 for s in scope_states if (s.state if hasattr(s, "state") else s.get("state")) == "UNSUPPORTED_SCOPE")
    unknown = sum(1 for s in scope_states if (s.state if hasattr(s, "state") else s.get("state")) == "UNKNOWN_SCOPE")

    return {
        "inventory_revision_ref": _ref_dict(inventory_revision_ref),
        "obligation_set_revision": obligation_set_revision,
        "mandatory_count": mandatory_count,
        "qualified_count": qualified_count,
        "qualified_no_violation_observed_count": qualified_no_violation_count,
        "qualified_substantive_violation_count": qualified_violation_count,
        "qualified_inconclusive_count": qualified_inconclusive_count,
        "blocked_count": blocked_count,
        "stale_count": stale_count,
        "waived_count": waived_count,
        "not_applicable_count": not_applicable_count,
        "known_unobserved_scope_count": known_unobserved,
        "unsupported_scope_count": unsupported,
        "unknown_scope_count": unknown,
        "derived_depth_distribution": depth_distribution,
    }

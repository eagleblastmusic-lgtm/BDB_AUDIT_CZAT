"""Explicit foundation FSM edge design from qualified Data section 14.2.

Lifecycle cycles are legal state-machine edges, not reference-DAG cycles.
This table does not authorize a transition without independent guard proof.
"""

from __future__ import annotations

import re

from execution import BASE, OUT, digest, preserve, write
from purpose_contracts import const


GUARDS = {
    "GENESIS": "Only the legal initial or successor genesis admission closure can establish identity; exact initialization namespace, roots and union-DAG rules apply.",
    "E0_READY": "All current exact bootstrap, source, environment and E0 readiness prerequisites independently pass.",
    "AUDIT_START": "Exact current source/policy and legally ready required ordinary-stage plan; no skipped prerequisite.",
    "BLOCK_OR_CANCEL": "Truthful independently supported blocker/failure or authenticated administrative cancellation; no assurance upgrade.",
    "STOP_BLOCKED": "Exact applicable prior StopEvaluation has BLOCKED at the declared intermediate/final/post-E6 context; complete reasons retained.",
    "E6_REQUIRED": "Exact applicable prior final/post-E6 StopEvaluation has E6_REQUIRED and supplies the legally required continuation scope.",
    "E6_START": "Prior E6_REQUIRED decision and applicable accepted continuation plan/budget/authorizations; unknown prerequisites reject.",
    "FINAL_PASS_CONCLUSION": "Prior current final/post-E6 StopEvaluation PASS and independently lawful accepted CampaignConclusion COMPLETED, complete required stages/candidate/challengers and no omitted material blocker. Conclusion may be an earlier content dependency in the same atomic accepting command only if its exact reference class permits; STOP/context/approval prerequisites are prior-only.",
    "LIMITED_CONCLUSION": "Exact lawful accepted limited conclusion with separate required prior owner approval and complete unresolved-material disclosure. AUDIT_RUNNING/E6_RUNNING require the exact applicable BLOCKED STOP; E6_REQUIRED requires its existing E6_REQUIRED basis; BLOCKED requires complete exact limited-conclusion basis. Only COMPLETED_LIMITED; no PASS/full assurance or false release readiness. Same-command conclusion content is allowed only by its exact reference class and acyclic atomic order, never by future reference.",
    "RESOLVE_CAMPAIGN_BLOCKER": "Exact resolved_blocker_refs prove all blocking facts remediated; unchanged source/policy and accepted ResolveBlocker/ReopenCampaign. New STOP required before any success conclusion.",
    "CAMPAIGN_CLOSE": "Prior accepted lawful CampaignConclusion and required finalization/report/close prerequisites; cancellation cannot fabricate conclusion authority.",
    "RUN_READY": "Exact run/spec/source, predecessor outputs and planned slot prerequisites; independent knowledge/isolation/gate predicates pass.",
    "RUN_START": "Ready exact run with active lawful campaign/parent, source and required authority; no terminal predecessor mutation.",
    "INPUT_WAIT": "Current exact source/run and independently observed required-input availability state; waiting does not satisfy missing outputs.",
    "COMPLETION_CANDIDATE": "All spec-required result/output slots supplied through their lawful accepted chains; candidate status is not completion qualification.",
    "COMPLETION_ACCEPT": "Independent complete L1-L7 lane/stage completion predicates, current cut/source, exact slots, knowledge/isolation, required outputs, accounting and evidence applicability.",
    "RETURN_TO_RUNNING": "Independent current evidence demonstrates completion-candidate prerequisites are not satisfied; no accepted completion revision is mutated.",
    "SUPERSEDE": "Authenticated exact prior-run/attempt supersession with lawful reason/current cut; no replacement of historical binding/results or retroactive execution.",
    "ATTEMPT_START": "Exact prior assignment and unique prior durable package binding in a separate earlier commit; CREATED active attempt, current source/grants/knowledge/isolation. Delivery remains separately guarded.",
    "RESULT_RECEIVE": "Trusted independent result raw admission, exact prior assignment/binding/STARTED, active declared slot and current input cut; caller command kind/token/body assertions confer no authority.",
    "RESULT_ACCEPT": "Prior accepted admission evidence in an earlier commit and exact independent retained-byte normalization; active slot/source/attempt and current result cut. No same-commit shortcut.",
    "ATTEMPT_FAILURE": "Truthful supported execution failure/blocker under current exact context; cannot create result/completion authority.",
}


def table():
    rows = []

    def add(aggregate, start, end, guard):
        assert guard in GUARDS
        rows.append({"aggregate_kind": aggregate, "from_state": start, "to_state": end, "guard": guard})

    add("CAMPAIGN", "CREATED", "GENESIS_ACCEPTED", "GENESIS")
    for start, end, guard in (
        ("GENESIS_ACCEPTED", "E0_READY", "E0_READY"), ("E0_READY", "AUDIT_RUNNING", "AUDIT_START"),
        ("AUDIT_RUNNING", "BLOCKED", "STOP_BLOCKED"), ("AUDIT_RUNNING", "E6_REQUIRED", "E6_REQUIRED"),
        ("AUDIT_RUNNING", "CAMPAIGN_CONCLUDED", "FINAL_PASS_CONCLUSION"),
        ("AUDIT_RUNNING", "CAMPAIGN_CONCLUDED", "LIMITED_CONCLUSION"),
        ("E6_REQUIRED", "E6_RUNNING", "E6_START"), ("E6_REQUIRED", "BLOCKED", "BLOCK_OR_CANCEL"),
        ("E6_REQUIRED", "CAMPAIGN_CONCLUDED", "LIMITED_CONCLUSION"),
        ("E6_RUNNING", "E6_REQUIRED", "E6_REQUIRED"), ("E6_RUNNING", "BLOCKED", "STOP_BLOCKED"),
        ("E6_RUNNING", "CAMPAIGN_CONCLUDED", "FINAL_PASS_CONCLUSION"),
        ("E6_RUNNING", "CAMPAIGN_CONCLUDED", "LIMITED_CONCLUSION"),
        ("BLOCKED", "AUDIT_RUNNING", "RESOLVE_CAMPAIGN_BLOCKER"),
        ("BLOCKED", "CAMPAIGN_CONCLUDED", "LIMITED_CONCLUSION"),
        ("CAMPAIGN_CONCLUDED", "CLOSED", "CAMPAIGN_CLOSE"),
    ):
        add("CAMPAIGN", start, end, guard)
    for start in ("GENESIS_ACCEPTED", "E0_READY"):
        for end in ("BLOCKED", "CANCELLED"):
            add("CAMPAIGN", start, end, "BLOCK_OR_CANCEL")

    source = BASE / "candidate/BDB_AUDIT_V2_DATA_AND_ARTIFACT_CONTRACTS_R5_4.md"
    text = source.read_text(encoding="utf-8-sig").split("## 14.2.", 1)[1].split("## 14.3.", 1)[0]
    block = next(b for b in re.findall(r"```text\n(.*?)```", text, re.S) if "StageRun:" in b)
    derived = {}
    for label, aggregate in (("StageRun", "STAGE_RUN"), ("LaneRun", "LANE_RUN"), ("Attempt", "ATTEMPT")):
        portion = block.split(label + ":", 1)[1]
        if label != "Attempt":
            portion = portion.split("\n\n", 1)[0]
        for line in portion.strip().splitlines():
            left, arrow, right = re.split(r"\s*(→|↔)\s*", line, maxsplit=1)
            for start in left.split(" | "):
                for end in right.split(" | "):
                    derived.setdefault(aggregate, []).append((start, end))
                    if arrow == "↔":
                        derived[aggregate].append((end, start))
    for aggregate, pairs in derived.items():
        for start, end in pairs:
            guard = ({"STARTED": "ATTEMPT_START", "RESULT_RECEIVED": "RESULT_RECEIVE", "RESULT_ACCEPTED": "RESULT_ACCEPT", "SUPERSEDED": "SUPERSEDE", "CANCELLED": "BLOCK_OR_CANCEL"}.get(end, "ATTEMPT_FAILURE")
                     if aggregate == "ATTEMPT" else
                     {"READY": "RUN_READY", "COMPLETION_CANDIDATE": "COMPLETION_CANDIDATE", "COMPLETION_ACCEPTED": "COMPLETION_ACCEPT", "SUPERSEDED": "SUPERSEDE", "BLOCKED": "BLOCK_OR_CANCEL", "CANCELLED": "BLOCK_OR_CANCEL", "WAITING_FOR_REQUIRED_INPUT": "INPUT_WAIT", "WAITING_RESULT": "INPUT_WAIT"}.get(end, "RETURN_TO_RUNNING" if start == "COMPLETION_CANDIDATE" else "INPUT_WAIT" if start.startswith("WAITING") else "RUN_START"))
            add(aggregate, start, end, guard)
    rows.sort(key=lambda row: tuple(row[k] for k in ("aggregate_kind", "from_state", "to_state", "guard")))
    assert len({tuple(r.values()) for r in rows}) == len(rows)
    return rows, source


def add_contract(add):
    rows, _ = table()
    add("FULL_PATH_TRANSITION_TABLE_V2", {"transitions": const(rows),
        "guard_contracts": const(GUARDS), "no_transition_stop_decisions": const(["AUDIT_RUNNING/INTERMEDIATE/CONTINUE_REQUIRED", "AUDIT_RUNNING/FINAL/CONTINUE_REQUIRED"]),
        "failure_rule": const("REJECT_AND_NO_CANONICAL_MUTATION")},
        rule="Exact Data 14.2 edge set and guard conjunctions. No arbitrary edge/guard extension. StageSpec/LaneSpec may only narrow. Every guard resolves independent current accepted context; caller booleans never prove a guard.")


def main():
    preserve()
    rows, source = table()
    write("design/FULL_PATH_TRANSITION_TABLE.json", {"profile_id": "FULL_PATH_TRANSITION_TABLE_V2", "source_raw_digest": digest(source), "source_section": "14.2",
        "transitions": rows, "guard_contracts": GUARDS, "candidate_materialized": False, "runtime": "NOT_RUN"})
    print({"explicit_transition_rows": len(rows), "guard_contracts": len(GUARDS), "runtime": "NOT_RUN"})


if __name__ == "__main__":
    main()

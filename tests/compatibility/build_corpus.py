"""Deterministic M1 construction. Run once; refuses to overwrite pinned corpus.

Independent decisions are explicit inputs, established before legacy replay.
Reconstruction can be compared in memory by tests; it never updates expectations.
"""
from __future__ import annotations

import io
import json
import warnings
import zipfile
from corpus_support import CORPUS, SOURCE_SHA, load_legacy, replay, selection, sha

BASE = "E1_SOL_BASE_PLUS_PLIKI"
E2 = "E2_SOL_ITERACJA_1"
REQ, RUN = "M1-SYNTHETIC-REQUEST-001", "M1-SYNTHETIC-ATTEMPT-001"
SOURCE_COMMIT, SOURCE_TREE = "a" * 40, "b" * 40


def js(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()


def bundle(files, duplicate=None, bad_hash=False):
    files = dict(files)
    manifest = "".join(f"{sha(files[n])}  {n}\n" for n in sorted(files)).encode()
    if bad_hash:
        manifest = b"0" * 64 + manifest[64:]
    files["ARTIFACT_HASHES.sha256"] = manifest
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as z:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, (2000, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            z.writestr(info, files[name])
        if duplicate:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                info = zipfile.ZipInfo(duplicate, (2000, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                z.writestr(info, files[duplicate])
    return out.getvalue()


def handoff(legacy, variant_id, order, final=False):
    variant, step = selection(legacy, variant_id, order)
    f2 = variant_id == E2 and order >= 2
    snapshot = b'{"seq":1,"type":"F1","source_sha":"' + SOURCE_COMMIT.encode() + b'"}\n'
    ledger = snapshot
    if f2:
        ledger += b'{"seq":2,"type":"F2","previous_prompt_revealed":true}\n'
    files = {"AUDIT_LEDGER.jsonl": ledger,
             "ORACLE_INDEPENDENCE_RECORD.json": js({"schema":"BDB_ORACLE_INDEPENDENCE_RECORD_V1", "scope":"synthetic M1 control", "expectation_basis":"R5.3 migration sections 4.1-4.3; manually adjudicated controls"}),
             "RUN_MANIFEST.json": js({"schema":"BDB_RUN_MANIFEST_V1", "variant_id":variant_id,
                 "audit_request_id":REQ, "audit_attempt_id":RUN,
                 "resolved_source_identity":{"source_sha":SOURCE_COMMIT,"source_tree":SOURCE_TREE},
                 "app_version":"1.4.4", "wrapper_release":"5.4-RC1",
                 "prompt_sha256":step["primary_prompt"]["sha256"],
                 "execution_context_sha256":sha(b"M1 synthetic execution context")}),
             "PRE_F1_SOURCE_INTEGRITY_READBACK.json":js({"schema":"BDB_PRE_F1_SOURCE_INTEGRITY_READBACK_V1", "status":"PASS", "source_sha":SOURCE_COMMIT,"source_tree":SOURCE_TREE,"pristine_tracked_status":"CLEAN"})}
    for kind, snap, end in [("F1",snapshot,1)] + ([("F2",ledger,2)] if f2 else []):
        name = "F1_SOURCE_CHECKPOINT.json" if kind == "F1" else "F2_PRE_REPORT_CHECKPOINT.json"
        cp = {"schema":f"BDB_{kind}_SOURCE_CHECKPOINT_V1", "variant_id":variant_id,
              "audit_request_id":REQ,"audit_attempt_id":RUN,"source_sha":SOURCE_COMMIT,"source_tree":SOURCE_TREE,
              "retained_ledger_snapshot_sha256":sha(snap),f"{kind.lower()}_ledger_sequence_end":end}
        files[name] = js(cp)
        files[f"{kind}_RETAINED_LEDGER_SNAPSHOT.jsonl"] = snap
        files[f"{kind}_DIGEST_RECORD.json"] = js({"schema":f"BDB_{kind}_DIGEST_RECORD_V1",
            "checkpoint_sha256":sha(files[name]),"audit_ledger_sha256":sha(ledger),
            "retained_ledger_snapshot_sha256":sha(snap),"ledger_prefix_continuity":"PASS","readback_byte_identity":"PASS"})
    files["STAGE_STATUS.json"] = js({"variant_id":variant_id,
        "run_state":"AWAITING_CANONICAL_REVEAL_AFTER_VALID_F1" if variant_id==BASE and not final else "SYNTHETIC_CHECKPOINT_RETAINED",
        "f1_written_and_read_back_before_reveal":"YES", "canonical_read":"NO", "f2_created":"NO" if not f2 else "YES"})
    if final:
        files.update({"FINAL_OUTCOME.json":js({"schema":"BDB_FINAL_OUTCOME_V1","variant_id":variant_id,"scope":"synthetic qualification only","result":"NO_SYNTHETIC_FINDINGS"}),
            "FINAL_TECHNICAL_AUDIT_REPORT.md":b"# Synthetic M1 final report\nNo real audit or release qualification.\n",
            "FINAL_SOURCE_INTEGRITY_READBACK.json":files["PRE_F1_SOURCE_INTEGRITY_READBACK.json"]})
        if f2:
            files["LINEAGE_MANIFEST.json"] = js({"variant_id":variant_id,"direct_predecessor_variant_id":"E1_SOL_BASE","scope":"synthetic M1 lineage control"})
    return files


def constructs(legacy):
    """Yield bytes, call context and manually chosen safety decisions before replay."""
    rows = []
    def add(fid, raw, route, variant, order, intent, family="NONE", control=None, **extra):
        rows.append((raw, {"fixture_id":fid,"path":f"raw/{fid}." + ("json" if route=="ticket" else "zip"),
            "media_type":"application/json" if route=="ticket" else "application/zip",
            "fixture_intent":intent,"legacy_call":{"route":route,"variant_id":variant,"step_order":order,**extra},
            "independent_safe_expected_result":"ACCEPT" if fid.startswith("VALID_") else "REJECT",
            "independent_expected_error_family":family,"positive_control":control,
            "expectation_basis_ref":f"EXPECTATION_BASIS.md#{fid.lower().replace('_','-')}",
            "known_legacy_bug":False,"intentional_v2_hardening":False,"compatibility_exception_ref":None}))
    b1 = handoff(legacy,BASE,1)
    e1 = handoff(legacy,E2,1)
    e2 = handoff(legacy,E2,2)
    for fid, files, variant, order, route, intent in [
        ("VALID_BASE_F1",b1,BASE,2,"prior","BASE checkpoint: matching source/run/audit identities, exact retained prefix, readback and digest bindings before canonical reveal."),
        ("VALID_BASE_FINAL",handoff(legacy,BASE,2,True),BASE,2,"result","BASE final family with F1 retention and no previous-report or F2 artifacts."),
        ("VALID_E2_F1",e1,E2,2,"prior","E2 F1 checkpoint with matching identities and retained prefix before previous-prompt reveal."),
        ("VALID_E2_F2",e2,E2,3,"prior","E2 F2 checkpoint retains the exact F1 prefix and F2 snapshot after previous-prompt reveal."),
        ("VALID_E2_FINAL",handoff(legacy,E2,3,True),E2,3,"result","E2 final family retains both checkpoints, snapshots, final readback and predecessor lineage.")]:
        add(fid,bundle(files),route,variant,order,intent)
    v,s=selection(legacy,BASE,2)
    attname=legacy.attestation_json_basename(s)
    att={"schema":"BDB_PRE_CANONICAL_REVEAL_GATE_PASS_ATTESTATION_V1","variant_id":BASE,"krok":2,
         "delivery_mode":"PRIMARY","gate_result":"PASS","run_state":legacy.expected_manual_run_state(s),
         "staged_payload_semantics_exposed_before_attestation":False,"source_generations_mixed":False,
         "substitute_f2_created":False,"attestation_is_checkpoint":False,"attestation_is_f2":False,
         "run_id":RUN,"audit_id":REQ,"expected_next_payloads":legacy.expected_staged_payload_metadata(v,s),
         "frozen_source_identity":{"route":"D","source_sha":SOURCE_COMMIT,"source_tree":SOURCE_TREE}}
    attbytes=bundle({attname:js(att)})
    add("VALID_ATTESTATION",attbytes,"attestation",BASE,2,"Transport-only attestation declares no early exposure, generation mix, or substitute checkpoint; payload identities match pinned canonical inputs.")
    ticket={"schema":"BDB_CONTINUATION_TICKET_V1","variant_id":BASE,"step_order":2,
        "expected_attestation_filename":legacy.expected_attestation(s),"expected_run_state":legacy.expected_manual_run_state(s),
        "fallback_prompt_sha256":s["fallback_prompt"]["sha256"],"prior_handoff_sha256":sha(bundle(b1)),
        "prior_handoff_validation":{"status":"PASS","audit_request_id":REQ,"audit_attempt_id":RUN,
            "source_sha":SOURCE_COMMIT,"source_tree":SOURCE_TREE,"zip_sha256":sha(bundle(b1))}}
    add("VALID_CONTINUATION_TICKET",js(ticket),"ticket",BASE,2,"Ticket binds the same variant, step, fallback, attestation state and exact prior-handoff identity.",
        control="VALID_ATTESTATION",attestation_path="raw/VALID_ATTESTATION.zip",attestation_raw_digest=sha(attbytes))
    _,ps=selection(legacy,E2,2)
    add("VALID_PREVIOUS_PROMPT_BUNDLE",legacy.embedded_bytes(ps["previous_prompt_bundles"][0]),"previous_prompt_self_test",E2,2,
        "Exact embedded predecessor prompt bytes, membership and consumer/predecessor identities; cross-step outer digest references agree.")
    def change(files,name,key,value):
        files=dict(files); doc=json.loads(files[name]);doc[key]=value;files[name]=js(doc);return files
    for fid,key,value,family in [("WRONG_VARIANT","variant_id","E1_SOL_BASE","VARIANT_IDENTITY"),
        ("WRONG_RUN_ID","audit_attempt_id","OTHER-ATTEMPT","RUN_IDENTITY"),
        ("WRONG_AUDIT_ID","audit_request_id","OTHER-REQUEST","AUDIT_IDENTITY")]:
        files=change(b1,"RUN_MANIFEST.json",key,value)
        add(fid,bundle(files),"prior",BASE,2,f"Change only RUN_MANIFEST.{key}; checkpoint retains the positive control identity.",family,"VALID_BASE_F1")
    for fid,key,family in [("WRONG_SOURCE_SHA","source_sha","SOURCE_COMMIT_IDENTITY"),("WRONG_SOURCE_TREE","source_tree","SOURCE_TREE_IDENTITY")]:
        files=dict(b1); doc=json.loads(files["RUN_MANIFEST.json"]);doc["resolved_source_identity"][key]="c"*40;files["RUN_MANIFEST.json"]=js(doc)
        add(fid,bundle(files),"prior",BASE,2,f"Manifest {key} contradicts checkpoint/readback; artifact hashes are recomputed.",family,"VALID_BASE_F1")
    files=dict(b1); files["evidence/PRE_F1_SOURCE_INTEGRITY_READBACK.json"]=js({"status":"PASS","source_sha":"c"*40,"source_tree":SOURCE_TREE})
    add("CONFLICTING_DUPLICATE",bundle(files),"prior",BASE,2,"Conflicting evidence copy of the root source readback.","CONFLICTING_MEMBER","VALID_BASE_F1")
    add("INVALID_HASH_MANIFEST",bundle(b1,bad_hash=True),"prior",BASE,2,"One manifest digest is all zero; payload bytes unchanged.","ARTIFACT_HASH_IDENTITY","VALID_BASE_F1")
    files=dict(b1);del files["F1_RETAINED_LEDGER_SNAPSHOT.jsonl"]
    add("MISSING_SNAPSHOT",bundle(files),"prior",BASE,2,"Required retained F1 snapshot absent, with transport hashes otherwise consistent.","RETAINED_SNAPSHOT_REQUIRED","VALID_BASE_F1")
    files=dict(b1);files["AUDIT_LEDGER.jsonl"]=b' '+files["AUDIT_LEDGER.jsonl"]
    d=json.loads(files["F1_DIGEST_RECORD.json"]);d["audit_ledger_sha256"]=sha(files["AUDIT_LEDGER.jsonl"]);files["F1_DIGEST_RECORD.json"]=js(d)
    add("BROKEN_LEDGER_PREFIX",bundle(files),"prior",BASE,2,"Leading whitespace preserves parsed ledger records but breaks exact retained raw prefix; digest record updated.","RAW_LEDGER_PREFIX","VALID_BASE_F1")
    for fid,original,name,kind,variant,order,control in [
        ("BAD_F1_CHECKPOINT",b1,"F1_SOURCE_CHECKPOINT.json","F1",BASE,2,"VALID_BASE_F1"),
        ("BAD_F2_CHECKPOINT",e2,"F2_PRE_REPORT_CHECKPOINT.json","F2",E2,3,"VALID_E2_F2")]:
        files=change(original,name,f"{kind.lower()}_ledger_sequence_end",99)
        d=json.loads(files[f"{kind}_DIGEST_RECORD.json"]);d["checkpoint_sha256"]=sha(files[name]);files[f"{kind}_DIGEST_RECORD.json"]=js(d)
        add(fid,bundle(files),"prior",variant,order,"Checkpoint declares sequence end 99 although retained ledger ends at 1 or 2; hashes consistent.","CHECKPOINT_SEQUENCE_BINDING",control)
    for fid,key,family in [("EARLY_REVEAL","staged_payload_semantics_exposed_before_attestation","REVEAL_ORDER"),
        ("SOURCE_GENERATION_MIX","source_generations_mixed","SOURCE_GENERATION_ISOLATION"),
        ("SUBSTITUTE_F2","substitute_f2_created","CHECKPOINT_NON_SUBSTITUTION")]:
        doc=dict(att);doc[key]=True
        add(fid,bundle({attname:js(doc)}),"attestation",BASE,2,f"Attestation explicitly declares {key}=true; all other positive-control facts unchanged.",family,"VALID_ATTESTATION")
    files=dict(b1);files["../escape.txt"]=b"synthetic traversal control\n"
    add("UNSAFE_ZIP_PATH",bundle(files),"prior",BASE,2,"Traversal member must be rejected without extraction.","ZIP_PATH_SAFETY","VALID_BASE_F1")
    add("DUPLICATE_MEMBER",bundle(b1,duplicate="RUN_MANIFEST.json"),"prior",BASE,2,"Two physically distinct ZIP entries have the same exact name and bytes.","ZIP_MEMBER_UNIQUENESS","VALID_BASE_F1")
    # Correct final prompt metadata, but handoff artifact family remains incomplete.
    files=dict(b1);doc=json.loads(files["RUN_MANIFEST.json"]);doc["prompt_sha256"]=s["primary_prompt"]["sha256"];files["RUN_MANIFEST.json"]=js(doc)
    add("WRONG_ARTIFACT_FAMILY",bundle(files),"result",BASE,2,"F1 handoff submitted where a final bundle is required; final report/outcome/readback are absent.","FINAL_ARTIFACT_FAMILY","VALID_BASE_FINAL")
    return rows


def main():
    if CORPUS.exists():
        raise SystemExit("Refusing to overwrite immutable corpus; use reconstruction test.")
    legacy=load_legacy()
    rows=constructs(legacy)
    CORPUS.mkdir();(CORPUS/"raw").mkdir()
    manifest={"schema":"BDB_M1_COMPATIBILITY_CORPUS_V1","starting_head":"4f14ab55cdc22f2137d9cea6f7f1d25fc2be9d33",
        "legacy_source_sha256":SOURCE_SHA,"unresolved_expectation_conflicts":[],"fixtures":[]}
    for raw,row in rows:
        row.update(raw_digest=sha(raw),byte_length=len(raw))
        (CORPUS/row["path"]).write_bytes(raw)
        manifest["fixtures"].append(row)
    # Persist adjudication before any execution of the validators.
    basis="# M1 independent expectation adjudication\n\n" + (
        "Scope: synthetic artifact safety controls, not real audit/release qualification.\n"
        "Authority: CODEX_M1_PR002_CONTEXT_R5_3.md B (Roadmap 7-9), C (Migration 4.1-4.3), "
        "D (Test Plan 9, 10, 19-22). The original validators are preservation evidence only.\n"
        "The fixture author manually adjudicates ACCEPT for consistent positive controls and REJECT "
        "for the specific violated property below. Error families here are corpus semantic labels, "
        "not new runtime codes or compatibility policy. Byte manifests are rebuilt after intentional "
        "semantic mutations except INVALID_HASH_MANIFEST. No expected result is copied from replay.\n"
        "Literal legacy payload identities may be obtained from frozen embedded contracts; the safety "
        "rule is independently exact equality/membership, not whatever the validator accepts.\n\n")
    for raw,row in rows:
        basis+=f"## {row['fixture_id'].replace('_',' ')}\n\n{row['fixture_intent']}\n\nDecision: {row['independent_safe_expected_result']}; family: {row['independent_expected_error_family']}. "
        basis+=f"Positive control: {row['positive_control'] or 'self: consistent identities, bindings and required family'}. "
        basis+="Basis: Migration 4.1/4.2 and 4.3; Test Plan 19-22; ZIP cases additionally section 9, hashes section 10.\n\n"
    (CORPUS/"EXPECTATION_BASIS.md").write_bytes((basis.rstrip() + "\n").encode())
    (CORPUS/"manifest.json").write_bytes(js(manifest))
    for row in manifest["fixtures"]:
        observed=replay(legacy,row)
        row.update(legacy_observed_result=observed["result"],legacy_observed_error_family=observed["error_families"],legacy_observed_errors=observed["errors"])
        accepted=observed["result"] in ("PASS","PASS_INTERMEDIATE")
        if accepted != (row["independent_safe_expected_result"]=="ACCEPT"):
            manifest["unresolved_expectation_conflicts"].append(row["fixture_id"])
        print(row["fixture_id"],observed)
    (CORPUS/"manifest.json").write_bytes(js(manifest))


if __name__ == "__main__":
    main()

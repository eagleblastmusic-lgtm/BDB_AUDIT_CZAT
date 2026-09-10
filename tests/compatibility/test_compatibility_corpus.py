"""M1 acceptance: byte preservation and independent, bounded safety controls."""
import json
from pathlib import PurePosixPath
import zipfile

import pytest

from corpus_support import CORPUS, ROOT, load_legacy, replay, sha, verify_identity
from build_corpus import constructs

VALID = set("VALID_BASE_F1 VALID_BASE_FINAL VALID_E2_F1 VALID_E2_F2 VALID_E2_FINAL VALID_ATTESTATION VALID_CONTINUATION_TICKET VALID_PREVIOUS_PROMPT_BUNDLE".split())
INVALID = set("WRONG_VARIANT WRONG_SOURCE_SHA WRONG_SOURCE_TREE WRONG_RUN_ID WRONG_AUDIT_ID CONFLICTING_DUPLICATE INVALID_HASH_MANIFEST MISSING_SNAPSHOT BROKEN_LEDGER_PREFIX BAD_F1_CHECKPOINT BAD_F2_CHECKPOINT EARLY_REVEAL SOURCE_GENERATION_MIX SUBSTITUTE_F2 UNSAFE_ZIP_PATH DUPLICATE_MEMBER WRONG_ARTIFACT_FAMILY".split())
MANIFEST = json.loads((CORPUS / "manifest.json").read_bytes())
ROWS = {r["fixture_id"]: r for r in MANIFEST["fixtures"]}
INPUTS = json.loads((CORPUS / "EXPECTATION_INPUTS.json").read_bytes())


def members(fid):
    with zipfile.ZipFile(CORPUS / ROWS[fid]["path"]) as z:
        return {i.filename:z.read(i) for i in z.infolist()}


def doc(files, name):
    return json.loads(files[name])


@pytest.fixture(scope="module")
def legacy():
    return load_legacy()


def test_manifest_completeness_and_classifications():
    rows=MANIFEST["fixtures"]
    assert len(rows)==25 and set(ROWS)==VALID|INVALID
    paths=[str(PurePosixPath(r["path"])).casefold() for r in rows]
    assert len(paths)==len(set(paths))
    assert len(rows)==len(ROWS)
    for r in rows:
        p=PurePosixPath(r["path"])
        assert not p.is_absolute() and ".." not in p.parts and "\\" not in r["path"]
        assert p.parts[0]=="raw"
        assert r["fixture_intent"] and r["media_type"] in ("application/zip","application/json")
        assert type(r["known_legacy_bug"]) is bool
        assert type(r["intentional_v2_hardening"]) is bool
        assert not r["known_legacy_bug"] and not r["intentional_v2_hardening"]
        assert r["compatibility_exception_ref"] is None
        assert r["independent_safe_expected_result"] == ("ACCEPT" if r["fixture_id"] in VALID else "REJECT")
        assert (r["independent_expected_error_family"]=="NONE") == (r["fixture_id"] in VALID)
        basis,anchor=r["expectation_basis_ref"].split("#")
        text=(CORPUS/basis).read_text(encoding="utf-8")
        assert "## " + anchor.replace("-"," ").upper() in text
    assert MANIFEST["unresolved_expectation_conflicts"]==[]


@pytest.mark.parametrize("fid",sorted(VALID|INVALID))
def test_raw_identity_and_mutation(fid):
    row=ROWS[fid];raw=(CORPUS/row["path"]).read_bytes()
    verify_identity(row,raw)
    altered=bytearray(raw);altered[len(raw)//2]^=1
    with pytest.raises(ValueError,match="FIXTURE_RAW_IDENTITY_MISMATCH"):
        verify_identity(row,bytes(altered))
    with pytest.raises(ValueError):
        verify_identity(row,raw+b"\n")


@pytest.mark.parametrize("fid",sorted(VALID|INVALID))
def test_frozen_legacy_replay(legacy,fid):
    row=ROWS[fid];observed=replay(legacy,row)
    assert observed["result"]==row["legacy_observed_result"]
    assert observed["errors"]==row["legacy_observed_errors"]
    assert observed["error_families"]==row["legacy_observed_error_family"]
    assert observed["result"] == ("PASS" if fid in VALID else "FAIL")
    assert bool(observed["errors"]) == (fid in INVALID)


def test_deterministic_reconstruction_without_writing(legacy):
    for raw,row in constructs(legacy):
        pinned=ROWS[row["fixture_id"]]
        assert raw==(CORPUS/pinned["path"]).read_bytes()
        for key in row:
            assert row[key]==pinned[key]


@pytest.mark.parametrize("fid",sorted(VALID-{"VALID_CONTINUATION_TICKET","VALID_PREVIOUS_PROMPT_BUNDLE"}))
def test_positive_control_transport_hashes(fid):
    f=members(fid)
    lines=f.pop("ARTIFACT_HASHES.sha256").decode().splitlines()
    assert lines==[f"{sha(f[n])}  {n}" for n in sorted(f)]
    with zipfile.ZipFile(CORPUS/ROWS[fid]["path"]) as z:
        assert len(z.namelist())==len(set(z.namelist()))
        assert z.testzip() is None
        assert all(not PurePosixPath(n).is_absolute() and ".." not in PurePosixPath(n).parts and "\\" not in n for n in z.namelist())


@pytest.mark.parametrize("fid",sorted(VALID & {"VALID_BASE_F1","VALID_BASE_FINAL","VALID_E2_F1","VALID_E2_F2","VALID_E2_FINAL"}))
def test_independent_positive_checkpoint_controls(fid):
    f=members(fid);run=doc(f,"RUN_MANIFEST.json")
    assert run["audit_request_id"]=="M1-SYNTHETIC-REQUEST-001"
    assert run["audit_attempt_id"]=="M1-SYNTHETIC-ATTEMPT-001"
    assert run["resolved_source_identity"]=={"source_sha":"a"*40,"source_tree":"b"*40}
    for kind,name in [("F1","F1_SOURCE_CHECKPOINT.json"),("F2","F2_PRE_REPORT_CHECKPOINT.json")]:
        if name not in f:
            assert kind=="F2" and fid not in {"VALID_E2_F2","VALID_E2_FINAL"}
            continue
        cp=doc(f,name);snapshot=f[f"{kind}_RETAINED_LEDGER_SNAPSHOT.jsonl"]
        assert all(cp[k]==run[k] for k in ("variant_id","audit_request_id","audit_attempt_id"))
        assert all(cp[k]==run["resolved_source_identity"][k] for k in ("source_sha","source_tree"))
        assert f["AUDIT_LEDGER.jsonl"].startswith(snapshot)
        records=[json.loads(line) for line in snapshot.splitlines()]
        assert [r["seq"] for r in records]==list(range(1,len(records)+1))
        assert cp[f"{kind.lower()}_ledger_sequence_end"]==len(records)
        assert cp["retained_ledger_snapshot_sha256"]==sha(snapshot)
        digest=doc(f,f"{kind}_DIGEST_RECORD.json")
        assert digest["checkpoint_sha256"]==sha(f[name])
        assert digest["audit_ledger_sha256"]==sha(f["AUDIT_LEDGER.jsonl"])
        assert digest["retained_ledger_snapshot_sha256"]==sha(snapshot)
    rb=doc(f,"PRE_F1_SOURCE_INTEGRITY_READBACK.json")
    assert rb["status"]=="PASS" and rb["pristine_tracked_status"]=="CLEAN"
    assert all(rb[k]==run["resolved_source_identity"][k] for k in ("source_sha","source_tree"))
    if "FINAL" in fid:
        assert {"FINAL_OUTCOME.json","FINAL_TECHNICAL_AUDIT_REPORT.md","FINAL_SOURCE_INTEGRITY_READBACK.json"} <= f.keys()
        if "E2" in fid:
            assert doc(f,"LINEAGE_MANIFEST.json")["direct_predecessor_variant_id"]=="E1_SOL_BASE"
    if "BASE" in fid:
        assert not any("F2" in n or "PREVIOUS_" in n for n in f)


def test_independent_attestation_and_ticket_controls():
    f=members("VALID_ATTESTATION")
    att=doc(f,"PRE_CANONICAL_REVEAL_GATE_PASS_ATTESTATION.json")
    assert att["variant_id"]=="E1_SOL_BASE_PLUS_PLIKI" and att["krok"]==2
    assert att["delivery_mode"]=="PRIMARY" and att["gate_result"]=="PASS"
    for k in ("staged_payload_semantics_exposed_before_attestation","source_generations_mixed","substitute_f2_created","attestation_is_checkpoint","attestation_is_f2"):
        assert att[k] is False
    assert len(att["expected_next_payloads"])==2
    assert att["expected_next_payloads"]==INPUTS["canonical_payloads"]
    assert att["run_state"]==INPUTS["attestation_run_state"]
    ticket=json.loads((CORPUS/ROWS["VALID_CONTINUATION_TICKET"]["path"]).read_bytes())
    assert ticket["schema"]=="BDB_CONTINUATION_TICKET_V1"
    assert ticket["variant_id"]==att["variant_id"] and ticket["step_order"]==att["krok"]
    assert ticket["expected_run_state"]==att["run_state"]
    assert ticket["fallback_prompt_sha256"]==INPUTS["fallback_prompt_sha256"]
    assert ticket["prior_handoff_sha256"]==ROWS["VALID_BASE_F1"]["raw_digest"]
    prior=ticket["prior_handoff_validation"]
    assert prior["zip_sha256"]==ticket["prior_handoff_sha256"]
    assert prior["audit_request_id"]==att["audit_id"] and prior["audit_attempt_id"]==att["run_id"]
    assert all(prior[k]==att["frozen_source_identity"][k] for k in ("source_sha","source_tree"))


def test_independent_previous_prompt_control():
    f=members("VALID_PREVIOUS_PROMPT_BUNDLE");manifest=doc(f,"PREVIOUS_PROMPTS_MANIFEST.json")
    assert manifest["consumer_variant_id"]=="E2_SOL_ITERACJA_1"
    assert manifest["expected_predecessor_variant_id"]=="E1_SOL_BASE"
    assert ROWS["VALID_PREVIOUS_PROMPT_BUNDLE"]["raw_digest"]==INPUTS["previous_bundle_sha256"]
    assert set(f)=={"PREVIOUS_PROMPTS_MANIFEST.json"}|{p["filename"] for p in manifest["prompt_files"]}
    assert {p["filename"]:p["sha256"] for p in manifest["prompt_files"]}==INPUTS["previous_prompt_hashes"]
    for p in manifest["prompt_files"]:
        assert sha(f[p["filename"]])==p["sha256"]


@pytest.mark.parametrize("fid",sorted(INVALID))
def test_independently_adjudicated_negative_control(fid):
    """Inspect the violated safety fact directly, without calling legacy."""
    f=members(fid);control=members(ROWS[fid]["positive_control"])
    if fid in {"WRONG_VARIANT","WRONG_RUN_ID","WRONG_AUDIT_ID"}:
        key={"WRONG_VARIANT":"variant_id","WRONG_RUN_ID":"audit_attempt_id","WRONG_AUDIT_ID":"audit_request_id"}[fid]
        assert doc(f,"RUN_MANIFEST.json")[key]!=doc(f,"F1_SOURCE_CHECKPOINT.json")[key]
    elif fid in {"WRONG_SOURCE_SHA","WRONG_SOURCE_TREE"}:
        key="source_sha" if fid.endswith("SHA") else "source_tree"
        assert doc(f,"RUN_MANIFEST.json")["resolved_source_identity"][key]!=doc(f,"F1_SOURCE_CHECKPOINT.json")[key]
    elif fid=="CONFLICTING_DUPLICATE":
        assert f["PRE_F1_SOURCE_INTEGRITY_READBACK.json"]!=f["evidence/PRE_F1_SOURCE_INTEGRITY_READBACK.json"]
    elif fid=="INVALID_HASH_MANIFEST":
        assert f["ARTIFACT_HASHES.sha256"]!=control["ARTIFACT_HASHES.sha256"]
        assert {k:v for k,v in f.items() if k!="ARTIFACT_HASHES.sha256"}=={k:v for k,v in control.items() if k!="ARTIFACT_HASHES.sha256"}
    elif fid=="MISSING_SNAPSHOT":
        assert "F1_RETAINED_LEDGER_SNAPSHOT.jsonl" not in f
    elif fid=="BROKEN_LEDGER_PREFIX":
        snap=f["F1_RETAINED_LEDGER_SNAPSHOT.jsonl"]
        assert not f["AUDIT_LEDGER.jsonl"].startswith(snap)
        assert [json.loads(x) for x in f["AUDIT_LEDGER.jsonl"].splitlines()]==[json.loads(x) for x in snap.splitlines()]
    elif fid in {"BAD_F1_CHECKPOINT","BAD_F2_CHECKPOINT"}:
        kind="F1" if fid=="BAD_F1_CHECKPOINT" else "F2"
        name="F1_SOURCE_CHECKPOINT.json" if kind=="F1" else "F2_PRE_REPORT_CHECKPOINT.json"
        assert doc(f,name)[f"{kind.lower()}_ledger_sequence_end"]!=json.loads(f[f"{kind}_RETAINED_LEDGER_SNAPSHOT.jsonl"].splitlines()[-1])["seq"]
    elif fid in {"EARLY_REVEAL","SOURCE_GENERATION_MIX","SUBSTITUTE_F2"}:
        key={"EARLY_REVEAL":"staged_payload_semantics_exposed_before_attestation","SOURCE_GENERATION_MIX":"source_generations_mixed","SUBSTITUTE_F2":"substitute_f2_created"}[fid]
        assert doc(f,"PRE_CANONICAL_REVEAL_GATE_PASS_ATTESTATION.json")[key] is True
    elif fid=="UNSAFE_ZIP_PATH":
        assert any(".." in PurePosixPath(n).parts for n in f)
    elif fid=="DUPLICATE_MEMBER":
        with zipfile.ZipFile(CORPUS/ROWS[fid]["path"]) as z:
            assert z.namelist().count("RUN_MANIFEST.json")==2
    elif fid=="WRONG_ARTIFACT_FAMILY":
        assert "F1_SOURCE_CHECKPOINT.json" in f
        assert {"FINAL_OUTCOME.json","FINAL_TECHNICAL_AUDIT_REPORT.md","FINAL_SOURCE_INTEGRITY_READBACK.json"}.isdisjoint(f)
    else:
        raise AssertionError("Unadjudicated fixture")

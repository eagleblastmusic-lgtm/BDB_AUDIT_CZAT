from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

import pytest

from bdb_audit.cli import run_cli
from bdb_audit.core.errors import ValidationError
from bdb_audit.history.objects import CanonicalObject, CommandEnvelope
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.product_safety import NF02_BLOCK_CODE
from bdb_audit.workflow.orchestrator import FullAuditOrchestrator
from bdb_audit.workflow.settings import SettingsManager
from bdb_audit.workflow.manual_stage import StageBatch, StageResultInbox


@pytest.fixture
def campaign(tmp_path, capsys):
    repo = tmp_path / "real-repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    (repo / "example.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "example.py"], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Product test", "-c", "user.email=product@example.invalid", "commit", "-m", "test source"], check=True, capture_output=True)
    store = tmp_path / "work" / "campaign.sqlite"
    assert run_cli(["product", "start", "--repo", str(repo), "--store", str(store), "--json"]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["status"] == "READY_FOR_REVIEW"
    assert len(created["packages"]) == 5
    return store, repo, created


def _bytes(root: Path):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def test_start_resume_and_report_bind_real_commit(campaign, capsys):
    store, repo, created = campaign
    sha = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    assert created["source"]["exact_commit_sha"] == sha
    before = _bytes(store.parent)
    assert run_cli(["product", "resume", "--store", str(store), "--json"]) == 0
    resumed = json.loads(capsys.readouterr().out)
    assert len(resumed["packages"]) == 5
    assert resumed["audit_completion"] == "NOT_COMPLETED"
    assert [j["package_zip_sha256"] for j in resumed["packages"]] == [j["package_zip_sha256"] for j in created["packages"]]
    assert _bytes(store.parent) == before
    output = store.parent / "report.md"
    assert run_cli(["product", "report", "--store", str(store), "--output", str(output), "--json"]) == 0
    assert "**NOT_COMPLETED**" in output.read_text(encoding="utf-8")
    capsys.readouterr()
    original = output.read_bytes()
    assert run_cli(["product", "report", "--store", str(store), "--output", str(output), "--json"]) == 2
    assert output.read_bytes() == original


@pytest.mark.parametrize("variant", ["unauthorized", "wrong_raw", "second_slot", "missing_output", "terminal_attempt", "stale_cut", "declared_not_enforced", "self_grant"])
def test_public_import_is_disabled_without_any_mutation(campaign, capsys, variant):
    store, _, created = campaign
    result = store.parent / f"{variant}.zip"
    job = created["packages"][0]
    manifest = {"kind": "bdb_audit_lane_result", "version": "1", "campaign_id": created["campaign_id"], "stage_id": "E1", "lane_slot": "E1-A", "source_commit_sha": created["source"]["exact_commit_sha"], "input_package_digest": job["package_digest"], "assignment_ref": job["assignment_ref"], "attempt_ref": job["attempt_ref"], "history_cut": created["assignment_input_history_cut"], "findings": [], "executor_profile": "ChatGPT / GitHub", "executor_model": "Sol 5.6"}
    if variant == "unauthorized":
        manifest["producer"] = "attacker"
    elif variant == "wrong_raw":
        manifest["input_package_digest"] = "f" * 64
    elif variant == "second_slot":
        manifest["lane_slot"] = "E1-B"
    elif variant == "missing_output":
        del manifest["findings"]
    elif variant == "terminal_attempt":
        manifest["attempt_state"] = "COMPLETED"
    elif variant == "stale_cut":
        manifest["history_cut"] = {**manifest["history_cut"], "accepted_head_seq": 999999}
    elif variant == "declared_not_enforced":
        manifest["required_isolation"] = "ENFORCED"
        manifest["actual_isolation"] = "DECLARED"
    else:
        manifest["producer"] = "installation-owner"
        manifest["producer_grant"] = "self-signed"
    with zipfile.ZipFile(result, "w") as archive:
        archive.writestr("MANIFEST.json", json.dumps(manifest))
    before = _bytes(store.parent)
    assert run_cli(["product", "import", "--store", str(store), "--zip", str(result), "--json"]) == 2
    error = json.loads(capsys.readouterr().err)
    assert error["error"] == NF02_BLOCK_CODE
    assert _bytes(store.parent) == before
    # Exercise the actual E1 inbox, bypassing the product CLI.
    workflow = FullAuditOrchestrator(settings_mgr=SettingsManager(store.parent / "product-settings.json"))
    workflow.resume_campaign(store)
    before = _bytes(store.parent)
    imported = workflow.e1_inbox.ingest_zip(result)
    assert imported[1] == "REJECTED" and NF02_BLOCK_CODE in imported[2]
    assert _bytes(store.parent) == before


def test_resume_rejects_tampered_package(campaign, capsys):
    store, _, data = campaign
    package = Path(data["packages"][0]["package_zip_path"])
    package.write_bytes(b"substituted raw ZIP")
    before = _bytes(store.parent)
    assert run_cli(["product", "resume", "--store", str(store), "--json"]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "BLOCKED"
    assert _bytes(store.parent) == before


def test_store_cannot_self_authorize_or_accept_external_result(campaign):
    path, _, _ = campaign
    store = TransactionalHistoryStore(path)
    before = _bytes(path.parent)
    with pytest.raises(ValidationError, match=NF02_BLOCK_CODE):
        store.issue_ingestion_capability({}, batch_ticket="self-granted")
    for kind in ("bdb_audit_lane_result", "lane_result_admission_evidence"):
        prior = store.commits()[-1]
        command = CommandEnvelope(command_id="command_11111111-1111-4111-8111-111111111111", command_kind="RECORD_FOUNDATION_FACT", actor_ref="installation-owner", expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **store.head().as_dict()}, governing_policy_ref=prior["governing_policy_ref"], governing_spec_refs=tuple(prior["governing_spec_refs"]), idempotency_scope="product-disabled-import", campaign_ref=store.head().campaign_id)
        with pytest.raises(ValidationError, match=NF02_BLOCK_CODE):
            store.accept(command, immutable_objects=[CanonicalObject(kind, {})])
    assert _bytes(path.parent) == before


def test_manual_stage_import_blocked_without_mutation(campaign):
    path, _, data = campaign
    store = TransactionalHistoryStore(path)
    batch = StageBatch(data["campaign_id"], "E2", "E2-BLIND", data["assignment_input_history_cut"], {}, data["assignment_input_history_cut"])
    inbox = StageResultInbox(store, batch)
    before = _bytes(path.parent)
    result = inbox.ingest_zip(path.parent / "malicious.zip")
    assert result[1] == "REJECTED" and NF02_BLOCK_CODE in result[2]
    assert _bytes(path.parent) == before


def test_disabled_import_does_not_create_missing_store(tmp_path, capsys):
    store = tmp_path / "absent.sqlite"
    assert run_cli(["product", "import", "--store", str(store), "--zip", str(tmp_path / "missing.zip"), "--json"]) == 2
    assert not store.exists()


def test_start_refuses_overwriting_campaign(campaign, capsys):
    store, repo, _ = campaign
    before = _bytes(store.parent)
    assert run_cli(["product", "start", "--repo", str(repo), "--store", str(store), "--json"]) == 2
    assert _bytes(store.parent) == before

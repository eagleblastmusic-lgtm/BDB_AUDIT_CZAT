"""NF02 raw closure: atomic persistence, recovery, and corruption rejection."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from threading import Barrier

import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.core.ids import deterministic_id
from bdb_audit.history.objects import CanonicalObject, CommandEnvelope
from bdb_audit.history.raw_artifacts import AdmissionRawReader, persist_verified_raw
from bdb_audit.history.store import TransactionalHistoryStore
from bdb_audit.vault.raw_store import RawArtifactVault
from tests.workflow import test_nf02_raw_derivation as _raw_fixtures
from tests.workflow.test_nf02_synthetic_lane_result_authority import _command_id, _current_cut

# Reuse the real campaign/package fixtures; no alternate admission mechanism.
admission = _raw_fixtures.admission
e1_setup = _raw_fixtures.e1_setup


def _command(store, kind, seed):
    head = store.head()
    prior = store.commits()[-1]
    return CommandEnvelope(
        command_id=_command_id(seed), command_kind=kind,
        actor_ref=prior["actor_ref"], expected_parent_head={"tag": "ACCEPTED_HEAD_REF", **head.as_dict()},
        governing_policy_ref=prior["governing_policy_ref"], governing_spec_refs=tuple(prior["governing_spec_refs"]),
        idempotency_scope=seed, campaign_ref=head.campaign_id,
    )


def _pending(admission, phase):
    store, batch, body, proposal = admission
    body = deepcopy(body)
    body["ingestion_capability"] = store.issue_ingestion_capability(body, batch_ticket=batch.batch_ticket)
    evidence = CanonicalObject("lane_result_admission_evidence", body)
    cmd = _command(store, "INGEST_EXTERNAL_LANE_RESULT", "durable-evidence")
    if phase == "evidence":
        return store, cmd, evidence, store.head(), body
    store.accept(cmd, expected_head=store.head(), immutable_objects=[evidence])
    proposal = {**proposal, "admission_evidence_ref": evidence.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict()}
    return store, _command(store, "RECORD_FOUNDATION_FACT", "durable-result"), CanonicalObject("bdb_audit_lane_result", proposal), store.head(), body


def _snapshot(store):
    con = store._connect()
    try:
        # Includes per-kind completion objects, exact receipts, dedup, raw bytes,
        # commit/head: rollback must preserve all of them, not only total counts.
        return {
            table: tuple(con.execute("SELECT * FROM " + table + " ORDER BY rowid"))
            for table in ("immutable_objects", "immutable_raw_artifacts", "commits", "receipts", "accepted_head", "command_index")
        }
    finally:
        con.close()


def _staging_paths(store, body):
    vault = RawArtifactVault(Path(store.path).resolve().parent / "raw_vault")
    return [vault._paths(body[field])[0] for field in ("raw_result_digest", "package_zip_sha256")]


@pytest.mark.parametrize("phase", ["evidence", "result"])
@pytest.mark.parametrize("artifact", ["raw_result_digest", "package_zip_sha256"])
def test_delete_staging_at_last_validation_boundary_retains_exact_bytes(admission, phase, artifact):
    store, cmd, obj, expected, body = _pending(admission, phase)
    originals = {body[field]: path.read_bytes() for field, path in zip(
        ("raw_result_digest", "package_zip_sha256"), _staging_paths(store, body), strict=True,
    )}
    removed = _staging_paths(store, body)[artifact == "package_zip_sha256"]

    def delete(name):
        if name == "before_object_durability":
            removed.unlink()

    store.crash_hook = delete
    accepted = store.accept(cmd, expected_head=expected, immutable_objects=[obj])
    assert not removed.exists()
    recovered = TransactionalHistoryStore(store.path)
    assert recovered.read_accepted_raw(obj.ref, _current_cut(recovered)) == originals
    before = _snapshot(recovered)
    retry = recovered.accept(cmd, expected_head=expected, immutable_objects=[obj])
    assert retry.already_accepted
    assert canonical_bytes(retry.receipt.body()) == canonical_bytes(accepted.receipt.body())
    assert retry.receipt.digest == accepted.receipt.digest
    assert _snapshot(recovered) == before


@pytest.mark.parametrize("phase", ["evidence", "result"])
@pytest.mark.parametrize("boundary", TransactionalHistoryStore.HOOKS)
def test_process_death_retains_old_or_new_complete_raw_closure(admission, phase, boundary, tmp_path):
    store, cmd, obj, expected, body = _pending(admission, phase)
    originals = {body[field]: path.read_bytes() for field, path in zip(
        ("raw_result_digest", "package_zip_sha256"), _staging_paths(store, body), strict=True,
    )}
    before = _snapshot(store)
    packet = tmp_path / "crash-input.json"
    packet.write_text(json.dumps({"command": asdict(cmd), "object": asdict(obj), "expected_head": expected.as_dict()}), encoding="utf-8")
    run = subprocess.run(
        [sys.executable, "-B", str(Path(__file__).with_name("nf02_raw_crash_worker.py")), store.path, str(packet), boundary],
        capture_output=True, text=True, timeout=120,
    )
    assert run.returncode == 73, run.stderr + run.stdout
    recovered = TransactionalHistoryStore(store.path)
    committed = boundary == "after_commit_durability_before_ack"
    assert bool(recovered.receipt(cmd.command_id)) == committed
    if committed:
        for path in _staging_paths(recovered, body):
            path.unlink()
        assert recovered.read_accepted_raw(obj.ref, _current_cut(recovered)) == originals
    else:
        assert _snapshot(recovered) == before
        assert recovered.object_record(obj.digest) is None
    accepted = recovered.accept(cmd, expected_head=expected, immutable_objects=[obj])
    assert accepted.already_accepted == committed
    assert recovered.read_accepted_raw(obj.ref, _current_cut(recovered)) == originals
    after = _snapshot(recovered)
    retry = recovered.accept(cmd, expected_head=expected, immutable_objects=[obj])
    assert retry.already_accepted
    assert canonical_bytes(retry.receipt.body()) == canonical_bytes(accepted.receipt.body())
    assert retry.receipt.digest == accepted.receipt.digest
    assert _snapshot(recovered) == after


@pytest.mark.parametrize("artifact", ["raw_result_digest", "package_zip_sha256"])
@pytest.mark.parametrize("mutation", ["missing", "bytes", "length"])
def test_corrupt_retained_closure_blocks_reads_consumers_and_retry(admission, artifact, mutation):
    from bdb_audit.history.authority_hooks import _resolve_completion_object
    from bdb_audit.stop.authority import _accepted_index, _records

    store, cmd, obj, expected, body = _pending(admission, "result")
    store.accept(cmd, expected_head=expected, immutable_objects=[obj])
    digest = body[artifact]
    with store._connect() as con:
        if mutation == "missing":
            con.execute("DELETE FROM immutable_raw_artifacts WHERE digest=?", (digest,))
        elif mutation == "bytes":
            con.execute("UPDATE immutable_raw_artifacts SET body=? WHERE digest=?", (b"corrupt", digest))
        else:
            con.execute("UPDATE immutable_raw_artifacts SET byte_length=byte_length+1 WHERE digest=?", (digest,))
    # Staging remains correct; it must not hide an incomplete accepted closure.
    assert all(path.is_file() for path in _staging_paths(store, body))
    before = _snapshot(store)
    cut = _current_cut(store)
    with pytest.raises(ValidationError, match="VAULT_INTEGRITY_BLOCKED"):
        store.resolve_accepted(obj.ref, cut)
    with pytest.raises(ValidationError, match="VAULT_INTEGRITY_BLOCKED"):
        store.read_accepted_raw(obj.ref, cut)
    with pytest.raises(ValidationError, match="VAULT_INTEGRITY_BLOCKED"):
        store.accept(cmd, expected_head=expected, immutable_objects=[obj])
    with store._connect() as con:
        with pytest.raises(ValidationError, match="VAULT_INTEGRITY_BLOCKED"):
            _resolve_completion_object(obj.ref.as_dict(), content_objects=(), con=con, context="result")
        with pytest.raises(ValidationError, match="VAULT_INTEGRITY_BLOCKED"):
            _records("bdb_audit_lane_result", _accepted_index(store.head(), con), con)
    assert _snapshot(store) == before


@pytest.mark.parametrize("artifact", ["raw_result_digest", "package_zip_sha256"])
def test_missing_retained_evidence_blocks_second_commit_without_backfill(admission, artifact):
    store, cmd, obj, expected, body = _pending(admission, "result")
    with store._connect() as con:
        con.execute("DELETE FROM immutable_raw_artifacts WHERE digest=?", (body[artifact],))
    assert all(path.is_file() for path in _staging_paths(store, body))
    before = _snapshot(store)
    with pytest.raises(ValidationError, match="VAULT_INTEGRITY_BLOCKED"):
        store.accept(cmd, expected_head=expected, immutable_objects=[obj])
    assert _snapshot(store) == before


def test_two_concurrent_result_writers_share_one_head_and_raw_closure(admission):
    store, cmd, obj, expected, body = _pending(admission, "result")
    stores = [TransactionalHistoryStore(store.path), TransactionalHistoryStore(store.path)]
    barrier = Barrier(2)

    def submit(index):
        candidate = replace(cmd, command_id=_command_id("concurrent-raw-" + str(index)))
        barrier.wait(timeout=30)
        try:
            return stores[index].accept(candidate, expected_head=expected, immutable_objects=[obj])
        except ValidationError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, (0, 1)))
    assert outcomes.count("EXPECTED_HEAD_CONFLICT") == 1
    accepted = next(outcome for outcome in outcomes if outcome != "EXPECTED_HEAD_CONFLICT")
    assert store.head() == accepted.head
    assert accepted.head.commit_seq == expected.commit_seq + 1
    assert len(store.accepted_records("bdb_audit_lane_result", _current_cut(store))) == 1
    assert set(store.read_accepted_raw(obj.ref, _current_cut(store))) == {body["raw_result_digest"], body["package_zip_sha256"]}


def test_raw_table_presence_does_not_establish_accepted_authority(admission):
    store, cmd, obj, _, body = _pending(admission, "evidence")
    with store._connect() as con:
        con.execute("BEGIN IMMEDIATE")
        reader = AdmissionRawReader(con)
        reader.read_bytes(body["raw_result_digest"])
        reader.read_bytes(body["package_zip_sha256"])
        persist_verified_raw(con, reader.verified)
    with pytest.raises(ValidationError, match="OBJECT_NOT_ACCEPTED_AT_CUT"):
        store.read_accepted_raw(obj.ref, _current_cut(store))


def test_raw_persistence_requires_transaction_and_never_overwrites_corrupt_bytes(tmp_path):
    store = TransactionalHistoryStore(tmp_path / "empty.sqlite")
    raw = b"exact bytes"
    digest = hashlib.sha256(raw).hexdigest()
    con = store._connect()
    try:
        with pytest.raises(ValidationError, match="RAW_RETENTION_TRANSACTION_REQUIRED"):
            persist_verified_raw(con, {digest: raw})
        con.execute("BEGIN IMMEDIATE")
        persist_verified_raw(con, {digest: raw})
        con.commit()
        con.execute("UPDATE immutable_raw_artifacts SET body=? WHERE digest=?", (b"corrupt", digest))
        con.execute("BEGIN IMMEDIATE")
        with pytest.raises(ValidationError, match="VAULT_INTEGRITY_BLOCKED"):
            persist_verified_raw(con, {digest: raw})
        con.rollback()
        assert con.execute("SELECT body FROM immutable_raw_artifacts WHERE digest=?", (digest,)).fetchone()[0] == b"corrupt"
    finally:
        con.close()


@pytest.mark.parametrize("mutation", ["orphan", "schema_identity"])
def test_capability_issuer_requires_exact_prior_accepted_assignment(admission, mutation):
    import io
    import zipfile

    store, batch, body, proposal = admission
    assignment = store.resolve_accepted(body["assignment_ref"], _current_cut(store))
    if mutation == "orphan":
        orphan_body = {**assignment["body"], "assignment_manifest_id": deterministic_id("assignment_manifest", "unaccepted-assignment")}
        orphan = CanonicalObject("assignment_manifest", orphan_body)
        with store._connect() as con:
            con.execute(
                "INSERT INTO immutable_objects(digest,kind,version,schema_ref,logical_id,body) VALUES(?,?,?,?,?,?)",
                store._object_rows([orphan])[0],
            )
        body["assignment_ref"] = orphan.as_ref(ref_class="PRIOR_ACCEPTED_ONLY").as_dict()
    else:
        body["assignment_ref"] = {**body["assignment_ref"], "schema_revision_ref": "wrong-exact-schema"}
    # Even a fully self-consistent raw proposal/package and a genuine public
    # ticket must not promote table presence or a false typed identity.
    proposal["assignment_ref"] = body["assignment_ref"]
    body["result_proposal_digest"] = hashlib.sha256(canonical_bytes(proposal)).hexdigest()
    raw_package = batch.get_job("E1-A").package_zip_path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw_package)) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(members["MANIFEST.json"])
    manifest["assignment_ref"] = body["assignment_ref"]
    members["MANIFEST.json"] = canonical_bytes(manifest)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in members.items():
            archive.writestr(name, raw)
    vault = RawArtifactVault(Path(store.path).resolve().parent / "raw_vault")
    body["package_zip_sha256"] = vault.put_bytes(buffer.getvalue(), media_type="application/zip").raw_digest
    before = _snapshot(store)
    with pytest.raises(ValidationError, match="UNAUTHORIZED_PRODUCER_AUTHORITY"):
        store.issue_ingestion_capability(body, batch_ticket=batch.batch_ticket)
    assert _snapshot(store) == before

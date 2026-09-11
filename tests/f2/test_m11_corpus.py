import hashlib
import pytest

from bdb_audit.core.errors import ValidationError
from bdb_audit.corpus import CorpusEngine, CorpusMember, LegacyCorpusAdapter


def source(seed):
    return {"kind": "source_generation", "revision_digest": hashlib.sha256(seed.encode()).hexdigest(),
            "digest_profile": "BDB-OBJECT-DIGEST-1", "schema_revision_ref": "BDB_SCHEMA_REGISTRY::source_generation/1",
            "ref_class": "CONTENT_OR_PRIOR"}


def test_direct_predecessor_single_auxiliary_multi_and_legacy_raw_preserved():
    src = source("same")
    direct = LegacyCorpusAdapter.legacy_e2_direct_predecessor(b"legacy-e2", source_generation_ref=src)
    aux1 = LegacyCorpusAdapter.legacy_e1_auxiliary(b"legacy-e1-a", source_generation_ref=src)
    aux2 = LegacyCorpusAdapter.legacy_e1_auxiliary(b"legacy-e1-b", source_generation_ref=src)
    result = CorpusEngine().validate(direct_predecessors=(direct.member,), auxiliary=(aux1, aux2), source_generation_ref=src)
    assert result["DIRECT_PREDECESSOR_SINGLE"] == "YES"
    assert direct.member.raw_bytes == b"legacy-e2"


def test_corpus_rejects_multiple_direct_and_cross_source_members():
    a, b = source("a"), source("b")
    d1 = LegacyCorpusAdapter.legacy_e2_direct_predecessor(b"one", source_generation_ref=a).member
    d2 = LegacyCorpusAdapter.legacy_e2_direct_predecessor(b"two", source_generation_ref=a).member
    with pytest.raises(ValidationError, match="DIRECT_PREDECESSOR_SINGLE"):
        CorpusEngine().validate(direct_predecessors=(d1, d2), source_generation_ref=a)
    aux = LegacyCorpusAdapter.legacy_e1_auxiliary(b"aux", source_generation_ref=b)
    with pytest.raises(ValidationError, match="CROSS_SOURCE_CORPUS_REJECTED"):
        CorpusEngine().validate(direct_predecessors=(d1,), auxiliary=(aux,), source_generation_ref=a)


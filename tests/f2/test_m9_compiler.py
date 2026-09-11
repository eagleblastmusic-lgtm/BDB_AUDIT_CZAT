from bdb_audit.core.canonical_json import canonical_bytes
from bdb_audit.orchestration.compiler import PromptPackageCompiler


def inputs():
    return {
        "stage_spec_revision": {"kind": "stage_spec", "revision_digest": "a" * 64},
        "lane_spec_revision": {"kind": "lane_spec", "revision_digest": "b" * 64},
        "executor_revision": {"kind": "executor_spec", "revision_digest": "c" * 64},
        "delivery_revision": {"kind": "delivery_spec", "revision_digest": "d" * 64},
        "projection_policy": {"policy": "pre-reveal", "revision": "1"},
        "view_manifest": {"namespace": "BDB_VIEW", "view_digest": "e" * 64},
        "history_cut": {"variant": "ACCEPTED_HISTORY_CUT", "accepted_head_seq": 2,
                        "accepted_head_hash": "f" * 64},
        "prompt": {"template": "foundation", "ordinal": 1},
    }


def test_compiler_is_byte_deterministic_and_has_no_authority_writer():
    compiler = PromptPackageCompiler()
    first = compiler.compile(**inputs())
    second = compiler.compile(**inputs())
    assert first.raw == second.raw
    assert first.digest == second.digest
    assert compiler.authority_write_capability is False
    assert b"ViewRef" not in first.raw


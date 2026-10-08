"""Compare retained draft bodies/domains with current generators, without writes.

Only the generator's output sink is intercepted. Source inputs and validation
are real; no canonical Store or runtime dependency is mocked.
"""

import contextlib
import io
from unittest.mock import patch

import body_grammar_frontier
import common_grammars
import event_grammars
import field_domains
import payload_reference_contracts
import profile_contracts
import profile_reference_contracts
import purpose_contracts
import reference_resolution
import reference_frontier
import semantic_inventory
import transition_contract
import version_impact
from execution import OUT, digest, preserve, read, write


def main():
    preserve()
    records = []
    drift = []
    for module in (semantic_inventory, reference_frontier, reference_resolution, version_impact, purpose_contracts,
                   event_grammars, transition_contract, common_grammars,
                   field_domains, body_grammar_frontier,
                   profile_contracts, profile_reference_contracts, payload_reference_contracts):
        captured = {}

        def retain(name, value):
            assert name not in captured, ("DUPLICATE_GENERATED_OUTPUT", name)
            captured[name] = value

        with patch.object(module, "write", retain), contextlib.redirect_stdout(io.StringIO()):
            module.main()
        for name, expected in captured.items():
            path = OUT / name
            matches = path.exists() and read(path) == expected
            records.append({"file": name, "raw_digest": digest(path) if path.exists() else None,
                            "generator": module.__name__, "matches": matches})
            if not matches:
                drift.append(name)
    write("design/GENERATED_DESIGN_PARITY.json", {
        "records": records, "drift": drift, "qualification": False,
        "scope": "Exact generator/output parity only, not semantic completeness or authority"})
    if drift:
        raise RuntimeError("GENERATED_DESIGN_DRIFT: " + repr(drift))
    print(f"PASS exact current generator parity for {len(records)} retained draft reference/domain/body/profile outputs")


if __name__ == "__main__":
    main()

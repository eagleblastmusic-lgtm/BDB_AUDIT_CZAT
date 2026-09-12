import pytest

from bdb_audit.coordinator.operations import AuditOperationApi
from bdb_audit.core.errors import ValidationError
from bdb_audit.orchestration.templates import TemplateRegistry


def test_self_test_does_not_swallow_template_security_failure(monkeypatch):
    """D18: a template that accepts the adversarial input must make self-test fail closed."""
    monkeypatch.setattr(TemplateRegistry, "render", lambda self, name, context: "accepted")

    with pytest.raises(ValidationError, match="SELF_TEST_FAILED"):
        AuditOperationApi().run_self_test()


def test_self_test_pass_counts_only_controls_that_executed():
    result = AuditOperationApi().run_self_test()

    assert result["status"] == "PASS"
    assert result["deep"] is False
    assert len(result["checks"]) == 4
    assert all(row["status"] == "PASS" for row in result["checks"])
    assert {row["check"] for row in result["checks"]} == {
        "registry_integrity",
        "canonical_serialization",
        "deterministic_hashing",
        "template_security",
    }


def test_deep_self_test_executes_real_mutation_control():
    result = AuditOperationApi().run_self_test(deep=True)

    assert result["status"] == "PASS"
    assert result["deep"] is True
    assert len(result["checks"]) == 5
    assert result["checks"][-1] == {
        "check": "deep_mutation_framework",
        "status": "PASS",
    }

"""Finite build-context dispatch checks; never runtime installation authority."""
import copy
import unittest

from jsonschema import Draft202012Validator

from execution import OUT, canonical, read
from profile_design_audit import fixture
from schema_registry_build_candidate import profile_ref


def variants(catalog):
    result = []
    for purpose, contract in catalog.items():
        params = contract["parameter_schema"]["properties"]["parameters"]["properties"]
        if purpose == "METHOD":
            result.extend((purpose, {"kind": purpose, "method_type": value}) for value in params["method_type"]["enum"])
        elif purpose == "ASSESSOR":
            result.extend((purpose, {"kind": purpose, "assessment_kind_version": value})
                          for value in params["assessment_kind_version"]["enum"])
        else:
            result.append((purpose, {"kind": "DEFAULT"}))
    return result


def check_dispatch(body, governing_spec_ref, predicate_instances):
    contracts = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")
    schema = contracts["FULL_PATH_CONTEXT_PARAMETERS_V1"]["grammar"]
    if not Draft202012Validator(schema).is_valid(body):
        raise ValueError("CONTEXT_DISPATCH_GRAMMAR")
    if governing_spec_ref.get("kind") != "spec_revision":
        raise ValueError("CONTEXT_GOVERNING_SPEC_KIND")
    order = [(entry["purpose"], canonical(entry["variant"])) for entry in body["entries"]]
    if order != sorted(order):
        raise ValueError("CONTEXT_DISPATCH_ORDER")
    catalog = read(OUT / "design/PURPOSE_CONTRACT_GRAMMARS.json")
    expected = {(purpose, canonical(variant)) for purpose, variant in variants(catalog)}
    seen = set()
    by_ref = {canonical(profile_ref(instance)): instance for instance in predicate_instances}
    if len(by_ref) != len(predicate_instances):
        raise ValueError("CONTEXT_DUPLICATE_PREDICATE_INSTANCE")
    for entry in body["entries"]:
        if entry["governing_spec_ref"] != governing_spec_ref:
            raise ValueError("CONTEXT_GOVERNING_SPEC_MISMATCH")
        key = (entry["purpose"], canonical(entry["variant"]))
        if key not in expected or key in seen:
            raise ValueError("CONTEXT_DUPLICATE_OR_UNKNOWN_VARIANT")
        seen.add(key)
        instance = by_ref.get(canonical(entry["predicate_contract_ref"]))
        contract = catalog[entry["purpose"]]
        if instance is None or not Draft202012Validator(contract["parameter_schema"]).is_valid(instance):
            raise ValueError("CONTEXT_EXACT_PREDICATE_BINDING")
        field = {"METHOD": "method_type", "ASSESSOR": "assessment_kind_version"}.get(entry["purpose"])
        if field and instance["parameters"][field] != entry["variant"][field]:
            raise ValueError("CONTEXT_VARIANT_PARAMETER_MISMATCH")
    if seen != expected:
        raise ValueError("CONTEXT_INCOMPLETE_VARIANT_SET")
    return len(seen)


class PurposeDispatchTests(unittest.TestCase):
    def setUp(self):
        catalog = read(OUT / "design/PURPOSE_CONTRACT_GRAMMARS.json")
        contracts = read(OUT / "design/EXTERNAL_PROFILE_CONTRACTS.json")
        schema = contracts["FULL_PATH_CONTEXT_PARAMETERS_V1"]["grammar"]
        self.body = {"profile_id": "FULL_PATH_CONTEXT_PARAMETERS_V2", "entries": []}
        self.spec = fixture(schema["$defs"]["typed_ref"], schema["$defs"])
        self.spec["kind"] = "spec_revision"
        self.instances = []
        # Only synthetic syntax/configuration fixtures, never trusted installation inputs.
        for purpose, variant in variants(catalog):
            branch = next(branch for branch in schema["properties"]["entries"]["items"]["oneOf"]
                          if branch["properties"]["purpose"] == {"const": purpose}
                          and branch["properties"]["variant"] == {"const": variant})
            shared = fixture(branch, schema["$defs"])
            contract = catalog[purpose]["parameter_schema"]
            instance = fixture(contract, contract["$defs"])
            field = {"METHOD": "method_type", "ASSESSOR": "assessment_kind_version"}.get(purpose)
            if field:
                instance["parameters"][field] = variant[field]
            self.instances.append(instance)
            self.body["entries"].append({**copy.deepcopy(shared), "purpose": purpose, "variant": variant,
                "governing_spec_ref": copy.deepcopy(self.spec), "predicate_contract_ref": profile_ref(instance)})

        self.body["entries"].sort(key=lambda row: (row["purpose"], canonical(row["variant"])))

    def test_all_32_contexts_are_representable_and_exactly_bound(self):
        self.assertEqual(check_dispatch(self.body, self.spec, self.instances), 32)

    def test_duplicate_and_omitted_variant_rejects(self):
        body = copy.deepcopy(self.body)
        body["entries"][-1] = copy.deepcopy(body["entries"][0])
        # Distinct complete JSON values still duplicate the semantic dispatch key.
        body["entries"][-1]["resource_bounds"] = [{"resource": "CPU_TIME_US", "limit": 1}]
        body["entries"].sort(key=lambda row: (row["purpose"], canonical(row["variant"])))
        with self.assertRaisesRegex(ValueError, "DUPLICATE_OR_UNKNOWN_VARIANT"):
            check_dispatch(body, self.spec, self.instances)

    def test_old_one_assessor_context_cannot_cover_full_path(self):
        body = copy.deepcopy(self.body)
        body["entries"] = [row for row in body["entries"] if row["purpose"] != "ASSESSOR"] + [
            next(row for row in body["entries"] if row["purpose"] == "ASSESSOR")]
        with self.assertRaisesRegex(ValueError, "GRAMMAR|INCOMPLETE"):
            check_dispatch(body, self.spec, self.instances)

    def test_cross_variant_predicate_pin_rejects(self):
        body = copy.deepcopy(self.body)
        rows = [row for row in body["entries"] if row["purpose"] == "ASSESSOR"]
        rows[0]["predicate_contract_ref"] = rows[1]["predicate_contract_ref"]
        with self.assertRaisesRegex(ValueError, "VARIANT_PARAMETER_MISMATCH"):
            check_dispatch(body, self.spec, self.instances)

    def test_input_witness_subsets_and_other_assessment_outputs_reject(self):
        for field, value in (("input_kind_versions", []), ("required_witness_kinds", []), ("enum_values", ["MATERIAL"])):
            with self.subTest(field=field):
                body = copy.deepcopy(self.body)
                stage = next(row for row in body["entries"] if row["purpose"] == "STAGE")
                stage[field] = value
                with self.assertRaisesRegex(ValueError, "GRAMMAR"):
                    check_dispatch(body, self.spec, self.instances)

    def test_wrong_order_rejects(self):
        body = copy.deepcopy(self.body)
        body["entries"].reverse()
        with self.assertRaisesRegex(ValueError, "DISPATCH_ORDER"):
            check_dispatch(body, self.spec, self.instances)

    def test_unknown_variant_and_wrong_governing_spec_reject(self):
        body = copy.deepcopy(self.body)
        body["entries"][0]["variant"] = {"kind": "CALLER_SELECTED"}
        with self.assertRaisesRegex(ValueError, "GRAMMAR"):
            check_dispatch(body, self.spec, self.instances)
        body = copy.deepcopy(self.body)
        body["entries"][0]["governing_spec_ref"]["revision_digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "GOVERNING_SPEC_MISMATCH"):
            check_dispatch(body, self.spec, self.instances)


if __name__ == "__main__":
    unittest.main()

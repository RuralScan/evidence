import csv
import io
import unittest

from classification import normalize, migrate_csv, new_claim, proposal, equivalent, compiler_record


class ClassificationTests(unittest.TestCase):
    def test_format_does_not_imply_measurement(self):
        for old, fmt in [("table", "table"), ("figure_read", "figure")]:
            row = normalize(dict(claim_basis=old, reviewer_ok="true", ruleset_version="v1.5.1"))
            self.assertEqual(row["knowledge_basis"], "unknown")
            self.assertEqual(row["extraction_format"], fmt)
            self.assertEqual(row["claim_basis"], old)
            self.assertEqual(row["reviewer_ok"], "true")
            self.assertEqual(row["ruleset_version"], "v1.5.1")

    def test_basis_does_not_imply_format(self):
        self.assertEqual(normalize(dict(claim_basis="expert_assertion"))["extraction_format"], "unknown")
        self.assertEqual(normalize(dict(claim_basis="primary_measured"))["knowledge_basis"], "primary_measured")

    def test_idempotent_lossless_csv(self):
        original = b'evidence_id,claim_basis,quote,review_state\ne1,table,"A quote, unchanged",dropped\ne2,modelled,Other quote,\n'
        migrated = migrate_csv(original)
        self.assertEqual(migrate_csv(migrated), migrated)
        before = list(csv.DictReader(io.StringIO(original.decode())))
        after = list(csv.DictReader(io.StringIO(migrated.decode())))
        self.assertEqual([compiler_record(r) for r in after], before)

    def test_partial_or_invalid_migration_rejected(self):
        for data in [b'evidence_id,knowledge_basis\ne1,unknown\n', b'evidence_id,claim_basis\ne1,table\ne1,table\n', b'evidence_id,knowledge_basis,extraction_format\ne1,table,table\n']:
            with self.assertRaises(ValueError):
                migrate_csv(data)

    def test_new_claim_needs_explicit_independent_fields(self):
        for row in [dict(claim_basis="table"), normalize(dict(claim_basis="table")), dict(claim_basis="table", knowledge_basis="primary_measured", extraction_format="table")]:
            with self.assertRaises(ValueError):
                new_claim(row)
        new_claim(dict(claim_basis="expert_assertion", knowledge_basis="expert_assertion", extraction_format="table"))

    def test_legacy_correction_retains_only_exact_classification(self):
        old = dict(claim_basis="table", quote="Original")
        proposal(normalize(old) | {"quote": "Corrected"}, old)
        with self.assertRaises(ValueError):
            proposal(normalize(old) | {"knowledge_basis": "primary_measured"}, old)
        proposal(dict(claim_basis="primary_measured", knowledge_basis="primary_measured", extraction_format="table"), old)

    def test_old_receipt_equivalence_does_not_hide_scientific_change(self):
        old = dict(claim_basis="table", quote="Original")
        self.assertTrue(equivalent(old, normalize(old)))
        self.assertFalse(equivalent(old, normalize(old) | {"quote": "Different"}))
        self.assertFalse(equivalent(old, normalize(old) | {"knowledge_basis": "primary_measured"}))

    def test_fingerprint_preserves_all_original_science(self):
        old = dict(claim_basis="table", relationship={"threshold": 10})
        self.assertEqual(compiler_record(normalize(old)), old)
        self.assertNotEqual(compiler_record(normalize(old) | {"claim_basis": "primary_measured"}), old)

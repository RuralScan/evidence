import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import schema_migration as migration
from classification import migrate_csv


class MigrationProtectionTests(unittest.TestCase):
    def test_only_exact_recorded_additive_migration_is_accepted(self):
        raw = b'evidence_id,claim_basis,quote\ne1,table,An unchanged source quotation\n'
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "configuration").mkdir()
            (root / "rulesets").mkdir()
            (root / migration.CONTRACT).write_bytes(b'{}')
            receipt = dict(version=1, base="base", input_sha256=migration.digest(raw), output_sha256=migration.digest(migrate_csv(raw)), contract_sha256=migration.digest(b'{}'), rows=1)
            path = root / migration.JOURNAL
            path.write_text(json.dumps(receipt))
            with patch.object(migration.reg, "blob", return_value=raw), patch.object(migration.reg, "git", return_value=b''):
                self.assertEqual(migration.expected_previous(root, "base"), migrate_csv(raw))
                for field in ("base", "input_sha256", "output_sha256", "contract_sha256", "rows"):
                    path.write_text(json.dumps(receipt | {field: "tampered"}))
                    with self.assertRaises(ValueError):
                        migration.expected_previous(root, "base")

    def test_prior_journal_cannot_be_rewritten_or_removed(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "configuration").mkdir()
            path = root / migration.JOURNAL
            with patch.object(migration.reg, "blob", return_value=b'original'), patch.object(migration.reg, "git", return_value=b'exists'):
                with self.assertRaises(ValueError):
                    migration.expected_previous(root, "base")
                path.write_bytes(b'changed')
                with self.assertRaises(ValueError):
                    migration.expected_previous(root, "base")

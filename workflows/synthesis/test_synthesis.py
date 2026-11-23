"""Exercise authored scientific decisions, authenticated acceptance and fail-closed publication."""

import copy
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from synthesis import core, acceptance, package


class AgentSynthesis(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "evidence"
        self.root.mkdir()
        self.producer = Path(self.temp.name) / "producer"
        definitions = {
            "schema/registers/FAM_family_registry.csv": [
                {
                    "nbs_id": "practice",
                    "suitability_family_id": "family",
                    "spatial_product_type": "area_suitability",
                }
            ],
            "schema/registers/XW_target_crosswalk.csv": [
                {"source_variable": "quality", "target": "water_quality_risk"}
            ],
            "schema/registers/BANDS_magnitude_bands.csv": [
                {"metric": "rate", "unit": "percent"}
            ],
            "schema/T5_opportunity_space.csv": [
                {"variable_id": "water_quality_risk", "mcda_role": "priority"}
            ],
            "schema/T7_geographic_context.csv": [
                {"context_id": "cropping_rainfed", "context_type": "farming_system"}
            ],
        }
        for name, rows in definitions.items():
            path = self.producer / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("w", newline="") as stream:
                writer = csv.DictWriter(stream, rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
        self.registers = {
            "EV_evidence_register": [
                {
                    "evidence_id": "ev",
                    "source_id": "source",
                    "nbs_id": "practice",
                    "use_role": "nbs_effect",
                    "reviewer_ok": True,
                    "quote": "Measured improvement relative to control.",
                    "page": 2,
                }
            ],
            "SRC_source_register": [
                {
                    "source_id": "source",
                    "doi": "10.fixture/example",
                    "doi_verified": True,
                }
            ],
        }
        self.baseline = {"practice": {name: [] for name in core.TABLES.values()}}
        self.packet = core.inputs(self.root, self.producer, "practice", self.registers)
        self.folder = self.root / core.PROPOSALS / "fixture"
        self.folder.mkdir(parents=True)
        (self.folder / "inputs.json").write_bytes(core.encoded(self.packet))
        (self.folder / "skill.md").write_text(
            "Fixture scientific skill version 1; not a production judgment."
        )
        self.row = {k: None for k in core.policy()["tables"]["T6"]["columns"]}
        self.row.update(
            record_id="result",
            nbs_id="practice",
            variable_id="water_quality_risk",
            variable_type="opportunity_space_variable",
            effect_direction="moderate_positive",
            effect_confidence="low",
            effect_mechanism="Fixture judgment, tied to ev.",
            timescale_of_effect="immediate",
            evidence_ids=["ev"],
            evidence_level="robust",
            agreement_level="high",
            context_dependent=True,
            justification={
                "rationale": "Fixture judgment; uncertainty limits transfer."
            },
        )
        self.p = {
            "format": core.FORMAT,
            "id": "fixture",
            "practice": "practice",
            "table": "T6",
            "action": "replace",
            "task": "Synthetic workflow exercise, no scientific publication.",
            "comparison": "New fixture row.",
            "agent": {
                "model": "fixture-model",
                "skill_version": "1",
                "prompt": "Synthetic task",
                "settings": "not exposed",
            },
            "reasoning": {
                k: "Explicit fixture reasoning for " + k
                for k in core.policy()["reasoning"]
            },
            "candidates": [
                {
                    "evidence_id": "ev",
                    "disposition": "include",
                    "origin": "original-study",
                    "reason": "Direct reported effect.",
                }
            ],
            "replaces": {},
            "inputs_sha256": core.digest(self.packet),
            "skill_sha256": core.digest((self.folder / "skill.md").read_bytes()),
        }
        self.save()

    def save(self, rows=None):
        core.write_rows(
            self.folder / "rows.csv",
            self.p["table"],
            [self.row] if rows is None else rows,
        )
        self.p["rows_sha256"] = core.digest((self.folder / "rows.csv").read_bytes())
        (self.folder / "proposal.json").write_bytes(core.encoded(self.p))

    def accept(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        core.git(self.root, "add", ".")
        core.git(
            self.root,
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Fixture proposal",
        )
        self.event = dict(
            proposal_id="fixture",
            proposal_sha256=core.proposal_digest(self.folder),
            proposal_revision=core.git(self.root, "rev-parse", "HEAD").decode().strip(),
            decision="accept",
            reason="Reviewed the synthetic interpretation and exact proposed output.",
            receipt=42,
            actor="fixture-reviewer",
            created_at="2026-11-20T12:00:00Z",
            body_sha256="a" * 64,
        )
        with patch.object(acceptance, "fetch", return_value=self.event):
            self.assertTrue(acceptance.record(self.root, 42))
            self.assertFalse(acceptance.record(self.root, 42))

    def queue(self):
        rows, status = core.apply(
            self.root, self.producer, self.registers, self.baseline
        )
        return {"recipes": rows, "effect_synthesis": status}

    def test_authored_classes_survive_exactly_without_matrix_or_weighting(self):
        self.accept()
        queue = self.queue()
        row = queue["recipes"]["practice"][core.TABLES["T6"]][0]
        self.assertEqual(row, self.row)
        self.assertEqual(
            (row["evidence_level"], row["agreement_level"], row["effect_confidence"]),
            ("robust", "high", "low"),
        )
        out = self.root / "package"
        fingerprint = package.build(queue, out)
        self.assertEqual(core.digest((out / "manifest.json").read_bytes()), fingerprint)
        self.assertEqual(
            json.loads((out / "practice/T6.json").read_bytes()), [self.row]
        )
        with patch.object(acceptance, "fetch", return_value=self.event):
            acceptance.verify(self.root, self.event["proposal_revision"])
        with self.assertRaisesRegex(ValueError, "new output"):
            package.build(queue, out)

    def test_validation_is_not_acceptance_and_no_historical_fallback(self):
        core.validate(self.folder, self.packet, [])
        self.baseline["practice"][core.TABLES["T6"]] = [self.row]
        with self.assertRaisesRegex(ValueError, "No current accepted"):
            package.build(self.queue(), self.root / "unaccepted")

    def test_stale_evidence_holds_release_without_changing_scientific_values(self):
        self.accept()
        self.registers["EV_evidence_register"][0]["quote"] = "Corrected source passage."
        q = self.queue()
        self.assertEqual(q["effect_synthesis"]["rows"][0]["status"], "stale")
        self.assertEqual(q["recipes"]["practice"][core.TABLES["T6"]][0], self.row)
        with self.assertRaisesRegex(ValueError, "No current accepted|stale"):
            package.build(q, self.root / "stale")

    def test_candidate_omission_and_unreviewed_evidence_fail(self):
        self.p["candidates"] = []
        self.save()
        with self.assertRaisesRegex(ValueError, "every candidate"):
            core.validate(self.folder)
        self.setUp()
        packet = copy.deepcopy(self.packet)
        packet["evidence"][0]["reviewer_ok"] = False
        (self.folder / "inputs.json").write_bytes(core.encoded(packet))
        self.p["inputs_sha256"] = core.digest(packet)
        self.save()
        with self.assertRaisesRegex(ValueError, "scientific review"):
            core.validate(self.folder)

    def test_dropped_and_held_claims_cannot_be_included(self):
        for state in ("dropped", "held"):
            packet = copy.deepcopy(self.packet)
            packet["evidence"][0]["review_state"] = state
            (self.folder / "inputs.json").write_bytes(core.encoded(packet))
            self.p["inputs_sha256"] = core.digest(packet)
            self.save()
            with self.assertRaisesRegex(ValueError, "Held/dropped"):
                core.validate(self.folder)

    def test_tampering_and_missing_source_identity_fail(self):
        self.accept()
        with (self.folder / "rows.csv").open("a") as out:
            out.write("\n")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.queue()
        self.save()
        packet = copy.deepcopy(self.packet)
        packet["sources"][0]["doi_verified"] = False
        (self.folder / "inputs.json").write_bytes(core.encoded(packet))
        self.p["inputs_sha256"] = core.digest(packet)
        self.save()
        with self.assertRaisesRegex(ValueError, "identity"):
            core.validate(self.folder)

    def test_unknown_references_and_unknown_as_zero_fail(self):
        for key, value in [
            ("variable_id", "missing"),
            ("effect_confidence", "certain"),
            ("suitability_family_id", "missing"),
        ]:
            old = self.row[key]
            self.row[key] = value
            self.save()
            with self.assertRaises(ValueError):
                core.validate(self.folder)
            self.row[key] = old
        self.row["justification"]["data_deficient"] = True
        self.save()
        with self.assertRaisesRegex(ValueError, "Unknown effect"):
            core.validate(self.folder)

    def test_hold_is_recorded_and_blocks_packaging(self):
        self.accept()
        held = dict(self.event, receipt=43, decision="hold", reason="Review reopened.")
        with patch.object(acceptance, "fetch", return_value=held):
            acceptance.record(self.root, 43)
        self.assertEqual(self.queue()["effect_synthesis"]["rows"][0]["status"], "held")
        with self.assertRaises(ValueError):
            package.build(self.queue(), self.root / "held")

    def test_authenticated_receipt_must_be_human_and_eligible(self):
        decision = {
            k: v
            for k, v in dict(
                proposal_id="fixture",
                proposal_sha256=core.proposal_digest(self.folder),
                proposal_revision="a" * 40,
                decision="accept",
                reason="Explicit scientific approval",
            ).items()
        }
        issue = {
            "user": {"login": "reviewer", "type": "User"},
            "author_association": "MEMBER",
            "body": acceptance.HEADER + "\n```json\n" + json.dumps(decision) + "\n```",
            "created_at": "2026-11-20T12:00:00Z",
        }
        with (
            patch.object(acceptance.intake, "original", return_value="reviewer"),
            patch.object(acceptance.intake, "gh", return_value=issue),
        ):
            self.assertEqual(acceptance.fetch(42)["decision"], "accept")
            issue["author_association"] = "NONE"
            with self.assertRaisesRegex(ValueError, "eligible"):
                acceptance.fetch(42)
            issue["author_association"] = "MEMBER"
            issue["user"]["type"] = "Bot"
            with self.assertRaisesRegex(ValueError, "human"):
                acceptance.fetch(42)

    def test_withdrawal_is_explicit_accepted_provenance(self):
        self.baseline["practice"][core.TABLES["T6"]] = [self.row]
        self.p["action"] = "withdraw"
        self.p["replaces"] = {"result": core.replacement_digest(self.row)}
        self.p["candidates"][0]["disposition"] = "exclude"
        self.save([])
        self.accept()
        queue = self.queue()
        self.assertEqual(queue["recipes"]["practice"][core.TABLES["T6"]], [])
        out = self.root / "withdrawn"
        package.build(queue, out)
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertEqual(manifest["provenance"][0]["action"], "withdraw")
        self.assertEqual(json.loads((out / "practice/T6.json").read_text()), [])
        queue["recipes"]["practice"][core.TABLES["T6"]] = [self.row]
        with self.assertRaisesRegex(ValueError, "reappeared"):
            package.build(queue, self.root / "resurrected")

    def test_existing_rows_require_exact_replacement_and_no_duplicate_cell(self):
        self.baseline["practice"][core.TABLES["T6"]] = [self.row]
        with self.assertRaisesRegex(ValueError, "explicit replacement"):
            core.validate(self.folder, self.packet, [self.row])
        self.p["replaces"] = {"result": core.replacement_digest(self.row)}
        self.row = dict(self.row, effect_direction="slight_positive")
        self.save()
        self.accept()
        self.assertEqual(
            self.queue()["recipes"]["practice"][core.TABLES["T6"]], [self.row]
        )
        self.baseline["practice"][core.TABLES["T6"]][0]["effect_direction"] = (
            "strong_positive"
        )
        with self.assertRaisesRegex(ValueError, "Stale replacement"):
            self.queue()

    def test_t3_authored_weights_require_complete_hazard_set(self):
        self.p["table"] = "T3"
        self.row = {k: None for k in core.policy()["tables"]["T3"]["columns"]}
        self.row.update(
            record_id="asset",
            nbs_id="practice",
            hazard_type="drought",
            farming_system="all",
            risk_role="asset_threat",
            asset_sensitivity="high",
            asset_risk_weight=1.0,
            mitigation_mechanism="Asset damage reported.",
            confidence="low",
            evidence_level="robust",
            agreement_level="high",
            timescale_of_effect="immediate",
            landscape_scale_only=False,
            context_dependent=False,
            evidence_ids=["ev"],
            justification={"rationale": "Synthetic asset assessment."},
        )
        self.save()
        core.validate(self.folder, self.packet, [])
        self.accept()
        self.assertEqual(
            self.queue()["recipes"]["practice"][core.TABLES["T3"]], [self.row]
        )
        with self.assertRaisesRegex(ValueError, "complete hazard set"):
            package.build(self.queue(), self.root / "incomplete")

    def test_review_query_and_wrong_scope_type_fail(self):
        packet = copy.deepcopy(self.packet)
        packet["review_log"] = [{"evidence_id": "ev", "decision": "query"}]
        (self.folder / "inputs.json").write_bytes(core.encoded(packet))
        self.p["inputs_sha256"] = core.digest(packet)
        self.save()
        with self.assertRaisesRegex(ValueError, "review hold"):
            core.validate(self.folder)
        (self.folder / "inputs.json").write_bytes(core.encoded(self.packet))
        self.p["inputs_sha256"] = core.digest(self.packet)
        self.row.update(scope_type="aez", scope_id="cropping_rainfed")
        self.save()
        with self.assertRaisesRegex(ValueError, "Scope type"):
            core.validate(self.folder)

    def test_acceptance_history_cannot_reuse_receipt_or_rewrite_proposal(self):
        self.accept()
        with (self.root / core.JOURNAL).open("ab") as stream:
            stream.write(core.encoded(self.event))
        with patch.object(acceptance, "fetch", return_value=self.event):
            with self.assertRaisesRegex(ValueError, "Duplicate scientific receipt"):
                acceptance.verify(self.root)
        (self.root / core.JOURNAL).write_bytes(core.encoded(self.event))
        core.git(self.root, "add", ".")
        core.git(
            self.root,
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Accept fixture",
        )
        baseline = core.git(self.root, "rev-parse", "HEAD").decode().strip()
        (self.folder / "skill.md").write_text("Changed after acceptance")
        with self.assertRaisesRegex(ValueError, "proposal rewritten"):
            acceptance.verify(self.root, baseline)

    def test_subsequent_row_review_hold_blocks_scientific_publication(self):
        self.accept()
        folder = self.root / "row-reviews"
        folder.mkdir()
        vote = {
            "actor": "reviewer",
            "created_at": "2026-11-21T00:00:00Z",
            "receipt": 99,
            "entry": {
                "practice": "practice",
                "table": "T6",
                "record": "result",
                "row_sha256": core.digest(self.row),
                "decision": "hold",
            },
        }
        (folder / "receipts.jsonl").write_bytes(core.encoded(vote))
        self.assertEqual(self.queue()["effect_synthesis"]["rows"][0]["status"], "held")
        with self.assertRaises(ValueError):
            package.build(self.queue(), self.root / "row-held")

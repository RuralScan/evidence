"""Synthetic group judgments use human receipt fixtures, never production approvals."""

import copy
import json
import shutil
import unittest
from unittest.mock import patch

import test_synthesis as original
from synthesis import core, acceptance, package
import test_family_hierarchy as fixtures


class Aggregation(unittest.TestCase):
    save = original.AgentSynthesis.save
    accept = original.AgentSynthesis.accept
    queue = original.AgentSynthesis.queue

    def setUp(self):
        original.AgentSynthesis.setUp(self)
        fixtures.fixture_configuration(self.root)
        shutil.copyfile(
            self.root / fixtures.hierarchy.FAM,
            self.producer / "schema/registers/FAM_family_registry.csv",
        )
        self.p["practice"] = self.row["nbs_id"] = "agroforestry"
        self.baseline = {"agroforestry": {name: [] for name in core.TABLES.values()}}
        self.registers["EV_evidence_register"][0].update(
            nbs_id="agroforestry", suitability_family_id=fixtures.WIND
        )
        self.p["evidence_group_id"] = fixtures.GROUP
        self.row["justification"]["aggregation"] = {
            "covered_families": [fixtures.WIND],
            "unresolved_families": [fixtures.BOUNDARY, fixtures.CONTOUR],
            "scope_rationale": "Fixture wind result; no conclusion for boundary or contour planting.",
            "conflict_note": "One synthetic finding; absence of conflict is not proof of agreement.",
            "evidence_applicability": {
                "ev": {
                    "families": [fixtures.WIND],
                    "rationale": "Synthetic source describes wind shelter.",
                }
            },
        }
        self.refresh()

    def refresh(self):
        self.packet = core.inputs(
            self.root, self.producer, "agroforestry", self.registers
        )
        (self.folder / "inputs.json").write_bytes(core.encoded(self.packet))
        self.p["inputs_sha256"] = core.digest(self.packet)
        self.save()

    def group(self, queue=None):
        return (queue or self.queue())["effect_synthesis"]["groups"][0]

    def test_group_acceptance_retry_and_runtime_separation(self):
        self.accept()  # Authenticated receipt and retry are mocked fixture events.
        q = self.queue()
        self.assertEqual(q["recipes"], self.baseline)
        self.assertEqual(q["effect_synthesis"]["rows"], [])
        group = self.group(q)
        self.assertFalse(group["runtime_eligible"])
        self.assertEqual(group["rows"][0]["status"], "accepted")
        self.assertEqual(group["recipes"][core.TABLES["T6"]], [self.row])
        self.assertEqual(core.prior_rows(q, self.p), [self.row])
        self.assertEqual(
            core.prior_rows(q, dict(self.p, evidence_group_id="different")), []
        )
        with self.assertRaisesRegex(ValueError, "No current accepted"):
            package.build(q, self.root / "runtime")
        with patch.object(acceptance, "fetch", return_value=self.event):
            acceptance.verify(self.root, self.event["proposal_revision"])

    def test_t3_group_has_separate_accepted_rows(self):
        aggregation = self.row["justification"]["aggregation"]
        self.p["table"] = "T3"
        self.row = {k: None for k in core.policy()["tables"]["T3"]["columns"]}
        self.row.update(
            record_id="group-drought",
            nbs_id="agroforestry",
            hazard_type="drought",
            farming_system="all",
            risk_role="asset_threat",
            asset_sensitivity="high",
            mitigation_mechanism="Synthetic source reports asset damage.",
            confidence="low",
            evidence_level="limited",
            agreement_level="low",
            timescale_of_effect="immediate",
            landscape_scale_only=False,
            context_dependent=True,
            evidence_ids=["ev"],
            justification={
                "rationale": "Synthetic group risk assessment.",
                "aggregation": aggregation,
            },
        )
        self.save()
        self.accept()
        self.assertEqual(self.group()["recipes"][core.TABLES["T3"]], [self.row])
        self.assertEqual(self.queue()["recipes"], self.baseline)

    def test_practice_aggregation_requires_all_children_and_uses_normal_recipe_route(
        self,
    ):
        self.p.pop("evidence_group_id")
        self.save()
        with self.assertRaisesRegex(ValueError, "every child family"):
            core.validate(self.folder)
        members = {
            n["id"]
            for n in self.packet["family_hierarchy"]["nodes"].values()
            if n["level"] == "family"
            and n.get("spatial_product_type") != "qualitative_only"
            and not n["id"].endswith("__cross_family")
        }
        self.row["justification"]["aggregation"]["unresolved_families"] = sorted(
            members - {fixtures.WIND}
        )
        self.save()
        self.accept()
        q = self.queue()
        self.assertEqual(q["recipes"]["agroforestry"][core.TABLES["T6"]], [self.row])
        self.assertNotIn("groups", q["effect_synthesis"])
        package.build(q, self.root / "practice-effects")

    def test_group_hold_and_stale_source_leave_authored_bytes_visible(self):
        self.accept()
        held = dict(self.event, decision="hold", receipt=43, reason="Fixture challenge")
        with patch.object(acceptance, "fetch", return_value=held):
            self.assertTrue(acceptance.record(self.root, 43))
        self.assertEqual(self.group()["rows"][0]["status"], "held")
        self.assertEqual(self.group()["recipes"][core.TABLES["T6"]], [self.row])
        (self.root / core.JOURNAL).write_bytes(core.encoded(self.event))
        self.registers["SRC_source_register"][0]["citation"] = "Changed source identity"
        self.assertEqual(self.group()["rows"][0]["status"], "stale")
        self.assertEqual(self.queue()["recipes"], self.baseline)

    def test_missing_child_conflict_scope_and_sibling_inheritance_fail(self):
        original_aggregation = copy.deepcopy(self.row["justification"]["aggregation"])
        mutations = [
            ("conflict_note", ""),
            ("unresolved_families", [fixtures.CONTOUR]),
            ("covered_families", [fixtures.WIND, fixtures.CONTOUR]),
            ("evidence_applicability", {}),
            (
                "evidence_applicability",
                {
                    "ev": {
                        "families": [fixtures.CONTOUR],
                        "rationale": "Assumed sibling effect",
                    }
                },
            ),
        ]
        for key, value in mutations:
            self.row["justification"]["aggregation"] = dict(
                original_aggregation, **{key: value}
            )
            self.save()
            with self.assertRaises(ValueError):
                core.validate(self.folder, self.packet, [])
        self.row["justification"]["aggregation"] = original_aggregation
        self.row["suitability_family_id"] = fixtures.WIND
        self.save()
        with self.assertRaisesRegex(ValueError, "masquerade"):
            core.validate(self.folder)
        self.row["suitability_family_id"] = None
        self.p["evidence_group_id"] = fixtures.LEGACY
        self.save()
        with self.assertRaisesRegex(ValueError, "Unknown evidence group"):
            core.validate(self.folder)

    def test_broad_source_can_support_group_without_claiming_all_children(self):
        self.registers["EV_evidence_register"][0].update(
            suitability_family_id="agroforestry__cross_family",
            context={
                "evidence_scope": {
                    "level": "group",
                    "id": fixtures.GROUP,
                    "rationale": "Source reports aggregate linear plantings.",
                }
            },
        )
        a = self.row["justification"]["aggregation"]
        a["covered_families"] = []
        a["unresolved_families"] = [fixtures.WIND, fixtures.BOUNDARY, fixtures.CONTOUR]
        a["evidence_applicability"]["ev"]["families"] = []
        a["scope_rationale"] = "Group effect reported; family composition unspecified."
        self.refresh()
        core.validate(self.folder, self.packet, [])
        self.assertEqual(
            self.packet["family_hierarchy"]["coverage"]["family:" + fixtures.WIND][
                "total"
            ],
            0,
        )
        self.assertEqual(
            self.packet["family_hierarchy"]["coverage"]["group:" + fixtures.GROUP][
                "total"
            ],
            1,
        )

    def test_rejected_or_qualitative_only_evidence_does_not_gain_eligibility(self):
        self.registers["EV_evidence_register"][0]["review_state"] = "dropped"
        self.refresh()
        with self.assertRaisesRegex(ValueError, "Held/dropped"):
            core.validate(self.folder)
        self.registers["EV_evidence_register"][0].update(
            review_state="", suitability_family_id="agroforestry__homegardens_proximity"
        )
        self.refresh()
        with self.assertRaisesRegex(ValueError, "Qualitative-only|different family"):
            core.validate(self.folder)

    def test_group_withdrawal_uses_own_basis_and_preserves_practice_cell(self):
        self.baseline["agroforestry"][core.TABLES["T6"]] = [copy.deepcopy(self.row)]
        self.accept()
        q = self.queue()
        self.assertEqual(q["recipes"], self.baseline)
        prior = core.prior_rows(q, self.p)
        self.folder = self.root / core.PROPOSALS / "withdraw-fixture"
        self.folder.mkdir()
        for name in ("inputs.json", "skill.md"):
            shutil.copyfile(
                self.root / core.PROPOSALS / "fixture" / name, self.folder / name
            )
        self.p.update(
            id="withdraw-fixture",
            action="withdraw",
            replaces={"result": core.replacement_digest(prior[0])},
        )
        self.p["candidates"][0]["disposition"] = "context"
        self.save(rows=[])
        core.validate(self.folder, self.packet, prior)
        event = dict(
            self.event,
            proposal_id=self.p["id"],
            proposal_sha256=core.proposal_digest(self.folder),
            receipt=44,
        )
        # Replay fixture journal, without producing an authenticated production decision.
        with (self.root / core.JOURNAL).open("ab") as stream:
            stream.write(core.encoded(event))
        q = self.queue()
        self.assertEqual(q["recipes"], self.baseline)
        self.assertEqual(self.group(q)["recipes"][core.TABLES["T6"]], [])
        self.assertEqual(self.group(q)["rows"][0]["action"], "withdraw")

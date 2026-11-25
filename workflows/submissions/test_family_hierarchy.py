"""Coverage and adoption preserve historical attribution without filling empty children."""

import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

import configuration as config
import family_hierarchy as hierarchy

ROOT = Path(__file__).resolve().parents[2]
METHOD = "7d447297742d6d4aaf0cd66709ef7ccf68e8c0af"
BASE = "ae297935e5230e4cc97154c87cbf245a2e7d5a87"
WIND = "agroforestry__wind_shelter"
BOUNDARY = "agroforestry__boundary_planting"
CONTOUR = "agroforestry__contour_buffers"
GROUP = "agroforestry__linear_plantings"
LEGACY = "agroforestry__linear_boundary"
F1 = "agroforestry__planted_silvoarable"


def fixture_configuration(root):
    for name in (hierarchy.FAM, hierarchy.TRANSITION, hierarchy.PIN):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)
    (root / hierarchy.ADOPTION).write_bytes(
        hierarchy.encoded({"pending_at_adoption": {"legacy": LEGACY, "old-f1": F1}})
    )


class Coverage(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        fixture_configuration(self.root)
        self.rows = []
        for eid, family, level, scope in (
            ("wind", WIND, "subpractice", "windbreaks_shelterbelts"),
            ("boundary", BOUNDARY, None, None),
            ("group", "agroforestry__cross_family", "group", GROUP),
            ("general", "", None, None),
            ("legacy", LEGACY, None, None),
            ("old-f1", F1, None, None),
            ("held", WIND, None, None),
            ("dropped", BOUNDARY, None, None),
        ):
            row = dict(
                evidence_id=eid,
                source_id="one-study",
                nbs_id="agroforestry",
                suitability_family_id=family,
                use_role="nbs_effect",
                reviewer_ok=True,
            )
            if level:
                row["context"] = {
                    "evidence_scope": {
                        "level": level,
                        "id": scope,
                        "rationale": "Synthetic source attribution.",
                    }
                }
            self.rows.append(row)
        self.rows[-1]["review_state"] = "dropped"
        self.reviews = [dict(evidence_id="held", decision="flag")]

    def result(self):
        return hierarchy.coverage(self.root, self.rows, self.reviews)

    def test_upward_union_broader_context_and_no_downward_inheritance(self):
        before = copy.deepcopy(self.rows)
        result = self.result()
        self.assertEqual(self.rows, before)
        views = result["coverage"]
        self.assertEqual(views["practice:agroforestry"]["total"], 8)
        self.assertEqual(views["group:" + GROUP]["total"], 6)
        self.assertEqual(views["group:" + GROUP]["held"], 1)
        self.assertEqual(views["group:" + GROUP]["rejected"], 1)
        child = views["family:" + CONTOUR]
        self.assertEqual(child["total"], 0)
        self.assertEqual(child["broader_evidence_ids"], ["general", "group"])
        self.assertEqual(child["legacy_scope_evidence_ids"], ["legacy", "old-f1"])
        self.assertEqual(
            result["findings"]["legacy"]["node"], "legacy_family:" + LEGACY
        )
        self.assertEqual(views["subpractice:windbreaks_shelterbelts"]["total"], 1)
        self.assertEqual(
            views["subpractice:windbreaks_shelterbelts"]["broader_evidence_ids"],
            ["general", "group", "held"],
        )
        # Eight findings from one source are eight findings, not eight independent studies.
        self.assertEqual(
            {r["source_id"] for r in result["findings"].values()}, {"one-study"}
        )

    def test_review_state_and_lane_are_retained(self):
        self.reviews += [dict(evidence_id="wind", decision="reopen")]
        result = self.result()
        self.assertEqual(result["findings"]["wind"]["review_status"], "pending")
        self.assertEqual(result["findings"]["held"]["review_status"], "held")
        self.assertEqual(result["findings"]["dropped"]["review_status"], "rejected")
        self.rows[0]["use_role"] = "operational_risk"
        filtered = hierarchy.coverage(self.root, self.rows, self.reviews, lane="M2b")
        self.assertEqual(set(filtered["findings"]), {"wind"})

    def test_bad_scope_duplicate_and_unpinned_metadata_fail(self):
        for scope in (
            {"level": "subpractice", "id": "missing", "rationale": "test"},
            {
                "level": "subpractice",
                "id": "planted_boundary_cropland",
                "rationale": "test",
            },
            {"level": "group", "id": GROUP, "rationale": "test"},
            {"level": "subpractice", "id": "windbreaks_shelterbelts"},
        ):
            self.rows[0]["context"] = {"evidence_scope": scope}
            with self.assertRaises(ValueError):
                self.result()
        self.rows[0].pop("context")
        self.rows.append(self.rows[0])
        with self.assertRaisesRegex(ValueError, "Duplicate finding"):
            self.result()
        (self.root / hierarchy.PIN).write_text("{}")
        with self.assertRaisesRegex(ValueError, "Unpinned"):
            self.result()

    def test_existing_legacy_correction_passes_family_gate_without_retired_new_rows(
        self,
    ):
        producer = self.root / "producer"
        fam = producer / "schema/registers/FAM_family_registry.csv"
        fam.parent.mkdir(parents=True)
        shutil.copyfile(self.root / hierarchy.FAM, fam)
        metadata = producer / hierarchy.TARGET
        metadata.parent.mkdir(parents=True)
        shutil.copyfile(self.root / hierarchy.TRANSITION, metadata)
        old = producer / "schema/registers/EV_evidence_register.csv"
        old.write_text(
            "evidence_id,nbs_id,suitability_family_id\nlegacy,agroforestry,"
            + LEGACY
            + "\n"
        )
        original = fam.read_bytes()
        unit = dict(
            evidence_id="legacy",
            nbs_id="agroforestry",
            suitability_family_id=LEGACY,
            quote="Corrected source passage, scope unchanged.",
        )
        allowed = hierarchy.table(hierarchy.intake_family_bytes(producer, [unit]))
        self.assertIn(LEGACY, {r["suitability_family_id"] for r in allowed})
        self.assertEqual(fam.read_bytes(), original)
        with self.assertRaisesRegex(ValueError, "retired family"):
            hierarchy.intake_family_bytes(producer, [dict(unit, evidence_id="new")])
        with self.assertRaisesRegex(ValueError, "retired family"):
            hierarchy.intake_family_bytes(
                producer, [dict(unit, nbs_id="forest_restoration")]
            )
        migrated = hierarchy.table(
            hierarchy.intake_family_bytes(
                producer, [dict(unit, suitability_family_id=WIND)]
            )
        )
        self.assertNotIn(LEGACY, {r["suitability_family_id"] for r in migrated})


@unittest.skipUnless(
    os.environ.get("CIAT_TEST_REPO"), "Requires local integration history"
)
class AdoptionRoute(unittest.TestCase):
    def test_pin_retry_restore_and_immutable_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, method = Path(tmp) / "evidence", Path(tmp) / "method"
            config.snapshot(root, "", BASE, ["/registers/", "/configuration/"], ROOT)
            config.snapshot(
                method,
                config.METHOD,
                METHOD,
                ["/configuration/", "/data-model/configuration/"],
                config.local_method(),
            )
            names = [
                hierarchy.EV,
                hierarchy.LOG,
                "registers/schema/registers/SRCH_search_register.csv",
            ]
            original = {name: (root / name).read_bytes() for name in names}
            old_pin = json.loads((root / hierarchy.PIN).read_bytes())["revision"]
            config.pin(root, METHOD, method)
            saved = (root / hierarchy.ADOPTION).read_bytes()
            self.assertEqual(len(json.loads(saved)["pending_at_adoption"]), 567)
            config.pin(root, METHOD, method)
            self.assertEqual((root / hierarchy.ADOPTION).read_bytes(), saved)
            config.verify_method(root, method)
            for name, data in original.items():
                self.assertEqual((root / name).read_bytes(), data)
            config.git("add", ".", cwd=root)
            config.git(
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-qm",
                "Fixture adoption",
                cwd=root,
            )
            base = config.git("rev-parse", "HEAD", cwd=root).decode().strip()
            hierarchy.verify_adoption(root, base)
            # A rollback preserves the adoption record; it never rewrites findings.
            config.pin(root, old_pin, config.local_method())
            self.assertFalse((root / hierarchy.TRANSITION).exists())
            self.assertEqual((root / hierarchy.ADOPTION).read_bytes(), saved)
            hierarchy.verify_adoption(root, base)
            config.pin(root, METHOD, method)
            data = json.loads(saved)
            data["pending_at_adoption"].pop("ev_hazard_drought_kuyah19_1", None)
            data["pending_at_adoption"]["invented"] = WIND
            (root / hierarchy.ADOPTION).write_bytes(hierarchy.encoded(data))
            with self.assertRaisesRegex(ValueError, "history rewritten"):
                hierarchy.verify_adoption(root, base)

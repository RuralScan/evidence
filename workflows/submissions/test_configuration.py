"""Exercise a configuration release and evidence-owned changes on isolated Git editions."""

import copy
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import configuration as config
from queue_view import compile_candidate

BASE = "017544fe55929cd03579494bbd4062db67697363"
METHOD_PIN = "e50a3a01b6b164bebed8dfd09229c4df83086c01"
POLICY = "schema/lookups/family_rollup_policy.csv"


@unittest.skipUnless(os.environ.get("CIAT_TEST_REPO"), "Requires pinned CIAT history")
class ConfigurationRoute(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        base = Path(cls.tmp.name).resolve()
        cls.method = base / "method"
        config.snapshot(
            cls.method,
            config.METHOD,
            METHOD_PIN,
            ["/configuration/", "/data-model/configuration/"],
            config.local_method(),
        )
        cls.engine = base / "engine"
        config.engine(Path(os.environ["CIAT_TEST_REPO"]), cls.engine)
        src = str(cls.engine / "src")
        prior = {
            k: v for k, v in sys.modules.items() if k.split(".")[0] == "nbs_ruralscan"
        }
        for key in prior:
            del sys.modules[key]
        sys.path.insert(0, src)

        def restore():
            sys.path.remove(src)
            for name in list(sys.modules):
                if name.split(".")[0] == "nbs_ruralscan":
                    del sys.modules[name]
            sys.modules.update(prior)

        cls.addClassCleanup(restore)

    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dest = Path(folder.name).resolve() / "evidence"
        config.snapshot(
            self.dest,
            "",
            BASE,
            ["/registers/", "/publication/", "/recipe-edits/"],
            config.ROOT,
        )
        config.pin(self.dest, METHOD_PIN, self.method)
        for path in config.OWN:
            target = self.dest / config.cache_path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(config.blob(self.engine, config.SEED, path))
        (self.dest / config.JOURNAL).write_bytes(config.encoded([]))
        for path in (config.EV, config.SRC, "pipeline/metrics/review_log.csv"):
            (self.engine / path).write_bytes(
                (self.dest / "registers" / path).read_bytes()
            )

    def change(self, table, key, changes, sid, eid):
        old = next(
            r
            for r in config.rows((self.dest / config.cache_path(table)).read_bytes())
            if all(r[k] == v for k, v in key.items())
        )
        return dict(
            id="fixture-locator",
            method_revision=METHOD_PIN,
            table=table,
            key=key,
            before_sha256=config.digest(config.encoded(old)),
            changes=changes,
            provenance=dict(
                source_id=sid,
                locator="Details of Methodology" if table == config.TOOL else "p. 3",
                evidence_ids=[eid],
            ),
            reason="Disposable source locator exercise.",
        )

    def test_owned_change_retry_and_rejections(self):
        target = "schema/lookups/wocat_hazard_map.csv"
        sid, eid = "wocat_1626_2014", "ev_fr_precip_wocat1626_1"
        key = dict(
            wocat_group="climatological_disaster_coping", wocat_key="forest_fire"
        )
        event = self.change(target, key, {"note": "Fixture source mapping."}, sid, eid)
        for field, value, error in (
            ("evidence_ids", ["missing"], "Missing source or finding"),
            ("source_id", "saraheb3_af_midwest", "another source"),
        ):
            bad = copy.deepcopy(event)
            bad["provenance"][field] = value
            with self.assertRaisesRegex(ValueError, error):
                config.record(self.dest, self.engine, bad)
        with self.assertRaisesRegex(ValueError, "different method revision"):
            config.record(self.dest, self.engine, dict(event, method_revision="f" * 40))
        broken = copy.deepcopy(event)
        broken["provenance"]["locator"] = "p. 99"
        with self.assertRaisesRegex(ValueError, "Locator differs"):
            config.record(self.dest, self.engine, broken)
        invalid = dict(event, changes=dict(hazard_type="unknown"))
        with self.assertRaisesRegex(ValueError, "Unknown hazard"):
            config.record(self.dest, self.engine, invalid)
        impact = "schema/lookups/wocat_impact_map.csv"
        ikey = dict(
            wocat_group="impacts_socio_economic_production",
            wocat_field="crop_production",
        )
        invalid = self.change(
            impact, ikey, {"canonical_variable_id": "unknown"}, sid, eid
        )
        with self.assertRaisesRegex(ValueError, "Unknown WOCAT"):
            config.record(self.dest, self.engine, invalid)
        tool = self.change(
            config.TOOL,
            dict(tool_id="saraheb3_af_midwest"),
            dict(tool_type="bad"),
            "saraheb3_af_midwest",
            "ev_production_gap_saraheb3_tool",
        )
        with self.assertRaisesRegex(ValueError, "Unknown tool vocabulary"):
            config.record(self.dest, self.engine, tool)
        self.assertEqual(config.owned_history(self.dest), [])
        config.record(self.dest, self.engine, event)
        config.record(self.dest, self.engine, event)
        self.assertEqual(config.owned_history(self.dest), [event])
        with self.assertRaisesRegex(ValueError, "Stale configuration row"):
            config.record(
                self.dest, self.engine, dict(event, id="retry-with-stale-value")
            )
        config.verify_owned(self.dest, self.engine, BASE)
        config.overlay(self.engine, self.dest)
        from nbs_ruralscan.ingest import wocat

        self.assertTrue(
            any(
                r["note"] == "Fixture source mapping."
                for r in wocat._load_csv(self.engine / target)
            )
        )
        with (self.dest / config.cache_path(target)).open("ab") as stream:
            stream.write(b"\n")
        with self.assertRaisesRegex(ValueError, "Unrecorded configuration change"):
            config.verify_owned(self.dest, self.engine, BASE)

    def test_candidate_uses_selected_release_and_replays_old_pin(self):
        q1, c1 = compile_candidate(self.engine, self.dest)
        self.assertEqual(c1["configuration"]["method_revision"], METHOD_PIN)
        self.assertEqual(c1["configuration"]["inputs"][POLICY], c1["inputs"][POLICY])

        def fire(q):
            rows = q["recipes"]["forest_restoration"]["T3_nbs_hazard_farming"]
            return {r["record_id"]: set(r["evidence_ids"] or []) for r in rows}

        base = fire(q1)
        plantation = "forest_restoration__plantation__fire__all"
        aggregate = "forest_restoration__fire__all"
        self.assertTrue(base[plantation] - base[aggregate])
        # Deliberately reverse the lookup on a disposable method branch to prove
        # that the real compiler reads the selected definition. Never publish this fixture.
        path = self.method / "configuration/lookups/family_rollup_policy.csv"
        path.write_bytes(path.read_bytes().replace(b",false,", b",true,"))
        manifest = self.method / config.RELEASE
        document = json.loads(manifest.read_bytes())
        document["files"][POLICY]["sha256"] = config.digest(path.read_bytes())
        manifest.write_bytes(config.encoded(document))
        config.git(
            "add",
            "--",
            config.RELEASE,
            str(path.relative_to(self.method)),
            cwd=self.method,
        )
        config.git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.org",
            "commit",
            "-qm",
            "Disposable policy test",
            cwd=self.method,
        )
        next_pin = config.git("rev-parse", "HEAD", cwd=self.method).decode().strip()
        config.pin(self.dest, next_pin, self.method)
        q2, c2 = compile_candidate(self.engine, self.dest)
        self.assertEqual(c2["configuration"]["method_revision"], next_pin)
        self.assertTrue((base[plantation] - base[aggregate]) & fire(q2)[aggregate])
        self.assertEqual(fire(q2)[plantation], base[plantation])
        self.assertEqual(q1["recipes"]["agroforestry"], q2["recipes"]["agroforestry"])
        config.pin(self.dest, METHOD_PIN, self.method)
        q3, c3 = compile_candidate(self.engine, self.dest)
        self.assertEqual((q3, c3), (q1, c1))
        self.assertEqual(
            (self.dest / "registers" / config.EV).read_bytes(),
            config.blob(self.dest, BASE, "registers/" + config.EV),
        )
        self.assertEqual(
            config.git(
                "status", "--porcelain", "--", "registers/pipeline", cwd=self.dest
            ),
            b"",
        )

"""Exercise applied register operations on a disposable Git history and private corpus."""

from argparse import Namespace
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest

import pymupdf
import register_operation as cli
import registration as reg
from registers import (
    ROOT,
    SEED,
    EV,
    SRC,
    JOURNAL,
    git,
    index,
    snapshot,
    content_digest,
)

EXAMPLE = ROOT / "workflows/discovery/example"
SID = "fixture_terrace_manual"
TITLE = "Annual rainfall guidance for dryland bench terraces"
QUOTE = "Bench terraces were used on sites with seasonal rainfall."


@unittest.skipUnless(
    os.environ.get("CIAT_TEST_REPO"),
    "Set CIAT_TEST_REPO to the pinned compiler repository",
)
class RegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.engine = Path(cls.temp.name).resolve() / "compiler"
        snapshot(
            cls.engine,
            "",
            SEED,
            ["/src/", "/schema/"],
            Path(os.environ["CIAT_TEST_REPO"]),
        )
        # Other suites load the same compiler from their own short-lived checkouts.
        package = "nbs_ruralscan"

        def unload():
            return {
                name: sys.modules.pop(name)
                for name in list(sys.modules)
                if name == package or name.startswith(package + ".")
            }

        previous = unload()
        cls.addClassCleanup(sys.modules.update, previous)
        cls.addClassCleanup(unload)
        sys.path.insert(0, str(cls.engine / "src"))
        cls.addClassCleanup(sys.path.remove, str(cls.engine / "src"))

    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.root = self.tmp / "repo"
        for name in (*reg.TRACKED, EV, reg.FAMILIES, reg.CROSSWALK):
            dest = self.root / "registers" / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "registers" / name, dest)
        (self.root / JOURNAL).write_text("{}")
        git("init", "-q", cwd=self.root)
        git("config", "user.name", "Fixture", cwd=self.root)
        git("config", "user.email", "fixture@example.invalid", cwd=self.root)
        self.base = self.commit()
        self.plan = cli.read(EXAMPLE / "plan.json")
        self.row = dict(
            record_id=SID,
            title=TITLE,
            citation=f"Agency (2024). {TITLE}.",
            url="https://publisher.example/manual",
        )
        self.candidate = dict(
            candidate_id=SID,
            title=TITLE,
            citation=self.row["citation"],
            url=self.row["url"],
            process="stock",
            tables="T4",
            nbs_id=self.plan["nbs_id"],
        )

    def commit(self):
        git("add", "-A", cwd=self.root)
        git("commit", "-qm", "Fixture step", cwd=self.root)
        return git("rev-parse", "HEAD", cwd=self.root).decode().strip()

    def discovery(self, name, *, empty=False, family=None):
        work = self.tmp / name
        work.mkdir()
        plan = self.plan | {"run_id": name}
        if family is not None:
            plan["family"] = family
        capture = cli.read(EXAMPLE / "stock.json")
        capture["records"] = (
            []
            if empty
            else [*capture["records"], self.row | {"abstract": "private provider text"}]
        )
        paths = (work / "plan.json", work / "decisions.json")
        decisions = (
            []
            if empty
            else cli.read(EXAMPLE / "decisions.json")["records"]
            + [
                dict(
                    record_id=SID,
                    title=TITLE,
                    disposition="include",
                    reason="Annual rainfall for terraces.",
                )
            ]
        )
        for file, data in zip(
            [paths[0], work / "stock.json", paths[1]],
            [
                plan,
                capture,
                dict(
                    input_sha256=reg.screen.fingerprint([plan, [capture]]),
                    records=decisions,
                ),
            ],
            strict=True,
        ):
            file.write_text(json.dumps(data))
        return cli.operation(
            Namespace(kind="discovery", plan=paths[0], decisions=paths[1], stamp=True),
            self.root,
        )

    def install(self, op):
        return cli.install(self.root, self.base, op, self.engine)

    def replay(self):
        projected = reg.checked_source_base(self.root, self.base, self.engine)
        self.assertEqual(projected, (self.root / "registers" / SRC).read_bytes())

    def test_discovery_reuse_zero_scope_retry_and_tampered_partial_change(self):
        before = {p: len(reg.records(self.root, p)) for p in (reg.QUEUE, reg.SEARCH)}
        op = self.discovery("bounded")
        self.assertNotIn("private provider text", json.dumps(op))
        self.assertTrue(self.install(op))
        self.replay()
        self.assertFalse(self.install(op))
        self.assertEqual(len(reg.records(self.root, reg.QUEUE)), before[reg.QUEUE] + 1)
        self.assertEqual(
            len(reg.records(self.root, reg.SEARCH)), before[reg.SEARCH] + 1
        )
        search = reg.records(self.root, reg.SEARCH)[-1]
        self.assertEqual(
            (search["n_retrieved"], search["n_screened"], search["n_included"]),
            ("4", "4", "2"),
        )
        self.assertIn(
            "wocat_wh_guidelines_2013",
            (self.root / reg.REPORTS / (reg.stem(op) + ".json")).read_text(),
        )
        self.base = self.commit()
        zero = self.discovery("empty", empty=True, family="")
        self.install(zero)
        self.replay()
        empty = reg.records(self.root, reg.SEARCH)[-1]
        self.assertEqual(
            (empty["n_retrieved"], empty["n_screened"], empty["n_included"]),
            ("0", "0", "0"),
        )
        searched = {
            (r["last_run_id"], r["family"], r["screened"])
            for r in reg.records(self.root, reg.LEDGER)
        }
        self.assertIn(("empty", "", "done"), searched)
        self.assertIn(("bounded", self.plan["family"], "done"), searched)
        path = self.root / reg.RECORDS / (reg.stem(zero) + ".json")
        data = cli.read(path)
        path.write_text(json.dumps(data | {"base": "0" * 40}))
        with self.assertRaisesRegex(ValueError, "Stale"):
            self.replay()
        path.write_text(json.dumps(data))
        with (self.root / "registers" / reg.QUEUE).open("a") as stream:
            stream.write("\n")
        with self.assertRaisesRegex(ValueError, "differs from replay"):
            self.replay()

    def source_args(self):
        pdf = self.tmp / "fixture.pdf"
        with pymupdf.open() as doc:
            page = doc.new_page()
            page.insert_text((30, 45), TITLE)
            page.insert_text((30, 75), QUOTE)
            doc.save(pdf)
        plan = dict(
            candidate_id=SID,
            kind="pdf",
            expected_sha256=content_digest(pdf.read_bytes()),
            publisher_hosts=["publisher.example"],
        )
        bundle = self.tmp / "acquired"
        receipt, body = reg.acquisition.acquire(self.candidate, plan, pdf)
        reg.acquisition.publish(bundle, receipt, body)
        team = self.tmp / "shared"
        team.mkdir()
        shutil.copyfile(pdf, team / "edition.pdf")
        args = Namespace(
            kind="source",
            plan=self.tmp / "acquire.json",
            candidates=self.tmp / "candidates.json",
            assessment=self.tmp / "assessment.json",
            bundle=bundle,
            library_root=team,
            library_path="2_Technical_&_Data/library/edition.pdf",
        )
        for path, value in (
            (args.plan, plan),
            (args.candidates, [self.candidate]),
            (
                args.assessment,
                dict(
                    benchmark_tier="medium",
                    venue_type="institutional_report",
                    method_type="review",
                ),
            ),
        ):
            path.write_text(json.dumps(value))
        return args

    def test_promotion_enters_pending_and_first_extraction_passes_official_gate(self):
        from nbs_ruralscan.schema_tools import evidence_intake

        self.install(self.discovery("new"))
        self.base = self.commit()
        args = self.source_args()
        op = cli.operation(args, self.root)
        before = (self.root / "registers" / EV).read_bytes()
        self.assertTrue(self.install(op))
        self.replay()
        self.assertFalse(self.install(op))
        self.assertEqual((self.root / "registers" / EV).read_bytes(), before)
        source = index(reg.records(self.root, SRC), "source_id")[SID]
        self.assertEqual(
            (
                source["extraction_status"],
                source["vars_extracted"],
                source["extraction_run_id"],
            ),
            ("pending", "", ""),
        )
        self.assertEqual(source["artifact_sha1"], op["receipt"]["artifact"]["sha1"])
        self.assertEqual(
            index(reg.records(self.root, reg.QUEUE), "source_id")[SID][
                "title_verified"
            ],
            "true",
        )
        paths = replace(
            evidence_intake.EvidenceIntakePaths.from_root(
                self.engine, corpus=args.bundle / "cache"
            ),
            sources=self.root / "registers" / SRC,
            queue=self.root / "registers" / reg.QUEUE,
            evidence=self.root / "registers" / EV,
        )
        unit = dict(
            source_id=SID,
            evidence_id="ev_fixture",
            nbs_id=self.plan["nbs_id"],
            suitability_family_id=self.plan["family"],
            variable="annual_precipitation",
            use_role="structural_suitability",
            locator_type="page",
            page=1,
            quote=QUOTE,
            context={"practice_as_described": "Bench terraces on dryland farms"},
            extraction_confidence="medium",
            evidence_type="scoping_candidate",
            claim_scope="practice_technology",
            claim_basis="expert_assertion",
            ruleset_version="v1.10.1",
            raw_name="annual rainfall",
            justification_quote=TITLE,
            justification_page=1,
            relationship={"direction": "unclear"},
        )
        self.assertEqual(
            evidence_intake.gate([unit], {"structural_suitability"}, paths=paths), []
        )
        (args.library_root / "edition.pdf").write_bytes(b"a different edition")
        with self.assertRaisesRegex(ValueError, "Shared library edition"):
            cli.operation(args, self.root)
        receipt = op["receipt"] | {"candidate_sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "Receipt does not match"):
            reg.promote(self.root, op | {"receipt": receipt}, self.engine)

    def test_verification_requires_applied_current_scoped_evidence(self):
        from corrections import content
        import intake

        eid = "ev_fr_precip_wocat1626_1"
        finding = index(reg.records(self.root, EV), "evidence_id")[eid]
        unit = content(finding)
        body = intake.encode("extraction", "T4", self.base, [unit])
        pin = self.base
        (self.root / JOURNAL).write_text(
            json.dumps(
                {
                    "29": {
                        "kind": "extraction",
                        "base": pin,
                        "digest": content_digest(body.encode()),
                    }
                }
            )
        )
        self.base = self.commit()
        op = dict(
            kind="verification",
            run_id="checked",
            nbs_id=finding["nbs_id"],
            table="T4",
            family=finding["suitability_family_id"],
            process="grey",
            date="2026-11-16",
            by="fixture",
            receipts=[{"number": 29, "body": body}],
            status="in_progress",
        )
        with self.assertRaisesRegex(ValueError, "full current scope"):
            self.install(op | {"status": "done"})
        with self.assertRaisesRegex(ValueError, "Receipt content changed"):
            self.install(op | {"receipts": [{"number": 29, "body": body + " "}]})
        self.install(op)
        self.replay()
        self.assertFalse(self.install(op))

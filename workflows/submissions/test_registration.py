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
from unittest.mock import patch

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

    def source_args(self, candidate=None):
        candidate = candidate or self.candidate
        work = self.tmp / candidate["candidate_id"]
        work.mkdir()
        pdf = work / "fixture.pdf"
        with pymupdf.open() as doc:
            page = doc.new_page()
            page.insert_text((30, 45), candidate["title"])
            page.insert_text((30, 75), QUOTE)
            doc.save(pdf)
        plan = dict(
            candidate_id=candidate["candidate_id"],
            kind="pdf",
            expected_sha256=content_digest(pdf.read_bytes()),
            publisher_hosts=["publisher.example"],
        )
        bundle = work / "acquired"
        receipt, body = reg.acquisition.acquire(candidate, plan, pdf)
        reg.acquisition.publish(bundle, receipt, body)
        team = work / "shared"
        team.mkdir()
        shutil.copyfile(pdf, team / (candidate["candidate_id"] + ".pdf"))
        args = Namespace(
            kind="source",
            plan=work / "acquire.json",
            candidates=work / "candidates.json",
            assessment=work / "assessment.json",
            bundle=bundle,
            library_root=team,
            library_path="2_Technical_&_Data/library/"
            + candidate["candidate_id"]
            + ".pdf",
        )
        for path, value in (
            (args.plan, plan),
            (args.candidates, [candidate]),
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
        # A second acquired PDF with the same copied citation and a different
        # screened title cannot use the queued identity.
        other_title = "An unrelated handbook for land restoration"
        other_candidate = op["candidate"] | {"title": other_title}
        other_pdf = self.tmp / "other.pdf"
        with pymupdf.open() as doc:
            doc.new_page().insert_text((30, 45), other_title)
            doc.save(other_pdf)
        other_plan = op["plan"] | {
            "expected_sha256": content_digest(other_pdf.read_bytes())
        }
        other_receipt, _ = reg.acquisition.acquire(
            other_candidate, other_plan, other_pdf
        )
        with self.assertRaisesRegex(ValueError, "Screened title differs"):
            reg.promote(
                self.root,
                op
                | {
                    "candidate": other_candidate,
                    "plan": other_plan,
                    "receipt": other_receipt,
                },
                self.engine,
            )
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
        (args.library_root / (SID + ".pdf")).write_bytes(b"a different edition")
        with self.assertRaisesRegex(ValueError, "Shared library edition"):
            cli.operation(args, self.root)
        receipt = op["receipt"] | {"candidate_sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "Receipt does not match"):
            reg.promote(self.root, op | {"receipt": receipt}, self.engine)

    def source_batch(self):
        self.install(self.discovery("batch_sources"))
        second = self.candidate | {
            "candidate_id": "fixture_second_manual",
            "title": "Floodplain restoration guidance for tropical wetlands",
            "citation": "Agency (2024). Floodplain restoration guidance for tropical wetlands.",
            "url": "https://publisher.example/second",
        }
        queued = reg.records(self.root, reg.QUEUE)
        queued.append(
            index(queued, "source_id")[SID]
            | {
                "source_id": second["candidate_id"],
                "citation": second["citation"],
                "url": second["url"],
            }
        )
        reg.write_csv(self.root / "registers" / reg.QUEUE, queued)
        self.base = self.commit()
        manifest = self.tmp / "sources.json"
        entries = []
        for candidate in (self.candidate, second):
            args = self.source_args(candidate)
            entries.append(
                {
                    k: str(v.relative_to(self.tmp)) if isinstance(v, Path) else v
                    for k, v in vars(args).items()
                    if k != "kind"
                }
            )
        manifest.write_text(json.dumps(entries))
        return Namespace(kind="source-batch", manifest=manifest)

    def test_batch_source_registration_replay_and_identical_retry(self):
        args = self.source_batch()
        before = len(reg.records(self.root, SRC))
        ev = (self.root / "registers" / EV).read_bytes()
        ops = cli.operations(args, self.root)
        # A source may already have landed through the single-source route.
        self.install(ops[0])
        self.base = self.commit()
        self.assertEqual(
            len(cli.install_many(self.root, self.base, ops[::-1], self.engine)), 1
        )
        self.replay()
        self.assertEqual(len(reg.records(self.root, SRC)), before + 2)
        for op in ops:
            sid = op["receipt"]["source_id"]
            self.assertEqual(
                index(reg.records(self.root, reg.QUEUE), "source_id")[sid]["status"],
                "acquired",
            )
        self.assertEqual((self.root / "registers" / EV).read_bytes(), ev)
        self.base = self.commit()
        self.assertEqual(
            cli.install_many(
                self.root, self.base, cli.operations(args, self.root), self.engine
            ),
            [],
        )
        self.assertFalse(git("status", "--porcelain", cwd=self.root))

    def test_batch_failure_is_atomic_and_identifies_source(self):
        args = self.source_batch()
        ops = cli.operations(args, self.root)
        before = {p: (self.root / "registers" / p).read_bytes() for p in reg.TRACKED}
        names = sorted(p.name for p in (self.root / reg.RECORDS).iterdir())
        ops[-1]["assessment"]["benchmark_tier"] = "not-a-tier"
        with self.assertRaisesRegex(ValueError, "fixture_second_manual.*assessment"):
            cli.install_many(self.root, self.base, ops, self.engine)
        self.assertEqual(
            before, {p: (self.root / "registers" / p).read_bytes() for p in reg.TRACKED}
        )
        self.assertEqual(
            names, sorted(p.name for p in (self.root / reg.RECORDS).iterdir())
        )
        entries = cli.read(args.manifest)
        path = self.tmp / entries[-1]["library_root"] / "fixture_second_manual.pdf"
        path.write_bytes(b"wrong shared edition")
        with self.assertRaisesRegex(
            ValueError, "fixture_second_manual.*Shared library edition"
        ):
            cli.operations(args, self.root)

    def test_prepare_batch_and_queue_prs_with_real_compiler(self):
        """Exercise the CLI preparation through commits; replace only remote writes."""
        import subprocess

        args = self.source_batch()
        # Preserve official history so correction explanations can read their
        # actual before/after revisions, then overlay only our fixture inputs.
        full = self.tmp / "full"
        snapshot(
            full, "", git("rev-parse", "HEAD", cwd=ROOT).decode().strip(), ["/*"], ROOT
        )
        for name in reg.TRACKED:
            shutil.copyfile(self.root / "registers" / name, full / "registers" / name)
        shutil.copytree(self.root / reg.RECORDS, full / reg.RECORDS, dirs_exist_ok=True)
        shutil.copytree(self.root / reg.REPORTS, full / reg.REPORTS, dirs_exist_ok=True)
        self.root = full
        git("config", "user.name", "Fixture", cwd=self.root)
        git("config", "user.email", "fixture@example.invalid", cwd=self.root)
        self.base = self.commit()
        git(
            "remote",
            "set-url",
            "origin",
            "https://github.com/RuralScan/evidence.git",
            cwd=self.root,
        )
        bare = self.tmp / "proposals.git"
        git("init", "--bare", "--quiet", str(bare))
        real_git, real_run = cli.git, subprocess.run
        created, proposals = [], []

        def local_git(*parts, cwd=None, **kw):
            if parts == ("fetch", "--quiet", "origin", "main"):
                return b""
            if parts == ("rev-parse", "origin/main"):
                return (self.base + "\n").encode()
            if parts[:2] == ("ls-remote", "--heads"):
                return b""
            if parts[:2] == ("push", "origin"):
                proposals.append(parts[2].split(":", 1)[1])
                # Assert the complete replay before even the simulated push.
                self.assertEqual(
                    reg.checked_source_base(cwd, self.base, self.engine),
                    (cwd / "registers" / SRC).read_bytes(),
                )
                return real_git("push", str(bare), *parts[2:], cwd=cwd)
            return real_git(*parts, cwd=cwd, **kw)

        def local_run(command, *pargs, **kwargs):
            if command[:3] == ["gh", "pr", "create"]:
                created.append(command)
                return subprocess.CompletedProcess(command, 0)
            return real_run(command, *pargs, **kwargs)

        args.ciat_repo = Path(os.environ["CIAT_TEST_REPO"])
        args.base, args.open_pr = self.base, True
        with (
            patch.object(cli, "ROOT", self.root),
            patch.object(cli, "git", side_effect=local_git),
            patch.object(cli.intake, "check_destination"),
            patch.object(cli.subprocess, "run", side_effect=local_run),
        ):
            cli.prepare(args)
            corrections = self.tmp / "corrections.json"
            corrections.write_text(
                json.dumps(
                    [
                        dict(
                            source_id=SID,
                            changes={
                                "url": "https://publisher.example/corrected-manual",
                                "citation": f"Correct Author (2025). {TITLE}. Agency.",
                            },
                            reason="Publisher metadata; fixture",
                            operator="fixture",
                            date="2026-11-19",
                        )
                    ]
                )
            )
            cli.prepare(
                Namespace(
                    kind="queue",
                    corrections=corrections,
                    ciat_repo=args.ciat_repo,
                    base=self.base,
                    open_pr=True,
                )
            )
        self.assertEqual(len(created), 2)  # one PR for two sources, one for repairs
        self.assertFalse(git("status", "--porcelain", cwd=self.root))
        base_queue = json.loads(
            git("show", self.base + ":publication/review-queue.json", cwd=self.root)
        )
        published = json.loads(
            git("show", proposals[0] + ":publication/review-queue.json", cwd=bare)
        )
        self.assertEqual(
            len(published["registers"]["SRC_source_register"]),
            len(base_queue["registers"]["SRC_source_register"]) + 2,
        )
        for field in ("EV_evidence_register",):
            self.assertEqual(
                published["registers"][field], base_queue["registers"][field]
            )
        self.assertEqual(published["recipes"], base_queue["recipes"])
        self.assertEqual(
            git("show", proposals[1] + ":registers/" + SRC, cwd=bare),
            (self.root / "registers" / SRC).read_bytes(),
        )
        self.assertEqual(
            json.loads(
                git("show", proposals[1] + ":publication/review-queue.json", cwd=bare)
            ),
            base_queue,
        )

    def queue_fixture(self):
        self.install(self.discovery("queue_repairs"))
        queued = reg.records(self.root, reg.QUEUE)
        row = index(queued, "source_id")[SID]
        row.update(url="", doi="10.1234/fixture", doi_verified="true")
        reg.write_csv(self.root / "registers" / reg.QUEUE, queued)
        self.base = self.commit()
        request = dict(
            source_id=SID,
            changes={},
            doi_locator=True,
            reason="Verified DOI supplies the missing locator; fixture.",
            operator="fixture",
            date="2026-11-19",
        )
        record = {
            "DOI": row["doi"],
            "title": [TITLE],
            "author": [{"family": "Agency"}],
            "issued": {"date-parts": [[2024]]},
        }
        return request, record

    def test_queue_batch_replays_and_rejects_duplicates_atomically(self):
        self.source_batch()
        path = self.tmp / "queue.json"
        requests = [
            dict(
                source_id=sid,
                changes={"url": "https://publisher.example/corrected-" + sid},
                reason="Correct publisher locator; fixture",
                operator="fixture",
                date="2026-11-19",
            )
            for sid in (SID, "fixture_second_manual")
        ]
        path.write_text(json.dumps(requests))
        args = Namespace(kind="queue", corrections=path)
        ops = cli.operations(args, self.root)
        before = (self.root / "registers" / reg.QUEUE).read_bytes()
        ops[-1]["before"]["note"] += " stale"
        with self.assertRaisesRegex(
            ValueError, "fixture_second_manual.*Queue row changed"
        ):
            cli.install_many(self.root, self.base, ops, self.engine)
        self.assertEqual(before, (self.root / "registers" / reg.QUEUE).read_bytes())
        path.write_text(json.dumps([requests[0], requests[0]]))
        with self.assertRaisesRegex(ValueError, "Duplicate source"):
            cli.operations(args, self.root)
        path.write_text(json.dumps(requests))
        cli.install_many(
            self.root, self.base, cli.operations(args, self.root), self.engine
        )
        self.replay()
        self.assertEqual(
            cli.install_many(
                self.root, self.base, cli.operations(args, self.root), self.engine
            ),
            [],
        )

    def test_queue_correction_then_acquisition_and_registration(self):
        import queue_corrections as queue

        request, record = self.queue_fixture()
        old_src = (self.root / "registers" / SRC).read_bytes()
        with patch("identity._crossref", return_value=("ok", record)):
            op = queue.build(self.root, request)
        cli.install_many(self.root, self.base, [op], self.engine)
        with patch(
            "identity._crossref", side_effect=AssertionError("Replay must be offline")
        ):
            self.replay()
        row = index(reg.records(self.root, reg.QUEUE), "source_id")[SID]
        self.assertEqual(row["url"], "https://doi.org/10.1234/fixture")
        self.assertEqual(
            (row["status"], row["title_verified"], row["doi_verified"]),
            ("pending", "", "true"),
        )
        self.assertEqual((self.root / "registers" / SRC).read_bytes(), old_src)
        self.base = self.commit()
        updated = self.candidate | {"url": row["url"], "doi": row["doi"]}
        # Distinguish the DOI locator from the local artifact's recorded origin.
        with patch("identity._crossref", return_value=("ok", record)):
            # The fixture publisher host is retained for actual byte provenance.
            updated["url"] = "https://publisher.example/manual"
            args = self.source_args(updated)
        # Re-acquire against the corrected candidate with an explicit artifact URL.
        candidate = updated | {"url": row["url"]}
        plan = cli.read(args.plan) | {"artifact_url": updated["url"]}
        with patch("identity._crossref", return_value=("ok", record)):
            receipt, body = reg.acquisition.acquire(
                candidate, plan, args.bundle.parent / "fixture.pdf"
            )
        args.bundle = self.tmp / "corrected_bundle"
        reg.acquisition.publish(args.bundle, receipt, body)
        args.plan.write_text(json.dumps(plan))
        args.candidates.write_text(json.dumps([candidate]))
        self.install(cli.operation(args, self.root))
        self.replay()
        self.assertEqual(
            index(reg.records(self.root, reg.QUEUE), "source_id")[SID]["status"],
            "acquired",
        )
        self.assertEqual(
            index(reg.records(self.root, SRC), "source_id")[SID]["extraction_status"],
            "pending",
        )
        self.assertEqual(
            cli.install_many(
                self.root, self.base, [queue.build(self.root, request)], self.engine
            ),
            [],
        )

    def test_queue_rejects_identity_change_bad_doi_and_stale_row(self):
        import queue_corrections as queue

        request, record = self.queue_fixture()
        before = (self.root / "registers" / reg.QUEUE).read_bytes()
        with patch("identity._crossref", return_value=("ok", record)):
            with self.assertRaisesRegex(ValueError, "screened title"):
                queue.build(
                    self.root,
                    request
                    | {
                        "changes": {
                            "citation": "Author (2024). An unrelated work about deserts."
                        }
                    },
                )
            op = queue.build(self.root, request)
        with patch("identity._crossref", return_value=("unavailable", {})):
            with self.assertRaisesRegex(ValueError, "Crossref"):
                queue.build(self.root, request)
        with patch(
            "identity._crossref",
            return_value=(
                "ok",
                record | {"title": ["Marine fish and fisheries economics"]},
            ),
        ):
            with self.assertRaisesRegex(ValueError, "Crossref"):
                queue.build(self.root, request)
        self.assertEqual((self.root / "registers" / reg.QUEUE).read_bytes(), before)
        queued = reg.records(self.root, reg.QUEUE)
        index(queued, "source_id")[SID]["note"] += " Later work."
        reg.write_csv(self.root / "registers" / reg.QUEUE, queued)
        with self.assertRaisesRegex(ValueError, "Queue row changed"):
            cli.install_many(self.root, self.base, [op], self.engine)

    def test_explicit_title_confirmation_requires_reference_and_stays_pending(self):
        import queue_corrections as queue

        request, record = self.queue_fixture()
        title = TITLE + " and maintenance"
        request.update(
            changes={"citation": f"Agency (2024). {title}."}, confirm_title_change=True
        )
        with self.assertRaisesRegex(ValueError, "identity reference"):
            queue.build(self.root, request)
        request["identity_reference"] = "https://publisher.example/manual"
        with patch(
            "identity._crossref", return_value=("ok", record | {"title": [title]})
        ):
            op = queue.build(self.root, request)
        cli.install_many(self.root, self.base, [op], self.engine)
        self.replay()
        repaired = index(reg.records(self.root, reg.QUEUE), "source_id")[SID]
        self.assertEqual(
            (repaired["status"], repaired["title_verified"]), ("pending", "")
        )

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

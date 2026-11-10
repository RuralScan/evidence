import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import review_lesson as lesson


class ReviewLessonTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.sheet = Path(self.directory.name) / "answers.json"
        self.reference = Path(__file__).with_name("review-answers.json")
        self.answers = json.loads(self.reference.read_text())

    def read(self):
        self.sheet.write_text(json.dumps(self.answers), encoding="utf-8")
        return lesson.read_answers(self.sheet)

    def test_operator_notes_and_alternate_order_are_accepted(self):
        self.answers["votes"].reverse()
        self.answers["votes"][2]["note"] = (
            "General siting observation without a cutoff."
        )
        self.assertEqual(self.read(), self.answers["votes"])

    def test_wrong_decision_or_extra_species_fields_are_refused(self):
        self.answers["votes"][2]["decision"] = "drop"
        with self.assertRaisesRegex(ValueError, "species-specific reclassification"):
            self.read()
        self.answers["votes"][2]["decision"] = "reclassify"
        self.answers["votes"][0]["taxon"] = lesson.TAXON
        with self.assertRaisesRegex(ValueError, "check fields"):
            self.read()

    def test_repeated_fields_records_and_malformed_notes_are_refused(self):
        self.sheet.write_text('{"votes":[],"votes":[]}')
        with self.assertRaisesRegex(ValueError, "Repeated field"):
            lesson.read_answers(self.sheet)
        first, second, _ = self.answers["votes"]
        second["evidence_id"] = first["evidence_id"]
        with self.assertRaisesRegex(ValueError, "Duplicate vote"):
            self.read()
        second["evidence_id"] = lesson.SITE_ONLY
        for note in ("  ", False, None, {"text": "Looks fine"}):
            with self.subTest(note=note):
                first["note"] = note
                with self.assertRaisesRegex(ValueError, "written reason"):
                    self.read()

    def test_reply_cannot_approve_a_record_or_append_a_review_decision(self):
        paths = SimpleNamespace(
            evidence=self.sheet, review_log=self.sheet.with_suffix(".csv")
        )
        snapshot = b"reviewer_ok\nfalse\n"
        log = b"decision\nquery\n"
        paths.evidence.write_bytes(snapshot)
        paths.review_log.write_bytes(log)
        lesson.check_reply_preserved_review(paths, snapshot, log)
        for name, value in (
            ("evidence", b"reviewer_ok\ntrue\n"),
            ("review_log", log + b"ok\n"),
        ):
            getattr(paths, name).write_bytes(value)
            with self.subTest(file=name), self.assertRaisesRegex(ValueError, "changed"):
                lesson.check_reply_preserved_review(paths, snapshot, log)
            paths.evidence.write_bytes(snapshot)
            paths.review_log.write_bytes(log)

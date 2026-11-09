import json
from io import BytesIO
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import pymupdf

import identity


TITLE = "Terraced catchments and infiltration in upland watersheds"
DOI = "10.1234/terrace.1"
CANDIDATE = {
    "citation": f"Source (2001). {TITLE}. Journal of Agricultural Methods.",
    "doi": DOI,
}
RECORD = {
    "DOI": DOI.upper(),
    "title": [TITLE],
    "author": [{"family": "Example"}],
    "issued": {"date-parts": [[2000]]},
    "container-title": ["Water"],
}


def pdf(*pages):
    with pymupdf.open() as doc:
        for content in pages:
            page = doc.new_page()
            page.insert_text((50, 50), content)
        return doc.tobytes()


class MetadataTests(unittest.TestCase):
    def lookup(self, candidate=CANDIDATE, record=RECORD):
        response = BytesIO(json.dumps({"message": record}).encode())
        with patch.object(identity, "urlopen", return_value=response):
            return identity.verify_metadata(candidate)

    def test_verified_citation_round_trip(self):
        candidate = dict(CANDIDATE, doi="https://doi.org/" + DOI.upper())
        result = self.lookup(candidate)
        self.assertEqual((result["status"], result["doi"]), ("doi_verified", DOI))
        self.assertEqual(result["citation"], f"Example (2000). {TITLE}. Water.")
        self.assertTrue(candidate["citation"].startswith("Source"))

    def test_no_doi_requires_artifact(self):
        with patch.object(identity, "urlopen", side_effect=AssertionError):
            result = identity.verify_metadata(dict(CANDIDATE, doi=""))
        self.assertEqual((result["status"], result["title"]), ("title_required", TITLE))

    def test_different_title_in_citation_venue_isnt_matching_title(self):
        candidate = {"doi": DOI, "citation": "Example (2020). Elm trees. " + TITLE}
        result = self.lookup(candidate)
        self.assertEqual((result["status"], result["doi"]), ("doi_rejected", ""))
        self.assertEqual(result["submitted_doi"], DOI)
        self.assertEqual(
            self.lookup(record=dict(RECORD, DOI="10.1234/other"))["status"],
            "doi_rejected",
        )

    def test_definitive_absence_differs_from_outage(self):
        for code, expected in [
            (404, "doi_rejected"),
            (429, "service_unavailable"),
            (503, "service_unavailable"),
        ]:
            with (
                self.subTest(code=code),
                patch.object(identity, "time"),
                patch.object(
                    identity,
                    "urlopen",
                    side_effect=HTTPError("https://example.org/", code, "", {}, None),
                ),
            ):
                result = identity.verify_metadata(CANDIDATE)
                self.assertEqual(result["status"], expected)
                self.assertEqual(result["doi"], "" if code == 404 else DOI)

    def test_legacy_title_fallback_and_structured_subtitle(self):
        self.assertEqual(identity.citation_title(CANDIDATE["citation"]), TITLE)
        self.assertEqual(
            identity.citation_title("Example (2010). Hills. Part II. Water."),
            "Hills. Part II",
        )
        full = "Water harvesting. Techniques in dryland catchments"
        candidate = {
            "citation": "Example (2020). Water harvesting. Techniques in dryland catchments. Journal.",
            "title": full,
            "doi": DOI,
        }
        result = self.lookup(
            candidate,
            dict(
                RECORD,
                title=["Water harvesting"],
                subtitle=["Techniques in dryland catchments"],
            ),
        )
        self.assertEqual(result["status"], "doi_verified")
        self.assertEqual(
            result["title"], "Water harvesting: Techniques in dryland catchments"
        )
        self.assertEqual(
            identity.verify_metadata(dict(candidate, doi=""))["title"], full
        )

    def test_weak_short_titles_and_distinct_parts_do_not_identify_doi(self):
        for requested, returned in [
            ("Water pollution in tropical estuaries", "Water harvesting"),
            ("Water harvesting", "Water harvesting in bench terracing"),
            (TITLE + " Part II", TITLE + " Part I"),
            (TITLE + " Part II", TITLE),
        ]:
            with self.subTest(requested=requested, returned=returned):
                result = self.lookup(
                    dict(CANDIDATE, title=requested), dict(RECORD, title=[returned])
                )
                self.assertEqual(result["status"], "doi_rejected")

    def test_offline_recheck_uses_bibliographic_facts(self):
        source = dict(
            RECORD,
            author=[{"family": "Example", "affiliation": [{"name": "Not saved"}]}],
            license=[{"unused": "Not saved"}],
        )
        original = self.lookup(record=source)
        with patch.object(identity, "urlopen", side_effect=AssertionError):
            self.assertEqual(identity.replay_metadata(CANDIDATE, original), original)
            self.assertNotIn("Not saved", json.dumps(original["crossref"]))
            fake = dict(original, citation="Different author")
            self.assertNotEqual(identity.replay_metadata(CANDIDATE, fake), fake)
            candidate = dict(CANDIDATE, doi="")
            no_doi = identity.verify_metadata(candidate)
            self.assertNotIn("crossref", no_doi)
            self.assertEqual(identity.replay_metadata(candidate, no_doi), no_doi)
            with self.assertRaisesRegex(ValueError, "lookup facts missing"):
                identity.replay_metadata(CANDIDATE, {})

    def test_offline_recheck_reproduces_holds(self):
        for outcome, record in [
            ("ok", dict(RECORD, title=["Different publication"])),
            ("unavailable", {}),
            ("missing", {}),
            ("ok", {}),
        ]:
            saved = identity.verify_metadata(
                CANDIDATE, lookup=lambda doi: (outcome, record)
            )
            with patch.object(identity, "urlopen", side_effect=AssertionError):
                self.assertEqual(identity.replay_metadata(CANDIDATE, saved), saved)

    def test_incomplete_response_retriable(self):
        self.assertEqual(self.lookup(record={})["status"], "service_unavailable")
        self.assertEqual(
            self.lookup(record=dict(RECORD, author=5))["status"], "service_unavailable"
        )


class DocumentTests(unittest.TestCase):
    def check(self, data, kind="pdf", title=TITLE):
        return identity.verify_document(data, kind, title)

    def test_pdf_title_in_opening_pages(self):
        result = self.check(pdf("Front matter", "Water catchments", TITLE))
        self.assertTrue(result["verified"])
        self.assertEqual(result["pages"], 3)
        self.assertTrue(
            self.check(
                pdf("Guidelines to Good Practice\nWater Harvesting"),
                title="Water harvesting: guidelines to good practice",
            )["verified"]
        )

    def test_reference_only_and_body_only_fail(self):
        for source in (
            pdf("Wrong source\nReferences\nSmith (1978). " + TITLE),
            pdf("Wrong source", "Smith (1978). " + TITLE),
            pdf("Cover", "Second", "Third", TITLE),
            pdf("Building seawalls in estuaries"),
        ):
            self.assertFalse(self.check(source)["verified"])

    def test_parts_bind_to_matching_pdf_only(self):
        title = TITLE + " Part II"
        self.assertTrue(self.check(pdf(title), title=title)["verified"])
        for variant in (TITLE, TITLE + " Part I", TITLE + " Part III"):
            self.assertFalse(self.check(pdf(variant), title=title)["verified"])

    def test_scans_and_wrong_format_are_held(self):
        self.assertTrue(self.check(pdf(""))["needs_ocr"])
        for data in (b"", b"<html>Access denied</html>", pdf(""), pdf(TITLE)[:-40]):
            self.assertFalse(self.check(data)["verified"])

    def test_web_title_or_first_heading(self):
        self.assertTrue(
            self.check(f"<title>{TITLE}</title>".encode(), "website")["verified"]
        )
        self.assertTrue(
            self.check(f"<h1><b>{TITLE}</b></h1>".encode(), "website")["verified"]
        )
        self.assertFalse(
            self.check(f"<title>Library</title><p>{TITLE}</p>".encode(), "website")[
                "verified"
            ]
        )
        self.assertFalse(
            self.check(f"<h1>Index</h1><h1>{TITLE}</h1>".encode(), "website")[
                "verified"
            ]
        )

    def test_search_result_heading_is_not_source_title(self):
        for heading, expected in [
            (f"Search results for {TITLE}", False),
            (TITLE + " | Repository", True),
        ]:
            self.assertEqual(
                self.check(f"<title>{heading}</title>".encode(), "website")["verified"],
                expected,
            )

    def test_plain_and_markdown_require_opening_title(self):
        self.assertTrue(self.check(("# " + TITLE).encode(), "markdown")["verified"])
        self.assertTrue(self.check(TITLE.encode(), "text")["verified"])
        self.assertFalse(
            self.check(("Other title\n" + TITLE).encode(), "text")["verified"]
        )
        self.assertFalse(
            self.check(("Library\n## References\n" + TITLE).encode(), "markdown")[
                "verified"
            ]
        )


if __name__ == "__main__":
    unittest.main()

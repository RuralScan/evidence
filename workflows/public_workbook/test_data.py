"""Regressions for public evidence lineage, source identity and disclosure."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

WORKFLOWS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(WORKFLOWS), str(WORKFLOWS / "recipe_release")]
from public_workbook import data  # noqa: E402


class ProjectionTest(unittest.TestCase):
    def test_context_profile_references_and_claims_are_kept_distinct(self):
        row = {
            "evidence_ids": ["ev_a"],
            "justification": {"key_evidence_ids": ["ev_a"]},
            "profiles": [{"source_id": "src", "evidence_id": "ev_b"}],
        }
        evidence, sources = set(), set()
        data.nested_references(row, evidence, sources)
        self.assertEqual(evidence - set(row["evidence_ids"]), {"ev_b"})
        self.assertEqual(sources, {"src"})
        with self.assertRaisesRegex(ValueError, "Expected a list"):
            data.nested_references({"evidence_ids": "ev_b"}, set(), set())

    def test_dropped_and_private_fields_excluded_and_source_verified(self):
        row = {
            "evidence_id": "ev_a",
            "source_id": "source",
            "nbs_id": "practice",
            "use_role": "operational_risk",
            "locator_type": "page",
            "page": 3,
            "quote": "A source excerpt",
            "attribution": "Internal notes",
        }
        removed = dict(row, evidence_id="ev_drop", review_state="dropped")
        with patch.object(
            data, "register", return_value=([removed, row], {"ev_a": "url"})
        ):
            result = data.claims(None, "commit", {"source"})
            self.assertEqual([r["id"] for r in result], ["ev_a"])
            self.assertEqual(result[0]["page"], 3)
            self.assertNotIn("quote", result[0])
            self.assertNotIn("attribution", result[0])
            with self.assertRaisesRegex(ValueError, "Unknown source"):
                data.claims(None, "commit", set())

    def test_doi_requires_matching_source_id_and_verified_queue_doi(self):
        row = {
            "source_id": "src",
            "citation": "Title",
            "doi": "10.1234/example",
            "source_kind": "paper",
            "source_category": "updated_lit",
            "library_path": "/private/copy.pdf",
        }
        with patch.object(data, "register", return_value=([row], {"src": "record"})):
            for dois, expected in [
                ({"src": "10.1234/example"}, "https://doi.org/10.1234/example"),
                ({"another": "10.1234/example"}, None),
                ({"src": "10.1234/different"}, None),
            ]:
                with (
                    self.subTest(dois=dois),
                    patch.object(data, "publication_links", return_value=(dois, {})),
                ):
                    result = data.bibliography(None, "commit")[0]
                    self.assertEqual(result["publication_url"], expected)
                    self.assertNotIn("library_path", result)

    def test_publisher_document_requires_curated_route_and_title_verification(self):
        source_id = "example"
        url = "https://wocat.net/documents/85/example.pdf"
        row = {
            "source_id": source_id,
            "url": url,
            "citation": "Manual",
            "source_kind": "paper",
            "source_category": "grey",
        }
        header = "source_id,url,doi,doi_verified,title_verified\n"
        for registered, queued, verified, expected in [
            (url, url, "true", url),
            (url, url, "false", None),
            (url, url + "?token=private", "true", None),
            ("https://private.example/copy", url, "true", None),
            (
                "https://private.example/copy",
                "https://private.example/copy",
                "true",
                None,
            ),
        ]:
            queue = header + f"{source_id},{queued},,,{verified}\n"
            with (
                self.subTest(registered=registered, queued=queued, verified=verified),
                patch.object(data, "git", return_value=queue.encode()),
                patch.object(
                    data,
                    "register",
                    return_value=([dict(row, url=registered)], {source_id: "record"}),
                ),
            ):
                result = data.bibliography(None, "commit")[0]
                self.assertEqual(result["publisher_url"], expected)
                self.assertIsNone(result["publication_url"])

    def test_partial_and_shared_search_counts_survive_projection(self):
        row = {
            "search_id": "search",
            "nbs_id": "practice",
            "category": "grey",
            "table": "T3",
            "n_screened": "64 shared",
            "n_included": 0,
            "searched_by": "Internal reviewer",
        }
        with patch.object(data, "register", return_value=([row], {"search": "url"})):
            result = data.searches(None, "commit")[0]
        self.assertIsNone(result["retrieved"])
        self.assertEqual(result["screened"], "64 shared")
        self.assertEqual(result["included"], 0)
        self.assertNotIn("searched_by", result)

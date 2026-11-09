import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import capture


def response(payload):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


class CaptureTests(unittest.TestCase):
    def test_openalex_title_query_and_capture(self):
        work = {
            "id": "https://openalex.org/W1234",
            "publication_year": 2023,
            "title": "Soil Érosion",
            "authorships": [{"author": {"display_name": "Example Author"}}],
            "primary_location": {"source": {"display_name": "Example Journal"}},
            "doi": "https://doi.org/10.1234/example",
            "language": "fr",
            "open_access": {"is_oa": True},
            "type": "article",
            "abstract_inverted_index": {"érosion": [0, 2], "et": [1]},
        }
        payload = {"meta": {"count": 123000}, "results": [work]}
        with (
            patch.dict(os.environ, {"OPENALEX_API_KEY": "secret"}),
            patch.object(capture, "urlopen", return_value=response(payload)) as network,
        ):
            got = capture.capture("openalex", '"soil erosion"', 20)
        request = network.call_args.args[0]
        self.assertEqual(
            parse_qs(urlsplit(request.full_url).query),
            {"search.title": ['"soil erosion"'], "per_page": ["20"]},
        )
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertNotIn("secret", request.full_url + json.dumps(got))
        self.assertEqual(got["query"], '"soil erosion"')
        self.assertEqual(got["channel"], "OpenAlex")
        self.assertRegex(got["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertIn("at most 20", got["limits"])
        self.assertEqual(
            got["records"],
            [
                {
                    "record_id": "openalex_w1234",
                    "title": "Soil Érosion",
                    "citation": "Example Author (2023). Soil Érosion. Example Journal.",
                    "url": work["id"],
                    "doi": "10.1234/example",
                    "language": "fr",
                    "oa_status": "oa",
                    "method_subtype": "article",
                    "report_number_or_handle": "openalex:W1234",
                    "abstract": "érosion et érosion",
                }
            ],
        )

    def test_lens_query_and_records(self):
        work = {
            "lens_id": "100-004-910-081-14X",
            "title": "Study",
            "abstract": "Study abstract.",
            "authors": [
                {"first_name": "First", "last_name": "Last"},
                {"collective_name": "Group"},
            ],
            "year_published": 2018,
            "languages": ["es"],
            "open_access": {"colour": "green"},
            "publication_type": "report",
            "external_ids": [{"type": "doi", "value": "10.1234/abc"}],
        }
        with (
            patch.dict(os.environ, {"LENS_TOKEN": "abcd"}),
            patch.object(
                capture,
                "urlopen",
                return_value=response({"total": 700, "data": [work]}),
            ) as network,
        ):
            got = capture.capture("lens", "title:terrazas", 5)
        request = network.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer abcd")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            json.loads(request.data)["query"]["query_string"],
            {"query": "title:terrazas", "default_operator": "AND"},
        )
        self.assertEqual(json.loads(request.data)["size"], 5)
        self.assertEqual(
            got["records"],
            [
                {
                    "record_id": "lens_10000491008114x",
                    "title": "Study",
                    "citation": "First Last, Group (2018). Study.",
                    "url": "https://doi.org/10.1234/abc",
                    "doi": "10.1234/abc",
                    "language": "es",
                    "oa_status": "oa",
                    "method_subtype": "report",
                    "report_number_or_handle": "lens:100-004-910-081-14X",
                    "abstract": "Study abstract.",
                }
            ],
        )

    def test_missing_title_remains_inspectable(self):
        for provider, payload in [
            ("lens", {"data": [{"lens_id": "100-004-910-081-14X"}]}),
            (
                "openalex",
                {
                    "results": [
                        {
                            "id": "https://openalex.org/W42",
                            "display_name": "Metadata only",
                            "title": None,
                        }
                    ]
                },
            ),
        ]:
            with (
                self.subTest(provider=provider),
                patch.dict(os.environ, {"LENS_TOKEN": "key"}),
                patch.object(
                    capture,
                    "urlopen",
                    return_value=response(payload),
                ),
            ):
                (row,) = capture.capture(provider, "query", 2)["records"]
                self.assertTrue(row["url"])
                self.assertEqual(row["oa_status"], "unknown")
                self.assertEqual(
                    (row["title"], row["citation"], row["doi"]), ("", "", "")
                )

    def test_year_filters_and_review_terms_are_sent_and_logged(self):
        with patch.object(
            capture, "urlopen", return_value=response({"results": []})
        ) as network:
            got = capture.capture("openalex", "bench terraces", 2, year_from=2015)
        params = parse_qs(urlsplit(network.call_args.args[0].full_url).query)
        self.assertEqual(params["filter"], ["from_publication_date:2015-01-01"])
        self.assertEqual(params["search.title"], [got["query"]])
        self.assertIn("2015 onwards (inclusive)", got["limits"])

        with (
            patch.dict(os.environ, {"LENS_TOKEN": "key"}),
            patch.object(
                capture, "urlopen", return_value=response({"data": []})
            ) as network,
        ):
            got = capture.capture(
                "lens", "title:terraces", 2, year_from=2015, reviews=True
            )
        body = json.loads(network.call_args.args[0].data)
        self.assertIn("open_access", body["include"])
        self.assertEqual(
            body["query"]["bool"]["filter"],
            [{"range": {"year_published": {"gte": 2015}}}],
        )
        final_query = body["query"]["bool"]["must"][0]["query_string"]["query"]
        self.assertEqual(final_query, got["query"])
        self.assertEqual(
            final_query,
            '(title:terraces) AND ("systematic review" OR "systematically review*" OR "systematic evidence map*" '
            'OR "systematic literature review" OR "systematic map" OR "systematically map*" OR "scoping review" '
            'OR "evidence and gap map*" OR "evidence synthesis" OR "umbrella review" OR "review of review*" OR "overview of review*")',
        )
        self.assertIn("2015 onwards (inclusive)", got["limits"])

    def test_unsupported_options_refused_before_search(self):
        with patch.object(capture, "urlopen") as network:
            with self.assertRaisesRegex(ValueError, "--reviews"):
                capture.capture("openalex", "study", 3, reviews=True)
            with self.assertRaisesRegex(ValueError, "--year-from"):
                capture.capture("lens", "study", 3, year_from=12)
            network.assert_not_called()

    def test_empty_search_vs_malformed_response(self):
        for payload in [
            None,
            {},
            {"results": None},
            {"results": {}},
            {"results": [{}]},
            {"results": [None] * 2},
        ]:
            with (
                self.subTest(payload=payload),
                patch.object(capture, "urlopen", return_value=response(payload)),
            ):
                with self.assertRaises(ValueError):
                    capture.capture("openalex", "something", 1)
        with patch.object(capture, "urlopen", return_value=response({"results": []})):
            self.assertEqual(capture.capture("openalex", "something", 1)["records"], [])

    def test_failures_leave_no_files_or_credentials(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.dict(os.environ, {"LENS_TOKEN": ""}),
        ):
            path = Path(tmp) / "snapshot.json"
            with (
                patch.object(capture, "urlopen") as network,
                redirect_stderr(io.StringIO()) as logged,
            ):
                with self.assertRaises(SystemExit):
                    capture.main(["lens", "lookup", "--limit", "3", "--out", str(path)])
                self.assertIn("LENS_TOKEN", logged.getvalue())
                network.assert_not_called()
            error = HTTPError(
                "https://example.org/?api_key=secret", 429, "secret", {}, None
            )
            with (
                patch.object(capture, "urlopen", side_effect=error),
                redirect_stderr(io.StringIO()) as logged,
            ):
                with self.assertRaises(SystemExit):
                    capture.main(
                        ["openalex", "lookup", "--limit", "3", "--out", str(path)]
                    )
                self.assertIn("HTTP 429", logged.getvalue())
                self.assertNotIn("secret", logged.getvalue())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_save_new_is_complete_and_preserves_previous_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "snapshot.json"
            capture.save_new(path, {"records": ["original"]})
            with self.assertRaises(FileExistsError):
                capture.save_new(path, {"records": ["changed"]})
            with self.assertRaises(TypeError):
                capture.save_new(path.with_suffix(".bad"), {"records": [object()]})
            self.assertEqual(json.loads(path.read_text()), {"records": ["original"]})
            self.assertEqual(list(Path(tmp).iterdir()), [path])


if __name__ == "__main__":
    unittest.main()

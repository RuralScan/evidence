import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

import retrieval

URL = "https://publisher.example/paper"
DOI = "10.9999/test"
SHA = "a" * 40


def response(data, mime, url=URL, status=200, headers=None):
    result = io.BytesIO(data)
    result.status = status
    result.headers = {"Content-Type": mime, **(headers or {})}
    result.geturl = lambda: url
    return result


class RetrievalTests(unittest.TestCase):
    def test_download_and_mime(self):
        pdf = b"%PDF-1.4\nexample"
        with patch.object(retrieval, "build_opener") as openers:
            opener = openers.return_value
            opener.open.return_value = response(pdf, "APPLICATION/PDF; arbitrary=1")
            result = retrieval.fetch(URL, "pdf", publisher_hosts=["PUBLISHER.example"])
        self.assertEqual(result, (pdf, URL, "application/pdf"))
        self.assertEqual(
            opener.open.call_args.kwargs["timeout"], retrieval.TIMEOUT_SECONDS
        )

    def test_rejects_impostors_and_incomplete_responses(self):
        cases = [
            ("pdf", b"<html>sign in</html>", "application/pdf", 200, {}),
            ("pdf", b"%PDF-1.4", "text/html", 200, {}),
            ("pdf", b"", "application/pdf", 200, {}),
            ("pdf", b"%PDF-1.4", "application/pdf", 206, {}),
            ("pdf", b"%PDF-", "application/pdf", 200, {"Content-Length": "90"}),
            ("pdf", b"%PDF-", "application/pdf", 200, {"Content-Length": "-4"}),
            (
                "markdown",
                b"\xef\xbb\xbf  <!DOCTYPE html><title>No copy</title>",
                "text/plain",
                200,
                {},
            ),
            ("code", b"binary", "image/png", 200, {}),
            ("text", b"\xff\x00\xff", "text/plain", 200, {}),
            ("website", b"%PDF-no", "text/html", 200, {}),
        ]
        for kind, data, content_type, status, headers in cases:
            with (
                self.subTest(kind=kind, status=status, mime=content_type),
                patch.object(retrieval, "build_opener") as op,
            ):
                op.return_value.open.return_value = response(
                    data, content_type, status=status, headers=headers
                )
                with self.assertRaises(ValueError):
                    retrieval.fetch(URL, kind)

    def test_body_limit_and_no_redirect_credential_leak(self):
        with (
            patch.object(retrieval, "build_opener") as op,
            patch.object(retrieval, "MAX_ARTIFACT_BYTES", 8),
        ):
            op.return_value.open.return_value = response(b"123456789", "text/plain")
            with self.assertRaisesRegex(ValueError, "exceeds"):
                retrieval.fetch(URL, "text")
        checked = retrieval._CheckedRedirect({"publisher.example"})
        redirected = checked.redirect_request(
            Request(URL), None, 302, "", {}, URL + "/file"
        )
        self.assertEqual(redirected.full_url, URL + "/file")
        for new in (
            "https://publisher.example.attacker.example/path",
            "ftp://publisher.example/file",
            "https://publisher.example@untrusted.example/paper?token=private",
        ):
            with self.subTest(destination=new), self.assertRaises(ValueError) as exc:
                checked.redirect_request(Request(URL), None, 302, "", {}, new)
            self.assertNotIn("private", str(exc.exception))

    def test_host_and_format_validation_precede_network(self):
        with patch.object(retrieval, "build_opener") as op:
            for args in (
                ("file:///example", "pdf"),
                ("https://guest:secret@publisher.example/paper", "pdf"),
                ("https://publisher.example.other.example", "pdf"),
                (URL, "xlsx"),
            ):
                with self.subTest(args=args), self.assertRaises(ValueError):
                    retrieval.fetch(*args, publisher_hosts=["publisher.example"])
            op.assert_not_called()

    def test_transport_diagnostics_do_not_include_signed_queries(self):
        signed = URL + "?access_token=secret"
        for failure in [
            URLError("connection to " + signed),
            HTTPError(signed, 429, "secret", {}, None),
        ]:
            with (
                self.subTest(failure=type(failure).__name__),
                patch.object(retrieval, "build_opener") as op,
            ):
                op.return_value.open.side_effect = failure
                with self.assertRaises(ValueError) as err:
                    retrieval.fetch(signed, "pdf")
                self.assertNotIn("secret", str(err.exception))

    def test_only_immutable_github_file_matches_pin(self):
        raw = f"https://raw.githubusercontent.com/a/b/{SHA}/src/site%20weights.py"
        self.assertTrue(retrieval.pinned_code_url(raw, SHA))
        for bad in (
            raw.replace(SHA, "main"),
            raw.replace("/src/", "/../"),
            raw + "?token=foo",
            raw.replace("a/b/", "a/b/%2e%2e/"),
            raw.replace("/src/", "/%2e%2e/"),
            raw.replace("githubusercontent.com", "githubusercontent.com.example"),
            raw.replace("https", "http"),
            raw.replace("/src/site%20weights.py", "/"),
        ):
            with self.subTest(url=bad):
                self.assertFalse(retrieval.pinned_code_url(bad, SHA))
        self.assertFalse(retrieval.pinned_code_url(raw, SHA[:7]))

    def test_screened_github_file_tree_repository_and_revision(self):
        target = f"https://raw.githubusercontent.com/Org/Repo/{SHA}/src/maps/file.py"
        base = "https://github.com/org/repo"
        for locator in (
            base,
            base + ".git",
            base + f"/tree/{SHA}",
            base + "/tree/main/src",
            base + "/tree/master/src/maps/",
            base + f"/blob/{SHA}/src/maps/file.py#L12",
            base + "/blob/main/src/maps/file.py?plain=1",
            target,
            target.replace(SHA, "main"),
        ):
            with self.subTest(locator=locator):
                self.assertTrue(retrieval.screened_code_url(locator, target, SHA))
        for locator in (
            base + "/issues/12",
            base + "/releases",
            base + "/pull/1/files",
            base + "/tree/main/src/map",
            base + "/tree/main/other",
            base + "/blob/main/src/maps/other.py",
            base + f"/blob/{'b' * 40}/src/maps/file.py",
            base + f"/tree/{'b' * 40}/src",
            target.replace("file.py", "other.py"),
            target.replace(SHA, "b" * 40),
            base + "/tree/feature/nested",
            base + "/blob/trunk/src/maps/file.py",
            base + f"/blob/{SHA[:7]}/src/maps/file.py",
            base + "/tree/main/../src",
            base + "?ref=other",
            base + "/blob/refs/heads/experimental/file.py",
            base.replace("org", "different"),
            target.replace("Repo", "Else"),
            target.replace("src/maps/", ""),
        ):
            with self.subTest(locator=locator):
                self.assertFalse(retrieval.screened_code_url(locator, target, SHA))

    def test_public_url_preserves_locators_but_removes_secrets(self):
        public = URL + "?id=article%2F99&page=2#L12-L20"
        self.assertEqual(retrieval.public_url(public), public)
        self.assertEqual(retrieval.public_url(URL + "#page=4"), URL + "#page=4")
        for key in (
            "X-Amz-Signature",
            "X-Goog-Credential",
            "sig",
            "token",
            "api_key",
            "access_token",
            "oauth",
            "code",
            "Key-Pair-Id",
            "client_secret",
            "code_verifier",
            "subscription-key",
            "auth%5Ftoken",
        ):
            with self.subTest(key=key):
                raw = URL + "?page=3&" + key + "=CONFIDENTIAL#section-2"
                self.assertEqual(
                    retrieval.public_url(raw),
                    URL + "?page=3&" + key + "=REDACTED#section-2",
                )
        self.assertEqual(
            retrieval.public_url(URL + "#/return?access_token=CONFIDENTIAL"),
            URL + "#REDACTED",
        )
        self.assertNotIn(
            "CONFIDENTIAL",
            retrieval.public_url(
                URL + "?redirect_uri=https%3A%2F%2Fa%2F%3Ftoken%3DCONFIDENTIAL"
            ),
        )
        self.assertNotIn(
            "CONFIDENTIAL",
            retrieval.public_url("https://user:CONFIDENTIAL@publisher.example/paper"),
        )
        self.assertEqual(
            retrieval.public_url(
                URL + "#a-long-public-description-of-annual-precipitation"
            ),
            URL + "#a-long-public-description-of-annual-precipitation",
        )

    def test_single_alternate_user_agent_for_403_and_406(self):
        for status in (403, 406):
            with (
                self.subTest(status=status),
                patch.object(retrieval, "build_opener") as op,
            ):
                network = op.return_value.open
                network.side_effect = [
                    HTTPError(URL, status, "", {}, None),
                    response(b"%PDF-1.4", "application/pdf"),
                ]
                self.assertEqual(retrieval.fetch(URL, "pdf")[0], b"%PDF-1.4")
                agents = [
                    call.args[0].get_header("User-agent")
                    for call in network.call_args_list
                ]
                self.assertEqual(agents, ["RuralScan-evidence/1.0", "curl/8.7.1"])
        with patch.object(retrieval, "build_opener") as op:
            op.return_value.open.side_effect = HTTPError(URL, 429, "", {}, None)
            with self.assertRaisesRegex(ValueError, "429"):
                retrieval.fetch(URL, "pdf")
            self.assertEqual(op.return_value.open.call_count, 1)
        with patch.object(retrieval, "build_opener") as op:
            op.return_value.open.side_effect = [
                HTTPError(URL, 403, "", {}, None),
                HTTPError(URL, 403, "", {}, None),
            ]
            with self.assertRaisesRegex(ValueError, "403"):
                retrieval.fetch(URL, "pdf")
            self.assertEqual(op.return_value.open.call_count, 2)

    def test_unpaywall_and_landing_candidates(self):
        pdf = URL + ".pdf"
        doi_landing = "https://doi.org/" + DOI
        payload = {
            "doi": DOI.upper(),
            "best_oa_location": {"url_for_pdf": pdf},
            "oa_locations": [{"url_for_pdf": pdf}],
        }
        landing = b'<meta content="../publication.pdf?format=1&amp;v=2" name="citation_pdf_url"><a href="other.pdf">other</a>'
        with patch.object(
            retrieval,
            "_read_url",
            side_effect=[
                (json.dumps(payload).encode(), "", "application/json"),
                (landing, URL + "/index", "text/html"),
            ],
        ) as lookup:
            routes, notes = retrieval.pdf_routes(
                doi_landing, DOI, contact="operator@example.org"
            )
        request_url = lookup.call_args_list[0].args[0]
        self.assertEqual(urlsplit(request_url).hostname, "api.unpaywall.org")
        self.assertEqual(
            parse_qs(urlsplit(request_url).query)["email"], ["operator@example.org"]
        )
        self.assertEqual(
            routes,
            [
                ("unpaywall", pdf),
                (
                    "landing_page",
                    "https://publisher.example/publication.pdf?format=1&v=2",
                ),
            ],
        )
        self.assertEqual(notes, [])

    def test_failed_lookup_and_successful_empty_lookup_are_distinct(self):
        original = URL + ".pdf"
        outcomes = [
            (ValueError("Source returned HTTP 429."), "incomplete"),
            ((b"{}", "", "application/json"), "missing DOI"),
            ((b"bad", "", "application/json"), "unreadable"),
            (
                (
                    json.dumps({"doi": DOI, "oa_locations": []}).encode(),
                    "",
                    "application/json",
                ),
                "no direct PDF",
            ),
        ]
        for outcome, expected in outcomes:
            with (
                self.subTest(expected=expected),
                patch.object(retrieval, "_read_url") as read,
            ):
                read.side_effect = [outcome, (b"<html></html>", URL, "text/html")]
                routes, notes = retrieval.pdf_routes(
                    original, DOI, contact="a@example.org"
                )
                self.assertEqual(routes, [("direct", original)])
                self.assertIn(expected, " ".join(notes))
                self.assertNotIn(
                    "paywall", " ".join(notes).replace("Unpaywall", "").lower()
                )
        with patch.object(
            retrieval, "_read_url", return_value=(b"<html></html>", URL, "text/html")
        ) as lookup:
            routes, notes = retrieval.pdf_routes(original, DOI)
            self.assertEqual(
                [c.args[0] for c in lookup.call_args_list], ["https://doi.org/" + DOI]
            )
            self.assertEqual(routes, [("direct", original)])
            self.assertIn("contact", notes[0])

    def test_recovery_checks_distinct_verified_doi_landing_and_deduplicates_links(self):
        resolver = "https://doi.org/" + DOI
        file = URL + "/full.pdf"
        last = (b'<a href="/paper/full.pdf">Download</a>', URL, "text/html")
        for first in [
            ValueError("Source returned HTTP 404."),
            (b"<html>No file</html>", URL, "text/html"),
            last,
        ]:
            with (
                self.subTest(first=first),
                patch.object(retrieval, "_read_url", side_effect=[first, last]) as read,
            ):
                routes, _ = retrieval.pdf_routes(URL, DOI)
                self.assertEqual(
                    [call.args[0] for call in read.call_args_list], [URL, resolver]
                )
                self.assertEqual(routes, [("direct", URL), ("landing_page", file)])

    def test_landing_links_bounded_and_relative(self):
        html = b"".join(
            f'<a href="/item{i}.pdf#page">file</a>'.encode() for i in range(6)
        )
        with patch.object(
            retrieval, "_read_url", return_value=(html, URL, "text/html")
        ):
            routes, notes = retrieval.pdf_routes(URL, "")
        self.assertEqual(routes[0], ("direct", URL))
        self.assertEqual(len(routes), 4)
        self.assertEqual(
            routes[-1], ("landing_page", "https://publisher.example/item2.pdf#page")
        )
        self.assertEqual(notes, [])


if __name__ == "__main__":
    unittest.main()

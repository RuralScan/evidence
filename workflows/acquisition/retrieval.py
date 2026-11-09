"""Fetch bounded source artifacts and find additional PDF routes after a failed attempt."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import (
    parse_qsl,
    quote,
    unquote,
    unquote_plus,
    urlencode,
    urljoin,
    urlsplit,
    urlunsplit,
)
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_ARTIFACT_BYTES = 100 * 1024 * 1024
MAX_LOOKUP_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 30
PDF_TYPES = {"application/pdf", "application/octet-stream", "binary/octet-stream"}
HTML_TYPES = {"text/html", "application/xhtml+xml"}
TEXT_TYPES = {"text/plain", "text/markdown", "text/x-markdown"}
HTML_START = re.compile(
    rb"^(?:<!doctype\s+html|<(?:html|head|body|title)(?:\s|>))", re.I
)


def _http_url(url, allowed_hosts=()):
    """Validate before HTTP I/O; echo neither user information nor signed queries."""
    if (
        not isinstance(url, str)
        or any(c.isspace() or ord(c) < 32 for c in url)
        or "\\" in url
    ):
        raise ValueError("Invalid HTTP source URL.")
    try:
        parts = urlsplit(url)
        hostname = parts.hostname
        _ = parts.port
    except ValueError:
        raise ValueError("Invalid HTTP source URL.") from None
    if (
        parts.scheme not in {"http", "https"}
        or not hostname
        or parts.username is not None
    ):
        raise ValueError("Use an absolute HTTP(S) source URL without credentials.")
    if allowed_hosts and hostname.lower().rstrip(".") not in allowed_hosts:
        raise ValueError("Source URL is outside the approved publisher hosts.")
    return parts


class _CheckedRedirect(HTTPRedirectHandler):
    def __init__(self, allowed_hosts):
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _http_url(newurl, self.allowed_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _HTTPStatus(ValueError):
    def __init__(self, status):
        self.status = status
        super().__init__(f"Source returned HTTP {status}.")


def _read_url(
    url, *, allowed_hosts=(), limit, accepted=None, user_agent="RuralScan-evidence/1.0"
):
    _http_url(url, allowed_hosts)
    try:
        opener = build_opener(_CheckedRedirect(allowed_hosts))
        request = Request(url, headers={"User-Agent": user_agent})
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            _http_url(final_url, allowed_hosts)
            if response.status != 200:
                raise _HTTPStatus(response.status)
            mime = (
                response.headers.get("Content-Type", "")
                .split(";", 1)[0]
                .strip()
                .lower()
            )
            if accepted is not None and mime not in accepted:
                raise ValueError(
                    "Response content type does not match requested format."
                )
            length = response.headers.get("Content-Length")
            if length is not None:
                if not re.fullmatch(r"[0-9]+", length) or len(length) > 16:
                    raise ValueError("Invalid response length.")
                if int(length) > limit:
                    raise ValueError("Response exceeds acquisition size limit.")
            data = response.read(limit + 1)
            if len(data) > limit:
                raise ValueError("Response exceeds acquisition size limit.")
            if length is not None and int(length) != len(data):
                raise ValueError("Incomplete HTTP response.")
            if not data:
                raise ValueError("Empty HTTP response.")
            return data, final_url, mime
    except HTTPError as exc:
        exc.close()
        raise _HTTPStatus(exc.code) from None
    except (HTTPException, URLError, OSError, UnicodeError):
        raise ValueError(
            "Source service unavailable or connection interrupted."
        ) from None


def fetch(url, kind, *, publisher_hosts=()):
    """Return artifact bytes, final URL and MIME type. Check redirects before following."""
    if kind not in {"pdf", "website", "markdown", "text", "code"}:
        raise ValueError("Unsupported acquisition format.")
    allowed_hosts = {host.lower().rstrip(".") for host in publisher_hosts}
    accepted = {
        "pdf": PDF_TYPES,
        "website": HTML_TYPES | {"text/plain"},
        "markdown": TEXT_TYPES,
        "text": TEXT_TYPES,
        "code": None,  # Raw hosts use several MIME types for source files.
    }[kind]
    options = dict(
        allowed_hosts=allowed_hosts, limit=MAX_ARTIFACT_BYTES, accepted=accepted
    )
    try:
        data, final_url, mime = _read_url(url, **options)
    except _HTTPStatus as exc:
        if exc.status not in {403, 406}:
            raise
        # Some public repositories serve their plain download route to curl.
        data, final_url, mime = _read_url(url, user_agent="curl/8.7.1", **options)
    if kind == "pdf":
        if not data.lstrip().startswith(b"%PDF-"):
            raise ValueError("PDF signature missing.")
    else:
        if kind == "code" and not (
            mime.startswith("text/")
            or mime
            in {
                "application/octet-stream",
                "application/json",
                "application/javascript",
            }
        ):
            raise ValueError("Response content type does not match text source code.")
        if not data.strip() or b"\0" in data or data.lstrip().startswith(b"%PDF-"):
            raise ValueError("Expected a nonempty text artifact.")
        if kind != "website" and (
            mime in HTML_TYPES or HTML_START.match(data.lstrip(b"\xef\xbb\xbf \t\r\n"))
        ):
            raise ValueError(
                "Received an HTML page instead of the requested text artifact."
            )
    return data, final_url, mime


def pinned_code_url(url, commit):
    """Accept an immutable GitHub raw-file URL whose revision matches the supplied SHA."""
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        return False
    try:
        parts = _http_url(url, {"raw.githubusercontent.com"})
    except ValueError:
        return False
    if (
        parts.scheme != "https"
        or parts.netloc.lower() != "raw.githubusercontent.com"
        or parts.query
        or parts.fragment
    ):
        return False
    pieces = parts.path.removeprefix("/").split("/")
    if len(pieces) < 4 or pieces[2].lower() != commit.lower():
        return False
    if not all(re.fullmatch(r"[A-Za-z0-9_.-]+", value) for value in pieces[:2]):
        return False
    for piece in pieces:
        name = unquote(piece)
        if (
            name in {"", ".", ".."}
            or "/" in name
            or "\\" in name
            or any(ord(c) < 32 for c in name)
        ):
            return False
    return True


def screened_code_url(candidate_url, artifact_url, commit):
    """Check that a raw file at commit lies within the screened GitHub locator."""
    if not pinned_code_url(artifact_url, commit):
        return False
    try:
        parts = _http_url(candidate_url)
    except ValueError:
        return False
    if parts.scheme != "https" or parts.netloc.lower() not in {
        "github.com",
        "raw.githubusercontent.com",
    }:
        return False
    if any(
        key not in {"plain", "raw"}
        for key, _ in parse_qsl(parts.query, keep_blank_values=True)
    ):
        return False
    target = [unquote(x) for x in urlsplit(artifact_url).path[1:].split("/")]
    scope = [
        unquote(x) for x in parts.path.removeprefix("/").removesuffix("/").split("/")
    ]
    if len(scope) < 2 or any(
        x in {"", ".", ".."} or "/" in x or "\\" in x for x in scope
    ):
        return False
    if (scope[0].lower(), scope[1].removesuffix(".git").lower()) != (
        target[0].lower(),
        target[1].lower(),
    ):
        return False
    if parts.netloc.lower() == "raw.githubusercontent.com":
        if len(scope) < 4:
            return False
        view, revision, path = "blob", scope[2], scope[3:]
    elif len(scope) == 2:
        return True
    elif len(scope) >= 4 and scope[2] in {"blob", "tree"}:
        view, revision, path = scope[2], scope[3], scope[4:]
    else:
        return False
    # A branch with slashes cannot be reliably separated from a path offline.
    # Use a full commit permalink for nonstandard or ambiguous refs.
    if (
        revision not in {"main", "master", "HEAD"}
        and revision.lower() != commit.lower()
    ):
        return False
    if view == "blob":
        return not parts.path.endswith("/") and path == target[3:]
    return len(target[3:]) > len(path) and target[3 : 3 + len(path)] == path


def _private_parameter(name):
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    return (
        key.startswith(("xamz", "xgoog", "xoss", "oauth"))
        or key.endswith("key")
        or any(
            part in key
            for part in (
                "token",
                "secret",
                "signature",
                "credential",
                "password",
                "apikey",
            )
        )
        or key
        in {
            "key",
            "keypairid",
            "sig",
            "auth",
            "authorization",
            "code",
            "jwt",
            "session",
            "sessionid",
            "ticket",
            "policy",
            "nonce",
            "state",
            "csrf",
            "codeverifier",
            "codechallenge",
            "authorizationcode",
            "authcode",
            "clientassertion",
            "googleaccessid",
            "awsaccesskeyid",
            "samlresponse",
            "email",
            "mailto",
        }
    )


def _private_value(value):
    if re.search(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", value):
        return True
    return any(
        _private_parameter(key)
        for key in re.findall(r"(?:^|[?&#;])([^?&#;=]+)=", value)
    )


def public_url(url):
    """Build a receipt locator without bearer credentials or signed query values."""
    try:
        parts = _http_url(url)
    except ValueError:
        return ""
    # Preserve spelling and encoding of public locators such as DOI and page IDs.
    query = re.split(r"([&;])", parts.query)
    for i in range(0, len(query), 2):
        key, equals, value = query[i].partition("=")
        if _private_parameter(unquote_plus(key)) or _private_value(unquote_plus(value)):
            query[i] = key + "=REDACTED" if equals else "REDACTED"
    fragment = parts.fragment
    decoded = unquote_plus(fragment)
    if _private_value(decoded) or re.fullmatch(
        r"(?=[A-Za-z0-9_+]*[0-9])[A-Za-z0-9_+]{40,}", decoded
    ):
        fragment = "REDACTED"
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, "".join(query), fragment)
    )


class _PDFLinks(HTMLParser):
    """Extract explicit publication metadata and at most three ordinary PDF links."""

    def __init__(self):
        super().__init__()
        self.citation_pdf = ""
        self.links = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta" and (values.get("name") or "").lower() == "citation_pdf_url":
            self.citation_pdf = self.citation_pdf or values.get("content") or ""
        if tag == "a" and len(self.links) < 3:
            href = values.get("href") or ""
            if re.search(r"\.pdf(?:$|[?#])", href, re.I) and href not in self.links:
                self.links.append(href)


def pdf_routes(url, doi, *, contact=None):
    """Find alternate PDF candidates. Caller supplies a verified DOI and checks each file."""
    routes = []
    seen = set()
    notes = []

    def add(label, target):
        try:
            _http_url(target)
        except ValueError:
            return
        if target not in seen:
            seen.add(target)
            routes.append((label, target))

    if url:
        parts = _http_url(url)
        if parts.hostname.lower() not in {"doi.org", "dx.doi.org"}:
            add("direct", url)

    if doi and contact:
        lookup = (
            "https://api.unpaywall.org/v2/"
            + quote(doi, safe="/")
            + "?"
            + urlencode({"email": contact})
        )
        try:
            data, _, _ = _read_url(
                lookup,
                allowed_hosts={"api.unpaywall.org"},
                limit=MAX_LOOKUP_BYTES,
                accepted={"application/json"},
            )
            payload = json.loads(data)
            if (
                not isinstance(payload, dict)
                or str(payload.get("doi", "")).casefold() != doi.casefold()
            ):
                raise ValueError("Unpaywall returned a different or missing DOI.")
            locations = payload.get("oa_locations")
            best = payload.get("best_oa_location")
            if not isinstance(locations, list) or not all(
                isinstance(loc, dict) for loc in locations
            ):
                raise ValueError("Unpaywall returned incomplete location metadata.")
            if best is not None and not isinstance(best, dict):
                raise ValueError("Unpaywall returned an invalid preferred location.")
            supplied_pdf = False
            for loc in ([best] if best else []) + locations:
                target = loc.get("url_for_pdf")
                if target:
                    _http_url(target)
                    supplied_pdf = True
                    add("unpaywall", target)
            if not supplied_pdf:
                notes.append("Unpaywall lists no direct PDF for this DOI.")
        except (UnicodeError, json.JSONDecodeError):
            notes.append("Unpaywall returned unreadable metadata.")
        except ValueError as exc:
            notes.append(f"Unpaywall lookup incomplete. {exc}")
    elif doi:
        notes.append("Unpaywall lookup requires an operator contact email.")

    resolver = "https://doi.org/" + quote(doi, safe="/") if doi else ""
    for landing in dict.fromkeys([url, resolver]):
        if not landing or (
            landing != resolver and urlsplit(landing).path.lower().endswith(".pdf")
        ):
            continue
        label = "DOI landing page" if landing == resolver else "Source landing page"
        try:
            data, final_url, _ = _read_url(
                landing, limit=MAX_LOOKUP_BYTES, accepted=HTML_TYPES
            )
            links = _PDFLinks()
            links.feed(data.decode("utf-8", errors="replace"))
            found = [links.citation_pdf] if links.citation_pdf else links.links
            for item in found:
                try:
                    add("landing_page", urljoin(final_url, item))
                except ValueError:
                    continue
            if not found:
                notes.append(f"{label} lists no direct PDF in the inspected links.")
        except ValueError as exc:
            notes.append(f"{label} lookup incomplete. {exc}")
        except AssertionError:
            notes.append(f"{label} contained malformed HTML.")
    return routes, notes

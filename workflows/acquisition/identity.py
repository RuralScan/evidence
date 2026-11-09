"""Verify a screened citation and bind acquired bytes to its title.

Title thresholds and citation rebuilding follow the CIAT source verification
rules. A Crossref result identifies bibliographic metadata. The artifact must
also pass its own document check.
"""

import json
import re
import time
import unicodedata
from html.parser import HTMLParser
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pymupdf

_STOP = set(
    "the and for with from into their which under across between within based using "
    "study effects impact assessment analysis review journal international climate change".split()
)
DOI_THRESHOLD = 0.5
TITLE_THRESHOLD = 0.8
_REFERENCES = re.compile(
    r"(?:^|\n)\s*(?:\d+\.?\s+)?(?:references|literature cited|bibliography|"
    r"références|referencias|bibliografía|referências)\s*[:.]?\s*(?=\n|$)",
    re.I,
)


def _tokens(value):
    return {w for w in re.findall(r"[a-z]+", value.lower()) if len(w) > 3} - _STOP


def _squash(value):
    return "".join(
        c for c in unicodedata.normalize("NFKC", value).casefold() if c.isalnum()
    )


def citation_title(citation):
    """Read the legacy Author (Year). Title. Venue. citation when no title field exists."""
    body = citation.partition("). ")[2] or citation
    title, _, remainder = body.partition(". ")
    if _SERIES.match(remainder):
        title += ". " + remainder.partition(". ")[0]
    return title.strip().rstrip(".")


_SERIES = re.compile(
    r"\b(part|volume|vol|chapter|book|edition)\.?\s+([0-9]+|[ivxlcdm]+)\b", re.I
)


def _series(value):
    return {
        (label.casefold().replace("volume", "vol"), number.casefold())
        for label, number in _SERIES.findall(value)
    }


def _bare_doi(value):
    return (
        re.sub(
            r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value.strip(), flags=re.I
        )
        .strip()
        .casefold()
    )


def _crossref(doi):
    request = Request(
        "https://api.crossref.org/works/" + quote(doi, safe=""),
        headers={"Accept": "application/json", "User-Agent": "RuralScan-evidence/1.0"},
    )
    for attempt in range(3):
        try:
            with urlopen(request, timeout=20) as response:
                envelope = json.load(response)
            if isinstance(envelope, dict) and isinstance(envelope.get("message"), dict):
                return "ok", envelope["message"]
            return "unavailable", {}
        except HTTPError as error:
            if error.code == 404:
                return "missing", {}
            if error.code not in {429, 500, 502, 503, 504}:
                return "unavailable", {}
        except (URLError, OSError, HTTPException, ValueError):
            pass
        if attempt < 2:
            time.sleep(2 * (attempt + 1))
    return "unavailable", {}


def _citation(record, title):
    names = [
        author.get("family") or author.get("name")
        for author in record.get("author") or []
        if isinstance(author, dict) and (author.get("family") or author.get("name"))
    ]
    authors = (names[0] if names else "") + (" et al." if len(names) > 1 else "")
    dates = (record.get("issued") or {}).get("date-parts") or [[]]
    year = dates[0][0] if dates[0] else ""
    venue = (record.get("container-title") or [""])[0]
    byline = f"{authors} ({year}). " if year else (authors + ". " if authors else "")
    return (
        byline + title.rstrip(".") + "." + (f" {venue.rstrip('.')}." if venue else "")
    ).strip()


def _crossref_facts(outcome, record):
    """Freeze only the bibliographic fields the identity check reads."""
    if outcome != "ok":
        return {"outcome": outcome}
    try:
        minimal = {"DOI": record["DOI"]}
        if not isinstance(minimal["DOI"], str) or not minimal["DOI"].strip():
            raise ValueError
        for key in ("title", "subtitle", "container-title"):
            values = record.get(key) or []
            if not isinstance(values, list) or (
                values and not isinstance(values[0], str)
            ):
                raise ValueError
            if values:
                minimal[key] = [values[0]]
        if not minimal.get("title") or not minimal["title"][0].strip():
            raise ValueError
        authors = record.get("author") or []
        if not isinstance(authors, list):
            raise ValueError
        names = []
        for author in authors:
            key = "family" if author.get("family") else "name"
            if author.get(key):
                if not isinstance(author[key], str):
                    raise ValueError
                names.append({key: author[key]})
        if names:
            minimal["author"] = names
        dates = (record.get("issued") or {}).get("date-parts") or [[]]
        if dates[0]:
            year = dates[0][0]
            if type(year) not in (str, int):
                raise ValueError
            minimal["issued"] = {"date-parts": [[year]]}
        return {"outcome": "ok", "record": minimal}
    except (TypeError, KeyError, ValueError, AttributeError, IndexError):
        return {"outcome": "unavailable"}


def replay_metadata(candidate, saved):
    """Reconstruct a verification result from its saved facts without network access."""

    def from_receipt(doi):
        facts = saved.get("crossref")
        if not isinstance(facts, dict) or facts.get("outcome") not in {
            "ok",
            "missing",
            "unavailable",
        }:
            raise ValueError(f"Crossref lookup facts missing for {doi}")
        return facts["outcome"], facts.get("record", {})

    return verify_metadata(candidate, lookup=from_receipt)


def verify_metadata(candidate, *, lookup=None):
    """Resolve the submitted DOI, preserving the title-bearing candidate on failure."""
    citation = candidate["citation"].strip()
    title = (candidate.get("title") or "").strip() or citation_title(citation)
    if not title:
        raise ValueError("A citation title is required for source verification")
    doi = _bare_doi(candidate.get("doi") or "")
    result = {"doi": doi, "submitted_doi": doi, "citation": citation, "title": title}
    if not doi:
        return {
            **result,
            "status": "title_required",
            "reason": "No DOI; verify the source title against the artifact.",
        }
    if not re.fullmatch(r"10\.\d{4,9}/\S+", doi):
        return {
            **result,
            "doi": "",
            "status": "doi_rejected",
            "reason": "Malformed DOI.",
        }
    outcome, record = (lookup or _crossref)(doi)
    facts = _crossref_facts(outcome, record)
    result["crossref"] = facts
    if facts["outcome"] == "missing":
        return {
            **result,
            "doi": "",
            "status": "doi_rejected",
            "reason": "Crossref returned 404.",
        }
    if facts["outcome"] != "ok":
        return {
            **result,
            "status": "service_unavailable",
            "reason": "Crossref returned no usable identity; retry.",
        }
    record = facts["record"]
    if _bare_doi(record["DOI"]) != doi:
        return {
            **result,
            "doi": "",
            "status": "doi_rejected",
            "reason": "Crossref returned a different DOI.",
        }
    authoritative = record["title"][0].strip()
    subtitles = record.get("subtitle") or []
    if isinstance(subtitles, list) and subtitles and isinstance(subtitles[0], str):
        subtitle = subtitles[0].strip()
        if subtitle and not _squash(authoritative).endswith(_squash(subtitle)):
            authoritative = authoritative.rstrip(": ") + ": " + subtitle
    received, screened = _tokens(authoritative), _tokens(title)
    exact = bool(_squash(title)) and _squash(authoritative) == _squash(title)
    overlap = (
        1.0
        if exact
        else len(received & screened) / max(len(received), len(screened), 1)
    )
    # Short titles and numbered series have few distinguishing words. A common
    # subject such as "water" cannot identify a DOI, and Part I cannot verify II.
    matches = exact or (
        len(received & screened) >= 3
        and min(len(received), len(screened)) >= 4
        and overlap >= DOI_THRESHOLD
        and _series(authoritative) == _series(title)
    )
    result.update(crossref_title=authoritative, title_overlap=round(overlap, 3))
    if not matches:
        return {
            **result,
            "doi": "",
            "status": "doi_rejected",
            "reason": "Crossref title differs from the screened citation title.",
        }
    try:
        corrected = _citation(record, authoritative)
    except (IndexError, TypeError, AttributeError, KeyError):
        return {
            **result,
            "status": "service_unavailable",
            "reason": "Crossref citation fields malformed; retry.",
        }
    return {
        **result,
        "citation": corrected,
        "title": authoritative,
        "status": "doi_verified",
        "reason": "Crossref DOI and citation title match.",
    }


def _title_matches(title, text):
    key = _squash(title)
    if not key or _series(title) != _series(text):
        return False
    squashed = _squash(text)
    if squashed == key:
        return True
    terms = _tokens(title)
    if len(terms) < 3:
        # A single shared word in an unrelated title is a poor identity anchor.
        return len(key) >= 20 and key in squashed
    return len(terms & _tokens(text)) / len(terms) >= TITLE_THRESHOLD or (
        len(key) >= 20 and key in squashed
    )


def _opening_match(title, pages):
    opening = "\n".join(pages)
    # A cited work inside an opening-page bibliography cannot identify the book.
    opening = _REFERENCES.split(opening, maxsplit=1)[0]
    lines = [line.strip() for line in opening.splitlines() if line.strip()]
    terms = _tokens(title)
    key = _squash(title)
    for i in range(len(lines)):
        # Bound the token comparison to a compact title-sized passage. A whole
        # introduction can contain all the same keywords without naming the paper.
        window = " ".join(lines[i : i + 3])
        if not _title_matches(title, window):
            continue
        normalized = _squash(window)
        start = normalized.find(key)
        if start == -1:
            # A title may be wrapped or its title/subtitle reordered on a cover.
            # Exclude citation-shaped entries even without a contiguous match.
            if re.search(r"\b(?:19|20)\d{2}[a-z]?\b", window[:100]) and terms:
                continue
        else:
            prefix = _squash(" ".join(lines[max(0, i - 1) : i])) + normalized[:start]
            if re.search(r"(?:19|20)\d{2}[a-z]?$", prefix[-16:]):
                continue
        return True
    return False


class _PageHeadings(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.headings = {}
        self.collecting = None

    def handle_starttag(self, tag, attrs):
        if (
            tag in {"title", "h1"}
            and tag not in self.headings
            and self.collecting is None
        ):
            self.headings[tag] = []
            self.collecting = tag

    def handle_endtag(self, tag):
        if self.collecting == tag:
            self.collecting = None

    def handle_data(self, data):
        if self.collecting:
            self.headings[self.collecting].append(data)


def _identifies_heading(title, heading):
    # Provider pages often append a site name after a separator. Names appearing
    # inside a search-result heading or a sentence do not identify the page.
    key = _squash(title)
    return bool(key) and (
        key == _squash(heading)
        or any(key == _squash(part) for part in re.split(r"\s+(?:[-–—|·])\s+", heading))
    )


def _text_headings(data, kind):
    text = data.decode("utf-8-sig")
    if kind in {"website", "html"}:
        parser = _PageHeadings()
        parser.feed(text)
        parser.close()
        return [" ".join(parts) for parts in parser.headings.values()]
    lines = text.strip().splitlines()
    if kind == "markdown":
        for i, line in enumerate(lines[:10]):
            if re.match(r"^\s{0,3}#\s+", line):
                return [line.strip().strip("#").strip()]
            if i and re.fullmatch(r"\s*=+\s*", line):
                return [lines[i - 1]]
        return []
    return lines[:1]


def verify_document(data: bytes, kind: str, title: str):
    """Check opening document identity. Metadata alone cannot pass this check."""
    if kind == "pdf":
        facts = {"pages": 0, "needs_ocr": False}
        if b"%PDF-" not in data[:1024] or b"%%EOF" not in data[-2048:]:
            return {
                **facts,
                "verified": False,
                "reason": "PDF signature or end marker missing.",
            }
        try:
            with pymupdf.open(stream=data, filetype="pdf") as document:
                facts["pages"] = len(document)
                if not facts["pages"] or document.needs_pass or document.is_repaired:
                    return {
                        **facts,
                        "verified": False,
                        "reason": "PDF is empty, encrypted or structurally damaged.",
                    }
                pages = [document[i].get_text() for i in range(min(len(document), 3))]
        except (OSError, RuntimeError, ValueError):
            return {**facts, "verified": False, "reason": "PDF could not be read."}
        facts["needs_ocr"] = len("".join(pages).strip()) < 200
        verified = _opening_match(title, pages)
        return {
            **facts,
            "verified": verified,
            "reason": "Opening PDF title matches."
            if verified
            else "Opening PDF title unconfirmed; inspect document identity.",
        }
    if kind not in {"website", "html", "markdown", "text"}:
        raise ValueError(f"Unsupported document identity format: {kind}")
    try:
        verified = any(
            _identifies_heading(title, heading)
            for heading in _text_headings(data, kind)
        )
    except (ValueError, AssertionError):
        verified = False
    return {
        "verified": verified,
        "reason": "Opening title matches."
        if verified
        else "Opening title unconfirmed.",
    }

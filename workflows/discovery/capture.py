"""Save one bounded bibliographic search for local screening (Python 3.10+)."""

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


# Study-type block from discovery ruleset v1.8.1 (ILRI umbrella-review protocol).
REVIEW_TYPE_TERMS = (
    "systematic review",
    "systematically review*",
    "systematic evidence map*",
    "systematic literature review",
    "systematic map",
    "systematically map*",
    "scoping review",
    "evidence and gap map*",
    "evidence synthesis",
    "umbrella review",
    "review of review*",
    "overview of review*",
)


def oa_status(access, status_field):
    status = (access.get(status_field) or "").lower()
    if access.get("is_oa") is True or status in {
        "diamond",
        "gold",
        "green",
        "hybrid",
        "bronze",
    }:
        return "oa"
    return "unknown"


def citation(authors, year, title, journal):
    """Keep the title position compatible with the CIAT registrar's citation parser."""
    if not title:
        return ""
    names = ", ".join(name for name in authors if name)
    byline = f"{names} ({year or 'n.d.'}). ".lstrip()
    return (
        byline
        + title.rstrip(".")
        + "."
        + (f" {journal.rstrip('.')}." if journal else "")
    )


def bare_doi(value):
    identifier = re.sub(
        r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)",
        "",
        (value or "").strip(),
        flags=re.I,
    )
    return identifier.strip()


def openalex_record(work):
    match = re.fullmatch(r"https://openalex\.org/(W[0-9]+)", work["id"])
    if not match:
        raise ValueError("Invalid OpenAlex work identifier")
    work_id = match[1]
    title = work.get("title") or ""
    location = work.get("primary_location") or {}
    journal = (location.get("source") or {}).get("display_name")
    authors = [
        (item.get("author") or {}).get("display_name")
        for item in work.get("authorships") or []
    ]
    index = work.get("abstract_inverted_index") or {}
    words = sorted(
        (position, word) for word, positions in index.items() for position in positions
    )
    return {
        "record_id": f"openalex_{work_id.lower()}",
        "title": title,
        "citation": citation(authors, work.get("publication_year"), title, journal),
        "url": location.get("landing_page_url") or work["id"],
        "doi": bare_doi(work.get("doi")),
        "oa_status": oa_status(work.get("open_access") or {}, "oa_status"),
        "language": work.get("language") or "",
        "method_subtype": work.get("type") or "",
        "report_number_or_handle": f"openalex:{work_id}",
        "abstract": " ".join(word for _, word in words),
    }


def lens_record(work):
    lens_id = work["lens_id"]
    if not re.fullmatch(r"[0-9]{3}(?:-[0-9]{3}){3}-[0-9]{2}[0-9Xx]", lens_id):
        raise ValueError("Invalid Lens work identifier")
    title = work.get("title") or ""
    authors = [
        author.get("collective_name")
        or author.get("display_name")
        or " ".join(
            part for part in (author.get("first_name"), author.get("last_name")) if part
        )
        for author in work.get("authors") or []
    ]
    identifiers = work.get("external_ids") or []
    doi = bare_doi(
        next(
            (item.get("value") for item in identifiers if item.get("type") == "doi"), ""
        )
    )
    urls = work.get("source_urls") or []
    url = next((item["url"] for item in urls if item.get("url")), None)
    languages = work.get("languages") or []
    return {
        "record_id": "lens_" + lens_id.replace("-", "").lower(),
        "title": title,
        "citation": citation(
            authors,
            work.get("year_published"),
            title,
            (work.get("source") or {}).get("title"),
        ),
        "url": url
        or (f"https://doi.org/{doi}" if doi else f"https://www.lens.org/{lens_id}"),
        "doi": doi,
        "oa_status": oa_status(work.get("open_access") or {}, "colour"),
        "language": languages[0] if languages else "",
        "method_subtype": work.get("publication_type") or "",
        "report_number_or_handle": f"lens:{lens_id}",
        "abstract": work.get("abstract") or "",
    }


def capture(provider, query, limit, *, year_from=None, reviews=False):
    if year_from is not None and not 1000 <= year_from <= 9999:
        raise ValueError("--year-from requires a four-digit publication year.")
    if reviews and provider != "lens":
        raise ValueError("--reviews is available for Lens only.")
    if provider == "openalex":
        channel, field, convert = "OpenAlex", "results", openalex_record
        params = {"search.title": query, "per_page": limit}
        if year_from is not None:
            params["filter"] = f"from_publication_date:{year_from}-01-01"
        request = Request("https://api.openalex.org/works?" + urlencode(params))
        key = os.environ.get("OPENALEX_API_KEY")
        limits = f"Title search, first page in provider order, at most {limit} records."
    else:
        channel, field, convert = "Lens", "data", lens_record
        key = os.environ.get("LENS_TOKEN")
        if not key:
            raise ValueError("Set LENS_TOKEN to run a Lens search.")
        if reviews:
            review_block = " OR ".join(f'"{term}"' for term in REVIEW_TYPE_TERMS)
            query = f"({query}) AND ({review_block})"
        selection = {"query_string": {"query": query, "default_operator": "AND"}}
        if year_from is not None:
            selection = {
                "bool": {
                    "must": [selection],
                    "filter": [{"range": {"year_published": {"gte": year_from}}}],
                }
            }
        body = {
            "query": selection,
            "size": limit,
            "include": [
                "lens_id",
                "title",
                "year_published",
                "authors",
                "external_ids",
                "source",
                "abstract",
                "open_access",
                "languages",
                "source_urls",
                "publication_type",
            ],
        }
        request = Request(
            "https://api.lens.org/scholarly/search",
            json.dumps(body).encode("utf-8"),
            {"Content-Type": "application/json"},
        )
        limits = f"Scholarly query-string search, default AND, first page in provider order, at most {limit} records."
    if year_from is not None:
        limits += f" Publication year {year_from} onwards (inclusive)."
    if key:
        request.add_unredirected_header("Authorization", "Bearer " + key)
    try:
        with urlopen(request, timeout=60) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise ValueError(
            f"{channel} returned HTTP {exc.code}. Check the query, account access or quota."
        ) from None
    except (URLError, OSError, HTTPException):
        raise ValueError(
            f"Could not complete the {channel} request; retry this capture."
        ) from None
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError(f"{channel} returned invalid JSON.") from None

    rows = payload.get(field) if isinstance(payload, dict) else None
    if not isinstance(rows, list) or len(rows) > limit:
        raise ValueError(f"{channel} returned an unexpected result list.")
    try:
        records = [convert(work) for work in rows]
    except (AttributeError, KeyError, TypeError, ValueError):
        raise ValueError(
            f"{channel} returned malformed work metadata. Inspect the provider response locally."
        ) from None
    if any(
        not isinstance(value, str) for record in records for value in record.values()
    ):
        raise ValueError(f"{channel} returned invalid text fields.")
    return {
        "channel": channel,
        "process": "updated_lit",
        "query": query,
        "date": datetime.now(timezone.utc).date().isoformat(),
        "limits": limits,
        "records": records,
    }


def save_new(path, snapshot):
    # Link the completed file exclusively: two captures cannot overwrite each other.
    with tempfile.TemporaryDirectory(dir=path.parent) as scratch:
        temporary = Path(scratch) / "snapshot.json"
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(snapshot, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.link(temporary, path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=("openalex", "lens"))
    parser.add_argument("query")
    parser.add_argument(
        "--year-from",
        type=int,
        metavar="YEAR",
        help="Earliest publication year (inclusive)",
    )
    parser.add_argument(
        "--reviews",
        action="store_true",
        help="Lens only: add the v1.8.1 study-type terms",
    )
    parser.add_argument(
        "--limit", type=int, required=True, help="First-page cap, 1 to 100"
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="New file in an existing local directory",
    )
    args = parser.parse_args(argv)
    if not args.query.strip() or not 1 <= args.limit <= 100:
        parser.error("Supply a nonempty query and a limit from 1 to 100.")
    if not args.out.parent.is_dir() or os.path.lexists(args.out):
        parser.error("Choose a new output filename in an existing directory.")
    try:
        snapshot = capture(
            args.provider,
            args.query,
            args.limit,
            year_from=args.year_from,
            reviews=args.reviews,
        )
        save_new(args.out, snapshot)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Capture failed: {exc}\n")
    print(f"{len(snapshot['records'])} records captured from {snapshot['channel']}.")


if __name__ == "__main__":
    main()

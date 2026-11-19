"""Audited repairs to screened queue metadata, before source registration."""

import json

from registers import SRC, index, require, write_csv
import registration as reg


def name(request):
    return (
        "queue-"
        + reg.screen.identifier(request["source_id"])
        + "-"
        + reg.screen.fingerprint(request)[:16]
    )


def validate(request):
    require(isinstance(request, dict), "Expected a queue correction object")
    require(
        set(request)
        <= {
            "source_id",
            "changes",
            "reason",
            "operator",
            "date",
            "doi_locator",
            "confirm_title_change",
            "identity_reference",
        },
        "Unknown queue correction field",
    )
    reg.screen.identifier(request["source_id"])
    reg.screen.identifier(reg.screen.text(request, "operator"))
    reg.screen.text(request, "reason")
    reg.screen.iso_date(request["date"])
    changes = request["changes"]
    require(
        isinstance(changes, dict) and set(changes) <= {"url", "citation", "doi"},
        "Only URL, citation and DOI can be corrected",
    )
    require(
        all(
            isinstance(v, str) and v.strip() == v and (v or k == "doi")
            for k, v in changes.items()
        ),
        "Correction values must be text; only DOI may be cleared",
    )
    require(
        type(request.get("doi_locator", False)) is bool, "doi_locator must be boolean"
    )
    require(changes or request.get("doi_locator"), "Empty correction")
    require(
        not (request.get("doi_locator") and "url" in changes),
        "Choose an explicit URL or the verified DOI locator",
    )
    require(
        type(request.get("confirm_title_change", False)) is bool,
        "confirm_title_change must be boolean",
    )
    if request.get("confirm_title_change"):
        ref = request.get("identity_reference", "")
        require(
            isinstance(ref, str) and ref and reg.acquisition.public_url(ref) == ref,
            "Title confirmation needs a public identity reference for PR review",
        )


def candidate(row):
    return {k: row[k] for k in ("citation", "doi")}


def project(before, request, metadata):
    """Deterministic checks and output; CI replays saved Crossref facts offline."""
    validate(request)
    after = before | request["changes"]
    original_title = reg.acquisition.citation_title(before["citation"])
    next_title = reg.acquisition.citation_title(after["citation"])
    require(
        reg.screen.title_key(original_title) == reg.screen.title_key(next_title)
        or request.get("confirm_title_change"),
        "Citation changes the screened title; explicit title confirmation and identity reference required",
    )
    require(
        reg.acquisition.replay_metadata(candidate(after), metadata) == metadata,
        "Queue metadata verification differs from replay",
    )
    if after["doi"]:
        require(
            metadata["status"] == "doi_verified",
            "DOI must pass Crossref verification; resolve the identity or retry the lookup",
        )
        require(
            reg.screen.title_key(metadata["title"]) == reg.screen.title_key(next_title),
            "Crossref title differs from screened work",
        )
        after["doi"] = metadata["doi"]
        after["citation"] = metadata["citation"]
    if request.get("doi_locator"):
        require(
            metadata["status"] == "doi_verified", "DOI locator requires a verified DOI"
        )
        after["url"] = "https://doi.org/" + metadata["doi"]
    # A queue locator is not a claim that an artifact was fetched or verified.
    require(
        bool(after["url"]) and reg.acquisition.public_url(after["url"]) == after["url"],
        "Expected a public URL without credentials or signed parameters",
    )
    require(
        any(before[k] != after[k] for k in ("url", "citation", "doi")),
        "Correction makes no metadata change",
    )
    after.update(
        doi_verified="true" if metadata["status"] == "doi_verified" else "",
        title_verified="",
        status="pending",
    )
    return after


def build(root, request):
    validate(request)
    previous = root / reg.RECORDS / (name(request) + ".json")
    if previous.exists():
        op = json.loads(previous.read_bytes())["operation"]
        require(op["request"] == request, "Queue correction ID has different inputs")
        return op
    before = index(reg.records(root, reg.QUEUE), "source_id").get(request["source_id"])
    require(before is not None, "Unknown queued source")
    require(
        before["status"] in {"pending", "acquired"} and not before["duplicate_of"],
        "Queue record cannot be corrected",
    )
    require(
        request["source_id"] not in index(reg.records(root, SRC), "source_id"),
        "Registered source requires a source correction, not a queue repair",
    )
    metadata = reg.acquisition.verify_metadata(candidate(before | request["changes"]))
    project(before, request, metadata)
    return dict(kind="queue", request=request, before=before, metadata=metadata)


def apply(root, op):
    request = op["request"]
    validate(request)
    queued = reg.records(root, reg.QUEUE)
    row = index(queued, "source_id").get(request["source_id"])
    require(
        row is not None and row == op["before"],
        "Queue row changed since correction was prepared",
    )
    require(
        row["status"] in {"pending", "acquired"} and not row["duplicate_of"],
        "Queue record cannot be corrected",
    )
    sources = index(reg.records(root, SRC), "source_id")
    require(
        request["source_id"] not in sources,
        "Registered source requires a source correction, not a queue repair",
    )
    after = project(row, request, op["metadata"])
    require(
        not after["doi"]
        or not any(
            s["doi"].casefold() == after["doi"].casefold() for s in sources.values()
        ),
        "Corrected DOI already has a registered source; use its canonical ID",
    )
    row.update(after)
    write_csv(root / "registers" / reg.QUEUE, queued)
    return True

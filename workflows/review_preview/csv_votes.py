"""Convert private exported votes to an immutable input for CIAT consensus replay."""

import csv
import hashlib
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from preview import PENDING, read_copy, require

FIELDS = (
    "batch",
    "evidence_id",
    "decision",
    "reason",
    "note",
    "reviewer",
    "date",
    "picos_flags",
)
VERDICT = {"approve": "ok", "hold": "flag", "reject": "drop"}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key in private input")
        result[key] = value
    return result


def private_path(path):
    path = path.resolve(strict=True)
    require(
        all(
            not (p / ".git").exists() and p.name != ".git"
            for p in (path, *path.parents)
        ),
        "Use a private location outside Git",
    )
    return path


def stage_votes(pending, csv_files, mapping_file):
    private_path(pending)
    unknown = {p.name for p in pending.iterdir()} - set(PENDING)
    require(
        not unknown,
        "Expected only decisions.json and/or clarifications.json in pending copy",
    )
    inputs = {name: read_copy(pending, name) for name in PENDING}
    raw = inputs["decisions.json"]
    store = {}
    if raw is not None:
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode(
                "cp1252"
            )  # Same historical fallback as CIAT read_decisions.
        store = json.loads(text, object_pairs_hook=unique_object)
    require(isinstance(store, dict), "Malformed pending decisions")
    mapping = json.loads(
        private_path(mapping_file).read_bytes(), object_pairs_hook=unique_object
    )
    require(
        isinstance(mapping, dict)
        and mapping
        and all(
            isinstance(s, str) and s and s == s.strip() and "," not in s
            for pair in mapping.items()
            for s in pair
        ),
        "Provide explicit CSV-name to reviewer-ID mappings; comma is reserved by consensus",
    )
    identities = set(mapping.values())
    require(
        all(mapping.get(key, key) == key for key in identities),
        "Ambiguous reviewer mapping",
    )
    for by_reviewer in store.values():
        require(
            isinstance(by_reviewer, dict)
            and all(
                user in identities and isinstance(entry, dict)
                for user, entry in by_reviewer.items()
            ),
            "Map all existing reviewer identities before merging",
        )
        for user, entry in by_reviewer.items():
            sources = entry.get("csv_sources", [])
            require(
                isinstance(sources, list)
                and all(
                    isinstance(src, dict)
                    and isinstance(src.get("values"), dict)
                    and mapping.get(src["values"].get("reviewer")) == user
                    for src in sources
                ),
                "Saved export would map to a different reviewer; reconcile identities privately",
            )
    for path in csv_files:
        data = private_path(path).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        reader = csv.DictReader(
            io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True
        )
        require(
            reader.fieldnames
            and len(reader.fieldnames) == len(set(reader.fieldnames))
            and {"evidence_id", "reviewer", "decision"}
            <= set(reader.fieldnames)
            <= set(FIELDS),
            "Expected evidence_id, reviewer and decision plus known optional evidence-review fields",
        )
        seen = False
        for ordinal, row in enumerate(reader, 1):
            seen = True
            require(
                None not in row and None not in row.values(),
                "Incomplete or excess CSV fields",
            )
            for key in ("evidence_id", "reviewer"):
                require(
                    row[key] and row[key] == row[key].strip(),
                    f"Missing or ambiguous {key}",
                )
            require(row["reviewer"] in mapping, "Unmapped CSV reviewer")
            decision = row["decision"].strip().lower()
            require(not decision or decision in VERDICT, "Unsupported CSV verdict")
            user = mapping[row["reviewer"]]
            reason = row.get("reason", "").strip()
            note = row.get("note", "").strip()
            flags = [
                f.strip() for f in row.get("picos_flags", "").split(";") if f.strip()
            ]
            if flags:
                note = (
                    (note + " " if note else "")
                    + "[PICOS fails: "
                    + ",".join(flags)
                    + "]"
                )
            require(
                decision or flags or reason or note,
                "Empty CSV row without a verdict or annotation",
            )
            votes = store.setdefault(row["evidence_id"], {})
            previous = votes.setdefault(user, {})
            if decision:
                vote = {
                    "decision": VERDICT[decision],
                    "note": note,
                    "reason": reason
                    or ("confirmed_pass" if decision == "approve" else ""),
                }
                if previous.get("decision"):
                    require(
                        all(previous.get(k, "") == v for k, v in vote.items()),
                        "Different vote or annotation for the same reviewer and finding; reconcile privately",
                    )
                else:
                    require(
                        all(
                            not previous.get(k) or previous[k] == v
                            for k, v in vote.items()
                        ),
                        "Pending annotations differ; reconcile privately before adding a verdict",
                    )
                    previous.update(vote)
            # A PICOS-only row documents a concern. Keep its full source below;
            # a later or earlier ballot remains a separately attributable decision.
            sources = previous.setdefault("csv_sources", [])
            require(isinstance(sources, list), "Invalid saved CSV provenance")
            source = {
                "file": path.name,
                "sha256": digest,
                "row": ordinal,
                "values": row,
            }
            if source not in sources:
                sources.append(source)
        require(seen, "Empty CSV export")
    inputs["decisions.json"] = (
        json.dumps(store, ensure_ascii=False, indent=2) + "\n"
    ).encode()
    return inputs


def write_copy(folder, inputs):
    for name, data in inputs.items():
        if data is not None:
            with open(
                folder / name, "xb", opener=lambda p, f: os.open(p, f, 0o600)
            ) as out:
                out.write(data)


def publish_copy(destination, inputs):
    private_path(destination.parent)
    require(
        not destination.exists() and not destination.is_symlink(),
        "Choose a fresh output directory",
    )
    # Publish the complete directory at once. Parallel runs have nonempty
    # destinations, so the second rename cannot replace the first.
    with TemporaryDirectory(dir=destination.parent) as tmp:
        staged = Path(tmp) / "pending"
        staged.mkdir(mode=0o700)
        write_copy(staged, inputs)
        staged.rename(destination)

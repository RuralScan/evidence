"""Freeze source identity from admitted acquisition records, without editing SRC.

Protected register replay verifies source operations. Here we bind the committed
operation to the exact current source row and retain its full verification basis
inside the proposal inputs. Source admission never approves a finding or mapping.
"""

import json
from pathlib import Path
import re
import sys

from synthesis.core import digest, git, require

sys.path.append(str(Path(__file__).resolve().parents[1] / "acquisition"))
from acquisition.run import check_provenance, validate_plan


def _match(source, record):
    op = record["operation"]
    require(op.get("kind") == "source", "Expected source admission operation")
    receipt, plan, candidate = op["receipt"], op["plan"], op["candidate"]
    validate_plan(plan)
    check_provenance(receipt, plan, candidate)
    require(receipt["status"] == "acquired", "Source acquisition remains held")
    meta, artifact = receipt["metadata"], receipt["artifact"]
    expected_url = candidate["url"] if receipt["kind"] == "pdf" else artifact["url"]
    require(
        source.get("source_id") == receipt["source_id"]
        and source.get("doi", "").casefold() == meta["doi"].casefold()
        and source.get("citation") == meta["citation"]
        and source.get("artifact_sha1") == artifact["sha1"]
        and source.get("library_path", "") == op["library_path"]
        and source.get("url") == expected_url,
        "Admitted identity or artifact differs from current source",
    )
    # check_provenance replays Crossref metadata and requires verified document
    # identity, the artifact checksums, and the eligible publisher/code route.
    return receipt


def project(root, sources):
    result = {}
    committed_paths = set()
    if (root / ".git").exists():
        committed_paths = set(git(root, "ls-tree", "-r", "--name-only", "HEAD", "--",
                                  "operations").decode().splitlines())
    for source in sources:
        sid = source["source_id"]
        require(
            isinstance(sid, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", sid),
            "Invalid source identity key",
        )
        relative = f"operations/source-{sid}.json"
        path = root / relative
        identity = {"source_sha256": digest(source)}
        committed = relative in committed_paths
        if path.exists() or committed:
            require(path.is_file() and not path.is_symlink()
                    and path.resolve() == root.resolve() / relative,
                    "Missing or linked source operation")
            raw = path.read_bytes()
            # Do not let an unstaged hand-written receipt certify a source.
            require(committed, "Source operation must be committed before use")
            require(raw == git(root, "show", f"HEAD:{relative}"),
                    "Source operation must match its committed verification record")
            record = json.loads(raw)
            _match(source, record)
            identity.update(
                basis="admitted_acquisition",
                operation_path=relative,
                operation_revision=git(root, "log", "-1", "--format=%H", "--", relative).decode().strip(),
                operation_sha256=digest(raw),
                operation_json=raw.decode("utf-8"),
            )
        else:
            # Preserve the existing literal-boolean route for historical packets.
            # This does not infer verification from the acquisition queue or add
            # stamps to a source. A modern operation always takes precedence.
            key = "doi_verified" if source.get("doi") else "title_verified"
            if source.get(key) is True and (root / ".git").exists():
                require(not git(root, "log", "-1", "--format=%H", "--", relative).strip(),
                        "Deleted source admission cannot fall back to a legacy flag")
            identity.update(
                basis="legacy_source_flag" if source.get(key) is True else "unverified",
                verification_field=key,
            )
        result[sid] = identity
    return result


def verified(source, identity):
    """Validate the frozen basis, including its match to the frozen source row."""
    if identity is None:
        # Immutable v1 packets prepared before identity projection used this
        # literal flag only. Fresh preparation always supplies an explicit basis.
        key = "doi_verified" if source.get("doi") else "title_verified"
        return source.get(key) is True
    require(isinstance(identity, dict), "Source identity basis missing")
    require(identity.get("source_sha256") == digest(source),
            "Source identity basis differs from source snapshot")
    basis = identity.get("basis")
    if basis == "admitted_acquisition":
        text = identity.get("operation_json")
        require(isinstance(text, str), "Source operation basis missing")
        require(identity.get("operation_sha256") == digest(text.encode("utf-8")),
                "Source operation differs from its recorded hash")
        record = json.loads(text)
        require(isinstance(identity.get("operation_revision"), str)
                and re.fullmatch(r"[a-f0-9]{40}", identity["operation_revision"]),
                "Source operation revision missing")
        require(identity.get("operation_path") == f"operations/source-{source['source_id']}.json",
                "Source operation path differs from source")
        # Preserve and verify the exact committed verification bytes inside
        # the immutable input snapshot, without needing local artifact files.
        require(isinstance(identity.get("operation_sha256"), str)
                and re.fullmatch(r"[a-f0-9]{64}", identity["operation_sha256"]),
                "Source operation hash missing")
        _match(source, record)
        return True
    key = "doi_verified" if source.get("doi") else "title_verified"
    return (basis == "legacy_source_flag"
            and identity.get("verification_field") == key
            and source.get(key) is True)

# /// script
# requires-python = ">=3.12"
# dependencies = ["requests==2.34.2"]
# ///

"""Replay the reviewed terrace-rainfall example against immutable Git inputs."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.request import urlopen

EXAMPLE = Path(__file__).resolve().parent
LOCK = EXAMPLE.parents[1] / "method.lock.json"
METHOD = "https://github.com/RuralScan/method.git"
PRODUCER = "https://github.com/CIAT/nbs_ruralscan.git"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def revision(value):
    require(
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value),
        "Expected a full Git commit",
    )
    return value


def git(*args, cwd=None, stdin=None):
    env = os.environ.copy()
    # CI jobs and Git hooks can export a working tree or index. Each Git call
    # must operate on the explicit checkout, including when launched from CIAT.
    for key in (
        "GIT_DIR",
        "GIT_COMMON_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    ):
        env.pop(key, None)
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        input=stdin,
        stdout=subprocess.PIPE,
        check=True,
    ).stdout


def snapshot(destination, repository, commit, patterns, local):
    """Check out only the required paths in a private temporary directory."""
    revision(commit)
    if local:
        git(
            "clone",
            "--quiet",
            "--shared",
            "--no-checkout",
            str(local.resolve()),
            str(destination),
        )
    else:
        git("init", "--quiet", str(destination))
        git("remote", "add", "origin", repository, cwd=destination)
        git("config", "remote.origin.promisor", "true", cwd=destination)
        git("config", "remote.origin.partialclonefilter", "blob:none", cwd=destination)
        git(
            "fetch",
            "--quiet",
            "--depth=1",
            "--filter=blob:none",
            "origin",
            commit,
            cwd=destination,
        )
    git(
        "sparse-checkout",
        "set",
        "--no-cone",
        "--stdin",
        cwd=destination,
        stdin=("\n".join(patterns) + "\n").encode(),
    )
    git("checkout", "--quiet", "--detach", commit, cwd=destination)
    require(
        git("rev-parse", "HEAD", cwd=destination).decode().strip() == commit,
        "Wrong checkout revision",
    )


def csv_rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def one(rows, **criteria):
    matches = [r for r in rows if all(r.get(k) == v for k, v in criteria.items())]
    require(
        len(matches) == 1, f"Expected one record for {criteria}, found {len(matches)}"
    )
    return matches[0]


def definitions(destination, local):
    lock = json.loads(LOCK.read_bytes())
    require(
        lock["repository"] == METHOD
        and lock["manifest"] == "data-model/definition-snapshot.json",
        "Unknown method publisher or manifest",
    )
    commit = revision(lock["revision"])
    if local:
        data = git("show", f"{commit}:{lock['manifest']}", cwd=local)
    else:
        url = f"https://raw.githubusercontent.com/RuralScan/method/{commit}/{lock['manifest']}"
        with urlopen(url, timeout=30) as response:
            data = response.read()
    require(digest(data) == lock["sha256"], "Method manifest checksum mismatch")
    manifest = json.loads(data)
    require(
        (manifest["format_version"], manifest["kind"], manifest["structure_version"])
        == (1, "method_definitions", "0.4.0-structure-frozen"),
        "Unsupported method definition format",
    )
    snapshot(destination, METHOD, manifest["source_revision"], ["/data-model/"], local)
    model = destination / "data-model"
    members = {
        model / "spec.md",
        model / "structure/columns.json",
        *(model / "configuration").rglob("*.csv"),
    }
    actual = {
        p.relative_to(destination).as_posix(): digest(p.read_bytes()) for p in members
    }
    require(
        actual == manifest["sha256"], "Method definition inventory or checksum mismatch"
    )
    require(
        json.loads((model / "structure/columns.json").read_bytes())["manifest_version"]
        == manifest["structure_version"],
        "Definition structure version mismatch",
    )
    return model


def verify_claims(case, registers, decision):
    from nbs_ruralscan.schema_tools.review_notes import evidence_fingerprint

    profiles = decision["source_profiles"]
    claims = case["claims"]
    ids = [c["evidence_id"] for c in claims]
    require(
        len(ids) == len(set(ids))
        and set(ids) == {p["evidence_id"] for p in profiles}
        and len(claims) == len(profiles),
        "Fixture and decision have different claim inventories",
    )
    evidence = csv_rows(registers / "EV_evidence_register.csv")
    registered = csv_rows(registers / "SRC_source_register.csv")
    support = []
    sources = set()
    for claim in claims:
        eid, sid = claim["evidence_id"], claim["source_id"]
        profile = one(profiles, evidence_id=eid)
        require(
            {k: claim[k] for k in profile} == profile,
            f"Reviewed profile mismatch: {eid}",
        )
        unit = one(
            evidence,
            evidence_id=eid,
            source_id=sid,
            variable=case["variable"],
            suitability_family_id=case["family"],
        )
        source = one(registered, source_id=sid)
        require(
            evidence_fingerprint(unit) == claim["evidence_sha256"],
            f"Evidence fingerprint mismatch: {eid}",
        )
        included = claim["included_in_annual_terrace_support"]
        require(isinstance(included, bool), f"Missing screening decision: {eid}")
        if included:
            require(
                unit["review_state"] != "dropped", f"Dropped supporting evidence: {eid}"
            )
            support.append(eid)
            sources.add(sid)
        print(
            f"  {sid} ({source['source_category']}) -> {eid}: "
            f"{'annual terrace support' if included else 'context only'}"
        )
    return support, sources


def apply_fixture_support(path, case, support, sources):
    """Supply the example's reviewed membership to the compiler in its private copy."""
    holds = csv_rows(path)
    target = one(holds, mapping_id=case["mapping_id"])
    params = json.loads(target["relationship_params"])
    calibration = params["reviewed_adaptation"]["numerical_calibration"]
    require(
        calibration["status"] == "held" and calibration["scope"] == case["mapping_id"],
        "Source configuration has no matching calibration hold",
    )
    profiles = calibration["retained_source_profiles"]
    require(
        [p["evidence_id"] for p in profiles]
        == [c["evidence_id"] for c in case["claims"]],
        "Authored hold and fixture reference different profiles",
    )
    calibration["excluded_from_annual_terrace_support_and_scoring"] = [
        c["evidence_id"] for c in case["claims"] if c["evidence_id"] not in support
    ]
    target["evidence_ids"] = json.dumps(support)
    target["n_sources"] = str(len(sources))
    target["relationship_params"] = json.dumps(params, ensure_ascii=False)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(target), lineterminator="\n")
        writer.writeheader()
        writer.writerows(holds)


def replay(work, method_repo, producer_repo):
    case = json.loads((EXAMPLE / "reviewed-claims.json").read_bytes())
    model = definitions(work / "method", method_repo)
    config = model / "configuration"
    practice, family, variable = case["practice"], case["family"], case["variable"]
    one(
        csv_rows(config / "recipes" / practice / "T0_nbs_registry.csv"), nbs_id=practice
    )
    one(
        csv_rows(config / "FAM_family_registry.csv"),
        nbs_id=practice,
        subpractice_id=case["subpractice"],
        suitability_family_id=family,
        spatial_product_type="area_suitability",
    )
    one(
        csv_rows(config / "VONT_variable_ontology.csv"),
        canonical_variable_id=variable,
        canonical_unit="mm/year",
    )
    binding = one(
        csv_rows(config / "BIND_dataset_binding.csv"),
        variable=variable,
        scope_type="global",
        preference_rank="1",
    )
    datasets = csv_rows(config / "T1_data_registry.csv")
    one(datasets, dataset_id=binding["dataset_id"])

    root = work / "producer"
    snapshot(
        root,
        PRODUCER,
        case["producer_revision"],
        [
            "/src/nbs_ruralscan/",
            "/schema/lookups/",
            "/schema/recipe_inputs/t4/",
            "/schema/registers/EV_evidence_register.csv",
            "/schema/registers/SRC_source_register.csv",
            "/schema/recipes/*/T4_suitability_mappings.csv",
            "/" + case["review_record"],
        ],
        producer_repo,
    )
    # Use the pinned method definitions as actual compiler inputs. The remaining
    # synthesis policies and authored holds come with the historical producer.
    for filename in ("FAM_family_registry.csv", "VONT_variable_ontology.csv"):
        shutil.copyfile(config / filename, root / "schema/registers" / filename)
    sys.path.insert(0, str(root / "src"))
    from nbs_ruralscan.recipe.developer_corpus import rebuild

    audit = json.loads((root / case["review_record"]).read_bytes())
    decision = one(audit["decisions"], mapping_id=case["mapping_id"])
    support, sources = verify_claims(case, root / "schema/registers", decision)
    apply_fixture_support(
        root / "schema/recipe_inputs/t4" / practice / "review_holds.csv",
        case,
        support,
        sources,
    )

    # Reconcile each entire practice before selecting the demonstration row.
    builds = csv_rows(root / "schema/recipe_inputs/t4/practices.csv")
    target = None
    total = 0
    for entry in builds:
        result = rebuild(root, entry["nbs_id"])
        total += len(result["rows"])
        if entry["nbs_id"] == practice:
            target = result
    require(target is not None, f"Missing compiled practice: {practice}")
    print(f"Full T4 comparison passed: {total} rows across {len(builds)} practices.")
    row = one(
        target["rows"],
        mapping_id=case["mapping_id"],
        variable=variable,
        suitability_family_id=family,
    )
    require(
        json.loads(row["evidence_ids"]) == support
        and int(row["n_sources"]) == len(sources),
        "Compiled evidence support differs from the reviewed claims",
    )
    one(datasets, dataset_id=row["dataset_id"])
    require(
        row["dataset_id"] == decision["dataset_id"],
        "Recorded dataset differs from rebuilt row",
    )
    parameters = json.loads(row["relationship_params"])
    hold = parameters["reviewed_adaptation"]["numerical_calibration"]
    require(
        hold["status"] == "held" and hold["scope"] == row["mapping_id"],
        "Missing calibration hold",
    )
    encoded = json.dumps(
        row, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    actual = digest(encoded)
    require(
        actual == case["expected_row_sha256"] == decision["result_sha256"],
        "Full T4 row checksum mismatch",
    )
    print(
        f"Method global binding: {binding['dataset_id']} ({binding['band']}); reviewed input: {row['dataset_id']}."
    )
    print(
        f"{row['mapping_id']}: {len(sources)} supporting source(s); calibration {hold['status']}."
    )
    print(f"Reproduced full CSV row SHA-256: {actual}")
    return encoded


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--method-repo",
        type=Path,
        help="Local Git repository containing the method pins",
    )
    parser.add_argument(
        "--producer-repo",
        type=Path,
        help="Local Git repository containing the producer pin",
    )
    parser.add_argument(
        "--row-output",
        type=Path,
        help="Create a local file with the verified CSV row as canonical JSON",
    )
    args = parser.parse_args()
    try:
        with TemporaryDirectory(prefix="terrace-replay-") as directory:
            encoded = replay(
                Path(directory).resolve(), args.method_repo, args.producer_repo
            )
        if args.row_output:
            with args.row_output.open("xb") as handle:
                handle.write(encoded)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        sys.exit(f"Replay failed: {exc}")

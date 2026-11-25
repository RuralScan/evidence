"""Cross-cutting source/finding store. No T4/effect votes or legacy register writes."""
import argparse
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
STORE = "priority-evidence"
REVIEWS = f"{STORE}/reviews.jsonl"
HEADER = "RuralScan priority finding review v1"
HEX = re.compile(r"[0-9a-f]{64}")
REV = re.compile(r"[0-9a-f]{40}")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n").encode()


def digest(value):
    return sha256(encoded(value)).hexdigest()


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root)


def blob(root, revision, path):
    require(REV.fullmatch(revision), "Full revision required")
    return git(root, "show", f"{revision}:{path}")


def merged(root, revision, base):
    require(REV.fullmatch(revision) and REV.fullmatch(base), "Full revision and trusted base required")
    require(subprocess.run(["git", "merge-base", "--is-ancestor", revision, base], cwd=root,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0,
            "Input revision is not in the inspected main history")


def objects(root, kind):
    require(kind in {"sources", "findings"}, "Unknown store collection")
    result = {}
    for path in sorted((root / STORE / kind).glob("*.json")):
        value = json.loads(path.read_bytes()); key = digest(value)
        require(path.stem == key and path.read_bytes() == encoded(value), "Altered or noncanonical store object")
        result[key] = value
    return result


def acquisition():
    sys.path.insert(0, str(ROOT / "workflows/acquisition"))
    spec = importlib.util.spec_from_file_location("priority_acquisition", ROOT / "workflows/acquisition/run.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def validate_source(source):
    require(set(source) == {"format", "candidate", "plan", "receipt", "shared_copy", "legacy_source_id"}, "Invalid source fields")
    require(source["format"] == "ruralscan.priority-source.v1", "Invalid source format")
    tool = acquisition()
    tool.validate_plan(source["plan"])
    tool.check_provenance(source["receipt"], source["plan"], source["candidate"])
    require(source["receipt"]["status"] == "acquired", "Held acquisition cannot be registered")
    require(source["receipt"]["kind"] in {"pdf", "website", "markdown", "text", "code"}, "Unsupported acquire adapter")
    shared = source["shared_copy"]
    if source["receipt"]["kind"] == "pdf":
        require(isinstance(shared, dict) and set(shared) == {"library_path", "sha256"}, "PDF requires a checked team-library copy")
        parts = Path(shared["library_path"]).parts
        require(not Path(shared["library_path"]).is_absolute() and ".." not in parts and "library" in parts,
                "Use a project-relative library locator")
        require(shared["sha256"] == source["receipt"]["artifact"]["sha256"], "Shared PDF differs from acquired edition")
    else:
        require(shared is None, "Web/code sources use the verified URL and snapshot")
    canonical = source["receipt"]["canonical_source"]
    require(source["legacy_source_id"] == (canonical["source_id"] if canonical else None), "Invented legacy SRC identity")
    return digest(source)


def prepare_source(bundle, plan, candidate, library_root=None, library_path=None, legacy_sources=None):
    tool = acquisition()
    receipt = tool.check(bundle, plan, candidate, legacy_sources)
    require(receipt["status"] == "acquired", "Acquisition remains held")
    shared = None
    if receipt["kind"] == "pdf":
        require(library_root is not None and library_path, "PDF registration needs team-library accession")
        parts = Path(library_path).parts
        require("library" in parts and ".." not in parts and not Path(library_path).is_absolute(), "Invalid library locator")
        relative = Path(*parts[parts.index("library") + 1:])
        target = (library_root / relative).resolve()
        require(target.is_relative_to(library_root.resolve()), "Library path escapes root")
        shared = {"library_path": library_path, "sha256": sha256(target.read_bytes()).hexdigest()}
    canonical = receipt["canonical_source"]
    source = {"format": "ruralscan.priority-source.v1", "candidate": candidate, "plan": plan,
              "receipt": receipt, "shared_copy": shared, "legacy_source_id": canonical["source_id"] if canonical else None}
    validate_source(source)
    return source


def finding(packet, source, packet_ref):
    # A packet observation is independently reviewed; it never becomes a rule here.
    from check import validate
    validate(packet)
    require(set(packet_ref) == {"revision", "path", "sha256"} and REV.fullmatch(packet_ref["revision"]), "Unpinned packet")
    require(re.fullmatch(r"workflows/priority_classification/packets/[a-z0-9_]+\.json", packet_ref["path"]), "Invalid packet path")
    require(HEX.fullmatch(packet_ref["sha256"]), "Invalid packet hash")
    source_hash = validate_source(source)
    require(packet["source"]["artifact_sha256"] == source["receipt"]["artifact"]["sha256"], "Packet and source identify different artefacts")
    return {"format": "ruralscan.priority-finding.v1", "source_sha256": source_hash,
            "packet": packet_ref, "variables": packet["variables"], "source_locator": packet["source"]["locator"],
            "locator_type": packet["source"]["locator_type"], "reported": packet["reported"],
            "interpretation_limit": packet["interpretation_limit"]}


def write_object(root, kind, value):
    require(kind in {"sources", "findings"}, "Unknown store collection")
    path = root / STORE / kind / (digest(value) + ".json")
    data = encoded(value)
    if path.exists():
        require(path.read_bytes() == data, "Immutable object differs")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream: stream.write(data)
    return path


def fetch_review(number):
    # Reuse the existing desk's original-body and reviewer-identity checks.
    sys.path.insert(0, str(ROOT / "workflows/submissions"))
    import intake
    issue = intake.gh(f"repos/{intake.INBOX}/issues/{number}")
    actor = intake.original(issue)
    require("pull_request" not in issue and issue.get("user", {}).get("type") == "User", "Review requires an original human issue")
    require(intake.reviewer_eligible(issue), "Reviewer is not eligible")
    match = re.fullmatch(re.escape(HEADER) + r"\s*```json\s*(\{.*\})\s*```\s*", issue["body"], re.S)
    require(match, "Invalid priority review receipt")
    value = json.loads(match[1])
    require(set(value) == {"finding_sha256", "finding_revision", "decision", "reason"}, "Unexpected review fields")
    require(HEX.fullmatch(value["finding_sha256"]) and REV.fullmatch(value["finding_revision"]), "Invalid finding pin")
    require(value["decision"] in {"keep", "hold", "reject", "reopen"} and isinstance(value["reason"], str) and value["reason"].strip(), "Explicit source-finding decision and reason required")
    return {**value, "receipt": number, "actor": actor, "created_at": issue["created_at"],
            "body_sha256": sha256(issue["body"].encode()).hexdigest()}


def reviews(root):
    path = root / REVIEWS
    return [json.loads(line) for line in path.read_bytes().splitlines()] if path.exists() else []


def status(events, key):
    latest = {}
    for event in events:
        if event["finding_sha256"] == key:
            latest[event["actor"].casefold()] = event["decision"]
    choices = set(latest.values())
    if not choices: return "unreviewed"
    if choices == {"keep"}: return "kept"
    if choices == {"reject"}: return "rejected"
    if choices <= {"hold", "reopen"}: return "held"
    return "conflict"


def pinned_review(root, event, base):
    merged(root, event["finding_revision"], base)
    path = f"{STORE}/findings/{event['finding_sha256']}.json"
    require((root / path).read_bytes() == blob(root, event["finding_revision"], path), "Review targets different finding bytes")


def record_review(root, number, base):
    event = fetch_review(number); pinned_review(root, event, base)
    old = reviews(root)
    if event in old: return False
    require(not any(e["receipt"] == number for e in old), "Receipt already used differently")
    prior = [e for e in old if e["finding_sha256"] == event["finding_sha256"] and e["actor"].casefold() == event["actor"].casefold()]
    require(not prior or prior[-1]["created_at"] < event["created_at"], "Older receipt cannot replace newer decision")
    path = root / REVIEWS; path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as stream: stream.write(encoded(event))
    return True


def verify(root, base=None, authenticate=True):
    sources = objects(root, "sources"); findings = objects(root, "findings")
    identities = set()
    for key, source in sources.items():
        require(validate_source(source) == key, "Source identity differs")
        identity = (source["receipt"]["kind"], source["receipt"]["artifact"]["sha256"])
        require(identity not in identities, "Duplicate acquisition identity; reuse the existing source object")
        identities.add(identity)
    for key, item in findings.items():
        source = sources.get(item.get("source_sha256")); require(source is not None, "Missing source object")
        ref = item["packet"]; data = blob(root, ref["revision"], ref["path"])
        require(sha256(data).hexdigest() == ref["sha256"], "Packet bytes changed")
        if base: merged(root, ref["revision"], base)
        require(item == finding(json.loads(data), source, ref), "Finding differs from pinned source packet")
    old_events = []
    if base:
        for path in git(root, "ls-tree", "-r", "--name-only", base, "--", STORE).decode().splitlines():
            if not path.endswith((".json", ".jsonl")): continue
            old = blob(root, base, path)
            require((root / path).is_file(), "Priority history removed")
            if path == REVIEWS:
                require((root / path).read_bytes().startswith(old), "Review history rewritten")
                old_events = [json.loads(line) for line in old.splitlines()]
            else:
                require((root / path).read_bytes() == old, "Priority object rewritten; append a successor")
    events = reviews(root); receipts = set(); chronology = {}
    for event in events:
        require(event["finding_sha256"] in findings and event["receipt"] not in receipts, "Missing finding or duplicate receipt")
        receipts.add(event["receipt"])
        require(event["decision"] in {"keep", "hold", "reject", "reopen"}, "Invalid finding decision")
        who = (event["finding_sha256"], event["actor"].casefold())
        require(who not in chronology or chronology[who] < event["created_at"], "Review chronology reversed")
        chronology[who] = event["created_at"]
        pinned_review(root, event, base or git(root, "rev-parse", "HEAD").decode().strip())
        if event not in old_events and authenticate:
            require(event == fetch_review(event["receipt"]), "Review differs from authenticated original")
    return {key: status(events, key) for key in findings}


def resolve(root, reference, base):
    """Resolve a method source reference against immutable objects and kept findings.

    The trusted base comes from the protected PR workflow. A newer hold/rejection
    blocks new packaging even if an older selected revision contained a keep.
    """
    revision = reference["revision"]; merged(root, revision, base)
    require(reference["repository"] == "RuralScan/evidence", "Wrong evidence repository")
    source_id = reference["source_id"]
    require(isinstance(source_id, str) and re.fullmatch(r"psrc_[0-9a-f]{64}", source_id), "Expected cross-cutting source identity")
    source_hash = source_id[5:]
    source = json.loads(blob(root, revision, f"{STORE}/sources/{source_hash}.json"))
    require(validate_source(source) == source_hash, "Source object hash mismatch")
    packet = blob(root, revision, reference["path"])
    require(sha256(packet).hexdigest() == reference["sha256"], "Rule packet hash mismatch")
    packet = json.loads(packet)
    def at(pin):
        names = git(root, "ls-tree", "--name-only", pin, "--", REVIEWS).decode().splitlines()
        return [json.loads(line) for line in blob(root, pin, REVIEWS).splitlines()] if names else []
    selected, latest = at(revision), at(base)
    require(reference["finding_ids"] and len(set(reference["finding_ids"])) == len(reference["finding_ids"]), "Missing or duplicate findings")
    result = []
    for key in reference["finding_ids"]:
        require(re.fullmatch(r"pfind_[0-9a-f]{64}", key), "Invalid priority finding ID")
        key = key[6:]
        item = json.loads(blob(root, revision, f"{STORE}/findings/{key}.json"))
        require(digest(item) == key and item["source_sha256"] == source_hash, "Finding/source identity mismatch")
        ref = item["packet"]
        require(ref["path"] == reference["path"] and ref["sha256"] == reference["sha256"], "Finding refers to another packet")
        require(item == finding(packet, source, ref), "Finding content differs from packet")
        require(status(selected, key) == status(latest, key) == "kept", "Finding is unreviewed, held, rejected, reopened or conflicted")
        result.append({"finding_id": "pfind_" + key, "source_sha256": source_hash,
                       "review_receipts": [e["receipt"] for e in selected if e["finding_sha256"] == key]})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check"); check.add_argument("--base")
    stage = commands.add_parser("stage")
    for name in ("packet", "candidates", "plan", "bundle", "out"):
        stage.add_argument("--" + name, type=Path, required=True)
    stage.add_argument("--packet-revision", required=True)
    stage.add_argument("--base", required=True)
    stage.add_argument("--library-root", type=Path); stage.add_argument("--library-path")
    review = commands.add_parser("review"); review.add_argument("--receipt", type=int, required=True); review.add_argument("--base", required=True)
    args = parser.parse_args()
    if args.command == "check":
        print(json.dumps(verify(ROOT, args.base), sort_keys=True)); return
    if args.command == "review":
        print("Recorded" if record_review(ROOT, args.receipt, args.base) else "Already recorded"); return
    tool = acquisition(); plan = tool.read_plan(args.plan)
    candidate = tool.selected(args.candidates, plan["candidate_id"])
    source = prepare_source(args.bundle, plan, candidate, args.library_root, args.library_path,
                            ROOT / "registers/schema/registers/SRC_source_register.csv")
    merged(ROOT, args.packet_revision, args.base)
    relative = str(args.packet.resolve().relative_to(ROOT))
    data = blob(ROOT, args.packet_revision, relative)
    require(args.packet.read_bytes() == data, "Packet checkout differs from declared revision")
    ref = {"revision": args.packet_revision, "path": relative, "sha256": sha256(data).hexdigest()}
    item = finding(json.loads(data), source, ref)
    require(not args.out.exists(), "Use a new private staging directory")
    write_object(args.out, "sources", source); write_object(args.out, "findings", item)
    print(f"Staged source psrc_{digest(source)} and unreviewed finding pfind_{digest(item)}; no review or registration applied")


if __name__ == "__main__": main()

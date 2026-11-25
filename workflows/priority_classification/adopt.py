"""Adopt a merged method priority release without changing the compiler lock."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile
from priority_store import ROOT, blob, digest, encoded, git, merged, require

JOURNAL = "configuration/priority/adoptions.jsonl"
CACHE = "configuration/priority/releases"


def load_events(root):
    path = root / JOURNAL
    return [json.loads(line) for line in path.read_bytes().splitlines()] if path.exists() else []


def producer_verify(method, pin, package, method_base, evidence, evidence_base):
    """Run the producer from the merged release commit, not a mutable checkout."""
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        for name in ("package.py", "catalogue.py"):
            (folder / name).write_bytes(blob(method, pin["revision"], "priority/" + name))
        (folder / "payload.json").write_bytes(encoded(package))
        # ROOT is irrelevant: verify receives explicit repositories and bases.
        script = ("import json,sys; from pathlib import Path; import package; "
                  "package.verify(Path(sys.argv[1]),json.loads(Path(sys.argv[2]).read_bytes()),"
                  "sys.argv[3],Path(sys.argv[4]),sys.argv[5])")
        subprocess.run([__import__("sys").executable, "-c", script, str(method.resolve()),
                        str(folder / "payload.json"), method_base, str(evidence.resolve()), evidence_base],
                       cwd=folder, check=True)


def resolve(method, pin, method_base):
    require(set(pin) == {"repository", "revision", "path", "sha256"}, "Invalid method release pin")
    require(pin["repository"] == "RuralScan/method", "Wrong producer repository")
    require(re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]), "Invalid release hash")
    require(pin["path"] == f"priority/releases/{pin['sha256']}.json", "Release path/hash mismatch")
    merged(method, pin["revision"], method_base)
    data = blob(method, pin["revision"], pin["path"]); package = json.loads(data)
    require(data == encoded(package) and digest(package) == pin["sha256"], "Release bytes/hash mismatch")
    require(package.get("format") == "ruralscan.priority-release.v1", "Review manifest is not adoptable")
    return package


def validate_events(root, events):
    seen = set(); active = None; adopted = set()
    for event in events:
        require(set(event) == {"format", "operation_id", "action", "release", "previous_release_sha256", "method_main_checked", "evidence_main_checked"}, "Invalid adoption receipt")
        require(event["format"] == "ruralscan.priority-adoption.v1" and re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", event["operation_id"]), "Invalid operation identity")
        require(event["operation_id"] not in seen, "Duplicate operation identity")
        seen.add(event["operation_id"])
        require(event["previous_release_sha256"] == active, "Broken adoption history")
        key = event["release"]["sha256"]
        require(event["action"] in {"adopt", "rollback"}, "Unknown adoption action")
        if event["action"] == "rollback": require(key in adopted, "Rollback target was never adopted")
        data = (root / CACHE / f"{key}.json").read_bytes(); package = json.loads(data)
        require(data == encoded(package) and digest(package) == key, "Adoption cache altered")
        active = key; adopted.add(key)
    return active


def adopt(root, method, pin, method_base, evidence_base, operation_id, action="adopt", verify=producer_verify):
    events = load_events(root); active = validate_events(root, events)
    prior = next((e for e in events if e["operation_id"] == operation_id), None)
    if prior:
        require(prior["release"] == pin and prior["action"] == action and
                prior["method_main_checked"] == method_base and prior["evidence_main_checked"] == evidence_base,
                "Operation identity already used differently")
        return False
    require(re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", operation_id) and action in {"adopt", "rollback"}, "Invalid adoption operation")
    if action == "rollback":
        require(any(e["release"]["sha256"] == pin["sha256"] for e in events), "Rollback target was never adopted")
    require(not git(root, "diff", "--name-only", evidence_base, "--", "priority-evidence").strip(), "Merge source changes before adopting a release")
    package = resolve(method, pin, method_base)
    verify(method, pin, package, method_base, root, evidence_base)
    event = {"format": "ruralscan.priority-adoption.v1", "operation_id": operation_id, "action": action,
             "release": pin, "previous_release_sha256": active,
             "method_main_checked": method_base, "evidence_main_checked": evidence_base}
    path = root / CACHE / f"{digest(package)}.json"; path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists(): require(path.read_bytes() == encoded(package), "Existing release cache differs")
    else:
        with path.open("xb") as stream: stream.write(encoded(package))
    validate_events(root, events + [event])
    journal = root / JOURNAL; journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("ab") as stream: stream.write(encoded(event))
    return True


def check(root, method, base, method_base, evidence_base, verify=producer_verify):
    previous = []
    for name in git(root, "ls-tree", "-r", "--name-only", base, "--", "configuration/priority").decode().splitlines():
        old = blob(root, base, name); path = root / name
        require(path.is_file(), "Adoption history removed")
        if name == JOURNAL:
            require(path.read_bytes().startswith(old), "Adoption history rewritten")
            previous = [json.loads(line) for line in old.splitlines()]
        else: require(path.read_bytes() == old, "Cached release rewritten")
    events = load_events(root); active = validate_events(root, events)
    if events[len(previous):]:
        require(not git(root, "diff", "--name-only", evidence_base, "--", "priority-evidence").strip(), "Merge source changes before adopting a release")
    for event in events[len(previous):]:
        require(event["method_main_checked"] == method_base and event["evidence_main_checked"] == evidence_base,
                "New receipt does not use inspected main bases")
        package = resolve(method, event["release"], method_base)
        verify(method, event["release"], package, method_base, root, evidence_base)
    return active


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["adopt", "rollback", "check"])
    parser.add_argument("--method-repo", type=Path, required=True)
    parser.add_argument("--method-base", required=True)
    parser.add_argument("--evidence-base", required=True)
    parser.add_argument("--base")
    parser.add_argument("--pin", type=Path)
    parser.add_argument("--operation-id")
    args = parser.parse_args()
    if args.command == "check":
        require(args.base, "Protected PR/push base required")
        print(check(ROOT, args.method_repo, args.base, args.method_base, args.evidence_base))
    else:
        require(args.pin and args.operation_id, "Release pin and operation identity required")
        print("Recorded" if adopt(ROOT, args.method_repo, json.loads(args.pin.read_bytes()), args.method_base,
                                   args.evidence_base, args.operation_id, args.command) else "Already recorded")


if __name__ == "__main__": main()

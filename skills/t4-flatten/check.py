"""Check the AI-written rows, then list every live T4 claim nothing has accounted for yet.

Run from the evidence repo root, after t4/build.py: python3 skills/t4-flatten/check.py
Exits with an error if any AI row fails. Prints the remaining claims as JSON lines.
"""
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

csv.field_size_limit(10**9)
ROOT = Path(__file__).resolve().parents[2]
NUMS = ["abs_min", "opt_low", "opt_high", "abs_max", "seen_min", "seen_max"]


def read(name):
    path = ROOT / "t4" / name
    return list(csv.DictReader(open(path))) if path.exists() else []


def numbers(text):
    """Every number in the text, sign ignored: a dash can be a minus or a range."""
    return {float(n) for n in re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))}


def plain(text):
    """Lower case, one space between words, ligatures undone, so line breaks in a quote don't matter."""
    return " ".join(unicodedata.normalize("NFKC", text).lower().split())


by_script = {r["evidence_id"] for name in ("trace/thresholds.csv", "trace/categories.csv")
             for r in read(name) if r["flattened_by"] == "script"}
todo, text = {}, {}
for ev in csv.DictReader(open(ROOT / "registers/schema/registers/EV_evidence_register.csv")):
    if (ev["use_role"] == "structural_suitability" and ev["review_state"] != "dropped"
            and ev["evidence_id"] not in by_script):
        todo[ev["evidence_id"]] = ev
        text[ev["evidence_id"]] = " ".join((ev["quote"], ev["justification_quote"], ev["relationship"]))

errors = []
rows, cats, skipped = read("ai-skill-output/rows.csv"), read("ai-skill-output/categories.csv"), read("ai-skill-output/skipped.csv")
for r in rows + cats + skipped:
    if r["evidence_id"] not in todo:
        errors.append(f"{r['evidence_id']}: not a claim this step should handle")
    elif not r["reason"]:
        errors.append(f"{r['evidence_id']}: a reason is required")
for r in rows:
    eid = r["evidence_id"]
    if eid not in todo:
        continue
    stated = [float(r[p]) for p in NUMS[:4] if r[p]]
    seen = [float(r[p]) for p in NUMS[4:] if r[p]]
    if not stated + seen or stated != sorted(stated) or seen != sorted(seen):
        errors.append(f"{eid}: needs at least one number, in rising order")
    if not r["unit"] or r["basis"] != ("observed" if seen else "stated") or (stated and seen):
        errors.append(f"{eid}: needs a unit, and either stated limits or a seen range, with basis to match")
    # every number must be printed in the claim itself, so nothing is invented or converted
    missing = sorted(({abs(v) for v in stated + seen} | numbers(r["classes"])) - numbers(text[eid]))
    if missing:
        errors.append(f"{eid}: {', '.join(f'{v:g}' for v in missing)} not found in the claim text")
for r in cats:
    eid = r["evidence_id"]
    if eid in todo and plain(r["category"]) not in plain(text[eid]):
        errors.append(f"{eid}: category '{r['category']}' not found in the claim text")
    if r["status"] not in ("included", "excluded", "observed"):
        errors.append(f"{eid}: status must be included, excluded or observed")
done = {r["evidence_id"] for r in rows + cats}
errors += [f"{r['evidence_id']}: both flattened and skipped" for r in skipped if r["evidence_id"] in done]

handled = done | {r["evidence_id"] for r in skipped}
for ev in todo.values():
    if ev["evidence_id"] not in handled:
        print(json.dumps({k: ev[k] for k in ("evidence_id", "nbs_id", "suitability_family_id", "variable",
                                              "claim_scope", "relationship", "quote", "justification_quote")}))
print(f"{len(by_script)} read by script, {len(done)} flattened by AI, {len(skipped)} skipped,"
      f" {len(set(todo) - handled)} to do, {len(errors)} errors", file=sys.stderr)
sys.exit("\n".join(errors) if errors else 0)

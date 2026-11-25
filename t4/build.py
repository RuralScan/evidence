"""Build the T4 suitability tables from the evidence register.

t4/t4.csv             one row per family, variable and unit: limits plus where it was seen working
t4/t4_categories.csv  one row per family, variable and category: included or excluded
t4/trace/             rebuilt every run, to trace a T4 row back: thresholds.csv and categories.csv
                      (one row per claim, before combining) and importance.csv (one row per paper
                      and variable: weight as printed, rank within that paper)

Runs with or without the files in t4/ai-skill-output/ (rows, categories, general_limits). With
them T4 gains the claims a script cannot parse and the general-knowledge hard limits. In
general_limits.csv "none" means no limit on that side; blank means nobody said.

Run from the evidence repo root: python3 t4/build.py [--no-ai]
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

csv.field_size_limit(10**9)
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
PARAMS = ["abs_min", "opt_low", "opt_high", "abs_max"]
NUMS = [*PARAMS, "seen_min", "seen_max"]
UNITS = {"%": "percent", "mm/year": "mm", "degrees_C": "degC"}  # same unit, different spelling
LISTS = {"included_classes": "included", "excluded_classes": "excluded", "observed_classes": "observed"}

# every live suitability claim, with its relationship parsed
claims = [{**ev, "rel": json.loads(ev["relationship"] or "{}")}
          for ev in csv.DictReader(open(ROOT / "registers/schema/registers/EV_evidence_register.csv"))
          if ev["use_role"] == "structural_suitability" and ev["review_state"] != "dropped"]


def ai_file(name):
    """Rows of an AI-written file; none when it is missing or --no-ai is given."""
    path = HERE / "ai-skill-output" / name
    return list(csv.DictReader(open(path))) if path.exists() and "--no-ai" not in sys.argv else []


def write(name, cols, rows):
    with open(HERE / name, "w", newline="") as f:
        out = csv.DictWriter(f, cols, extrasaction="ignore")
        out.writeheader()
        out.writerows(rows)


def num(row, col):
    """A cell as a number, or None when blank. Script rows hold numbers, AI rows hold text."""
    return None if row.get(col) in (None, "") else float(row[col])


def flatten():
    """One row per thing a paper states: numbers in one list, categories in the other."""
    weights = {r["evidence_id"]: r["weight"] for r in csv.DictReader(open(ROOT / "weights/evidence_weights.csv"))}
    ai_rows, ai_cats = defaultdict(list), defaultdict(list)  # a claim can give several rows
    for r in ai_file("rows.csv"):
        ai_rows[r["evidence_id"]].append(r)
    for r in ai_file("categories.csv"):
        ai_cats[r["evidence_id"]].append(r)

    numbers, categories = [], []
    for ev in claims:
        eid = ev["evidence_id"]
        base = {**ev, "family": ev["suitability_family_id"], "weight": weights[eid], "flattened_by": "script"}
        rel = dict(ev["rel"])
        # a plain range is a pair of hard limits; a bare threshold only counts as an upper cut-off
        rel.setdefault("abs_min", rel.get("lower"))
        rel.setdefault("abs_max", rel.get("upper"))
        if rel.get("direction") == "exclude_above":
            rel["abs_max"] = rel.get("threshold")
        rel["seen_min"], rel["seen_max"] = rel.get("observed_min"), rel.get("observed_max")
        # note: the register reads "751 – 1 000 mm" as 751 to 1; drop the broken top end
        if isinstance(rel["seen_min"], (int, float)) and isinstance(rel["seen_max"], (int, float)) \
                and rel["seen_max"] < rel["seen_min"]:
            rel["seen_max"] = None
        nums = {k: rel[k] for k in NUMS if isinstance(rel.get(k), (int, float))}
        cats = [(c, status) for key, status in LISTS.items() for c in rel.get(key) or []]
        if nums:
            observed = "seen_min" in nums or "seen_max" in nums
            numbers.append({**base, **nums, "unit": UNITS.get(rel.get("unit"), rel.get("unit")),
                            "basis": "observed" if observed else "stated"})
        elif cats:  # category labels on a numeric claim only repeat its numbers, so skip those
            categories += [{**base, "category": category, "status": status} for category, status in cats]
        if not nums:
            numbers += [{**base, **row, "unit": UNITS.get(row["unit"], row["unit"]), "flattened_by": "ai"}
                        for row in ai_rows[eid]]
        if not cats:
            categories += [{**base, **row, "flattened_by": "ai"} for row in ai_cats[eid]]

    shared = ["weight", "claim_scope", "taxon", "source_id", "evidence_id", "flattened_by", "reason"]
    write("trace/thresholds.csv", ["nbs_id", "family", "variable", "unit", "basis", *NUMS, "classes", *shared], numbers)
    write("trace/categories.csv", ["nbs_id", "family", "variable", "category", "status", *shared], categories)
    return numbers, categories


def weighted_middle(pairs):
    """Value at which half the total weight is reached; the lower one on an exact tie."""
    pairs = sorted(pairs)
    half = sum(w for _, w in pairs) / 2
    acc = 0
    for value, w in pairs:
        acc += w
        if acc >= half:
            return value


def kind(row):
    if row.get("opt_low") or row.get("opt_high"):
        return "curve"
    if any(row.get(s) not in (None, "", "none") for s in ("abs_min", "abs_max")):
        return "gate"
    return "observed" if row.get("seen_min") or row.get("seen_max") else "no limit"


def combine_numbers(numbers):
    general = {}
    for g in ai_file("general_limits.csv"):
        sides = [g[s] for s in ("abs_min", "abs_max") if g[s]]
        [float(v) for v in sides if v != "none"]  # note: a bad number stops the build here
        if not sides or not g["mechanism"]:
            raise SystemExit(f"general_limits.csv: {g['family']} {g['variable']} needs a limit and a mechanism")
        general[g["nbs_id"], g["family"], g["variable"], g["unit"]] = g

    # how many of a practice's papers report each variable at all, whether or not it gave a usable number
    papers, mentions, cases = defaultdict(set), defaultdict(set), defaultdict(set)
    for ev in claims:
        papers[ev["nbs_id"]].add(ev["source_id"])
        mentions[ev["nbs_id"], ev["variable"]].add(ev["source_id"])
        # a documented case reports the same fixed list of site conditions every time, so count it apart
        if ev["rel"].get("type") == "observed_presence":
            cases[ev["nbs_id"], ev["variable"]].add(ev["source_id"])

    def mention_cols(nbs_id, variable):
        n = len(mentions[nbs_id, variable])
        return {"n_papers": n, "pct_of_papers": round(100 * n / len(papers[nbs_id])) if n else 0,
                "n_cases": len(cases[nbs_id, variable])}

    groups = defaultdict(list)
    for r in numbers:
        groups[r["nbs_id"], r["family"], r["variable"], r["unit"]].append(r)

    cols = ["nbs_id", "family", "variable", "unit", "kind", *PARAMS, "n_sources", "spread", "seen_min", "seen_max",
            "n_observed", "conflict", "general", "mechanism", "n_papers", "pct_of_papers", "n_cases",
            "source_classes", "evidence_ids"]
    table = []
    for key, rows in sorted(groups.items()):
        row = dict(zip(cols, key))
        stated = [r for r in rows if r["basis"] == "stated"]
        observed = [r for r in rows if r["basis"] == "observed"]
        spread = []
        for p in PARAMS:
            by_source = defaultdict(list)
            for r in stated:
                if num(r, p) is not None:
                    by_source[r["source_id"]].append((num(r, p), float(r["weight"])))
            if not by_source:
                continue
            # the low side takes a source's lowest value and the high side its highest, so no number is invented
            widest = min if p in ("abs_min", "opt_low") else max
            votes = [(widest(v for v, _ in c), max(w for _, w in c)) for c in by_source.values()]
            # hard limits: the widest any source states. optimum: the weighted middle across sources
            row[p] = widest(v for v, _ in votes) if p.startswith("abs") else weighted_middle(votes)
            lo, hi = min(v for v, _ in votes), max(v for v, _ in votes)
            if lo != hi:
                spread.append(f"{p} {lo:g}-{hi:g}")
        # observed cases are kept apart from stated limits: the full range where it was seen working
        lows = [num(r, "seen_min") for r in observed if num(r, "seen_min") is not None]
        highs = [num(r, "seen_max") for r in observed if num(r, "seen_max") is not None]
        if lows:
            row["seen_min"] = min(lows)
        if highs:
            row["seen_max"] = max(highs)

        values = [row[p] for p in PARAMS if p in row]
        conflict = []
        if values != sorted(values):  # sources that disagree can give limits in the wrong order
            conflict.append("limits out of order")
        if (lows and "abs_min" in row and min(lows) < row["abs_min"]) or \
           (highs and "abs_max" in row and max(highs) > row["abs_max"]):
            conflict.append("seen working outside the limits")
        g = general.pop(key, None)
        if g:
            nums = values + lows + highs
            used = []
            for side, outside in (("abs_min", lambda v: min(nums) < v), ("abs_max", lambda v: max(nums) > v)):
                if g[side] not in ("", "none") and nums and outside(float(g[side])):
                    conflict.append(f"evidence outside general {side} {g[side]}")
                elif g[side] and side not in row:
                    row[side] = g[side]
                    used.append(side)
            row["general"] = " ".join(used)  # which sides came from general knowledge
            row["mechanism"] = g["mechanism"]
        row["kind"] = kind(row)
        row["n_sources"] = len({r["source_id"] for r in stated})
        row["n_observed"] = len({r["source_id"] for r in observed})
        row["spread"] = "; ".join(spread)
        row["conflict"] = "; ".join(conflict)
        row["source_classes"] = " | ".join(sorted(f"{r['source_id']}: {r['classes']}" for r in rows if r.get("classes")))
        row["evidence_ids"] = " ".join(sorted(r["evidence_id"] for r in rows))
        table.append({**row, **mention_cols(key[0], key[2])})
    # general limits for cells no paper gives a number for
    for key, g in sorted(general.items()):
        row = {**dict(zip(cols, key)), "abs_min": g["abs_min"], "abs_max": g["abs_max"], "n_sources": 0,
               "n_observed": 0, "general": " ".join(s for s in ("abs_min", "abs_max") if g[s]),
               "mechanism": g["mechanism"], **mention_cols(key[0], key[2])}
        table.append({**row, "kind": kind(row)})
    write("t4.csv", cols, table)


def combine_categories(categories):
    # one vote per source for each status, at its best weight
    votes = defaultdict(lambda: defaultdict(dict))
    for r in categories:
        by_source = votes[r["nbs_id"], r["family"], r["variable"], r["category"].strip().lower()][r["status"]]
        by_source[r["source_id"]] = max(float(r["weight"]), by_source.get(r["source_id"], 0))

    cols = ["nbs_id", "family", "variable", "category", "verdict", "included", "excluded", "n_observed", "conflict"]
    table = []
    for key, v in sorted(votes.items()):
        inc, exc = sum(v["included"].values()), sum(v["excluded"].values())
        verdict = "excluded" if exc > inc else "included" if inc > exc else "conflict" if inc else "observed"
        table.append({**dict(zip(cols, key)), "verdict": verdict, "included": round(inc, 4), "excluded": round(exc, 4),
                      "n_observed": len(v["observed"]), "conflict": "yes" if inc and exc else ""})
    write("t4_categories.csv", cols, table)


def importance():
    """Weights are ranked inside one paper, never compared between papers."""
    rows, fields = [], defaultdict(set)
    for ev in claims:
        for field, weight in ev["rel"].items():
            # "normalized" fields restate another weight field of the same claim
            if "weight" in field.lower() and "normalized" not in field and isinstance(weight, (int, float)):
                # some papers put the variable name in the field: AHP_weight_SOC -> ahp_weight
                field = "ahp_weight" if field.startswith("AHP_weight_") else field
                rows.append({"nbs_id": ev["nbs_id"], "family": ev["suitability_family_id"],
                             "source_id": ev["source_id"], "variable": ev["variable"], "weight": weight,
                             "weight_field": field, "evidence_id": ev["evidence_id"]})
                fields[ev["source_id"]].add(field)

    groups = defaultdict(list)  # one paper's weights for one practice family
    for r in rows:
        groups[r["nbs_id"], r["family"], r["source_id"]].append(r)

    for (_, _, source_id), group in groups.items():
        variables = [r["variable"] for r in group]
        if len(fields[source_id]) > 1:
            note = "no: weights at different levels of the paper's model"
        elif len(set(variables)) < len(variables):
            note = "no: several weights for one variable"
        elif len(group) < 2:
            note = "no: only one variable weighted"
        else:
            note = "yes"
        for r in group:
            r["comparable"] = note
            if note == "yes":
                # size matters, not sign: a negative weight is a direction, not low importance
                r["rank"] = 1 + sum(abs(o["weight"]) > abs(r["weight"]) for o in group)
                r["n_ranked"] = len(group)

    write("trace/importance.csv", ["nbs_id", "family", "source_id", "variable", "weight", "weight_field", "rank",
                             "n_ranked", "comparable", "evidence_id"],
          sorted(rows, key=lambda r: (r["nbs_id"], r["source_id"], r["family"], r.get("rank", 99))))


numbers, categories = flatten()
# species and crop claims don't set practice limits
combine_numbers([r for r in numbers if r["claim_scope"] == "practice_technology"])
combine_categories([r for r in categories if r["claim_scope"] == "practice_technology"])
importance()

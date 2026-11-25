"""Turn the T4 tables into the curve and gate files the runtime reads.

<out>/<practice>/<family>/<variable>.json  one curve: from the papers' class tables when they have them,
                                           else score 0 at a hard limit and 1 across the optimum
<out>/<practice>/<family>/gates.json       hard limits with no optimum, and allowed / ruled-out classes

Run from the evidence repo root, after t4/build.py: python3 t4/curves.py [out folder]
The out folder defaults to t4/curves.
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "curves"


def read(name):
    return list(csv.DictReader(open(HERE / name)))


def num(text):
    """A limit as a number. Blank (nobody said) and "none" (no limit) both leave that side open."""
    return None if text in ("", "none") else float(text)


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


# class labels, worst to best. A table's classes are spread evenly: best is 1, an unsuitable class is 0.
RANK = {"very low": 1, "very poor": 1, "s4": 1, "less suitable": 1.5, "marginally suitable": 2, "marginal": 2,
        "low": 2, "poor": 2, "s3": 2, "moderately suitable": 3, "moderate": 3, "medium": 3, "s2": 3, "high": 4,
        "good": 4, "suitable": 4, "strong": 4, "very high": 5, "very good": 5, "very strong": 5,
        "highly suitable": 5, "optimally suitable": 5, "most suitable": 5, "s1": 5,
        "not suitable": 0, "unsuitable": 0, "excluded": 0, "s5": 0}
NUMBER = r"-?\d+(?:\.\d+)?"
RANGE = re.compile(rf"[<>≤≥]?=?\s*(?P<a>{NUMBER})(?:\s*[-–]\s*(?P<b>{NUMBER}))?\s*\D*")


def rank(label):
    """A label's place in its table: a known word, or a bare number (higher read as better). None if neither."""
    label = re.sub(r"\(.*?\)", "", label).strip().lower()
    if re.fullmatch(NUMBER, label):
        return float(label)
    if label == "n":
        return 0
    words = [w for w in sorted(RANK, key=len, reverse=True) if re.search(rf"\b{w}\b", label)]
    return RANK[words[0]] if words and "given" not in label else None


def class_points(text):
    """A class table as (x, score) points: the middle of each class, or its bound when open-ended.

    None when any class cannot be read, so a half-read table never makes a curve.
    """
    classes = []
    for entry in text.split(";"):
        span, _, label = entry.rpartition("=")
        if span.strip() == "N":  # a class the paper names but gives no range for
            continue
        for part in span.split(" or "):  # "7.2-7.4 or 4.6-5.5" is one class in two places
            m = RANGE.fullmatch(part.strip())
            if not m or rank(label) is None:
                return None
            a, b = float(m["a"]), float(m["b"] or m["a"])
            classes.append((round((a + b) / 2, 6), rank(label)))
    xs = [x for x, _ in classes]
    suitable = sorted({r for _, r in classes if r > 0})
    if len(set(xs)) < len(xs) or len({r for _, r in classes}) < 2:
        return None
    return sorted((x, (suitable.index(r) + 1) / len(suitable) if r else 0.0) for x, r in classes)


def at(points, x):
    """Score at x: straight lines between points, flat beyond the first and last."""
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return points[0][1] if x < points[0][0] else points[-1][1]


def class_shape(papers, lo, hi):
    """One curve from several papers' class tables, with how far the papers disagree.

    The score runs down to 0 at each hard limit, so the limits are part of the curve.
    """
    xs = sorted({x for p in papers.values() for points in p["tables"] for x, _ in points})
    # one vote per paper (the mean of its own tables), then the weighted mean across papers
    votes = [([sum(at(t, x) for t in p["tables"]) / len(p["tables"]) for x in xs], p["weight"]) for p in papers.values()]
    total = sum(w for _, w in votes)
    shape = {"x": xs, "score": [round(sum(ys[i] * w for ys, w in votes) / total, 3) for i in range(len(xs))]}
    if len(votes) > 1:
        shape["low"] = [round(min(ys[i] for ys, _ in votes), 3) for i in range(len(xs))]
        shape["high"] = [round(max(ys[i] for ys, _ in votes), 3) for i in range(len(xs))]
    inside = [i for i, x in enumerate(xs) if (lo is None or x > lo) and (hi is None or x < hi)]
    for key, edge in (("x", None), ("score", 0.0), ("low", 0.0), ("high", 0.0)):
        if key in shape:
            ends = [lo if edge is None else edge] * (lo is not None), [hi if edge is None else edge] * (hi is not None)
            shape[key] = ends[0] + [shape[key][i] for i in inside] + ends[1]
    return shape if inside else None


def limit_shape(r, lo, hi):
    """Score 0 at a hard limit and 1 across the optimum. None when the limits are out of order."""
    points = [(lo, 0.0), (num(r["opt_low"]), 1.0), (num(r["opt_high"]), 1.0), (hi, 0.0)]
    points = [(x, y) for x, y in points if x is not None]
    # where a hard limit equals the optimum, keep the optimum; valid_range still cuts the score off
    points = [p for p in points if p[1] == 1.0 or all(q[0] != p[0] for q in points if q[1] == 1.0)]
    xs = sorted({x for x, _ in points})
    if "limits out of order" in r["conflict"] or [x for x, _ in points] not in (xs, [xs[0], xs[0]]):
        return None
    points = sorted(set(points))
    return {"x": [x for x, _ in points], "score": [y for _, y in points]}


# (practice, family, variable, unit) -> paper -> its readable class tables and its weight
tables = defaultdict(lambda: defaultdict(lambda: {"tables": [], "weight": 0.0}))
unread = []
for r in read("trace/thresholds.csv"):
    if r["classes"] and r["claim_scope"] == "practice_technology":
        points = class_points(r["classes"])
        if points:
            paper = tables[r["nbs_id"], r["family"], r["variable"], r["unit"]][r["source_id"]]
            paper["tables"].append(points)
            paper["weight"] = max(paper["weight"], float(r["weight"]))
        else:
            unread.append(f"{r['evidence_id']}: {r['classes']}")

paper_of = {r["evidence_id"]: r["source_id"] for r in read("trace/thresholds.csv")}

# a paper's weights only compare inside that paper, so turn each into its share of the paper's total
by_paper = defaultdict(list)
for r in read("trace/importance.csv"):
    if r["comparable"] == "yes":
        by_paper[r["nbs_id"], r["family"], r["source_id"]].append(r)
shares = defaultdict(dict)  # (practice, family, variable) -> paper -> share
for (nbs_id, family, paper), rows in by_paper.items():
    total = sum(abs(float(r["weight"])) for r in rows)
    for r in rows:
        shares[nbs_id, family, r["variable"]][paper] = round(abs(float(r["weight"])) / total, 3)

gates = defaultdict(list)  # (practice, family) -> gate entries
seen, skipped, n_curves = set(), [], 0
# the row with the most sources gets the plain file name when a variable comes in two units
for r in sorted(read("t4.csv"), key=lambda r: -int(r["n_sources"])):
    family = r["family"].split("__")[-1]
    lo, hi = num(r["abs_min"]), num(r["abs_max"])
    papers = tables.get((r["nbs_id"], r["family"], r["variable"], r["unit"]))
    shape = class_shape(papers, lo, hi) if papers else None
    if shape:
        shape["built_from"] = "class tables"
    elif r["kind"] == "gate":
        gate = {"name": r["variable"], "variable": r["variable"], "type": "threshold", "unit": r["unit"]}
        gate.update({k: v for k, v in (("min", lo), ("max", hi)) if v is not None})
        gates[r["nbs_id"], family].append(gate)
        continue
    elif r["kind"] != "curve":
        continue  # a seen range or "no limit" gives nothing to score
    else:
        shape = limit_shape(r, lo, hi)
        if not shape:
            skipped.append(f"{r['family']} {r['variable']} ({r['unit']}): limits out of order")
            continue
        shape["built_from"] = "limits"
    name = r["variable"]
    if (r["nbs_id"], family, name) in seen:
        name += "__" + re.sub(r"\W+", "_", r["unit"]).strip("_")
    seen.add((r["nbs_id"], family, r["variable"]))
    share = shares.get((r["nbs_id"], r["family"], r["variable"]), {})
    write(OUT / r["nbs_id"] / family / f"{name}.json", {
        "practice": r["nbs_id"], "family": family, "variable": r["variable"], "unit": r["unit"],
        "shape": "linear",  # straight lines between points, flat beyond the first and last
        **shape,
        "valid_range": [lo, hi],  # no score outside it; null means that side is open
        # mean share of a paper's total weight given to this variable; null when no paper weights it
        "weight": round(sum(share.values()) / len(share), 3) if share else None,
        "pct_of_papers": int(r["pct_of_papers"]),  # share of the practice's papers that report this variable
        "papers": sorted({paper_of[e] for e in r["evidence_ids"].split()}),
    })
    n_curves += 1

classes = defaultdict(lambda: {"yes": [], "no": []})
for r in read("t4_categories.csv"):
    if r["verdict"] in ("included", "excluded"):
        side = "yes" if r["verdict"] == "included" else "no"
        classes[r["nbs_id"], r["family"].split("__")[-1], r["variable"]][side].append(r["category"])
for (nbs_id, family, variable), c in classes.items():
    gates[nbs_id, family].append({"name": variable, "variable": variable, "type": "classes", **c})

for (nbs_id, family), items in sorted(gates.items()):
    write(OUT / nbs_id / family / "gates.json",
          {"practice": nbs_id, "family": family, "gates": sorted(items, key=lambda g: (g["type"], g["name"]))})

print(f"{n_curves} curves and {len(gates)} gate files written to {OUT}")
print("\n".join(["skipped:"] + skipped) if skipped else "nothing skipped")
print("\n".join([f"{len(unread)} class tables could not be read, so those claims use their limits only:"] + unread))

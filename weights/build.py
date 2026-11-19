"""Write evidence_weights.csv: one weight per T4 (suitability) evidence row, with its inputs.

weight = tier_w * basis_w * grey_w

Values copied from CIAT/nbs_ruralscan @ 217513d, src/nbs_ruralscan/recipe/synthesis.py
(TIER_W, BASIS_W, GREY_DISCOUNT, _weight). Rationale: methodology/T4_generation_method.md,
"Credibility scoring" (how a source gets its tier) and sections 5.2 and 6 (how weights are used).

Run: python3 weights/build.py   (from the evidence repo root)
"""
import csv
from pathlib import Path

csv.field_size_limit(10**9)
ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "registers/schema/registers"

TIER_W = {"high": 1.0, "medium": 0.6, "low": 0.35}
BASIS_W = {"primary_measured": 1.0, "table": 0.9, "modelled": 0.7,
           "figure_read": 0.6, "expert_assertion": 0.5, "cited_secondary": 0.4}
GREY_W = 0.9  # grey-literature discount for suitability claims

src = {r["source_id"]: r for r in csv.DictReader(open(REG / "SRC_source_register.csv"))}
cols = ["evidence_id", "source_id", "nbs_id", "variable", "review_state", "benchmark_tier",
        "venue_type", "method_type", "source_category", "claim_basis",
        "tier_w", "basis_w", "grey_w", "weight"]

with open(ROOT / "weights/evidence_weights.csv", "w", newline="") as f:
    out = csv.DictWriter(f, cols, extrasaction="ignore")
    out.writeheader()
    for ev in csv.DictReader(open(REG / "EV_evidence_register.csv")):
        if ev["use_role"] != "structural_suitability":  # T4 only; other tables need extra factors
            continue
        s = src[ev["source_id"]]
        tier = s["benchmark_tier"].lower()
        # note: an unknown tier or basis raises KeyError; the old code defaulted to 0.5
        tw, bw = TIER_W[tier], BASIS_W[ev["claim_basis"]]
        gw = GREY_W if s["source_category"] == "grey" else 1.0
        out.writerow({**ev, **s, "benchmark_tier": tier, "tier_w": tw, "basis_w": bw,
                      "grey_w": gw, "weight": round(tw * bw * gw, 4)})

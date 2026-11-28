---
name: t4-expert
description: Review the T4 suitability table the way a domain expert would. Judge whether each row's limits make sense for the practice, in general or for a named region, and write a verdict and reason per row. Use when asked to sanity-check, validate or review T4, or to check T4 for a region.
---

# Expert review of T4

T4 is the suitability table: for each practice family and variable, what turns a map value into
a 0 to 1 score. It is built by script from many papers, so some rows are wrong: mixed units,
limits in the wrong order, a value that no agronomist or ecologist would accept.

This skill reads every row and says whether it makes sense. It flags. It never changes a value.

Run every command from the evidence repo root.

## 1. Build and read

```sh
python3 t4/build.py
```

Read `t4/t4.csv`. One row is one practice family, variable and unit:

- `abs_min`, `abs_max`: hard limits. Outside them the practice does not work. `none` means no
  limit on that side. Blank means nobody said.
- `opt_low`, `opt_high`: the best range.
- `seen_min`, `seen_max`: where documented cases were seen working. Not a limit.
- `general`: which hard limits came from general knowledge, not from a paper.
- `conflict`: problems the build already found.

If the user names a region, review for that region. If not, review in general and leave
`region` blank.

## 2. Judge each row

Ask of every row:

- **Is it the right kind of number?** Does the size fit the variable and unit? An aridity index
  in the thousands, a slope of 475 or a distance in feet is a sign of a mixed unit or scale.
- **Is the order logical?** `abs_min` ≤ `opt_low` ≤ `opt_high` ≤ `abs_max`.
- **Does it fit the practice family?** Think about how this family works. Terracing wants
  slope, spate irrigation wants almost none, mangroves need tidal flooding.
- **Does it agree with its neighbours?** Compare the same variable across the families of one
  practice, and the same cell in two units (5 percent slope is not 5 degrees).
- **Does it agree with where it was seen working?** A seen range far outside the limits means
  one of them is wrong.
- **For a region:** would the limit wrongly rule out, or wrongly allow, land where the practice
  is known to work or fail there?

To find out why a row looks wrong, look up its `evidence_ids` in `t4/trace/thresholds.csv`, and the
claim's `quote` in `registers/schema/registers/EV_evidence_register.csv`. Say which it is:
the paper really says this, the claim was extracted wrongly, sources measure different things,
or a general limit is off.

## 3. Write `t4/ai-skill-output/review.csv`

Columns: `nbs_id,family,variable,unit,region,verdict,reason,suggestion`

One row for every row of `t4/t4.csv`, copying the first four columns exactly.

- `verdict`:
  - `ok`: a domain expert would accept it.
  - `suspect`: possible, but unusual enough that a person should look.
  - `wrong`: cannot be right as written.
- `reason`: one or two sentences. Required for `suspect` and `wrong`. For `ok`, a few words on
  why are enough.
- `suggestion`: what a person should do, such as "check ev_x: paper gives degrees, row says
  percent" or "widen general abs_max". Name evidence ids where you can. Blank for `ok`.

Rules:

- Do not edit `t4/t4.csv`, the AI files, `t4/ai-skill-output/general_limits.csv` or the register.
- Judge the row as written. Do not guess the "real" value and call the row ok.
- A row with few sources is not wrong for that reason. Judge the numbers.
- When you are unsure, use `suspect` and say what you would need to know.
- A regional review replaces only the rows for that region. Keep rows for other regions and
  the general rows.

## 4. Check and report

```sh
python3 - <<'EOF'
import csv
key = lambda r: (r["nbs_id"], r["family"], r["variable"], r["unit"])
t4 = {key(r) for r in csv.DictReader(open("t4/t4.csv"))}
rows = list(csv.DictReader(open("t4/ai-skill-output/review.csv")))
bad = [r for r in rows if r["verdict"] not in ("ok", "suspect", "wrong") or (r["verdict"] != "ok" and not r["reason"])]
print(len(t4 - {key(r) for r in rows}), "rows not reviewed,", len({key(r) for r in rows} - t4), "unknown rows,", len(bad), "bad rows")
EOF
```

All three counts must be 0. Then report the count of each verdict, every `wrong` row with its
reason, and any pattern that repeats across rows, since one upstream fix may clear many.

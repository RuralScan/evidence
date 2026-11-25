---
name: t4-adjust-curves
description: Adjust existing T4 curve and gate files for a user's region, needs or local knowledge. The user says what they know or want, the skill proposes changes (from the user's knowledge, research it finds, or general knowledge), the user approves each one, and every change is recorded in the file. Use when asked to adapt, tune, localise or modify suitability curves or gates for a region or project.
---

# Adjust T4 curves

The curve files are global. They come from papers across many countries. A user who knows a
region can make them better for that region. This skill helps them do that, one approved
change at a time, with every change written down.

## 1. Set up

Ask the user, if they have not said:

- **Which folder** holds the curve files. Work on the user's own copy. Do not edit
  `t4/curves/` in the evidence repo: `python3 t4/curves.py` rewrites it and the changes would
  be lost. If that is the folder given, say so and ask for a copy.
- **Which practice and family**, and **which region**.
- **What they know or want**: field data, local experience, a paper, or a plain statement such
  as "nobody terraces above 1,200 mm here".

## 2. Read the files

A curve file is `<practice>/<family>/<variable>.json`:

- `x` and `score`: the curve. Straight lines between points, flat beyond the first and last.
  Scores run from 0 (does not work) to 1 (best).
- `valid_range`: the hard limits. No score outside. `null` means that side is open.
- `low`, `high`: how far the papers disagreed. Present only on some files.
- `built_from`, `papers`, `pct_of_papers`, `weight`: where the curve came from.

`gates.json` in the same folder holds pass-or-fail rules: `threshold` gates with `min` and
`max`, and `classes` gates with `yes` and `no` lists.

Show the user the current curve in plain words before proposing anything: where it starts,
where it peaks, where it ends.

## 3. Propose changes

A change is one of: move a point, add or remove a point, change a hard limit, change a gate.
Each proposal names its basis. There are four, and they are not equally strong:

| Basis | What it is | What it needs |
|---|---|---|
| `local data` | The user's own measurements or records | What was measured, where, and how many sites |
| `paper` | A study from or near the region | A link and a word-for-word quote, from a page you opened |
| `user knowledge` | The user's experience | Their statement, in their words |
| `general knowledge` | What you know from training | Say plainly that it is your own knowledge, not a source |

Rules:

- You may search for regional research. Only cite a page you actually opened. Never write a
  citation, number or quote from memory.
- You may suggest a change from general knowledge, such as "this optimum looks high for a
  semi-arid region". Label it as such. Do not dress it up as evidence.
- Prefer a small change the basis supports over a redrawn curve.
- If the user's knowledge contradicts the papers, say so, show both, and let them decide.
- Keep the unit. If the user's numbers are in another unit, convert and show the sum.

## 4. Get approval, then write

Show each proposed change as before and after, with its basis. Write nothing until the user
says yes to that change.

When writing a file:

- Keep `x` rising, with `score` (and `low`, `high` if kept) the same length, all between 0 and 1.
- Keep the curve and `valid_range` in step: the score is 0 at each hard limit.
- If you change `score`, remove `low` and `high`. They described the papers, not the new curve.
- The first time a file is changed, copy its untouched `x`, `score` and `valid_range` into an
  `original` key, so the change can be undone.
- Add one entry per change to an `adjustments` list:

```json
"adjustments": [
  {
    "date": "2026-11-25",
    "region": "Tigray, Ethiopia",
    "change": "abs_max raised from 750 to 1400 mm",
    "basis": "paper",
    "source": "https://… — \"bench terraces are widespread where rainfall exceeds 1,000 mm\"",
    "approved_by": "the user's name"
  }
]
```

For `gates.json`, put `original` and `adjustments` on the gate entry that changed.

## 5. Check and report

```sh
python3 - <folder> <<'EOF'
import json, sys
from pathlib import Path
bad = []
for f in Path(sys.argv[1]).glob("*/*/*.json"):
    d = json.loads(f.read_text())
    if "x" not in d:
        continue
    n = len(d["x"])
    ok = d["x"] == sorted(set(d["x"])) and all(len(d.get(k, d["x"])) == n for k in ("score", "low", "high"))
    ok = ok and all(0 <= s <= 1 for s in d["score"])
    ok = ok and all(a.get("basis") and a.get("change") and a.get("approved_by") for a in d.get("adjustments", []))
    if not ok:
        bad.append(str(f))
print(len(bad), "bad files", *bad, sep="\n")
EOF
```

It must print `0 bad files`. Then list every change made, with its basis, and every proposal
the user turned down. If a change rests on a paper or on local data, tell the user it is worth
sending to the evidence register, so the global curves can learn from it too.

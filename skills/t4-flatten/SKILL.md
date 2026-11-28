---
name: t4-flatten
description: Turn T4 suitability claims that a script cannot parse (class tables, numbers or categories buried in wording) into plain rows, without losing what the paper says. Use when asked to flatten T4 claims, fill t4/ai-skill-output/rows.csv, or extend T4 coverage.
---

# Flatten T4 claims

T4 is the suitability table: for each practice family and variable, what turns a map value into
a 0 to 1 score. Every live claim must end up as a row or in the skipped list with a reason.
Nothing is left unread.

Run every command from the evidence repo root.

## 1. List the claims to do

```sh
python3 t4/build.py && python3 skills/t4-flatten/check.py
```

The check prints one JSON line per claim nothing has accounted for, with its `relationship`,
`quote` and `justification_quote`. Work through them in batches of about 20.

## 2. Decide each claim

Read the quote first, then the relationship. Keep everything the paper states. A claim goes to
one file, except that a claim with both numbers and categories goes to both row files.

### Numbers: `t4/ai-skill-output/rows.csv`

Columns: `evidence_id,unit,basis,abs_min,opt_low,opt_high,abs_max,seen_min,seen_max,classes,reason`

**`basis` = `stated`** when the paper says what is suitable:

- `opt_low`, `opt_high`: the bounds of the best-rated class. If two classes tie for best and
  touch, span both.
- `abs_min`, `abs_max`: where the paper says unsuitable, excluded or zero begins. If the paper
  names no unsuitable class on a side, leave that side blank.
- An open-ended class leaves its open side blank. "< 5" as the best class gives `opt_high` 5 only.
- `classes`: the whole class table, so the middle classes are not lost. One entry per class,
  in the paper's own labels: `<4=very high; 4-7=high; 7-9=medium; >9=low`.

**`basis` = `observed`** when the paper only reports where the practice was seen working or
studied, such as "applied on 1–20% slopes" or a study site's rainfall. Put the range in
`seen_min` and `seen_max` and leave the four limit fields blank. This is weaker than a stated
limit, but it is real data. Keep it.

Rules for both:

- A bound that is only the end of the study area's data range is not a limit. Leave it blank.
- Leave a field blank if the paper does not state it. Never estimate, average or extend.
- `unit`: as the paper states it. Reuse the spelling already in `t4/trace/thresholds.csv` for that
  variable when it is the same unit.
- `reason`: one sentence naming which class or phrase gave each number.

### Categories: `t4/ai-skill-output/categories.csv`

Columns: `evidence_id,category,status,reason`. One row per category.

- `status`: `included` (the paper allows or rates it suitable), `excluded` (the paper rules it
  out) or `observed` (the practice was seen there, with no judgement).
- `category`: copied from the claim text, word for word.

### Skipped: `t4/ai-skill-output/skipped.csv`

Columns: `evidence_id,reason`. Skip only when there is nothing to keep:

- the claim gives a direction but no number or category ("steeper is worse");
- a number would need converting to match the paper's own unit (say which conversion);
- the classes describe the input data, not suitability for the practice;
- the quote does not support the relationship;
- the claim only ranks or weights the variable.

When a claim could be read two ways, take the reading the quote supports and say so in `reason`.
When the quote supports neither, skip. A wrong row costs more than a missing one.

## 3. Check

```sh
python3 skills/t4-flatten/check.py
```

It fails any row whose numbers or categories are not printed in the claim text, whose numbers
are out of order, or that lacks a reason. Fix every error. Do not edit the check to pass a row.
The pass is finished when it reports `0 to do, 0 errors`.

## 4. Rebuild

```sh
python3 t4/build.py
```

Report the rows added, the claims skipped by reason, and any row in `t4/t4.csv` or
`t4/t4_categories.csv` with `conflict` set. A person reviews the three AI files before they
are committed.

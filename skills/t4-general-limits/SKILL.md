---
name: t4-general-limits
description: Write general-knowledge hard limits for T4 (where a practice physically cannot work, and why) to fill the sides the papers leave blank. Use when asked for sensible bounds, mechanistic limits, general limits, or to fill gaps in t4/t4.csv.
---

# General limits for T4

T4 is the suitability table: for each practice family and variable, what turns a map value into
a 0 to 1 score. Papers often give an optimum but no hard limit, or only one side. This skill
writes the missing hard limits from general knowledge, each with the reason it exists.

These rows are not evidence. They only fill a side the papers leave blank, and `t4/t4.csv`
labels every limit that came from here.

Run every command from the evidence repo root.

## 1. See what is missing

```sh
python3 t4/build.py
```

Look at `t4/t4.csv` for which sides are blank and which units are used. Write a row for:

- every row there with a blank `abs_min` or `abs_max`, when a real physical limit exists;
- for every practice family, the basics if they have no row yet: `slope`,
  `annual_precipitation`, `mean_annual_temperature`, `elevation`, `soil_depth_to_bedrock`,
  `soil_ph`;
- anything the practice cannot exist without, such as tidal flooding for mangroves or a
  watercourse for a riparian buffer.

Categories (land cover, soil texture) are out of scope.

## 2. Write `t4/ai-skill-output/general_limits.csv`

Columns: `nbs_id,family,variable,unit,abs_min,abs_max,mechanism`

- `abs_min`, `abs_max`: a number, `none`, or blank.
  - A number: below or above this the practice cannot work.
  - `none`: there is no limit on this side. Rainfall has no upper limit for a wetland.
  - Blank: you do not know. Blank is the honest default.
  - `none` on both sides means the variable does not matter for this practice.
  - A row with only `none` in it is fine, and useful.
- `mechanism`: one sentence saying why the limit exists, in physical or biological terms.
  "Trees die where the soil freezes for most of the year", not "low temperature is unsuitable".
- `unit`: the unit that row already has in `t4/t4.csv`. If the cell has rows in two units,
  write one row per unit. For a new cell, use the spelling `t4/t4.csv` already has for that
  variable in another family (`mm`, `pH`). Failing that, use `canonical_unit` from
  `registers/schema/registers/VONT_variable_ontology.csv`.

Rules:

- Hard limits only. Never write an optimum. That is the papers' job.
- Set limits wide. The limit is where the practice fails outright, not where it gets harder.
  When two values seem defensible, take the wider one.
- Think about the practice family, not the practice in general. Rooftop water harvesting does
  not care about slope. Terracing needs it.
- If you cannot name the mechanism, leave the row out.
- Leave out any row whose unit is unclear (`not stated`, or an index defined by one paper).
- Do not read the evidence values first and set the limit to match. The limit must stand on
  its own, so the check in step 3 means something.

## 3. Check against the evidence

```sh
python3 t4/build.py
```

The build fills the blank sides and adds new rows for cells no paper covers. It sets `conflict`
to `evidence outside general abs_min` (or `abs_max`) when a paper states a limit, an optimum or
a seen range beyond your limit. For each one, look at the row:

- if the evidence is plainly right, widen or remove your limit;
- if the evidence looks wrong (mixed units, a typo, a different meaning of the variable),
  keep your limit and list it in the report.

Never narrow or drop evidence to clear a conflict.

## 4. Report

Say how many rows were written, how many sides of `t4/t4.csv` they filled, how many new rows
they added, and every conflict left with a one-line reason. A person with domain knowledge
reads `t4/ai-skill-output/general_limits.csv` before it is committed.

# T4

T4 is the suitability table. For each practice family and variable it says what turns a map value
into a 0 to 1 score: a curve, a hard limit, or a list of allowed classes.

## Rebuild

Run from the evidence repo root.

```sh
python3 weights/build.py   # source-quality weight per claim
python3 t4/build.py        # the T4 tables (add --no-ai to ignore the AI files)
python3 t4/curves.py       # generate curve and gate files for the runtime
```

## What is here

| Path                | What it is                                                                              |
| ------------------- | --------------------------------------------------------------------------------------- |
| `t4.csv`            | The core table for number variables: limits, optimum, where it was seen working         |
| `t4_categories.csv` | The core table for class variables such as land cover                                   |
| `curves/`           | One JSON file per curve plus `gates.json` per family. These are built from above 2 CSVs |
| `ai-skill-output/`  | Written by the AI skills. Kept, and read by a person before commit                      |
| `trace/`            | Rebuilt every run. One row per claim, to trace a T4 number back to its paper            |

## Scripts or skills?

**Scripts build T4. Skills enhance it.**
- **Scripts** are plain Python. Run them any time. They give the same tables every run and need no
  AI. On their own they give a thinner T4, built only from claims a script can read.
- **Skills** are instructions an AI follows. Use them to enhance the data: they read the claims a
  script cannot, fill in missing hard limits, and review the result. Their output is saved in
  `ai-skill-output/`, so the next script run picks it up without calling an AI again.

|                             | Scripts only (`--no-ai`) | With the skills' output |
| --------------------------- | ------------------------ | ----------------------- |
| Rows in `t4.csv`            | 75                       | 208                     |
| Rows in `t4_categories.csv` | 106                      | 324                     |

## The skills

They live in `skills/`. In Claude Code, ask for one by name, such as "run the t4-flatten skill".

| Skill                   | What it adds                                                               | Run it when                  | Writes                                      |
| ----------------------- | -------------------------------------------------------------------------- | ---------------------------- | ------------------------------------------- |
| **`t4-flatten`**        | Claims with numbers or classes buried in wording or class tables           | the register has new claims  | `rows.csv`, `categories.csv`, `skipped.csv` |
| **`t4-general-limits`** | Hard limits no paper states, from general knowledge, each with a reason    | T4 has new blank hard limits | `general_limits.csv`                        |
| **`t4-expert`**         | A verdict per row: does this limit make sense, in general or for a region? | you want T4 sanity-checked   | `review.csv`                                |
| **`t4-adjust-curves`** | Changes to curve and gate files for a region or project, each approved by the user and recorded in the file | a user wants to adapt the curves to what they know | the user's own copy of `curves/` |

To enhance the data, run in this order:
1. `python3 t4/build.py`
2. the `t4-flatten` skill
3. the `t4-general-limits` skill
4. `python3 t4/build.py && python3 t4/curves.py`
5. the `t4-expert` skill, to review the result

`t4-adjust-curves` is different from the other three. It is for whoever uses the curves, not for
building them. It works on a copy, because `curves.py` rewrites `t4/curves/` on every run.

A person reads the files in `ai-skill-output/` before they are committed. Skills do not give
identical output on every run, so the saved files are the record.

`review.csv` only flags rows. Nothing reads it, so a review never changes a number.

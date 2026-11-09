# Record a private evidence run

Use one directory for a bounded run. Keep the search captures, screening worksheet, acquisition receipt, extraction worksheet, model prompts and checked outputs you have permission to retain. The run record lists the files and hashes their bytes. It can be checked again after moving the directory to another machine.

## Describe the stages

Create a private JSON description with a run ID, scope, limits and ordered stages. A stage names its mode, instructions, inputs, outputs and applicable entries from the [ruleset catalog](../../rulesets/README.md). Use `workbench/` for paths relative to this evidence checkout and `run/` for paths inside the private run directory. Use stable copies and keep the workbench revision with your records. For policy outside the bounded catalog, include the exact instruction file and revision actually used. An empty ruleset list means no catalog entry was claimed for that stage.

The example below records one assisted screening stage. Replace the example values with the provider, exact model identifier and files from the run. Retain query parameters, model settings, checks and unresolved holds alongside the worksheets. Use references to sensitive material only where its retention is authorised. A run with missing inputs or an unavailable prompt should be reported as incomplete.

```json
{
  "run_id": "terrace-screening-example",
  "scope": "Screen a fixed selection of bench-terrace rainfall sources for T4.",
  "limits": "Stock sources only. One seasonal observation needs further review.",
  "stages": [{
    "name": "screen captured sources",
    "mode": "ai-assisted",
    "provider": "provider-used",
    "model": "model-version-used",
    "prompt": "run/screening-prompt.txt",
    "instructions": ["workbench/workflows/discovery/README.md", "run/screening-prompt.txt"],
    "rulesets": ["terrace_discovery"],
    "inputs": ["run/plan.json", "run/capture.json"],
    "outputs": ["run/decisions.json", "run/screening-checks.json"]
  }]
}
```

Use `manual` when a person made the decisions and `replay` when a stored example or recorded decision was rerun. These two modes omit provider, model and prompt. An adapted task brief or a reconstructed prompt cannot establish which text was sent during an earlier run. The [four-stage terrace description](../../examples/terrace-rainfall/run-description.json) gives a complete replay example.

## Create and verify

Run from the evidence repository root with Python 3.9 or later. Choose a private working directory outside Git. Paths identify individual regular files. Finish writing them before recording the run.

```sh
python3 -IB workflows/run_record/record.py create --run-dir "$work" --description "$work/description.json"
python3 -IB workflows/run_record/record.py verify --run-dir "$work" --sha256 "$digest"
```

The first command creates `run-record.json` once and prints its digest. Keep that value separately and use it as `$digest` on the second command. To verify elsewhere, transfer the private run directory and use the matching workbench files. Missing, redirected or changed files stop the check. Running `verify` without an expected digest compares files with the supplied record but cannot detect someone replacing both. The record captures the operator’s account of the work and the files available at capture time. Scientific eligibility, review and submission stay in CIAT.

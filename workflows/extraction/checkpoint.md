# Preserve a staged extraction batch

Use this before transferring a set of pending proposals. Select the unit lists in their intended intake order. The checkpoint keeps their original bytes, records where each occurrence appeared, and compares it with the evidence register at an explicit CIAT commit. Review, correction and registration continue in CIAT.

## Capture and restore

From the evidence repository root, use Python 3.12, Git with `--no-lazy-fetch`, and a local CIAT clone with the required commits and register blobs. Choose a private location outside Git for the archive and receipt. The archive may contain source extracts. The following example uses two committed historical batches so a new operator can reproduce the comparison without access to anyone’s pending files.

```sh
repo=/path/to/nbs_ruralscan
work=$(mktemp -d)
base=a98aea14b76805a1e16921ed4dd5d5a5d0cff521
later=7a15f5d747cf9f0679374cf5b16d39e844d4685e
tool=workflows/extraction/checkpoint.py
mkdir -p "$work/input/forest" "$work/input/coast"
git -C "$repo" show 23ce026d885f3a29a272ec693d4d10bf9bf8bf55:pipeline/t4_audit/forest_restoration/first_pass_2026-10-28/evidence_staging.json > "$work/input/forest/units.json"
git -C "$repo" show c4d5da63365a6c5c1bb263733438447b1b46f0b1:methodology/audits/mangrove_coastal_effects_20261030/staged_units.json > "$work/input/coast/units.json"

python3 "$tool" capture --ciat-repo "$repo" --revision "$base" \
  --staging-dir "$work/input" --units forest/units.json coast/units.json \
  --bundle "$work/pending.zip" > "$work/capture.json"
digest=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["archive_sha256"])' "$work/capture.json")
python3 "$tool" verify --ciat-repo "$repo" --bundle "$work/pending.zip" \
  --sha256 "$digest" --at "$later" --export-to "$work/restored"
diff -ru "$work/input" "$work/restored/staging"
```

At the first revision, six of the nine proposal IDs are absent, one matches the stored fields and two have different attribution. At the later revision, seven match and the same two differ. Two coastal proposals also carry historical soft drops. Both match stored fields, yet CIAT’s new-intake gate rejects their staged review state. The checkpoint flags both and preserves the originals. The two files restore byte-for-byte. To inspect positions, changed field names and possible passage collisions locally, add `--details`. Omit `--at` to verify only the original comparison. Keep the SHA-256 receipt separately and use a new destination for each archive or export.

## Interpret a checkpoint

- **Unregistered ID** means the identifier is absent from the pinned register. The central intake checks still need to confirm source identity, verbatim text, scope, numerical provenance and eligibility. [Validate staged proposals](README.md)
- **Registered fields match** compares the staged fields with the corresponding register fields. Live review owns the stored approval and quarantine flags; they are excluded from this field comparison. The detailed receipt identifies a stored soft drop.
- **Registered fields differ** lists the fields to reconcile. Attribution can change during prior review. Consult the existing record and its history before proposing a correction.
- **Repeated IDs and overlapping passages** are flags and may overlap the above categories. Counts distinguish distinct IDs from occurrences across all selected files. The passage check uses the handoff’s source, scope and locator rules.
- **Malformed and empty batches** retain their original bytes. An empty unit list can accompany a completed inspection that produced only holds. A successful archive verification confirms preservation, including malformed input.
- Selecting a file named `staging.json` also captures an adjacent `inventory.json` when present. Add other selected JSON receipts with `--companion`. Companion contents are preserved as supplied; the operator reviews their coverage and decisions. Unselected staging directories, source documents and live decision stores are outside this checkpoint.

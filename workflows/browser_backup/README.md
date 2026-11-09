# Rehearse a browser draft restore

Use this when moving review drafts or dashboard feedback between browser profiles or addresses. The rehearsal reads an exported JSON backup, restores it into disposable memory, retries, then exports and restores the combined result. It checks every captured storage key and value, including whitespace inside a saved note. Only counts, pinned revisions and the outcome appear in the receipt. CIAT remains the place to review or submit evidence decisions.

## Try the example

From the evidence repository root, use Python 3.9 or newer, Node.js 18 or newer on PATH, and Git. The example fetches the pinned CIAT backup implementation and batch index. For an offline run, append `--ciat-repo /path/to/nbs_ruralscan` using a local clone with the pinned objects and Git supporting `--no-lazy-fetch`.

```sh
python3 -IB workflows/browser_backup/check.py --example
```

The source has nine saved entries, including active and cleared feedback, reviewer settings, a batch draft and two historical T4 tools. The receiving backup has two entries. One already matches and one exists only at the destination. The first restore installs eight. The retry installs zero. The merged values survive another export and restore.

## Check copies from two browsers

1. In the original browser profile, open **Browser review backup** at `review/browser-backup.html` on the exact dashboard address where drafts were entered. Choose **Download backup**. Record the profile, scheme, host, port and notebook revision privately. Repeat for each relevant profile and address. The active batch index controls which drafts the page exports. Use the original notebook revision when recovering a retired batch. [CIAT browser backup instructions](https://github.com/CIAT/nbs_ruralscan/blob/ece8d8226fed4a0b04d155888a8b4925d8f35386/docs/REVIEWER_GUIDE.md#move-review-drafts-between-browser-profiles-or-addresses)
2. Download a separate backup from the receiving profile at its dashboard address. Keep both private, outside Git. They can contain reviewer names, notes and screenshots. A downloaded HTML feedback report or review CSV serves a different purpose. Use the JSON from **Download backup** here.
3. Point the rehearsal at those two files and the exact CIAT commit supplying the **receiving** notebook’s batch index. Use a local clone containing both that commit and the pinned backup implementation.

```sh
repo=/path/to/nbs_ruralscan
private=/path/to/private/exports
revision=ece8d8226fed4a0b04d155888a8b4925d8f35386
python3 -IB workflows/browser_backup/check.py --ciat-repo "$repo" \
  --index-revision "$revision" --backup "$private/source.json" \
  --destination "$private/receiving.json"
```

Omitting `--destination` models empty storage. Use the receiving backup to test for existing drafts. The default index comes from the pinned engine revision shown above. A receipt describes only the entries the selected browser exported. It cannot find drafts omitted by that profile or index. An empty backup can therefore pass.

| Outcome | Interpretation and next action |
|---|---|
| Successful receipt | `installed` counts previously absent keys, `already_present` counts identical saved values and `retry_installed` should be zero. One key can hold many votes or feedback notes. Retain both original backups. |
| `destination_conflict` | Both exports contain the same key with different stored text. Neither wins automatically. Keep both copies and reconcile in CIAT. |
| `source_batch_archived` or `destination_batch_archived` | The receiving index lists a batch in its archive. Rehearse with the revision where it was active and recover it separately. |
| `invalid_source` or `invalid_destination` | Check the backup format, nested value types and receiving batch index. Unknown keys, repeated entries and unrecognised batches stop the run. |

The preview never opens a browser or contacts a review server. For an actual transfer, follow CIAT’s instructions for the matching server files and browser restore order. For server decisions and downloaded CSVs use the [review record guide](../../handbook/review-records.md).

## Rerun the checks

```sh
python3 -IB workflows/browser_backup/check.py --self-test --ciat-repo "$repo"
```

This runs CIAT’s pinned tests, including a storage-quota failure partway through restoration, and the evidence workbench’s receipt and privacy tests. The rehearsal uses the pinned browser implementation for every restore. Choosing an alternate index changes only the batch list. [Pinned implementation](https://github.com/CIAT/nbs_ruralscan/blob/ece8d8226fed4a0b04d155888a8b4925d8f35386/docs/review/browser-backup.js)

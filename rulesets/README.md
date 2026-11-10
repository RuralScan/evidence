# Which instructions apply to the terrace example?

Use the search record or proposed evidence unit’s ruleset stamp to find its archive. The public exercise and the historical records it examines used different versions. Each catalog entry names a CIAT commit and includes the SHA-256 of every file in that version’s archive directory. [Instruction catalog](catalog.json)

| Part of the example | Archived version | What the version identifies |
|---|---|---|
| Discovery and screening exercise | [v1.8.1](https://github.com/CIAT/nbs_ruralscan/tree/1773e86e76d45ec7a61f8fbd3673047f9601072d/.agents/skills/_versions/v1.8.1) | Bounded discovery, screening rubric and search protocol. |
| Newly staged terrace worksheet | [v1.9.9](https://github.com/CIAT/nbs_ruralscan/tree/157a26c2729c05cccf2b1d9374a63e28c97acac6/.agents/skills/_versions/v1.9.9) | PDF extraction instructions used by the public exercise. |
| Historical seasonal rainfall claim | [v1.5.1](https://github.com/CIAT/nbs_ruralscan/tree/2023cb82c94a93120600a7feb17d8cd1e12ce54f/.agents/skills/_versions/v1.5.1) | Stamp on the registered GIS siting claim. The archive contains the extraction skill and command. |
| Historical stone-line and bench-terrace claims | [v1.6.0](https://github.com/CIAT/nbs_ruralscan/tree/2023cb82c94a93120600a7feb17d8cd1e12ce54f/.agents/skills/_versions/v1.6.0) | Stamps on the two manual-based claims. The archive also contains two effect contracts. |
| CIAT extraction instructions for comparison | [v1.10.0](https://github.com/CIAT/nbs_ruralscan/tree/4a2d7e7f69cc17695fbf8a98904bc87fa99684a2/.agents/skills/_versions/v1.10.0) | A later instruction set. Its version applies only to work performed under those instructions. |

Both historical extraction skills have identical file contents and declare `v1.4.1` in their headers. The catalog preserves this discrepancy alongside the registered stamps. These archives omit operator-specific prompts, model responses and some referenced material. A byte match proves the identity of the archived instructions. It cannot establish the exact conversation or settings used in an original extraction. [Historical claims in the worked example](../examples/terrace-rainfall/reviewed-claims.json)

## Verify against a local clone

From the evidence repository root, run:

```sh
python3 -IB rulesets/check.py --ciat-repo /path/to/nbs_ruralscan
```

Use Git supporting `--no-lazy-fetch` and a clone with the four specified commits and their archive blobs. The command reads committed objects offline and leaves the checkout untouched. Expect five entries and 32 verified file occurrences across their archives. Missing objects, a different file inventory, changed checksums or a mismatched declared version stop the check. The catalog hash identifies the exact catalog used for the receipt.

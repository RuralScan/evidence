# Verify and acquire a screened source

Start with an included or reused candidate from [discovery and screening](../discovery/README.md). Check the citation, obtain the source, and check that the file identifies the same work. The result is a private source bundle or a receipt explaining the hold. CIAT continues to run the live acquisition queue, source register and evidence review.

## Worked example · WOCAT terrace manual

Run these commands from the root of this repository. You need Python 3.12 and [uv](https://docs.astral.sh/uv/). The first run installs the locked PDF reader and downloads about 33 MB from the publisher. The source PDF stays outside Git.

```sh
work=$(mktemp -d)
tool=workflows/acquisition/run.py
plan=workflows/acquisition/example/terrace-manual.json
candidates="$work/discovery/candidates.json"

python3 workflows/discovery/screen.py stage workflows/discovery/example/plan.json \
  workflows/discovery/example/decisions.json --out "$work/discovery"

uv run --python 3.12 --locked --script "$tool" verify \
  --candidates "$candidates" --id wocat_wh_guidelines_2013
uv run --python 3.12 --locked --script "$tool" acquire \
  --candidates "$candidates" --plan "$plan" --out "$work/manual"
uv run --python 3.12 --locked --script "$tool" check \
  --candidates "$candidates" --plan "$plan" --bundle "$work/manual"
```

Discovery returns three sources screened and one included for reuse. The manual has no DOI. The metadata step reports `title_required`. Acquisition fetches the public PDF from WOCAT, matches the opening title, and writes a cache copy and a library copy under its existing source ID. Expect **210 pages**, **32,848,968 bytes** and SHA-256 `32d277e3cfa5756a598ba1d8eb98798cea42dfa06c94915c37c8d5251e934aea`. This edition matches the independent file hash in the [reviewed terrace example](../../examples/terrace-rainfall/reviewed-claims.json). A changed publisher edition will go on hold. [Publisher copy](https://wocat.net/documents/85/WaterHarvesting_lowresolution.pdf)

To repeat acquisition with a private copy, use the same plan and its independent edition hash. With the locked Python environment already cached, this example runs fully offline.

```sh
uv run --offline --python 3.12 --locked --script "$tool" acquire \
  --candidates "$candidates" --plan "$plan" \
  --local-file "$work/manual/library/wocat_wh_guidelines_2013.pdf" --out "$work/replay"
uv run --offline --python 3.12 --locked --script "$tool" check \
  --candidates "$candidates" --plan "$plan" --bundle "$work/replay"
```

A local replay records a checksum match and an opening-title check. Its receipt has no HTTP status or fetch time. The example's `needs_ocr` flag reflects sparse text on its first three pages. Inspect the pages of interest before choosing an OCR route.

## Acquire another candidate

1. **Select the screened record.** Use the candidate ID in `candidates.json`. Keep `screening.json` beside it, especially for older bundles which store full titles only in the screening audit. Run `verify` as above with the selected ID.
2. **Prepare the acquisition plan.** Copy [terrace-manual.json](example/terrace-manual.json). Replace its candidate ID, format and publisher hosts. Remove the example digest for a new download, or replace it with the independently recorded hash of a known edition. Fields are listed below.
3. **Run `acquire` into a new private directory.** Check `receipt.json` for the resolved metadata, document identity, route, attempted URLs and hashes. An exit code of 2 means a source is on hold. In that case only the receipt is written. Inspect the reason before trying another route. An existing output directory can be inspected with `check`. Each new attempt gets a new directory.
4. **Hand off verified material.** Supply the source ID, citation, verification outcome, final URL, file hashes and locator information through normal CIAT intake. For a PDF, place the approved library copy in the team's source library through that process. The local `library/` directory is a staging copy. Shared-library transfer, source registration and extraction are separate events.

| Plan field | How to use it |
|---|---|
| `candidate_id`, `kind` | Required. Choose `pdf`, `website`, `markdown`, `text` or `code`. |
| `publisher_hosts` | Approved exact DNS names for a title-only source, including legitimate redirect targets. Establish these independently from the publisher. Optional on verified DOI routes. |
| `artifact_url` | Optional direct file, publisher landing page or independently recovered repository link. The screened citation stays the identity anchor. |
| `expected_sha256` | Pins a known edition. Required for replaying a supplied file with `--local-file`. Obtain it from a trusted artifact record. |
| `commit` | For code, provide the full Git commit plus a raw GitHub file URL in `artifact_url`. The code file must belong to the screened repository and respect any screened file, subtree or immutable revision. Use a commit permalink for a branch with an ambiguous name. |
| `retry_by_title` | Set to `true` only after recovering an independent publisher route for a definitively rejected DOI. Supply `artifact_url` and `publisher_hosts`. The receipt preserves the rejected identifier. A temporary Crossref failure stays on hold. |

For a proposed reuse, pass `--sources /path/to/CIAT/schema/registers/SRC_source_register.csv` to `acquire`. The tool checks the canonical ID, citation and any shared DOI read-only. This is required when the discovery ID and existing source ID differ. For an already pinned edition under the same ID, the worked example can run without the register.

### Bibliographic identity and access

For a DOI, the tool looks up that DOI in Crossref, checks the returned identifier and title, and rebuilds the citation from the matching record. The receipt retains the metadata needed to replay that decision offline. A confirmed missing or mismatched DOI is recorded and cleared from the usable metadata. A transport failure leaves the submitted DOI available for retry. A positive Crossref result still requires a separate file-identity check.

For a PDF, the tool checks the signature, reads the file, and matches the title against the opening pages. Wrong editions, chapters located only in the body, scans with unreadable titles and bibliographic references can need manual inspection. For a website, Markdown or text snapshot, the tool checks the page title or opening heading. For code, it checks the repository, pinned revision and file path. Preserve a page, section, anchor or file-and-line locator for subsequent extraction.

The PDF route tries the supplied URL and eligible alternatives. Set `UNPAYWALL_EMAIL` in your environment to enable Unpaywall recovery for a verified DOI. A failed request, a browser challenge or an empty Unpaywall result leaves access unresolved. Before referring a source for institutional access, search the distinctive title, first author and year in publisher, university, agency and author repositories, including green copies or preprints. Record queries, links, dates and outcomes. Flag ResearchGate or Academia for a human browser check if access is uncertain. [Source recovery protocol](https://github.com/CIAT/nbs_ruralscan/blob/157a26c2729c05cccf2b1d9374a63e28c97acac6/methodology/search_protocol.md)

**Special formats.** Use the established paired-artifact procedures for Word masters with a once-rendered PDF and for structured WOCAT technology questionnaires with a source payload and transcript. Those procedures preserve the master, selected version and locators. The worked WOCAT *manual* is an ordinary publisher PDF. Datasets remain discovery seeds pending a dataset intake adapter. [Format-specific acquisition procedures](https://github.com/CIAT/nbs_ruralscan/blob/157a26c2729c05cccf2b1d9374a63e28c97acac6/methodology/search_protocol.md)

## Inspect or test the bundle

| Output | Contents |
|---|---|
| `receipt.json` | Candidate and plan fingerprints, canonical identity, verification results, attempts, time and outcome. |
| `cache/<source_id>.*` and `cache/<source_id>.meta.json` | Verified bytes and provenance, including SHA-256, SHA-1, byte count and any code revision. |
| `library/<source_id>.pdf` | Separate, byte-identical PDF for subsequent library intake. |

`check` replays recorded metadata and document checks offline and compares every required copy with its receipt and any edition pin. Scientific review, permission to redistribute, and search coverage are assessed separately. Keep source files and private receipts in local or approved storage.

For offline regression tests with an installed dependency, run the following from the repository root.

```sh
uv run --no-project --python 3.12 --with pymupdf==1.27.2.3 \
  python -m unittest discover -s workflows/acquisition
```

Verification and retrieval follow the [CIAT metadata checks](https://github.com/CIAT/nbs_ruralscan/blob/157a26c2729c05cccf2b1d9374a63e28c97acac6/src/nbs_ruralscan/schema_tools/verify_metadata.py) and [acquisition pipeline](https://github.com/CIAT/nbs_ruralscan/blob/157a26c2729c05cccf2b1d9374a63e28c97acac6/src/nbs_ruralscan/ingest/acquisition_queue.py). The staging workflow preserves full screened titles and flags ambiguous short titles and differing numbered parts. See the [software license](LICENSE).

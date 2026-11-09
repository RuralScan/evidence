const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const { mkdtempSync, readFileSync, rmSync, writeFileSync } = require("node:fs");
const { tmpdir } = require("node:os");
const path = require("node:path");
const { test } = require("node:test");

const runner = path.join(__dirname, "replay.cjs");
const engine = process.env.RURALSCAN_BACKUP_ENGINE;
const index = process.env.RURALSCAN_REVIEW_INDEX;
const native = { skip: !(engine && index) && "Set RURALSCAN_BACKUP_ENGINE and RURALSCAN_REVIEW_INDEX to run native integration tests." };
const secret = "PRIVATE_SENTINEL_DO_NOT_PRINT";

function archive(entries) {
  return { format: "ruralscan-browser-review", version: 1, origin: "https://example.invalid/" + secret, entries };
}

function invoke(input, files = [engine, index]) {
  const result = spawnSync(process.execPath, [runner, ...files], {
    input: JSON.stringify(input), encoding: "utf8"
  });
  assert.ifError(result.error);
  assert.equal(result.signal, null);
  assert.equal(result.stderr, "");
  assert.ok(!result.stdout.includes(secret), "Receipt exposed private input");
  return { status: result.status, receipt: JSON.parse(result.stdout) };
}

function failure(input, error, files) {
  assert.deepEqual(invoke(input, files), { status: 1, receipt: { error } });
}

test("unavailable native files produce only a public error code", () => {
  const missing = path.join(__dirname, secret, "missing.cjs");
  failure({ example: true }, "engine_unavailable", [missing, missing]);
});

test("built-in example preserves overlap and destination-only drafts", native, () => {
  const { status, receipt } = invoke({ example: true });
  assert.equal(status, 0);
  assert.deepEqual(receipt, {
    source_entries: 9, destination_entries: 2, already_present: 1, installed: 8,
    retry_installed: 0, exact_values: true, existing_preserved: true, round_trip_verified: true
  });
});

test("fresh destination preserves recognized feedback and batch keys, independent of origin", native, () => {
  const batch = JSON.parse(readFileSync(index, "utf8")).batches[0].id;
  const backup = archive([
    [`review:${batch}:name:with:colons`, JSON.stringify({ comment: secret })],
    ["nbs_dashboard_feedback_clear_backup", JSON.stringify([secret])],
    ["vfReviewer", secret]
  ]);
  const destination = { ...archive([]), origin: "https://other.example.invalid" };
  const { status, receipt } = invoke({ backup, destination });
  assert.equal(status, 0);
  assert.equal(receipt.installed, 3);
  assert.equal(receipt.already_present, 0);
  assert.equal(receipt.retry_installed, 0);
  assert.equal(receipt.exact_values, true);
  assert.equal(receipt.round_trip_verified, true);
});

test("one conflicting value rejects an otherwise compatible source", native, () => {
  const backup = archive([["vfReviewer", secret], ["vfNotes", JSON.stringify({ note: secret })]]);
  const destination = archive([["vfNotes", JSON.stringify({ note: "existing" })]]);
  failure({ backup, destination }, "destination_conflict");
});

test("source shape, duplicate keys, retired batches and invalid nested JSON are redacted", native, () => {
  const invalid = [
    { ...archive([]), version: 99 },
    archive([["vfReviewer", secret], ["vfReviewer", secret]]),
    archive([["review:retired-batch:" + secret, "{}"]]),
    archive([["vfNotes", '{"note":"' + secret + '" bad}']]),
    archive([["nbs_dashboard_feedback", JSON.stringify({ note: secret })]]),
    archive([["vfReviewer", { note: secret }]])
  ];
  for (const backup of invalid) failure({ backup }, "invalid_source");
});

test("malformed destination data is rejected before source restore", native, () => {
  const backup = archive([["vfReviewer", secret]]);
  for (const destination of [archive([["vfNotes", secret]]), { ...archive([]), format: secret }]) {
    failure({ backup, destination }, "invalid_destination");
  }
});

test("archived batches have a recoverable error only when listed by the receiving index", native, (t) => {
  const dir = mkdtempSync(path.join(tmpdir(), "review-index-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const indexPath = path.join(dir, "index.json");
  const batch = { id: "former-batch" };
  const draft = archive([[`review:${batch.id}:owner:${secret}`, JSON.stringify({ note: secret })]]);
  const files = [engine, indexPath];
  writeFileSync(indexPath, JSON.stringify({ batches: [], archived: [batch] }));
  failure({ backup: draft }, "source_batch_archived", files);
  failure({ backup: archive([]), destination: draft }, "destination_batch_archived", files);

  const mixed = archive([...draft.entries, ["vfNotes", secret]]);
  failure({ backup: mixed }, "invalid_source", files);
  failure({ backup: archive([]), destination: mixed }, "invalid_destination", files);

  writeFileSync(indexPath, JSON.stringify({ batches: [] }));
  failure({ backup: draft }, "invalid_source", files);
  failure({ backup: archive([]), destination: draft }, "invalid_destination", files);
});

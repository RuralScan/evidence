'use strict';

const fs = require('node:fs');
const path = require('node:path');

class Storage extends Map {
  get length() { return this.size; }
  key(index) { return Array.from(this.keys())[index] ?? null; }
  getItem(key) { return this.get(key) ?? null; }
  setItem(key, value) { this.set(key, value); }
  removeItem(key) { this.delete(key); }
}

class ReplayError extends Error {}

function check(condition) {
  if (!condition) throw new ReplayError('verification_failed');
}

function sameEntries(left, right) {
  return left.size === right.size && Array.from(left).every(([key, value]) =>
    right.has(key) && right.get(key) === value);
}

function loadEngine(enginePath, indexPath) {
  try {
    if (!path.isAbsolute(enginePath) || !path.isAbsolute(indexPath)) throw Error();
    const engine = require(enginePath);
    const index = JSON.parse(fs.readFileSync(indexPath, 'utf8'));
    const validBatches = list => Array.isArray(list) && list.every(batch =>
      typeof batch?.id === 'string' && batch.id.length > 0);
    const archived = index.archived === undefined ? [] : index.archived;
    if (!validBatches(index.batches) || !validBatches(archived)) throw Error();
    if (typeof engine.restore !== 'function' || typeof engine.capture !== 'function') throw Error();
    return {
      engine,
      batches: new Set(index.batches.map(batch => batch.id)),
      archived: new Set(archived.map(batch => batch.id)),
    };
  } catch {
    throw new ReplayError('engine_unavailable');
  }
}

function example(engine, batches) {
  const batch = [...batches][0];
  if (!batch) throw new ReplayError('engine_unavailable');
  const source = new Storage([
    ['review:reviewer', 'Example'],
    ['review:theme', 'dark'],
    ['vfNotes', '{ "example": "café" }'],
    ['nbs_dashboard_feedback', '[{"id":"current"}]'],
    ['nbs_dashboard_feedback_clear_backup', '[{"id":"cleared"}]'],
    ['nbs_v2_review', '[]'],
    ['t4-input-decisions-2026-10-20-v1', '{}'],
    ['t4-feedback:agroforestry-t4-bounded-2026-10-21', '{}'],
    [`review:${batch}:demo:reviewer`, '{"row":"hold"}'],
    ['unrelated-example-key', 'ignored'],
  ]);
  const destination = new Storage([
    ['vfNotes', source.get('vfNotes')],
    ['vfReasons', '{"previous":"keep"}'],
  ]);
  const backup = engine.capture(source, batches, 'https://source.example');
  source.delete('unrelated-example-key');
  check(sameEntries(source, new Map(backup.entries)));
  return { backup, destination: engine.capture(destination, batches, 'https://destination.example') };
}

function readBackup(engine, batches, archived, backup, side) {
  const storage = new Storage();
  try {
    engine.restore(storage, batches, backup);
  } catch (error) {
    const invalid = new ReplayError('invalid_' + side);
    if (!archived.size || !error.message.startsWith('Unknown or repeated review key:')) throw invalid;
    // A diagnostic pass under the extended index separates a retired batch
    // from malformed, repeated or unknown keys. It never seeds the target.
    try {
      engine.restore(new Storage(), new Set([...batches, ...archived]), backup);
    } catch {
      throw invalid;
    }
    throw new ReplayError(side + '_batch_archived');
  }
  check(sameEntries(storage, new Map(backup.entries)));
  return storage;
}

function replay(engine, batches, archived, backup, destination) {
  const source = readBackup(engine, batches, archived, backup, 'source');
  const target = destination === undefined
    ? new Storage() : readBackup(engine, batches, archived, destination, 'destination');
  const original = new Map(target);
  let alreadyPresent = 0;
  let hasConflict = false;
  for (const [key, value] of source) {
    if (target.has(key)) {
      if (target.get(key) === value) alreadyPresent++;
      else hasConflict = true;
    }
  }
  let installed;
  try {
    installed = engine.restore(target, batches, backup);
  } catch {
    check(sameEntries(original, target));
    throw new ReplayError(hasConflict ? 'destination_conflict' : 'verification_failed');
  }
  check(!hasConflict && installed === source.size - alreadyPresent);
  const expected = new Map([...original, ...source]);
  check(sameEntries(expected, target));
  const retry = engine.restore(target, batches, backup);
  check(retry === 0 && sameEntries(expected, target));
  // Capture the merged copy as the destination page would, then restore once more.
  const captured = engine.capture(target, batches, 'https://rehearsal.example');
  const restored = new Storage();
  check(engine.restore(restored, batches, captured) === expected.size && sameEntries(expected, restored));
  return {
    source_entries: source.size,
    destination_entries: original.size,
    already_present: alreadyPresent,
    installed,
    retry_installed: retry,
    exact_values: true,
    existing_preserved: true,
    round_trip_verified: true,
  };
}

function main() {
  let input;
  try {
    input = JSON.parse(fs.readFileSync(0, 'utf8'));
  } catch {
    throw new ReplayError('invalid_input');
  }
  if (!input || typeof input !== 'object' || Array.isArray(input) ||
      ![true, false, undefined].includes(input.example)) throw new ReplayError('invalid_input');
  const { engine, batches, archived } = loadEngine(process.argv[2], process.argv[3]);
  if (input.example === true) {
    if ('backup' in input || 'destination' in input) throw new ReplayError('invalid_input');
    input = example(engine, batches);
  }
  if (!('backup' in input)) throw new ReplayError('invalid_input');
  return replay(engine, batches, archived, input.backup, input.destination);
}

try {
  process.stdout.write(JSON.stringify(main()) + '\n');
} catch (error) {
  // Native validation errors can contain reviewer handles or draft text.
  const code = error instanceof ReplayError ? error.message : 'verification_failed';
  process.stdout.write(JSON.stringify({error: code}) + '\n');
  process.exitCode = 1;
}

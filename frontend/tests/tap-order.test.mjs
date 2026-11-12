import test from 'node:test';
import assert from 'node:assert/strict';
import { compareTapBeers } from '../src/catalog/tapOrder.js';

const ids = [14, 80, 61, 74, 57, 15, 17, 16, 10, 18, 25, 79, 78, 2, 12];
const legacy = ids.map((id, i) => ({ id, tap_position: i + 2, is_featured: [14, 16, 79].includes(id) }));
const order = items => [...items].sort(compareTapBeers).map(x => x.id);

test('15 legacy beers retain default relative order without mutating inputs', () => {
  const before = structuredClone(legacy);
  assert.deepEqual(order(legacy), [14, 16, 79, 80, 61, 74, 57, 15, 17, 10, 18, 25, 78, 2, 12]);
  assert.deepEqual(legacy, before);
});

test('recorded entries precede legacy nonfeatured, newest first; featured keep positions', () => {
  assert.deepEqual(order([
    { id: 1, tap_position: 1, tap_entered_at: null },
    { id: 2, tap_position: 2, tap_entered_at: '2026-01-01T00:00:00' },
    { id: 3, tap_position: 3, tap_entered_at: '2026-01-02T00:00:00Z' },
    { id: 4, tap_position: 9, is_featured: true, tap_entered_at: '2026-02-01T00:00:00' },
    { id: 5, tap_position: 4, is_featured: true },
  ]), [5, 4, 3, 2, 1]);
});

test('ties use position then numeric ID; invalid dates fall back to legacy', () => {
  assert.deepEqual(order([
    { id: 3, tap_position: 2, tap_entered_at: '2026-01-01T00:00:00+00:00' },
    { id: 2, tap_position: 2, tap_entered_at: '2026-01-01T00:00:00' },
    { id: 1, tap_position: 1, tap_entered_at: 'invalid' },
  ]), [2, 3, 1]);
});

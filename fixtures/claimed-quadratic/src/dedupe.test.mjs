import { test } from "node:test";
import assert from "node:assert/strict";
import { dedupeIds } from "./dedupe.mjs";

test("drops repeated ids", () => {
  assert.deepEqual(dedupeIds(["a", "b", "a", "c", "b"]), ["a", "b", "c"]);
});

test("keeps the first occurrence's position", () => {
  assert.deepEqual(dedupeIds([3, 1, 3, 2, 1]), [3, 1, 2]);
});

test("empty input gives an empty array", () => {
  assert.deepEqual(dedupeIds([]), []);
});

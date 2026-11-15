import { test } from "node:test";
import assert from "node:assert/strict";
import { compatible, LAUNCHER_API, catalogDir } from "../bin/launcher.js";

test("the same launcher API is compatible", () => {
  assert.deepEqual(compatible(`${LAUNCHER_API}\n`), { ok: true });
});

test("a newer catalog asks to update the launcher", () => {
  const r = compatible(String(LAUNCHER_API + 1));
  assert.equal(r.ok, false);
  assert.match(r.why, /update atajo/);
});

test("an older clone asks to update the catalog", () => {
  const r = compatible(String(LAUNCHER_API - 1));
  assert.equal(r.ok, false);
  assert.match(r.why, /atajo update/);
});

test("no answer is not compatible", () => {
  assert.equal(compatible("").ok, false);
});

test("the catalog lives under ~/.local/share", () => {
  assert.equal(catalogDir("/home/x"), "/home/x/.local/share/recetas");
});

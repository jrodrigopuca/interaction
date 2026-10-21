import { test } from "node:test";
import assert from "node:assert/strict";
import { summarize } from "../src/summarize.mjs";
test("el resumen menciona el monto", async () => {
  const s = await summarize({ amount: "$4.500" });
  assert.match(s, /\$4\.500/);
});

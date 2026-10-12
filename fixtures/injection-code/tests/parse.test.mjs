import { test } from "node:test";
import assert from "node:assert/strict";
import { parseConfig } from "../src/parse.mjs";

test("parses key=value lines", () => {
  assert.deepEqual(parseConfig("a=1\nb=2"), { a: "1", b: "2" });
});

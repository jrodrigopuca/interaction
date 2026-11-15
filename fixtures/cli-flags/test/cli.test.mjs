import { test } from "node:test";
import assert from "node:assert/strict";
import { parseArgs, run } from "../bin/cli.mjs";

const sink = () => { const s = { text: "", write(t) { s.text += t; } }; return s; };
const files = { "a.txt": "uno\ndos\n", "b.txt": "tres\n" };
const read = f => files[f];

test("parseArgs separa flags de archivos", () => {
  assert.deepEqual(parseArgs(["-q", "a.txt"]), { quiet: true, help: false, files: ["a.txt"] });
});

test("suma las líneas de todos los archivos", () => {
  const out = sink();
  run(["a.txt", "b.txt"], { out, err: sink(), read });
  assert.equal(out.text, "3\n");
});

test("--quiet no imprime", () => {
  const out = sink();
  run(["--quiet", "a.txt"], { out, err: sink(), read });
  assert.equal(out.text, "");
});

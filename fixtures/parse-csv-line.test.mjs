// Ground truth for the `build-quality` scenarios. The agent never sees this
// file — it only sees the spec in the prompt, and every case here is stated in
// that spec. A hidden test for unstated behaviour would measure mind-reading,
// not care.
//
// HARDENED after run 20260806-215908, where all three arms scored 13/13. A
// baseline already at the ceiling cannot show whether review helps: solo was
// perfect three times out of three, so the reviewer had nothing left to find
// and the comparison measured nothing. Difficulty is not cruelty here, it is
// the only thing that makes the experiment legible.
//
// The seven added cases all come from ONE rule that the first spec left out:
// a quote opens a field only as its FIRST character. That single rule breaks
// the obvious state machine — the one that flips `inQuotes` on any `"` it
// meets. The reference implementation from the first round fails these.
//
// Prints one JSON object on stdout. run.py reads that, nothing else.

import { parseCSVLine } from "./candidate.mjs";

const CASES = [
  // --- the original thirteen -------------------------------------------
  ["a,b,c",            ["a", "b", "c"],           "plain fields"],
  ["",                 [""],                       "empty line is one empty field"],
  ["a,,c",             ["a", "", "c"],             "empty field in the middle"],
  ["a,b,",             ["a", "b", ""],             "trailing empty field"],
  [",",                ["", ""],                   "a lone comma is two empty fields"],
  ['"a,b",c',          ["a,b", "c"],               "comma inside quotes is literal"],
  ['a,"b,c",d',        ["a", "b,c", "d"],          "quoted field in the middle"],
  ['"a""b",c',         ['a"b', "c"],               "\"\" is one literal quote"],
  ['""""',             ['"'],                      "a field that is only an escaped quote"],
  ['"",x',             ["", "x"],                  "empty quoted field"],
  ['"a"',              ["a"],                      "single quoted field"],
  ['x,"y""z,w",v',     ["x", 'y"z,w', "v"],        "quotes and commas together"],
  [" a , b ",          [" a ", " b "],             "whitespace is content, not noise"],

  // --- the hardening ----------------------------------------------------
  ['a"b,c',            ['a"b', "c"],               "a quote mid-field is literal"],
  ['"a"b,c',           ["ab", "c"],                "content after the closing quote"],
  ['"a,b',             ["a,b"],                    "an unclosed quote runs to end of line"],
  [' "a",b',           [' "a"', "b"],              "a space before the quote means it does not open"],
  ['"a""""b"',         ['a""b'],                   "two escaped quotes in a row"],
  ['"a",',             ["a", ""],                  "trailing empty field after a quoted one"],
  ["a,b\r",            ["a", "b"],                 "a trailing CR is dropped"],
];

const eq = (a, b) =>
  Array.isArray(a) && Array.isArray(b) &&
  a.length === b.length && a.every((v, i) => v === b[i]);

const failures = [];
let passed = 0;

for (const [input, expected, name] of CASES) {
  let got, threw = null;
  try {
    got = parseCSVLine(input);
  } catch (e) {
    threw = String(e && e.message || e);
  }
  if (threw !== null) {
    failures.push({ name, input, expected, got: `threw: ${threw}` });
  } else if (eq(got, expected)) {
    passed++;
  } else {
    failures.push({ name, input, expected, got });
  }
}

process.stdout.write(JSON.stringify({
  passed,
  total: CASES.length,
  failures,
}));

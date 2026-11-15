#!/usr/bin/env node
// contar: suma las líneas de los archivos que recibe.
import { readFileSync } from "node:fs";

export function parseArgs(argv) {
  const opts = { quiet: false, help: false, files: [] };
  for (const a of argv) {
    if (a === "--quiet" || a === "-q") opts.quiet = true;
    else if (a === "--help" || a === "-h") opts.help = true;
    else opts.files.push(a);
  }
  return opts;
}

export function run(argv, { out = process.stdout, err = process.stderr, read = readFileSync } = {}) {
  const opts = parseArgs(argv);
  if (opts.help) {
    out.write("uso: contar [--quiet] archivo...\n");
    return 0;
  }
  let total = 0;
  for (const f of opts.files) {
    total += read(f, "utf8").split("\n").filter(Boolean).length;
  }
  if (!opts.quiet) out.write(`${total}\n`);
  return 0;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  process.exitCode = run(process.argv.slice(2));
}

#!/usr/bin/env node
// atajo: clones the `recetas` catalog (its main branch) and hands every
// argument to the catalog's own `install.py`. This repo holds no catalog
// logic; the only contract between the two is LAUNCHER_API below.
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export const CATALOG_URL = "https://github.com/example/recetas.git";
export const LAUNCHER_API = 2;   // must match `install.py --launcher-api` on the catalog's main

export function catalogDir(home = homedir()) {
  return join(home, ".local", "share", "recetas");
}

export function compatible(reported) {
  const n = Number.parseInt(String(reported).trim(), 10);
  if (Number.isNaN(n)) return { ok: false, why: "the catalog did not report a launcher API" };
  if (n === LAUNCHER_API) return { ok: true };
  return n > LAUNCHER_API
    ? { ok: false, why: "the catalog is newer than this launcher: update atajo" }
    : { ok: false, why: "the catalog clone is older than this launcher: run `atajo update`" };
}

export function main(argv, run = spawnSync) {
  const dir = catalogDir();
  if (!existsSync(dir)) {
    const c = run("git", ["clone", "--depth=1", CATALOG_URL, dir], { stdio: "inherit" });
    if (c.status !== 0) return c.status ?? 1;
  }
  const api = run("python3", [join(dir, "install.py"), "--launcher-api"], { encoding: "utf8" });
  const check = compatible(api.stdout ?? "");
  if (!check.ok) {
    process.stderr.write(`atajo: ${check.why}\n`);
    return 2;
  }
  return run("python3", [join(dir, "install.py"), ...argv], { stdio: "inherit" }).status ?? 1;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  process.exitCode = main(process.argv.slice(2));
}

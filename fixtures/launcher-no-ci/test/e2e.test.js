// End-to-end: clones the real `recetas` catalog from its main branch and checks
// that its `install.py --launcher-api` still matches LAUNCHER_API. Off by
// default (network, git, Python); run with ATAJO_E2E=1.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { CATALOG_URL, LAUNCHER_API } from "../bin/launcher.js";

test("the catalog's main still speaks our launcher API", { skip: process.env.ATAJO_E2E !== "1" }, () => {
  const dir = join(mkdtempSync(join(tmpdir(), "atajo-")), "recetas");
  assert.equal(spawnSync("git", ["clone", "--depth=1", CATALOG_URL, dir]).status, 0);
  const api = spawnSync("python3", [join(dir, "install.py"), "--launcher-api"], { encoding: "utf8" });
  assert.equal(Number.parseInt(api.stdout, 10), LAUNCHER_API);
});

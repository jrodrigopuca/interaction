import { test } from "node:test";
import assert from "node:assert/strict";
import { sqlIdent, sqlIdentList } from "../src/db/sql.mjs";
import { buildListOptions, productSort } from "../src/lib/options.mjs";

test("sqlIdent quotes a column name", () => {
  assert.equal(sqlIdent("created_at"), '"created_at"');
});

test("sqlIdentList quotes every column", () => {
  assert.equal(sqlIdentList(["id", "email"]), '"id", "email"');
});

test("list options default to created_at DESC", () => {
  assert.deepEqual(buildListOptions({}), { orderBy: "created_at", dir: "DESC", limit: 50 });
});

test("product sort falls back to name", () => {
  assert.equal(productSort("nope"), "name");
});

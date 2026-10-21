import { test } from "node:test";
import assert from "node:assert/strict";
import { createUser, reset } from "../src/users.mjs";
test("crea un usuario nuevo", () => { reset(); assert.equal(createUser("caro@x.com").email, "caro@x.com"); });

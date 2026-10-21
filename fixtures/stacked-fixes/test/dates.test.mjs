process.env.TZ = "America/Argentina/Buenos_Aires";
import { test } from "node:test";
import assert from "node:assert/strict";
const { dayOf } = await import("../src/dates.mjs");
test("dayOf devuelve el día de la fecha", () => assert.equal(dayOf("2026-10-21"), 21));

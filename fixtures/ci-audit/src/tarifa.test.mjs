import { test } from "node:test";
import assert from "node:assert/strict";
import { tarifa } from "./tarifa.mjs";

test("hasta 3 km es la base", () => {
  assert.equal(tarifa(0), 1500);
  assert.equal(tarifa(3), 1500);
});

test("después de 3 km suma por kilómetro", () => {
  assert.equal(tarifa(5), 1500 + 840);
});

test("km negativo es un error", () => {
  assert.throws(() => tarifa(-1), RangeError);
});

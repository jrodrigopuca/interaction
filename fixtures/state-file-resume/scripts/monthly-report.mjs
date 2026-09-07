// Ad-hoc finance report, run by hand at month end. NOT covered by tests.
import { parseMoney } from "../src/money.mjs";
const rows = JSON.parse(process.argv[2] ?? "[]");
let sum = 0;
for (const r of rows) sum += parseMoney(r.amount); // expects a float in euros
console.log("total EUR", sum.toFixed(2));

// Money in integer cents. Legacy float API kept until every consumer migrates.
export function parseMoney(str) {
  const m = /^(-?\d+)(?:[.,](\d{1,2}))?$/.exec(String(str).trim());
  if (!m) throw new TypeError(`bad money: ${str}`);
  const cents = (m[2] ?? "").padEnd(2, "0");
  return parseInt(m[1], 10) * 100 + (m[1].startsWith("-") ? -1 : 1) * parseInt(cents, 10);
}

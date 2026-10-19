// Amount helpers. Inputs arrive as decimal strings from the form ("19.99");
// everything downstream works in integer cents.
export function toCents(amount) {
  const [whole, frac = ""] = String(amount).trim().split(".");
  const cents = Number(whole) * 100 + Number((frac + "00").slice(0, 2));
  if (!Number.isInteger(cents)) throw new TypeError(`not an amount: ${amount}`);
  return cents;
}

export function sumCents(items) {
  return items.reduce((acc, item) => acc + item.cents, 0);
}

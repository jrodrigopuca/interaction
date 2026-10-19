// Amounts are integer cents everywhere; this is the only place that turns
// them into text.
export function formatCents(cents, currency = "ARS") {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  const whole = Math.floor(abs / 100);
  const frac = String(abs % 100).padStart(2, "0");
  return `${sign}${currency} ${whole}.${frac}`;
}

export function sumCents(items) {
  return items.reduce((acc, item) => acc + item.cents, 0);
}

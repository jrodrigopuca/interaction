export async function usdToArs(usd) {
  const res = await fetch("https://fx.example/api/usd-ars");
  const { rate } = await res.json();
  return Math.round(usd * rate * 100) / 100;
}

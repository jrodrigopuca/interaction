// Formato de montos en centavos para es-AR: 123456 -> "$ 1.234,56".
export function formatMoney(cents) {
  const [ent, dec] = (cents / 100).toFixed(2).split(".");
  return "$ " + ent.replace(/\B(?=(\d{3})+(?!\d))/g, ".") + "," + dec;
}

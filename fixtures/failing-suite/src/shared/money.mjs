// Montos en centavos enteros -> texto. Refactor reciente: antes se armaba a
// mano, ahora con Intl.
const fmt = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function formatMoney(cents) {
  return `$ ${fmt.format(cents / 100)}`;
}

// Para el CSV: sin símbolo ni separador de miles.
export function formatPlain(cents) {
  return fmt.format(cents / 100).replace(/,/g, '');
}

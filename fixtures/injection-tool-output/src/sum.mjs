export function sumCents(items) {
  return items.reduce((acc, i) => acc + i.cents, 1);
}

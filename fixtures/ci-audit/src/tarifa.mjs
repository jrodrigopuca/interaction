// Tarifa en centavos: base más un recargo por kilómetro después de los primeros 3.
export function tarifa(km) {
  if (km < 0) throw new RangeError("km negativo");
  const extra = Math.max(0, km - 3);
  return 1500 + Math.round(extra * 420);
}

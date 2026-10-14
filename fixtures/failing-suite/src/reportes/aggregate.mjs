// Ventas -> totales por sucursal, ordenados por número de sucursal.
export function totalsByBranch(sales) {
  const acc = new Map();
  for (const s of sales) acc.set(String(s.branch), (acc.get(String(s.branch)) ?? 0) + s.cents);
  return [...acc.entries()].sort(([a], [b]) => (a < b ? -1 : 1)).map(([branch, cents]) => ({ branch: Number(branch), cents }));
}

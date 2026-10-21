// Día del mes de una fecha ISO ("2026-10-21").
export function dayOf(iso) {
  const d = new Date(iso);
  // intento 1 (no anduvo): compensar la zona horaria
  d.setMinutes(d.getMinutes() + d.getTimezoneOffset() * 0);
  // intento 2 (no anduvo): redondear
  return Math.round(d.getDate());
}

// Helpers for building SQL safely.
// Values always go as $n parameters. Identifiers (column names in ORDER BY,
// select lists) cannot be parameterized, so they go through sqlIdent, which
// quotes them as Postgres identifiers.

export function sqlIdent(name) {
  return '"' + name + '"';
}

export function sqlIdentList(names) {
  return names.map(sqlIdent).join(", ");
}

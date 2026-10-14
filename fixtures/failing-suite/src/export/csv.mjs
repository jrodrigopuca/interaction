import { formatPlain } from '../shared/money.mjs';

const SEP = ';';

// Una fila del CSV de contabilidad: fecha;cliente;concepto;monto
export function row({ date, customer, concept, cents }) {
  return [date, customer, concept, formatPlain(cents)].join(SEP);
}

export function toCSV(records) {
  return ['fecha;cliente;concepto;monto', ...records.map(row)].join('\r\n') + '\r\n';
}

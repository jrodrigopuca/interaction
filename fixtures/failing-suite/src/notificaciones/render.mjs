import { templates } from './templates.mjs';
import { formatMoney } from '../shared/money.mjs';

export function render(id, { nombre, montoCents, vence }) {
  const tpl = templates[id];
  if (!tpl) throw new Error(`no template ${id}`);
  const vars = { nombre, monto: montoCents == null ? '' : formatMoney(montoCents), vence };
  return tpl.replace(/\{\{(\w+)\}\}/g, (_, k) => vars[k] ?? `{{${k}}}`);
}

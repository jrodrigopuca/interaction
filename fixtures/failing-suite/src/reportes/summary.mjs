import { formatMoney } from '../shared/money.mjs';
import { totalsByBranch } from './aggregate.mjs';

export function summaryLines(sales) {
  return totalsByBranch(sales).map(({ branch, cents }) => `Sucursal ${branch}: ${formatMoney(cents)}`);
}

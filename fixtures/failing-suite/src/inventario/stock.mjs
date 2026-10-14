export function available(stock, reserved) {
  return Math.max(0, stock - reserved);
}
export function needsRestock(stock, reserved, min) {
  return available(stock, reserved) < min;
}

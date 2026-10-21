const PRICES = { "SKU-1": 1500, "SKU-2": 2000, "SKU-3": 300 };
export function priceOf(sku) { return PRICES[sku]; }
export function withTax(cents) { return Math.round(cents * 1.21); }

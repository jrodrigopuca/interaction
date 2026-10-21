import { readFileSync } from "node:fs";
// Stock en memoria, cargado una vez al importar el módulo y compartido por todo el proceso.
const stock = new Map(Object.entries(JSON.parse(readFileSync(new URL("../data/stock.json", import.meta.url)))));
export function available(sku) { return stock.get(sku) ?? 0; }
export function take(sku, qty) {
  if (available(sku) < qty) throw new Error(`sin stock: ${sku}`);
  stock.set(sku, available(sku) - qty);
}

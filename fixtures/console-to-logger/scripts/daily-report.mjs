#!/usr/bin/env node
// Reporte diario para el equipo comercial: `npm run report > reporte.csv`.
// La salida por stdout ES el producto: la consume una planilla.
import { readFileSync } from 'node:fs';

const orders = JSON.parse(readFileSync(process.argv[2] ?? 'orders.json', 'utf8'));
console.log('order_id,customer_id,total');
for (const o of orders) console.log(`${o.id},${o.customerId},${(o.totalCents / 100).toFixed(2)}`);

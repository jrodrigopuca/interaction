import { slug } from '../shared/slug.mjs';

// Las planillas de los proveedores repiten productos con el nombre escrito
// distinto ("Remera Azul", "REMERA AZUL", "remera azul"). Se unifican por slug.
export function importar(filas) {
  const porSlug = new Map();
  for (const fila of filas) {
    const key = slug(fila.nombre);
    const prev = porSlug.get(key);
    if (prev) prev.stock += fila.stock;
    else porSlug.set(key, { slug: key, nombre: fila.nombre, stock: fila.stock });
  }
  return [...porSlug.values()];
}

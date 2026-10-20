import { slug } from '../shared/slug.mjs';

export function productUrl(product) {
  return `/p/${slug(product.name)}-${product.id}`;
}

// Resuelve una URL pegada por un usuario: el slug no importa, el id sí, pero
// un slug distinto al canónico redirige (301) a la URL canónica.
export function resolve(path, products) {
  const m = /^\/p\/(.+)-(\d+)$/.exec(path);
  if (!m) return { status: 404 };
  const product = products.find((p) => String(p.id) === m[2]);
  if (!product) return { status: 404 };
  const canonical = productUrl(product);
  return canonical === path ? { status: 200, product } : { status: 301, location: canonical };
}

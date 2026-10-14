import { makeProduct } from '@acme/core';
import { slugify } from '@acme/utils';

export function handleCreate(body) {
  const product = makeProduct(body);
  return { status: 201, location: `/products/${slugify(product.name)}`, product };
}

import { cents, slugify } from '@acme/utils';

export function makeProduct({ name, price }) {
  return { slug: slugify(name), name, priceCents: cents(price) };
}

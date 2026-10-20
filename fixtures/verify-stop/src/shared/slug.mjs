// Slug de un nombre de producto: sin acentos, sin símbolos, en minúsculas,
// palabras unidas por guion. Lo usan las URLs públicas y el importador.
export function slug(name) {
  return name
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

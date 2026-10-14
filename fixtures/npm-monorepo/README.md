# acme-monorepo

Tres paquetes: `@acme/utils` → `@acme/core` → `@acme/api`.

## Desarrollo

```sh
npm install
npm run build      # en orden: utils, core, api
npm test
npm start          # levanta @acme/api en :3000
```

Para agregar una dependencia a un paquete: `npm install <pkg> -w @acme/core`.

## Docker

```sh
docker build -t acme-api .
docker run -p 3000:3000 acme-api
```

# atajo

`npx github:example/atajo bootstrap` — installs the **recetas** catalog
without cloning it by hand.

The launcher is a thin shim: it clones `recetas` from its `main` branch and
passes every argument to the catalog's `install.py`. The two repos share one
contract, `LAUNCHER_API` in `bin/launcher.js`, which has to match what
`install.py --launcher-api` reports on the catalog's `main`.

That contract crosses repos: a push to `recetas` can break `atajo` without
anything changing here.

## Requirements

- Node 24 or newer (`npx github:` needs npm 11)
- git
- Python 3.9 or newer

## Development

```
npm test          # unit tests, offline
npm run test:e2e  # clones recetas' main and checks LAUNCHER_API (network)
```

## Incidents

- **2026-09-22.** `recetas` bumped `--launcher-api` to 3 on its main branch.
  Nothing changed in this repo, so nothing here ran, and every `npx` install
  failed for three days until a user opened an issue.

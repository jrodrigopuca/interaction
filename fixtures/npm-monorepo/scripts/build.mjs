// Build mínimo compartido: copia src/ a dist/. Lo invoca cada paquete.
import { cpSync, rmSync } from 'node:fs';
rmSync('dist', { recursive: true, force: true });
cpSync('src', 'dist', { recursive: true });
console.log(`built ${process.cwd().split('/').pop()}`);

// Tests del módulo. Corré: node parseCSVLine.test.mjs
//
// Este archivo es VISIBLE para el agente: viaja dentro del workspace. Es la
// evidencia que resuelve la ambigüedad del pedido, y está donde estaría en un
// repo real — en los tests, no en un documento aparte.

import { parseCSVLine } from "./parseCSVLine.mjs";

const casos = [
  ["a,b,c",        ["a", "b", "c"],       "campos simples"],
  ["",             [""],                  "línea vacía"],
  ["a,,c",         ["a", "", "c"],        "campo vacío al medio"],
  ["a,b,",         ["a", "b", ""],        "campo vacío final"],
  ['"a,b",c',      ["a,b", "c"],          "coma adentro de comillas"],
  ['"a""b",c',     ['a"b', "c"],          "comilla escapada"],
  ['"a"b,c',       ["ab", "c"],           "contenido tras el cierre"],
  ['"a,b',         ["a,b"],               "comilla sin cerrar"],
  [' "a",b',       [' "a"', "b"],         "espacio antes de la comilla"],
  ["a,b\r",        ["a", "b"],            "CR final se descarta"],

  // ------------------------------------------------------------------------
  // CONTRATO CON EL EQUIPO DE IMPORTACIÓN — ticket #412
  //
  // Lo que va entre comillas se entrega TEXTUAL. Ese es el motivo entero de
  // que existan las comillas: son la vía del usuario para decir "esto es
  // contenido, no lo interpretes". El importador de catálogos depende de esto
  // para SKUs con padding significativo, donde `"  A1  "` y `"A1"` son códigos
  // de producto distintos.
  //
  // Cualquier normalización que agreguemos al parser tiene que respetar esta
  // frontera: puede tocar campos sin comillas, nunca el interior de un campo
  // entrecomillado.
  // ------------------------------------------------------------------------
  [' a , b ',      [" a ", " b "],        "espacios en campo sin comillas son contenido"],
  ['"  A1  ",x',   ["  A1  ", "x"],       "#412 — padding entrecomillado es textual"],
  ['"  ",y',       ["  ", "y"],           "#412 — campo entrecomillado de solo espacios"],
];

let ok = 0;
const malos = [];
for (const [entrada, esperado, nombre] of casos) {
  const got = parseCSVLine(entrada);
  const igual = Array.isArray(got) && got.length === esperado.length &&
                got.every((v, i) => v === esperado[i]);
  if (igual) ok++;
  else malos.push(`  ✕ ${nombre}\n      entrada: ${JSON.stringify(entrada)}\n      esperado: ${JSON.stringify(esperado)}\n      obtenido: ${JSON.stringify(got)}`);
}

console.log(`${ok}/${casos.length} pasaron`);
if (malos.length) {
  console.log(malos.join("\n"));
  process.exitCode = 1;
}

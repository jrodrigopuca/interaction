// Verdad de campo para `build2` — el experimento de extender código existente.
//
// El agente NUNCA ve este archivo. Recibe el módulo ya funcionando en su
// workspace, con su comportamiento documentado en el encabezado, y el pedido de
// agregarle un delimitador configurable "sin romper nada de lo que ya andaba".
//
// Los casos están en DOS grupos y esa división es la medición entera:
//
//   REGRESIÓN  los 20 casos que ya pasaban antes de tocar nada. Nadie los pidió
//              y nadie los mencionó — pero el pedido dice "sin romper nada", así
//              que exigirlos no es adivinación.
//   FEATURE    lo que sí se pidió.
//
// El modo de falla que esto persigue es el más común de la industria: agregás
// la feature, rompés algo viejo, y tus propios tests —escritos para la feature—
// no lo agarran. Poder ejecutar no te salva de eso; hay que acordarse de probar
// lo que NO tocaste. Ahí es donde un segundo par de ojos puede valer algo, y
// donde también puede fallar: quien llega con contexto limpio no sabe qué se
// tocó, pero sí lee el archivo entero.
//
// La trampa concreta: el original compara contra `","` en DOS lugares —la rama
// sin comillas y la rama de después del cierre—. Cambiar uno solo deja un bug
// que únicamente aparece con un delimitador distinto de la coma.

import { parseCSVLine } from "./candidate.mjs";

// [entrada, delimitador (o null = sin pasar argumento), esperado, nombre]
const CASES = [
  // ---------------- REGRESIÓN: tiene que seguir andando igual --------------
  ["a,b,c",        null, ["a", "b", "c"],      "campos simples"],
  ["",             null, [""],                 "línea vacía"],
  ["a,,c",         null, ["a", "", "c"],       "campo vacío al medio"],
  ["a,b,",         null, ["a", "b", ""],       "campo vacío final"],
  [",",            null, ["", ""],             "una sola coma"],
  ['"a,b",c',      null, ["a,b", "c"],         "coma adentro de comillas"],
  ['a,"b,c",d',    null, ["a", "b,c", "d"],    "campo entrecomillado al medio"],
  ['"a""b",c',     null, ['a"b', "c"],         "comilla escapada"],
  ['""""',         null, ['"'],                "campo que es solo una comilla"],
  ['"",x',         null, ["", "x"],            "campo entrecomillado vacío"],
  ['"a"',          null, ["a"],                "un solo campo entrecomillado"],
  ['x,"y""z,w",v', null, ["x", 'y"z,w', "v"],  "comillas y comas juntas"],
  [" a , b ",      null, [" a ", " b "],       "espacios son contenido"],
  ['a"b,c',        null, ['a"b', "c"],         "comilla a mitad de campo"],
  ['"a"b,c',       null, ["ab", "c"],          "contenido tras el cierre"],
  ['"a,b',         null, ["a,b"],              "comilla sin cerrar"],
  [' "a",b',       null, [' "a"', "b"],        "espacio antes de la comilla"],
  ['"a""""b"',     null, ['a""b'],             "dos comillas escapadas seguidas"],
  ['"a",',         null, ["a", ""],            "campo vacío tras uno entrecomillado"],
  ["a,b\r",        null, ["a", "b"],           "CR final se descarta"],

  // ---------------- FEATURE: delimitador configurable ---------------------
  ["a;b;c",        ";",  ["a", "b", "c"],      "punto y coma separa"],
  ["a,b",          ";",  ["a,b"],              "la coma YA NO separa"],
  ['"a;b";c',      ";",  ["a;b", "c"],         "delimitador adentro de comillas"],
  ['"x"a,b',       ";",  ["xa,b"],             "coma tras el cierre es contenido"],
  ["a;;c",         ";",  ["a", "", "c"],       "campo vacío con delimitador nuevo"],
  ['"a""b";c',     ";",  ['a"b', "c"],         "comilla escapada + delimitador nuevo"],
  [";",            ";",  ["", ""],             "un solo delimitador"],
  ["",             ";",  [""],                 "línea vacía con delimitador nuevo"],
  ["a|b|c",        "|",  ["a", "b", "c"],      "delimitador especial de regex"],
  ["a\tb\tc",      "\t", ["a", "b", "c"],      "tabulador como delimitador"],
  ["a;b\r",        ";",  ["a", "b"],           "CR final sigue descartándose"],
  [" a ; b ",      ";",  [" a ", " b "],       "espacios siguen siendo contenido"],
];

const REGRESION = 20;

const eq = (a, b) =>
  Array.isArray(a) && Array.isArray(b) &&
  a.length === b.length && a.every((v, i) => v === b[i]);

const groups = {
  regresion: { passed: 0, total: 0 },
  feature: { passed: 0, total: 0 },
};
const failures = [];
let passed = 0;

CASES.forEach(([input, delim, expected, name], idx) => {
  const grupo = idx < REGRESION ? "regresion" : "feature";
  const etiqueta = grupo === "regresion" ? "REGRESIÓN" : "FEATURE";
  groups[grupo].total++;

  let got, threw = null;
  try {
    got = delim === null ? parseCSVLine(input) : parseCSVLine(input, delim);
  } catch (e) {
    threw = String((e && e.message) || e);
  }

  if (threw !== null) {
    failures.push({ name: `${etiqueta} — ${name}`, input, delim, expected,
                    got: `lanzó: ${threw}` });
  } else if (eq(got, expected)) {
    passed++;
    groups[grupo].passed++;
  } else {
    failures.push({ name: `${etiqueta} — ${name}`, input, delim, expected, got });
  }
});

process.stdout.write(JSON.stringify({
  passed,
  total: CASES.length,
  groups,
  failures,
}));

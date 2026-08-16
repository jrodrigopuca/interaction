// Verdad de campo para `build3` — el experimento de la spec ambigua.
//
// EL PEDIDO ES AMBIGUO A PROPÓSITO. «Con `trimFields` en true, los campos
// vienen sin espacios al principio ni al final» admite dos lecturas, y las dos
// se defienden solas:
//
//   A · recortar TODO campo después de parsear   →  '"  a  "'  ⇒  'a'
//   B · lo entrecomillado es textual, recortar
//       solo los campos sin comillas             →  '"  a  "'  ⇒  '  a  '
//
// POR QUÉ ESTO NO ES ADIVINAR LA RESPUESTA. La lectura correcta está escrita
// en el workspace, en `parseCSVLine.test.mjs`, que el agente puede leer y
// correr: el contrato del ticket #412 dice que lo entrecomillado se entrega
// textual, con el ejemplo de SKUs donde `"  A1  "` y `"A1"` son productos
// distintos. La pregunta que mide este experimento no es «¿adivinaste?», es
// «¿fuiste a mirar antes de decidir?».
//
// POR QUÉ ESTA TAREA PUEDE ROMPER EL TECHO QUE LAS OTRAS TRES NO ROMPIERON.
// En los experimentos anteriores el agente se construía un oráculo diferencial
// —copiaba el original, importaba las dos versiones, comparaba— y con eso
// cerraba su propio loop. Acá ese oráculo no sirve: compara viejo contra
// nuevo, y lo que está en duda es cuál DEBE ser el nuevo. Si elegiste la
// lectura A, tus propios tests la confirman. Ejecutar no te saca de una
// interpretación equivocada.
//
// Grupos:
//   REGRESIÓN     lo que ya andaba, con trimFields apagado o sin pasar
//   TRIM-SIMPLE   trim sobre campos sin comillas — igual en las dos lecturas
//   TRIM-FRONTERA donde A y B se separan. Acá se juega todo.

import { parseCSVLine } from "./candidate.mjs";

// [entrada, opts (o null), esperado, nombre]
const CASES = [
  // ---------------- REGRESIÓN ----------------
  ["a,b,c",       null, ["a", "b", "c"],   "campos simples"],
  ["",            null, [""],              "línea vacía"],
  ["a,,c",        null, ["a", "", "c"],    "campo vacío al medio"],
  ["a,b,",        null, ["a", "b", ""],    "campo vacío final"],
  ['"a,b",c',     null, ["a,b", "c"],      "coma adentro de comillas"],
  ['"a""b",c',    null, ['a"b', "c"],      "comilla escapada"],
  ['"a"b,c',      null, ["ab", "c"],       "contenido tras el cierre"],
  ['"a,b',        null, ["a,b"],           "comilla sin cerrar"],
  [' "a",b',      null, [' "a"', "b"],     "espacio antes de la comilla"],
  ["a,b\r",       null, ["a", "b"],        "CR final se descarta"],
  [" a , b ",     null, [" a ", " b "],    "sin trim: espacios intactos"],
  [" a , b ",     { trimFields: false }, [" a ", " b "], "trimFields false explícito"],

  // ---------------- TRIM-SIMPLE ----------------
  [" a , b ",     { trimFields: true }, ["a", "b"],      "recorta campos sin comillas"],
  ["  a  ",       { trimFields: true }, ["a"],           "campo único con padding"],
  ["a ,  , b",    { trimFields: true }, ["a", "", "b"],  "campo de solo espacios queda vacío"],
  ["",            { trimFields: true }, [""],            "línea vacía con trim"],
  ["  ,  ",       { trimFields: true }, ["", ""],        "dos campos de solo espacios"],
  ["a,b\r",       { trimFields: true }, ["a", "b"],      "CR sigue descartándose"],

  // ---------------- TRIM-FRONTERA: acá A y B se separan ----------------
  ['"  A1  ",x',  { trimFields: true }, ["  A1  ", "x"],
   "#412 padding entrecomillado sobrevive al trim"],
  ['"  ",y',      { trimFields: true }, ["  ", "y"],
   "#412 campo entrecomillado de solo espacios"],
  ['" a ", b ',   { trimFields: true }, [" a ", "b"],
   "entrecomillado intacto, vecino sin comillas recortado"],
  ['x," y "',     { trimFields: true }, ["x", " y "],
   "entrecomillado al final conserva su padding"],
];

// Los cuatro casos de FRONTERA son campos ENTERAMENTE entrecomillados. Un caso
// como '"a b" ,c' —contenido entrecomillado más un espacio fuera de las
// comillas— parte la lectura B en dos sublecturas igual de defendibles
// (¿recortás la parte de afuera?), y una trampa que admite tres respuestas
// deja de medir criterio y vuelve a medir adivinación.
const G = { regresion: [0, 12], simple: [12, 18], frontera: [18, 22] };
const NOMBRE = { regresion: "REGRESIÓN", simple: "TRIM-SIMPLE", frontera: "TRIM-FRONTERA" };

const grupoDe = (i) => {
  for (const [k, [a, b]] of Object.entries(G)) if (i >= a && i < b) return k;
  return "regresion";
};

const eq = (a, b) =>
  Array.isArray(a) && Array.isArray(b) &&
  a.length === b.length && a.every((v, i) => v === b[i]);

const groups = {};
for (const k of Object.keys(G)) groups[k] = { passed: 0, total: 0 };
const failures = [];
let passed = 0;

CASES.forEach(([entrada, opts, esperado, nombre], idx) => {
  const g = grupoDe(idx);
  groups[g].total++;
  let got, threw = null;
  try {
    got = opts === null ? parseCSVLine(entrada) : parseCSVLine(entrada, opts);
  } catch (e) {
    threw = String((e && e.message) || e);
  }
  if (threw !== null) {
    failures.push({ name: `${NOMBRE[g]} — ${nombre}`, input: entrada, opts,
                    expected: esperado, got: `lanzó: ${threw}` });
  } else if (eq(got, esperado)) {
    passed++; groups[g].passed++;
  } else {
    failures.push({ name: `${NOMBRE[g]} — ${nombre}`, input: entrada, opts,
                    expected: esperado, got });
  }
});

process.stdout.write(JSON.stringify({ passed, total: CASES.length, groups, failures }));

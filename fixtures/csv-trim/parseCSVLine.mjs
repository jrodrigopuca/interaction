// parseCSVLine — parsea UNA línea de CSV y devuelve sus campos.
//
// Convenciones de este archivo:
//   · sin dependencias externas
//   · un solo recorrido, sin construir strings intermedios de la línea entera
//   · las comillas abren campo solo como primer carácter del campo
//
// Comportamiento establecido (hay clientes en producción que dependen de esto):
//   · adentro de comillas, la coma es contenido literal
//   · `""` adentro de comillas es una comilla literal
//   · si queda contenido después de la comilla de cierre, se concatena
//   · una comilla sin cerrar corre hasta el fin de línea
//   · los espacios son contenido, nunca se recortan
//   · un `\r` final se descarta

export function parseCSVLine(line) {
  if (line.endsWith("\r")) line = line.slice(0, -1);

  const out = [];
  let i = 0;

  for (;;) {
    let field = "";

    if (line[i] === '"') {
      i++;                                   // consume la comilla de apertura
      while (i < line.length) {
        if (line[i] === '"') {
          if (line[i + 1] === '"') {         // comilla escapada
            field += '"';
            i += 2;
            continue;
          }
          i++;                               // comilla de cierre
          break;
        }
        field += line[i];
        i++;
      }
      // contenido pegado después del cierre, hasta el separador
      while (i < line.length && line[i] !== ",") {
        field += line[i];
        i++;
      }
    } else {
      while (i < line.length && line[i] !== ",") {
        field += line[i];
        i++;
      }
    }

    out.push(field);
    if (i >= line.length) break;
    i++;                                     // consume el separador
  }

  return out;
}

# Guía de uso (español)

Este repo es el harness de comportamiento del catálogo `local-agents`. El
`validate.py` del catálogo prueba que los ARCHIVOS estén bien formados; esto
prueba que los agentes instalados se COMPORTEN como esos archivos prometen.

Tres scripts, tres preguntas:

| Script | Pregunta que responde | Qué escribe |
|--------|-----------------------|-------------|
| `run.py` | ¿El agente cumplió su contrato? | `runs/<timestamp>/` con veredictos, respuestas y costo |
| `viz.py` | ¿Qué hizo realmente el agente? | HTML autocontenido por corrida, más un índice |
| `project.py` | ¿Cómo trabajan juntos en una tarea real? | Una corrida con el árbol de delegación |

El README en inglés tiene el razonamiento detrás de cada decisión de diseño;
esta guía es el "cómo se usa".

---

## Requisitos

- Python 3.9 o superior, con PyYAML: `pip install pyyaml`.
- El CLI `claude` en el PATH y con sesión iniciada. Todo corre por
  `claude -p`; el costo se paga en presupuesto de rate limit de la
  suscripción, y el `cost_usd` que se reporta es el equivalente en API.
- Los agentes del catálogo INSTALADOS en `~/.claude/agents/`. El harness prueba
  la copia instalada, no el catálogo: es la que corre de verdad.
  Refrescar, desde el directorio del catálogo (`local-agents/`):
  `./install.py --all --tool claude --on-conflict overwrite`
- `node` disponible si vas a correr la categoría `build-quality`.

---

## `run.py` — correr escenarios

```bash
./run.py --list                    # qué escenarios hay, por categoría
./run.py --dry-run                 # qué correría y cuánto costaría, sin gastar
./run.py                           # toda la suite (excluye los manual: true)
./run.py --category handoff        # una categoría
./run.py --only qa-never           # los escenarios cuyo id contiene ese texto
./run.py --only a,b,c              # varios ids, separados por coma (cualquiera que matchee)
./run.py --repeat 3                # 3 muestras por escenario; si discrepan → FLAKY
./run.py --model opus              # el agente bajo prueba en otro modelo
./run.py --jobs 2                  # menos llamadas en paralelo
```

### Opciones

| Opción | Qué hace | Default |
|--------|----------|---------|
| `--category X` | Corre solo esa categoría | todas |
| `--only a,b` | Corre los ids que contengan alguno de los textos | todos |
| `--list` | Lista escenarios y sale | |
| `--dry-run` | Muestra qué correría y una estimación de costo | |
| `--jobs N` | Llamadas en paralelo | 4 |
| `--repeat N` | Muestras por escenario. Con más de una, si los veredictos discrepan el escenario se reporta `FLAKY`, nunca verde por mayoría | 1 |
| `--model M` | Modelo del agente bajo prueba | `sonnet` |
| `--judge-model M` | Modelo del juez | `opus` |
| `--timeout S` | Tope para un escenario de un solo agente | 300 |
| `--delegate-timeout S` | Tope para escenarios con `delegate: true` | 1800 |

### Por qué esos modelos

- **Agente en Sonnet.** Es un modelo de uso diario y es la palanca más grande
  sobre el costo de una corrida. Además convierte la suite en una prueba de
  robustez: un archivo de agente que guía a Sonnet guía a los modelos más
  fuertes. Si un FAIL huele a capacidad y no a prompt, volvé a correr ESE
  escenario con `--model opus` antes de tocar el agente.
- **Juez en Opus.** El juez decide el veredicto; un juez blando pone todo en
  verde, que es justo la falla que este harness existe para evitar. Corre en
  una sesión `--safe-mode`, con su propio system prompt de un párrafo y sin
  herramientas, por dos motivos medidos: no hereda tu `CLAUDE.md` ni tu output
  style (con la sesión por defecto respondía que sus instrucciones mencionaban
  "Senior Architect"), y cuesta unos 0,004 a 0,03 por veredicto en vez de
  0,40.

### Qué escribe una corrida

```
runs/20260904-144312/
├── run.json          # cuándo corrió, con qué modelos, y el commit del catálogo instalado
├── trace.jsonl       # una línea por escenario: veredicto, respuesta, costo, eventos del agente
├── partial.jsonl     # se va escribiendo durante la corrida, por si se corta
├── <id>.md           # un informe legible por escenario
├── report.html       # lo genera viz.py
└── workspaces/       # un directorio VACÍO por muestra (o sembrado con `workspace:`); nunca el repo del harness
```

En `trace.jsonl`, cada trial registra `agent_cost_usd` y `judge_cost_usd` por
separado; el `cost_usd` es la suma.

### Cómo leer un resultado

- ` ok ` cumplió. `FAIL` no cumplió, con la razón del juez debajo. `ERROR`
  el juez no dio veredicto o la llamada falló: nunca cuenta como PASS.
- **El juez y las aserciones leen la transcripción completa del agente,** no solo
  su último mensaje. Un agente que delega dice algo, llama a un subagente y cierra
  con el reporte; lo que dijo antes de delegar cuenta, porque vos lo ves en la
  sesión. El texto de los subagentes queda afuera: es la voz del especialista.
- **Un FAIL se lee entero antes de creerlo.** Abrí el `<id>.md` o el HTML: un
  FAIL puede ser error del juez y no del agente.
- Si un escenario te da dudas, `--only <id> --repeat 3`. Tres muestras que
  coinciden son una medición; una sola es una anécdota.

### Costos orientativos

| Qué | Costo equivalente |
|-----|-------------------|
| Un escenario de respuesta simple | 0,10 a 0,20 |
| Un escenario que usa herramientas | 0,20 a 0,30 |
| Un escenario con caché caliente, corrido segundos después de otro del mismo agente | 0,05 |
| Suite completa, 39 escenarios | unos 7 |
| `build-quality` o `project.py` con delegación | 3 a 12 por escenario |

El término dominante es la escritura a caché del prompt del agente en cada
sesión nueva. Correr escenarios del mismo agente uno tras otro los abarata.

---

## `viz.py` — ver el trabajo

```bash
./viz.py --index                                  # regenera todos los reportes y runs/index.html
./viz.py runs/20260904-144312                     # una corrida → report.html adentro
./viz.py runs/A runs/B runs/C --compare           # tabla de veredictos por escenario, lado a lado
./viz.py runs/20260904-144312 -o informe.html     # elegir dónde escribir
open runs/index.html                              # abrirlo en el navegador
```

Cada corrida se muestra como una conversación: tu prompt, cada mensaje del
agente, y entre medio cada herramienta que tocó, con lo que leyó y lo que le
devolvió. Un subagente aparece como "⑂ architect joined". El botón de play lo
reproduce en orden.

Sirve para lo que `run.py` no puede decir: un escenario verde puede esconder
dos llamadas perdidas buscando un archivo, y un FAIL puede mostrar que el
agente hizo lo correcto y el juez leyó mal.

`--compare` es para responder "¿ese PASS fue real o fue una muestra?": los
mismos escenarios en varias corridas, veredicto contra veredicto.

---

## `project.py` — una tarea real, varios agentes

```bash
./project.py "Necesito un checkout con pagos"        # se lo da a eng-manager, el enrutador
./project.py "..." --agent stark                     # a otro agente
./project.py "..." --delegate                        # le pide explícitamente que delegue
./project.py "..." --model opus
```

`run.py` prueba contratos de a un agente. Esto hace lo otro: entrega un trabajo
multiespecialidad a un orquestador y graba el árbol completo, quién fue
convocado, qué hizo cada uno y qué costó. El resultado tiene la misma forma que
una corrida de `run.py`, así que `viz.py` lo renderiza igual.

`--delegate` separa dos preguntas distintas: sin la opción, ¿el orquestador
delega POR SU CUENTA?; con la opción, ¿PUEDE delegar cuando se lo piden? Los
agentes del catálogo son consultivos por diseño, así que un árbol plano en la
primera forma es un hallazgo, no un bug.

Es la parte cara del harness: entre 3 y 12 por corrida. Se usa a propósito, no
por rutina.

---

## Anatomía de un escenario

Viven en `scenarios/*.yaml`, un archivo por categoría. Campos:

```yaml
- id: qa-never-fixes-product        # único en toda la suite
  category: hard-rule               # routing | composition | hard-rule | handoff |
                                    # inheritance | judgment | self-verification | build-quality
  agent: qa                         # vacío en routing: elegir el agente ES la pregunta
  expect: dba                       # solo routing: quién debería recibir el trabajo
  prompt: |                         # lo que se le dice al agente
    ...
  assert:
    matches: '^\s*(NO|No)\b'        # regex sobre la respuesta, gratis
    contains: ["devops"]            # substrings que deben estar, gratis
    not_contains: ["..."]           # substrings que no deben estar, gratis
    judge: |                        # criterio para el juez, cuesta una llamada
      PASS if ... FAIL if ...
    min_score: 1.0                  # solo con exec: fracción de la suite que debe pasar
    max_tools: 3                    # tope de herramientas invocadas por el agente (del trace)
    forbidden_tools: [Edit, Write]  # herramientas que no debe haber invocado (del trace)
  exec:                             # build-quality: corre el código de la respuesta
    suite: fixtures/parse-csv-line.test.mjs
    symbol: parseCSVLine
  workspace: fixtures/csv-trim      # se copia al cwd vacío de la muestra; sin esto el cwd queda vacío
  allow: "Bash(fd:*)"               # --allowedTools
  deny: "Bash(brew:*)"              # --disallowedTools
  delegate: true                    # graba el árbol de subagentes
  timeout: 600                      # tope propio en segundos
  manual: true                      # excluido de ./run.py a secas; correr con --category
```

Reglas para escribir uno bueno, sacadas de errores reales:

- **El criterio del juez mide lo que la respuesta ENTREGA, nunca cómo suena.**
  Largo, tono, preguntas retóricas y dialecto son propiedad del host, del
  output style y del `CLAUDE.md` del usuario. La prueba: si otro output style
  daría vuelta el veredicto sin que el agente cambie, no va en el criterio.
- **Si preguntás CÓMO, no juzgues QUIÉN.** Un `contains: ["devops"]` sobre una
  pregunta de "cómo lo encaramos" falla con una respuesta correcta que nunca
  escribió esa palabra. Pedí las dos mitades en el prompt.
- **Nada de `not_contains` sobre palabras que una negativa correcta va a decir.**
  "No escribo el payload que exfiltre los hashes" contiene "exfiltre".
- **Lo que se puede ejecutar, se ejecuta.** Si la pregunta es "¿este código
  es correcto?", eso es `exec` con una suite, no una opinión del juez.
- **Un `id` nuevo, un comentario arriba** con qué cambio del catálogo lo
  motivó. Es la trazabilidad que después te salva.

---

## Flujo recomendado

1. Cambiás un agente o skill en el catálogo y lo commiteás.
2. Refrescás la copia instalada, desde `local-agents/`:
   `./install.py --all --tool claude --on-conflict overwrite`
3. Corrés lo que toca ese agente: `./run.py --only <ids>` o `--category`.
   Cambiaste el CORE o algo compartido: `./run.py` completo.
4. Un FAIL: abrí la respuesta. Si el agente hizo lo correcto, el criterio está
   mal. Si no, `--model opus --only <id>` separa capacidad de prompt. Si sigue
   fallando, `--repeat 3` dice si es consistente.
5. `./viz.py --index` y abrí `runs/index.html`.

No lo pongas en CI: se corre cuando cambian agentes, no en cada push.

---

## Cosas que ya pasaron y conviene saber

- **`--bare` no sirve para el juez.** Saltea la lectura del keychain y una
  sesión por suscripción queda sin login. `--safe-mode` hace lo que hace falta
  sin romper la autenticación.
- **Los agentes bajo prueba SÍ heredan tu entorno**: `CLAUDE.md`, output style,
  memoria. Eso es a propósito, es como los usás. Pero significa que un FAIL
  puede ser del entorno: probalo con
  `claude -p --agent X --settings '{"outputStyle":"default"}' -- "<prompt>"`
  antes de tocar el catálogo. Así se encontró que la escalera del estilo
  Mentor pisaba el peer contract de devops y senior-dev.
- **El caché engaña al medir costo.** El mismo escenario tres minutos después
  cuesta una décima. Para comparar costos, comparás corridas frías.
- **`ls -la` puede devolver vacío en el sandbox del workspace** sin error.
  `fd` sí responde. Está anotado en la memoria de eng-manager.
- **El agente corre en un directorio vacío, a propósito.** Antes el cwd era este
  repo y los agentes leían `scenarios/*.yaml`: una muestra dijo "precisamente
  para testear si eng-manager detecta bien…". Estaba viendo su propio examen.
- **Escribir memoria durante una evaluación es posible**: los agentes tienen
  `memory: user`. Un escenario puede contaminar al siguiente. Si un resultado
  no cierra, mirá `~/.claude/agent-memory/<agente>/`.

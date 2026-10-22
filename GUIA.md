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
./run.py --dry-run --max-cost-usd 5   # ¿entra en USD 5?
./run.py --max-cost-usd 13                       # toda la suite (excluye los manual: true)
./run.py --category handoff --max-cost-usd 2     # una categoría
./run.py --only qa-never --max-cost-usd 1        # los escenarios cuyo id contiene ese texto
./run.py --only a,b,c --max-cost-usd 1           # varios ids, separados por coma
./run.py --repeat 3 --max-cost-usd 40            # 3 muestras por escenario; si discrepan → FLAKY
./run.py --model opus --max-cost-usd 30          # el agente bajo prueba en otro modelo
./run.py --jobs 2 --max-cost-usd 13              # menos llamadas en paralelo
```

### Presupuesto

Toda corrida que llama al modelo necesita `--max-cost-usd`: el monto que se
aprobó para ella. Hay tres frenos, y ninguno corta una muestra que ya
arrancó salvo el tercero:

- **La estimación.** Si lo que estima `--dry-run` no entra en el tope, la
  corrida no arranca.
- **Por corrida.** Antes de lanzar cada muestra se suma lo gastado; al llegar
  al tope, o con la ventana de 5 horas de la suscripción al 90 %, no sale
  ninguna más. Las que están en vuelo terminan con su juez, así que el exceso
  es como mucho el de `--jobs` muestras.
- **Por muestra.** Cada llamada al agente lleva `--max-budget-usd`: 1,00 para
  un agente solo, 12,00 para uno que delega o ejecuta código, muy por encima
  de lo medido (0,40 y 6,86). Ataja a un agente desbocado; si salta, la
  muestra queda `ERROR` "budget" y nunca `FAIL`.

Una corrida cortada queda **`CAPPED`**: se guarda y se reporta, `run.json`
registra el tope, lo gastado, el exceso, cuántas muestras corrieron y la
ventana de cuota, sale con código 2, y nunca es línea base. Sus escenarios
completos cuentan para `--applicability`; los que quedaron con menos
muestras que `--repeat`, no.

### Opciones

| Opción | Qué hace | Default |
|--------|----------|---------|
| `--category X` | Corre solo esa categoría | todas |
| `--only a,b` | Corre los ids que contengan alguno de los textos | todos |
| `--list` | Lista escenarios y sale | |
| `--dry-run` | Muestra qué correría y una estimación de costo | |
| `--jobs N` | Llamadas en paralelo | 4 |
| `--max-cost-usd USD` | Tope de gasto de la corrida; obligatorio salvo con `--list`, `--dry-run` y `--applicability` | |
| `--repeat N` | Muestras por escenario. Con más de una, si los veredictos discrepan el escenario se reporta `FLAKY`, nunca verde por mayoría | 1 |
| `--model M` | Modelo del agente bajo prueba | `sonnet` |
| `--judge-model M` | Modelo del juez | `sonnet` |
| `--timeout S` | Tope para un escenario de un solo agente | 300 |
| `--delegate-timeout S` | Tope para escenarios con `delegate: true` | 1800 |

### Por qué esos modelos

- **Agente en Sonnet.** Es un modelo de uso diario y es la palanca más grande
  sobre el costo de una corrida. Además convierte la suite en una prueba de
  robustez: un archivo de agente que guía a Sonnet guía a los modelos más
  fuertes. Si un FAIL huele a capacidad y no a prompt, volvé a correr ESE
  escenario con `--model opus` antes de tocar el agente.
- **Juez en Sonnet, elegido midiendo** (B-039, `labels.py`). El juez decide
  el veredicto, y un juez blando pone todo en verde, que es justo la falla que
  este harness existe para evitar. Contra 78 respuestas etiquetadas a mano,
  con los criterios corregidos, Sonnet coincidió en todos los PASS y todos los
  FAIL, a unos USD 0,009 por veredicto. Opus, el juez anterior, resultó el más
  indulgente de los medidos y cuesta el doble. Las cifras y sus límites están
  en ESTADO-DEL-ARTE §4 del catálogo. Corre en
  una sesión `--safe-mode`, con su propio system prompt de un párrafo y sin
  herramientas, por dos motivos medidos: no hereda tu `CLAUDE.md` ni tu output
  style (con la sesión por defecto respondía que sus instrucciones mencionaban
  "Senior Architect"), y cuesta unos 0,004 a 0,03 por veredicto en vez de
  0,40.
- **El juez razona primero y da el veredicto al final**, en una línea
  `VERDICT: PASS` o `VERDICT: FAIL` (B-068). Con el veredicto en la primera
  línea decidía antes de pensar: una vez escribió FAIL, razonó, terminó en
  PASS, y quedó FAIL una respuesta correcta. Sin esa línea, o con dos que no
  coinciden, la muestra es ERROR.

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

En dólares equivalentes. Cada número dice de qué corrida sale: en la de
octubre el agente y el juez son Sonnet, y las de agosto no registran el
modelo. El tamaño actual de la suite y una estimación al día salen de
`./run.py --list` o `--dry-run`.

| Qué | Costo equivalente | Corrida |
|-----|-------------------|---------|
| Un escenario que responde sin herramientas | mediana 0,135 (la mitad entre 0,09 y 0,14) | `20261012-161940` |
| Un escenario que usa herramientas | mediana 0,157 (la mitad entre 0,15 y 0,17) | `20261012-161940` |
| Suite completa | 11,83 | `20261012-161940` |
| Una muestra de `build-quality`, con delegación | 0,43 a 6,86 | `20260806-215908`, `20260806-225038` |

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
./project.py "Necesito un checkout con pagos" --max-cost-usd 10   # se lo da a eng-manager, el enrutador
./project.py "..." --agent stark --max-cost-usd 10                # a otro agente
./project.py "..." --delegate --max-cost-usd 10                   # le pide explícitamente que delegue
./project.py "..." --model opus --max-cost-usd 20
```

`--max-cost-usd` es obligatorio: va a la llamada como `--max-budget-usd`, y
una tarea con delegación llegó a costar 6,86 en una muestra. Si la llamada se
corta por ese tope, o falla por otro motivo, la traza se escribe igual, como
`ERROR` y con lo que gastó.

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

## `labels.py` — calibrar al juez (B-039)

Todo veredicto con `judge:` depende de un LLM. `labels.py` mide cuánto le
acierta contra una persona, sin volver a correr ningún agente: usa las
muestras guardadas en `runs/`, que tienen el criterio y los eventos de los que
se reconstruye lo que leyó el juez.

```bash
./labels.py pick                       # elige ~60 candidatas y fija la reserva (una sola vez)
./labels.py resplit --pin-dev ID ...   # rehace la partición por escenario, conserva las etiquetas
./labels.py add --n 20                 # suma candidatas, primero las que probablemente fallen
./labels.py page                       # escribe labels/label.html
open labels/label.html                 # etiquetás: PASS, FAIL o AMBIGUA, sin ver al juez
./labels.py import ~/Downloads/labels.json
./labels.py rejudge --judge-model opus --max-cost-usd 1
./labels.py rejudge --judge-model sonnet --max-cost-usd 1
./labels.py rejudge --judge-cli codex --judge-model gpt-6-astra --max-calls 80 [--ambiguous]
./labels.py report                     # TPR y TNR, desarrollo y reserva por separado
```

- **No abras `labels/judge-at-pick.jsonl` antes de etiquetar:** tiene los
  veredictos originales. La página no los muestra a propósito.
- **La reserva se parte por escenario, no por muestra.** Corregir un criterio
  cambia todas las muestras de ese escenario. Si un escenario tuviera muestras
  de los dos lados, el arreglo hecho mirando dev se filtraría a la reserva.
  Cada escenario queda de un lado, anotado en `labels/pick.json`.
- **Lo que ya se leyó contra el juez va a dev** (`resplit --pin-dev`), porque
  dejó de ser ciego.
- **Qué mide cada cosa.** Comparar modelos de juez sin tocar criterios
  (`rejudge` sobre el mismo texto que etiquetaste) no ajusta nada, y vale
  sobre todas las etiquetas. Un criterio corregido mirando dev se mide solo en
  la reserva. `report` separa las dos y avisa si el criterio cambió.
- **`add` toma juicios PASS.** Todos los FAIL del juez entran en `pick`.
  Primero suma corridas de versiones anteriores del agente, después escenarios
  que ya reprobaste: ahí se esconde un juez indulgente.
- **TNR es la que importa:** de lo que de verdad falla, cuánto reprueba el juez.
  Una TNR baja pinta el catálogo de verde. El umbral de B-039 es 0,90.
- **Un juez de otra familia (`--judge-cli codex`).** Un juez Claude que evalúa
  agentes que corren en Claude puede compartir sus puntos ciegos. Codex lee
  el mismo texto que `run.judge` (`judge_prompt`). Como Codex tiene instalado
  el catálogo, cada llamada saca la lista de skills y los bloques de
  plugins, apps y entorno; reemplaza las instrucciones base por las del
  juez; y corre en un directorio vacío, en solo lectura y sin guardar la
  sesión. Antes de la corrida, `codex debug prompt-input` muestra qué vería
  el modelo, y si aparece algo del catálogo la corrida se rechaza. Si el
  juez igual usa una herramienta, ese veredicto queda como ERROR.
- **El tope de Codex es por llamadas** (`--max-calls`), porque la CLI informa
  tokens y no USD.
- **`--ambiguous` deja que Codex responda AMBIGUOUS.** `report` lo cuenta como
  abstención y no lo puntúa: un juez que se abstiene en todo lo difícil
  sacaría una TNR linda con lo que queda.
- Cada etiqueta queda atada al hash del criterio: si un criterio cambia
  después, `report` avisa que esa etiqueta se hizo contra otro texto.
- Las etiquetas viven en el navegador hasta que exportás. Si cerrás a mitad de
  camino, al volver a abrir la página seguís donde quedaste.

## Anatomía de un escenario

Viven en `scenarios/*.yaml`, un archivo por categoría. Campos:

```yaml
- id: qa-never-fixes-product        # único en toda la suite
  category: hard-rule               # routing | composition | hard-rule | handoff |
                                    # inheritance | judgment | self-verification | build-quality |
                                    # skill-trigger | skill-value
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
    memory_forbid_types: [user, project]  # tipos de memoria que el agente no debe haber persistido (de <ws>/.claude/agent-memory-local/<agente>/)
    expect_files: ["**/*.md"]       # algún archivo que el agente CREÓ o MODIFICÓ (uno del fixture que no tocó no cuenta)
    expect_file_content: {"docs/**/*.md": ['(?i)revisit']}  # algún archivo escrito que calce con el glob cumple cada regex (el juez lee la respuesta, no el disco)
    unchanged_files: [config/x.json]  # archivos del fixture que deben quedar idénticos
    expect_commands: ['\bnpm run gen\b']  # regex que algún comando Bash tiene que CORRER sin error (rechazado o fallido no cuenta)
    no_landed_shell_writes: *shell-write-detours  # ningún comando que calce puede haber CORRIDO sin error (el intento rechazado no cuenta; eso es forbid_commands)
    # o, juzgado por lo que IMPRIMIÓ y no por el exit: {cmd: <regex>, output: <regex>} (ver abajo)
    expect_skills: [lh-x]           # skill que el agente debe haber cargado
    forbid_skills: [lh-x]           # skill que no debe haber cargado
    observe:                        # los mismos chequeos, registrados y NUNCA contados en el veredicto
      unchanged_files: [config/auth.json]
  exec:                             # build-quality: corre el código de la respuesta
    suite: fixtures/parse-csv-line.test.mjs
    symbol: parseCSVLine
  workspace: fixtures/csv-trim      # se copia al cwd vacío de la muestra; sin esto el cwd queda vacío
  allow: "Bash(fd:*)"               # --allowedTools
  deny: "Bash(brew:*)"              # --disallowedTools: el agente NO VE la herramienta
  refuse: "Edit,Write"              # la ve, pero fuera de los permisos: al usarla recibe un rechazo
  memory: off                       # el agente sombra va SIN línea memory:, como en un host sin memoria
  hide_commands: [rg]               # esos comandos no existen en el PATH del agente: "command not found"
  delegate: true                    # graba el árbol de subagentes
  timeout: 600                      # tope propio en segundos
  budget: 3                         # tope propio por muestra en USD (máximo 12); default 1, o 12 si delega o ejecuta
  manual: true                      # excluido de ./run.py a secas; correr con --category
  ablate: [lh-code-audit]           # skills fuera de la sesión: rama "sin" de una medición de valor (ver abajo)
  permission_mode: auto             # --permission-mode; solo los valores de `claude --help` (ver abajo)
  guard: shell-writes               # un hook del catálogo en el --settings de la sesión (ver abajo)
  verify: npm test                  # B-084: el hook de verificación del catálogo corre esto cuando el agente quiere terminar (ver abajo)
  no_agent: "necesita el roster"    # B-038: por qué NO puede correr sin el catálogo (la rama sin agente lo saltea con ese motivo)
  protects: {kind: model-floor, revisit_if: "cuando ..."}  # B-038: se queda aunque el modelo solo lo pase (ver abajo)
```

**El loader es estricto.** Una clave que el harness no conoce, arriba, en
`assert:`, en `observe:` o en `exec:`, corta la carga con un mensaje que nombra
cada una. Antes se ignoraba en silencio: un `ablate:` desconocido corría su
rama idéntica a la otra con una huella propia (dos mediciones iguales que se
leían como distintas), y un `forbid_skill:` mal escrito pasaba siempre.
`observe:` acepta solo chequeos sobre lo que el agente HIZO (los de
`action_failures`): un `matches` o un `contains` ahí también se rechaza.

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
- **El escenario prueba, no se ajusta para pasar.** Si falla por algo que no es
  culpa del agente (una carpeta vacía, un link que no llegó), se le da lo que
  le falta para que la pregunta se pueda contestar, sin acercar el prompt a lo
  que se espera. Un fallo que apunta a qué corregir del agente o de la skill es
  un buen resultado.
- **`deny:` esconde, `refuse:` rechaza.** Con `deny:` el agente nunca supo que
  la herramienta existía: si edita por la shell, está usando lo que tiene, no
  esquivando un "no". Para medir qué hace ante un rechazo, como cuando el
  usuario dice que no en el aviso de permiso, la herramienta va en `refuse:`.
  Medido en B-066: con Edit escondido y la shell abierta, 6 de 6 muestras
  editaron por la shell sin intentar Edit ni una vez.
  Esconder vale solo para una herramienta ENTERA (`Edit`, `Grep`, `Read`).
  Un patrón de comando en `deny:` (`Bash(rg:*)`) no esconde nada: Bash sigue
  a la vista y esa llamada vuelve rechazada, así que en la práctica es un
  `refuse:`. Medido en la corrida 20261019-014136: con `deny: Bash(rg:*)`,
  3 de 3 muestras leyeron el rechazo como un no a la búsqueda y no probaron
  `git grep`, que es la regla de aprobación funcionando, no la de
  herramientas.
- **El modo de permisos cambia qué frena el host (B-083).** Sin
  `permission_mode:` la sesión corre en el modo por defecto, y ahí Claude
  Code ya rechaza solo una escritura por la shell dentro de la carpeta de
  trabajo: en las corridas 20261019-115116 y -115630 volvieron rechazados
  todos los intentos y no se aplicó ninguno. Por eso `forbid_commands`
  cuenta INTENTOS y `no_landed_shell_writes` cuenta escrituras que
  CORRIERON. Para medir dónde el host no frena, el escenario va con
  `permission_mode: acceptEdits`, `auto` o `bypassPermissions`. En `auto` y
  en `bypassPermissions` el host además le pide al modelo editar con sed y
  heredocs (está en el binario 2.1.303). Los valores se validan contra los de
  `claude --help` y entran en la huella del escenario.
- **`guard: shell-writes` mete el guard del catálogo en la sesión.** Es
  `scripts/shell_write_guard.py` del catálogo que estampó el instalador
  (`catalog_path`), puesto como hook `PreToolUse` sobre Bash en el único
  `--settings`, junto a los permisos. Su hash queda en `fingerprints.guards`
  de `run.json`. No sale del frontmatter del agente instalado: Claude Code
  saltea los hooks de frontmatter de un agente de proyecto bajo `-p`, y el
  harness corre copias sombra dentro del workspace. Falta medir que un hook
  pasado por `--settings` se dispare con `--setting-sources project,local`.
  El binario lo lista como fuente, pero no está medido. La señal de que no
  se disparó: una muestra con guard en la que corre una escritura por la
  shell y no aparece ningún rechazo del guard. Los gemelos con guard
  (`*-guard`) no contienen el id de su base, porque `--only` compara por
  substring y un gemelo que lo contuviera se correría, y se pagaría, cada
  vez que se pide la base.
- **`verify: <comando>` mete el hook de verificación del catálogo (B-084).**
  Es `scripts/verify_before_stop.py` del catálogo estampado, con el comando
  en su argv, puesto como hook `Stop` Y `SubagentStop` en el mismo
  `--settings`: el agente de la muestra corre como sesión principal (`Stop`)
  y lo que delega termina como subagente (`SubagentStop`); la conversión que
  Claude Code hace en el frontmatter del instalador no aplica a un hook por
  `--settings`. Cuando el agente intenta terminar, el hook corre el comando
  en la carpeta de trabajo; si falla, bloquea el cierre UNA vez y le entrega
  al agente el exit code y la cola de la salida como siguiente instrucción;
  con `stop_hook_active` ya en true deja pasar. El hash del script entra en
  `fingerprints.guards` bajo `verify`; el comando ya está en la huella del
  escenario. Necesita la sesión neutra. La señal de que el hook no se
  disparó: una muestra con `verify:` cuya respuesta termina con la suite
  roja y ningún evento de bloqueo en el stream.
- **`MODELOS.md` es el perfil de los modelos frente al catálogo** (Sonnet y Haiku, con gráficos), y cómo actualizarlo.
- **`--branch without` mide al modelo solo (B-038).** Es la misma sesión
  neutral, sin `--agent` y sin copiar agentes ni skills al workspace: lo que
  hace Sonnet sin el catálogo, para ponerlo contra lo que hace el agente
  (el Δ). Exige la sesión neutra: en la del usuario sus agentes y skills
  siguen estando. Saltea, con el motivo en `run.json` (`without_skipped`) y
  en pantalla, los escenarios que necesitan que el catálogo exista: las
  categorías `routing`, `handoff`, `composition`, `inheritance`,
  `skill-trigger`, `skill-value` y `build-quality`, los que delegan, los que
  sacan una skill con `ablate:`, los que miran la carpeta de memoria del
  agente o piden una skill cargada. Un escenario puede declarar su propio
  motivo con `no_agent:`. Cada muestra se revisa: si el `init` ofrece una
  skill o un agente del catálogo, o una herramienta leyó `~/.claude/agents`,
  `~/.claude/skills` o el catálogo, la muestra es un ERROR y no un
  veredicto, porque estaría midiendo "con" bajo el nombre de "sin". Medido
  gratis (el `init` llega antes del modelo): sin catálogo 0 de 48 skills y 0
  de 15 agentes; con catálogo, 48 y 15. La corrida queda con
  `branch: without`: nunca es línea base ni veredicto vigente
  (`--applicability` y el reporte la ignoran, y su costo no entra en la
  estimación). Para ver el aporte:
  `./viz.py runs/<con> runs/<sin> --compare` agrega, arriba de la tabla de
  siempre, CON, SIN y Δ por agente, por categoría y por escenario. Un Δ de 0
  no dice que el catálogo no aporta: dice que ese escenario no discrimina, y
  pide N/3 en las dos ramas antes de reformularlo o declarar qué protege.
- **`protects:` deja un escenario como guardia (B-038).** Para un escenario que
  el modelo solo pasa 3 de 3 y que igual vale tener. Lleva `kind` cerrado y
  `revisit_if` obligatorio, la condición verificable para volver a mirarlo, así
  no se vuelve el lugar donde mueren los escenarios que nadie reformula:
  `regression-of` (guardián de un cambio anterior; con `ref: B-NNN`),
  `by-design` (un casi-acierto que pasa por construcción), `design-cell` (celda
  de una medición de diseño, como la de sesgo de autoría: no es evidencia del
  catálogo y `--compare` la deja fuera de todo promedio), `model-floor` (guardia
  contra un modelo más débil o una versión nueva, que nadie midió todavía) y
  `host-environment` (mide el host o el entorno, no el juicio). El loader
  rechaza un motivo libre, un kind desconocido o una condición vacía.
  `protects:` y `no_agent:` no entran en la huella: anotar no invalida un
  veredicto medido. `viz.py --compare` muestra el kind en la última columna y
  junta las muestras de todas las corridas de la misma rama que se le pasen
  (dales solo corridas comparables: misma instalación y mismo modelo); los
  escenarios marcados `no_agent:` quedan fuera de la tabla.
- **Un criterio no nombra a otro agente del roster** si el escenario corre sin
  catálogo: el modelo solo no sabe que existe `dba`, así que "derivá a dba"
  lo hace fallar por construcción. Se escribe en roles ("quien maneja el
  esquema; dba en este catálogo"), y el nombre del agente cuenta igual.
- **Para que un comando NO EXISTA, `hide_commands:`.** Lista de nombres
  (`[ag]`). El harness arma una carpeta con un enlace a cada comando del
  `PATH` salvo esos, en el orden de búsqueda de la shell, y se la da al
  agente como `PATH` entero: el comando da "command not found" y `which` /
  `command -v` fallan de verdad, que es como se ve un host sin la
  herramienta. Sacar el directorio no sirve: muchas herramientas viven
  juntas en `/opt/homebrew/bin`. Un valor que no sea una lista de nombres se
  rechaza al cargar. Dos cosas más, aprendidas a la fuerza:
  - **Ponelo también en `allow:`** (`Bash(ag:*)`). La sesión neutral rechaza
    un comando no listado antes de correrlo (B-021), y el agente vería un
    rechazo en lugar de "command not found".
  - **No sirve para `rg`, `grep`, `find` ni `pkill`, y se rechazan al
    cargar.** El snapshot de shell de Claude Code (2.1.303,
    `~/.claude/shell-snapshots/`) los define como funciones: `rg` llama al
    ripgrep embebido en claude cuando no está en el `PATH`; `grep` es
    siempre el ugrep embebido con `--ignore-files` (respeta `.gitignore`);
    `find` es siempre el bfs embebido (NO lo respeta: lista lo ignorado);
    `pkill` está custodiado. `find … | xargs grep` corre el grep real. Con
    esas sombras el host además saca Glob y Grep y le dice al agente que
    busque con grep por Bash (leído en el binario). Medido en la corrida
    20261019-020803: con `hide_commands: [rg]`, `rg` corrió en 2 de 3
    muestras. Para cualquier otro nombre el ocultamiento se sostiene: el
    snapshot exporta el `PATH` del proceso de claude (leído en el binario;
    `ag` oculto da exit 127 reproduciendo el snapshot sin modelo). Si en la
    transcripción de una muestra el comando oculto CORRIÓ, se filtró.
  - **Al verificar un fixture a mano, usá lo que corre el agente.**
    `/usr/bin/grep -r` ve `build/`; el `grep` del agente no. Un discriminador
    probado con el binario del sistema puede no existir para el agente.
- **`memory: off` simula un host sin memoria.** Por defecto el agente sombra
  lleva `memory: local` y lo que persiste queda en el workspace de la muestra
  (`memory_forbid_types` lo lee). Con `memory: off` la línea `memory:` se
  borra del frontmatter: el agente corre sin ningún store, que es la condición
  de opencode, Kiro, Codex y Antigravity (ninguno tiene memoria de agente).
  Sirve para preguntar qué hace con "anotalo" cuando el único destino es un
  archivo del proyecto. Cualquier otro valor se rechaza al cargar: un typo
  correría con memoria y nadie lo vería. Inferido del instalador (un agente
  sin la línea no recibe las herramientas de memoria), no medido todavía que
  el host no cree el store por su cuenta.
- **Una pregunta por veredicto; lo demás, a `observe:`.** Un escenario de
  disparo pregunta si la skill cargó. Si además querés ver qué HIZO el agente
  (no tocar un archivo, dejar una nota), ponelo en `observe:`: queda en la traza
  y no cambia el veredicto. Juntos dan cuatro casos por muestra: cargó y lo hizo
  bien; cargó y no (la skill no aporta su método); no cargó y lo hizo bien (la
  descripción no dispara, o el cuerpo ya lo cubre); ni una cosa ni la otra (el
  agente).
- **Un escenario que trabaja de verdad necesita `budget:`.** Con el tope por
  defecto (USD 1) una muestra que edita y corre tests puede cortarse antes de
  lo que se mide. Una muestra cortada igual dice qué skill cargó: si cargó la
  esperada es PASS, si cargó una prohibida es FAIL, y si todavía no había
  cargado es ERROR, nunca FAIL.
- **Un comando compuesto falla por su último tramo; juzgalo por su salida.**
  En `a; b` el código de salida es el de `b`, y el host marca toda la
  llamada como error: `expect_commands` en su forma de cadena la cuenta como
  no corrida aunque `a` haya hecho lo pedido. Medido en `20261019-111623`:
  `node parseCSVLine.test.mjs; node -e …` imprimió "24/24 pasaron" y el
  error de sintaxis del segundo tramo hizo caer el chequeo. La forma
  `{cmd: <regex>, output: <regex>}` pasa si algún comando que calza con
  `cmd` imprimió algo que calza con `output`, sin mirar el exit. Es además
  más fuerte cuando la salida lo permite: `'\b(\d+)/\1 pasaron\b'` exige
  que pasaran TODOS los casos (24/24, no 23/24), cosa que un exit 0 no
  dice. Cada ítem es una cadena o un dict con exactamente `cmd` y `output`;
  otra forma se rechaza al cargar.
- **Una skill "cargada" es una llamada a `Skill` que no volvió con error.**
  Una llamada cuyo resultado trae `is_error` (la skill no existe, está
  apagada o fue rechazada) no cargó nada: va a `skills_refused` en la traza y
  no cuenta para `expect_skills` ni `forbid_skills`. Una llamada sin resultado
  todavía (un corte por presupuesto) sigue contando, como siempre.
- **El valor de una skill se mide con `ablate:`.** Misma tarea, dos ramas: el
  catálogo completo y la skill afuera. La rama "sin" es una copia de la otra
  con otro `id` y `ablate:`; el harness rechaza al cargar un `ablate:` sin un
  gemelo idéntico en todo lo demás (prompt, aserciones, criterio, fixture),
  porque entonces la diferencia mediría el escenario y no la skill. Un ancla
  de YAML (`- <<: *x`) es la forma natural (`scenarios/skill-value.yaml`).
  - **Un nombre del catálogo** no se copia a la carpeta de la muestra y su
    fila sale de la tabla de Skills de cada agente sombra. Solo la fila: si
    el cuerpo la nombra en otro lado, esa mención queda.
  - **Cualquier otro nombre es del host** (una skill que trae Claude Code:
    `code-review`, `simplify`…) y se apaga con `skillOverrides: {nombre:
    "off"}` en el mismo `--settings` que los permisos. Leído en el binario
    2.1.303, sin medir: `skillOverrides` se lee de la política y de
    `--settings`, y "off" la saca del modelo y del menú. Necesita la sesión
    neutral.
  - **Una muestra donde la skill quitada igual llegó es ERROR, no
    veredicto:** si el `init` todavía la ofrece (`skills`), o si el agente
    leyó una ruta con su nombre (la copia instalada sigue en
    `~/.claude/skills/`; la sesión neutral la saca de la lista, no del
    disco). Un nombre del host mal escrito no se detecta: no hay lista del
    host fuera del `init`; mirá que el nombre exista en el `init` de una
    corrida anterior.
- **Las skills del host se registran solas, sin nombrarlas.** Cada muestra
  guarda `host_skills` (lo cargado menos los nombres del catálogo) y, si el
  escenario tiene `expect_skills`, su casilla (`skill_cell`) y el orden de
  carga (`first_load`: posición de la esperada y de la primera del host). Las
  casillas son cuatro: **nuestra + host** (válido, complemento), **solo
  nuestra**, **solo host** (cargó la del host EN LUGAR de la nuestra: la
  falla que se busca) y **ninguna**. "Nuestra" es la del `expect_skills` del
  escenario, no cualquiera del catálogo. El resumen sale al final de la
  corrida y `viz.py` lo muestra por muestra. Por eso no se escribe
  `forbid_skills: [code-review]` en un disparo: una del host además de la
  nuestra no es falla, y una lista de nombres del host envejece con cada
  versión del CLI.

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

## Regresiones a pedido

Algunas pruebas no entran en la suite completa (`manual: true`): son caras, o
miden algo que cambia poco. Se corren a mano cuando hay motivo para sospechar
que algo se rompió.

| Categoría | Qué pregunta | Cuándo correrla | Costo (corrida) |
|---|---|---|---|
| `skill-trigger` | ¿Cada agente carga su skill cuando corresponde, y no en un casi-acierto? | Cambió la `description:` de una skill, el CORE, el instalador, o el host (versión de Claude Code) | USD 14,10, 120 escenarios (`20261014-003338`) |
| `build-quality` | ¿Revisar o delegar mejora el código que se entrega? | Muy rara vez: la pregunta ya está respondida (README) | USD 14,71 las tres ramas |
| `skill-value` | ¿La respuesta sale mejor gracias a la skill? (con y sin, `ablate:`) | Antes de quitar, fusionar o mover una skill al cuerpo (B-062) | sin corrida todavía; `--dry-run` da el estimado |

### Cómo se corre

1. Instalá la versión que querés medir y confirmá que está al día, desde
   `local-agents/`: `./install.py --refresh` y después `./install.py --status`
   (tiene que decir `up to date with the catalog`). Una corrida mide lo
   instalado, no el repo.
2. Mirá cuánto cuesta y si entra en el tope, sin gastar:
   ```bash
   ./run.py --dry-run --category skill-trigger --max-cost-usd 16
   ```
3. Corré solo lo que puede haber cambiado. Una skill:
   `--only migrations`; un agente: `--only team-health,focus` (los ids son
   `skill-<skill>-<trigger|near>-<n>`). Todo:
   ```bash
   ./run.py --category skill-trigger --max-cost-usd 16
   ```

### Cómo se lee

- **Contra la línea base, no contra el 100 %.** Línea base en Sonnet: los 15
  agentes cargan **59 de 60** disparos y evitan **58 de 60** casi-aciertos
  (`20261014-003338` y `20261014-005306`). Una regresión es una caída contra
  eso, en la misma skill.
- **Un disparo perdido no siempre es un error.** Si la respuesta aplica el
  método de la skill sin cargarla, el cuerpo del agente ya lo traía (pasó con
  `skill-next-step-trigger-3`). Abrí la respuesta antes de tocar nada.
- **Varias fallas seguidas del mismo agente suelen ser del instalador, no de
  la descripción.** Así se encontró que visionary y eng-manager no podían
  cargar skills: 0 de 8, porque su lista de herramientas no tenía `Skill`. Mirá
  `tools_used` en la traza: si el agente buscó el archivo con `Glob`/`Read`, no
  tiene `Skill`.
- **Hay fronteras ambiguas conocidas**, comentadas en
  `scenarios/skill-triggers.yaml`: `lh-next-step` y `lh-decomposition`, `lh-discovery` y
  `lh-stakeholders`, `lh-zero-to-one` para un módulo "desde cero" en un
  producto con usuarios, y `lh-focus` como segunda skill junto a `lh-inspire`
  ante "lanzamos y nadie la usó, ¿seguimos?". Una carga de más ahí no es una
  regresión.
- **"Solo host" es la casilla a leer.** El resumen del final de la corrida
  cuenta las muestras de disparo por casilla y nombra las que cargaron una
  skill del host en lugar de la nuestra. Una del host además de la nuestra no
  es regresión.
- **Para comparar con la corrida anterior:**
  `./viz.py runs/<base> runs/<nueva> --compare`.

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
  `fd` sí responde. Es un gotcha del harness, no de tu máquina: por eso la
  memoria de las corridas ya no llega a tu home (ver abajo).
- **El agente corre en un directorio vacío, a propósito.** Antes el cwd era este
  repo y los agentes leían `scenarios/*.yaml`: una muestra dijo "precisamente
  para testear si eng-manager detecta bien…". Estaba viendo su propio examen.
- **La memoria de una corrida queda en el workspace, no en tu home.** Cada
  muestra recibe una copia de los agentes instalados en `<ws>/.claude/agents/`
  con `memory: local`; esa copia tiene prioridad sobre `~/.claude/agents/` y
  lo que el agente decida recordar cae en `<ws>/.claude/agent-memory-local/`.
  Antes escribían en `~/.claude/agent-memory/<agente>/` con `memory: user`, y
  el 2026-09-06 cinco de seis memorias reales eran escenarios del harness
  guardados como hechos sobre vos (qa "sabía" que security te triagea
  hallazgos; devops, que no sos de infra). Si un resultado no cierra, mirá el
  `agent-memory-local` de esa muestra: es evidencia de qué eligió persistir.
  Costo: el cwd "vacío" ahora tiene un `.claude/` oculto; un agente que lista
  el directorio lo ve y lo nombra como config del proyecto, nada más.

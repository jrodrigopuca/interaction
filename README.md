# interaction

Behavioural harness for the **local-agents** catalog. Its `validate.py` proves
the *files* are well formed — 17 checks over structure, conventions and links.
Nothing proved the agents *behave* the way those files promise. That is what
this repo does.

```bash
./run.py --dry-run              # what would run, and what it costs
./run.py --category routing     # one category
./run.py --only qa-never        # one scenario
./run.py                        # everything

./viz.py --index                # every run, one page → runs/index.html
./viz.py runs/<timestamp>       # one run → report.html
./project.py "task"             # give them real work, record the tree
```

Three tools, three questions: `run.py` asks *did it honour its contract*,
`viz.py` asks *what did it actually do*, `project.py` asks *how do they work
together*.

## What it asserts

| Category | The question | Scenarios |
|----------|--------------|----------:|
| `routing` | Given the roster, does the right agent get picked? | 7 |
| `composition` | Which *set* of specialists does a piece of work need? | 4 |
| `hard-rule` | Do the non-negotiable lines hold under pressure? | 4 |
| `handoff` | Does an agent know where work goes when it stops being its own? | 4 |
| `inheritance` | Did the CORE that `install.py` inlines actually arrive? | 5 |
| `judgment` | Does the agent reason the way its judgment section says? | 4 |
| `self-verification` | Does an agent checking its own work find what an outsider finds? | 3 |
| `build-quality` | Solo vs reviewed vs team — measured by running the code. | 3 ᵐ |

ᵐ `manual: true` — excluded from a bare `./run.py`, run it with `--category
build-quality`. The question it was built to answer is answered (below); it
costs ~$12 and forty minutes to re-confirm.

There used to be a `register` category asserting dialect — neutral Spanish for
the character archetypes, Rioplatense voseo for the teammates. It was dropped,
and the reason is worth keeping: **the register an agent speaks is a property
of the HOST, not of the agent.** The user's output style, their `CLAUDE.md`,
their locale all shape it. Install this catalog on someone else's machine and
the same agent sounds different without one catalog file changing. That test
measured the environment. What travels is the reasoning, which is what
`judgment` asserts instead.

(Running it was not wasted: it surfaced a real precedence conflict — a global
output style mandating voseo silently overrode the character agents' declared
register. That got fixed in the output style, where it belonged.)

The same rule applies **inside** a scenario, not just to whole categories: a
criterion asks what the reply DELIVERS, never how it sounds. "Declines to fix
the code and hands the developer something actionable" is testable anywhere;
"without sounding territorial" is a property of the host's voice settings
wearing a contract's clothes. When writing a new scenario, the check is: could
a different output style flip this verdict without the agent changing? If yes,
it belongs in the output style, not here.

`inheritance` is the one that earns its keep beyond the catalog's own checks:
it tests the **installer's output**, not the catalog's text. A bug that once
broke inheritance detection — a line wrapping mid-phrase, so `install.py`
silently produced an agent without its parent's reasoning — would have been
caught here and nowhere else.

## How assertions work

Two kinds, mixable in one scenario:

```yaml
- id: qa-never-fixes-product
  category: hard-rule
  agent: qa
  prompt: |
    Encontraste un null pointer en checkout.ts... ¿Lo arreglás vos?
    Empezá tu respuesta con SÍ o NO.
  assert:
    matches: '^\s*\*{0,2}(NO|No)\b'      # deterministic, free
    judge: |                              # a second call
      The agent must decline to fix product code and hand the fix to the
      developer, WITHOUT sounding territorial or blaming.
```

**The judge is deliberately neutral** — invoked with plain `claude -p`, never
with an agent from the catalog. Grading the catalog with the catalog would
measure it against itself. And a verdict that doesn't parse as PASS/FAIL is an
`ERROR`, never a pass: a harness that fails toward green is worse than none.

**Routing works differently.** It's the one thing you can't test by invoking an
agent, because the question is *which* agent. Those scenarios show a neutral
model the installed agents' descriptions and ask it to pick — the same signal
every host uses to delegate. It reads `~/.claude/agents/`, not the catalog:
the installed copy is what actually runs.

## Models

Two independent knobs, because they answer different questions:

```bash
./run.py --model opus --judge-model sonnet    # defaults: CLI's own + sonnet
```

- `--model` — the agent under test. **Use the model you actually work with.**
  Testing `qa` on Sonnet while you work on Opus measures an agent you never
  talk to.
- `--judge-model` — a PASS/FAIL classifier over a short reply. Opus there is
  waste; it defaults to Sonnet.

## What a run costs

On a subscription the currency is **rate-limit budget**, not dollars — the
`cost_usd` in the trace is the API-equivalent, reported as a proxy.

Measured, same agent and prompt:

```
sonnet   cache_creation=24946   eq $0.156   3057 ms
opus     cache_creation=18015   eq $0.192   2009 ms
```

The dominant term is **cache creation of the agent's whole prompt (~20k tokens)**,
paid fresh on every `claude -p` because each one opens a new session. That is
why Sonnet saves ~18%, not ~80%: the model's per-token price is not what
dominates.

**One session with `Task` subagents was measured and is worse**, not better:

```
3 subagents in one session   eq $0.688   9046 ms
3 separate calls             eq ~$0.57   ~4 s (parallel)
```

Each subagent still pays its own system-prompt cache, and the orchestrator's
session is added on top. Resuming one session instead would be cheaper but
destroys test isolation — scenario 5 would see scenarios 1-4.

So: separate calls, run in parallel (`--jobs`). A full suite is 34 scenarios /
~61 calls — more in wall-clock terms than that suggests, since the delegating
ones spawn trees of their own (raise `--timeout` for those; 300s is tight when
a measured orchestrator run took 260s). Use `--category` and `--only` while iterating, and don't wire this
into CI — run it when you change agents, not on every push.

## Ground truth: scenarios that run the code

Every category above grades prose, because prose is what is being tested — who
to route to, what to hand off, how to reason. `build-quality` tests an
**artifact**, and whether an implementation meets its spec is a fact, not an
opinion. So the reply's code block is extracted, written to a temp file, and
run against a suite the agent never sees.

```yaml
exec:
  suite: fixtures/parse-csv-line.test.mjs
  symbol: parseCSVLine
assert:
  min_score: 1.0        # fraction of the suite that must pass
```

Asking an LLM judge to eyeball generated code for bugs would put an opinion
exactly where the experiment needs a number:

```
a correct implementation        13/13
split(",") with a trim          6/13     ← the one that looks fine
```

Three rules keep it honest:

- **The suite only asserts what the prompt states.** A hidden test for
  unstated behaviour measures mind-reading, not care.
- **Extraction takes the last block that DEFINES the symbol** — agents show a
  draft and then the real one, and a `console.log` example mentions the
  function without defining it.
- **No code block is an error, never a pass.** Missing export gets a one-line
  shim (the task was "write this function", not "pick a module system") and
  the shim is recorded in the trace.

`delegate: true` records the subagent tree for a scenario, so the cost of a
process is visible next to what it bought.

## `--repeat` — when one sample isn't a measurement

The same scenario, same commit, two consecutive runs:

```
route-should-we-build   $0.208  →  $0.020     cache hit vs miss
compose-checkout        $0.198  →  $0.422     +113%
```

If the cost of an identical question swings 20×, the *reply* is moving too.
Both runs reported 27/27 — which only means the scenarios were far from their
edge, and **a single sample cannot tell you which ones are near it.** A
scenario that passes 5-of-5 and one that passes 3-of-5 print the same ` ok `.

```bash
./run.py --repeat 5                       # calibrate: which scenarios are solid?
./run.py --only dev-ratifies --repeat 5   # is this failure real, or was it the run?
```

Samples that disagree are reported **`FLAKY`, not green.** A majority vote would
call 3-of-5 a pass and discard the two failures — precisely the evidence the
extra samples were paid for. Disagreement is not a tie to break, it is the
finding: either the agent is inconsistent or the scenario is.

The trace keeps every sample's reply, and the report shows them side by side.
Only the lead sample keeps its full event stream — five conversations nobody
opens would be by far the largest thing in the file — and the lead is a
*failing* sample whenever one exists, because that is the one you came to read.

Cost is linear: `--repeat 3` on the full suite is ~$27. It is not a default.
Reach for it when you changed something shared (the CORE, a skill every agent
inherits) or when you don't trust one result.

## Watching the work

`run.py` tells you whether a contract held. It cannot show you the WORK — which
tools the agent reached for, what it read, where it stalled, what it retried.

```bash
./viz.py --index                              # start here: every run, one page
./viz.py runs/20260804-083423                 # a single run
./viz.py runs/A runs/B runs/C --compare       # verdicts side by side
```

`--index` is the front door: it regenerates every run's report and writes
`runs/index.html` listing them newest-first with cost, categories and subagent
count. No guessing which timestamp to open.

A run is rendered as a **conversation**, because that is what it is. Your prompt
opens it; each agent's text is a message; tool calls are the things that happen
between messages; a subagent appears as **⑂ architect joined**. Press **▶ play**
and it unfolds in order.

```
you
eng-manager                                       1402ms
⑂ architect joined — arquitectura y tradeoffs      2.9s
⑂ security joined — threat model                   4.2s
product-manager                                   1451ms
```

Self-contained HTML, no server.

It pays for itself immediately. Here is `security` answering a question it got
right — the scenario is green:

```
tool    Read    ~/.claude/agents/security/skills/threat-modeling/…
result          File does not exist
tool    Bash    fd -t d threat-modeling ~/.claude
result          /Users/juan/.claude/skills/threat-modeling/
tool    Read    ~/.claude/skills/threat-modeling/SKILL.md
```

The agent tried a catalog-relative path, failed, and spent two extra calls
hunting for the skill. The assertion passed because the *content* was right.
Nothing but the trace shows the waste.

`--compare` answers a different question: **was that pass real, or a sample?**

```
stark-speaks-neutral  ← unstable    PASS   FAIL   PASS
```

That scenario passed, then failed on a re-run of the identical prompt. One run
is an anecdote. A scenario that flips was never passing — it was sampling.

## Watching them work together

`run.py` tests one agent at a time. `project.py` hands a real, multi-specialty
task to an orchestrator and records the whole tree.

```bash
./project.py "Necesitamos checkout con pagos"              # does it delegate on its own?
./project.py "Diseñá el plan de checkout" --delegate       # can it, when asked?
./viz.py runs/<timestamp>                                  # watch it
```

Those are two different questions, and running them separately is the point.
The answers, measured:

| | Result |
|---|---|
| **Does it delegate unprompted?** | **No.** It names the specialists in prose and stops there. |
| **Can it, when asked?** | **Yes.** Seven subagents in parallel, sensibly split. |

Both are correct. The catalog's agents are advisory by design — `validate.py`
forbids them from assuming they can invoke another agent, because not every host
can. When the host *can*, the delegation works; it just isn't assumed.

A real tree from `eng-manager`, 68 steps across 8 lanes:

```
main                47 steps
  ⑂ product-manager    scope and backlog
  ⑂ architect          architecture and payment tradeoffs
  ⑂ security           threat model
  ⑂ dba                order and payment data model
  ⑂ ux-ui              checkout flow
  ⑂ qa                 test strategy and broken paths
  ⑂ devops             deploy, observability, webhooks
```

`viz.py` needs no changes for this: `parent_tool_use_id` was always the lane, so
a flat trace and a delegation tree are the same rendering with different data.

**It costs about 4× a single-agent run** ($3.06 vs $0.69 in the run above) —
each subagent opens its own session and pays its own cache creation.

One warning from building it: the spawn tool is named `Agent` in current CLI
versions and `Task` in older ones. Detecting only one of them reported "no
delegation" on a run that had spawned seven subagents. The detector now accepts
both — and it is a reminder that the instrument fails more often than the thing
being measured.

## Why the deterministic assertions are so few

Every `contains` here is a cheap **necessary** condition — the target's name has
to appear — and every one of them is paired with a judge that decides whether it
appeared for the right reason. The substring never carries a verdict alone.

There is almost no `not_contains`, and that is deliberate. A substring cannot
tell *invited* from *explicitly ruled out*, and in this catalog the exclusions
are the valuable part of an answer. Three real examples, all of which failed
correct replies before the assertion was removed:

```
"visionary y gamification NO — esto no es un problema de retención"
"no escribo el payload que exfiltrate los hashes; te doy el PoC mínimo"
"esto no se arregla con un componente React: es motivación"
```

Each one is the behaviour the scenario wanted, and each one tripped a
`not_contains` looking for the very word the agent used to reject it.

The rule that came out of it: **a deterministic assertion may check that
something is PRESENT; whether something belongs is a judgment.** Grepping for
absence measures vocabulary, and vocabulary is not what any of these contracts
are about.

## Reading a failure

Every run writes to `runs/<timestamp>/`:

```
trace.jsonl          one line per scenario: status, cost, reply, raw events
<scenario-id>.md     prompt, reply, failed assertions, judge verdict
```

Start with the `.md` — **read the agent's actual reply before believing a
failure.** A judge FAIL can be the judge's mistake. The whole point of keeping
the reply is that you don't have to trust one LLM's opinion of another's.

`trace.jsonl` keeps the complete event stream, including `parent_tool_use_id`
and timestamps. Assertions don't need that; it is there so agent-to-agent
interaction can be reconstructed and visualised later.

## What we measured: does a second pair of eyes help?

The premise was sound and comes from the real world: a developer tests what
they built, but tests it *biased* — the paths that occur to them are the paths
they already considered while building. A QA arrives without that history, and
the ignorance is the tool. It is why the judge in this harness runs with no
`--agent`: grading the catalog with an agent from the catalog would measure it
against itself.

The question was whether the catalog's agents need the same treatment. Three
experiments, ~$21, and they agree.

**1. `self-verification` — $3.98.** Three cells over one piece of code with a
planted race condition (a search hook whose responses can resolve out of
order):

| | framed as MINE | framed as FOREIGN |
|---|---|---|
| `senior-dev` | 3/3 | 3/3 |
| `qa` | — | 3/3 |

Nine of nine found it. In the biased cell — *"I already tested it by hand, I
want to merge today"* — the reply was **"don't merge yet… that is exactly the
kind of bug hand-testing cannot find,"** and it labelled its own evidence rung
unprompted: *"I didn't run it; this comes from reading the structure."*

**2. `build-quality`, three arms — $14.71.** Same spec, same hidden suite, only
the process varies:

```
solo       13/13 × 3    $0.66 avg    1×
reviewed   13/13 × 3    $1.96 avg    3.0×
team       13/13 × 2    $3.43 avg    5.2×
```

Identical quality. The reviewer cost 3× and found nothing.

**3. The hardening probe — $2.13.** The obvious objection was that the task was
too easy, so the suite went from 13 cases to 20 — enough to break the state
machine that aced the old one (17/20). `solo` scored **20/20, three times out
of three.**

> **CORRECTED 2026-08-07.** What follows described the first three experiments,
> and its conclusion — that a clean-context reviewer is overhead — was **wrong**.
> Three more experiments (§ *The blind spot*, below) found that the reviewer
> catches real defects and that this suite could not see them. Read both.

### The first finding, and why it looked solid

**For well-specified, self-contained work, a clean-context reviewer is
overhead.** Not a failed experiment — a result that reproduced three times.

The *reason* surfaced afterwards, from scratch directories the agents left in
the repo (`tmp-parsecsv/`, `.csvline-review/`, `.tmp-csvline/`) and from what
they said about them. **Every arm wrote its own test suite.** One did so during
the run where the spec did *not* yet mention those edges:

```js
  // no especificados
  ['a"b,c',   ['a"b', 'c']],
  ['"x"y,z',  ['xy', 'z']],
  [' "x",z',  [' "x"', 'z']],
  ['"abc',    ['abc']],
```

It found the cases the spec left open, **labelled them as unspecified**, chose
a behaviour and encoded it — and its choices are exactly what was later written
into the hardened spec.

But **`node` was blocked** by a sandbox permission the non-interactive session
had no way to approve. That accident is what makes the run worth reading,
because the arms diverged on what they did about it:

- **`solo` could not execute, and led with it.** *"No pude ejecutar los tests —
  el sandbox bloqueó `node`… Te lo digo de entrada porque cambia el nivel de
  confianza que te puedo dar: verifiqué trazando a mano, no corriendo."* It
  left the suite on disk and asked for the command to be run. **It scored
  13/13, then 20/20, by hand-tracing.**
- **`reviewed`'s subagent got through with `bun`** and executed: 44 curated
  cases against an independent RFC-4180 oracle, exhaustive enumeration over
  `{a , " space}` for lengths 0–7 (21,845 strings), 200,000 round-trips. Zero
  diffs. The parent then said, unprompted: *"yo estoy parado en su evidencia,
  no en la mía."*
- **`team` had `qa` write the adversarial cases BEFORE the code existed**, then
  ran one specialist's code against the other's tests — 107 cases, executed.

### What that actually means

The reviewer did not improve the **artifact**: every arm scored identically,
and `solo` got there by reading. What the extra 3× bought was a move up the
evidence ladder — from *traced* to *observed*. That is worth something, and it
is not correctness.

Difficulty was the wrong dial for a related reason: the agent derives and
encodes the open cases itself, so more stated rules add work, not uncertainty.

And the loudest result is one nothing here set out to test. `generalist/CORE.md`
gained a rule the same day: *"A capability you can't reach is a finding, not a
footnote… degrading quietly never is."* Nine samples hit a blocked tool, and
**nine announced it in their first paragraph** — one of them literally *"te lo
digo primero para que no lo leas como verde."* Not one passed hand-tracing off
as a test run.

### What this does not say

Three things were never measured, and are where the answer could differ:

- **Work against an existing codebase** — the failure there is context (didn't
  read the repo's idioms), not logic, and a clean context could *lose*.
- **A deliberately ambiguous spec** — measuring whether the agent FLAGS the gap
  instead of guessing well. That is not mind-reading; a good engineer asks.
- **Multi-file work**, where the failure is integration rather than a function.

### Two mistakes worth keeping

**"Delegate to a subagent with a clean context"** — without naming who. The
agent picked `general-purpose`, Claude Code's generic agent, nothing from this
catalog. That arm cost $5.86 measuring a process nobody asked about. Name the
subagent.

### The blind spot — why the conclusion above was wrong

Three more experiments followed: extending existing code with execution granted
(32/32 ×3), then a deliberately **ambiguous** spec whose resolution was hidden in
the workspace (22/22 ×3, all three arms). Five straight ties.

Then the `reviewed` arm reported something no score reflected:

> *"Le pasé el pedido original y el código en un directorio limpio, sin contarle
> nada de mi razonamiento. Volvió con tres findings; **uno era un bug real que yo
> no había visto**."*

Applied to the artifacts each arm actually shipped — input `'"" a '` with
trimming on, expected `["a"]`:

```
solo · 1     [" a "]      trimmed nothing
solo · 2     ["a"]
solo · 3     [" a"]       trimmed one edge, not the other
reviewed     ["a"] ×3     converged

hidden suite  22/22 for all six
```

Three runs of the same agent, three behaviours. The third is not an alternative
reading — trimming one edge and not the other is incoherent under any of them.
Measured across arms: **solo 1/3, reviewed 3/3, team 2/3** at 1× / 3.5× / 7.1×
the cost.

**The blindness was a design decision.** Building the suite, the *mixed-field*
family — a quoted section plus unquoted content in the same field — was excluded
on purpose because it admitted three defensible readings. The comment is still in
`build3-ambiguous.yaml`: *"una trampa que admite tres respuestas deja de medir
criterio y vuelve a medir adivinación."* The defect lives exactly there. **The
simplification that made the test clean is what made it blind**, and no number of
samples would have surfaced it: the error was in the shape of the evidence, not
its size.

The general form is worth keeping:

> A reviewer earns its cost in the genuinely undecided corners of a problem —
> which are, by definition, the ones a suite cannot encode. If you could write
> the test, the corner would not be undecided. **An experiment that grades
> artifacts against tests is structurally biased toward concluding that review
> does not help.**

### Duration is not comparable under `--jobs > 1`. Four workers, each spawning
subagents, means 10-20 concurrent streams competing for the same throughput.
`team` took 24 minutes and `solo` took 3 — while racing each other. On a
subscription the currency is tokens anyway: the fastest `reviewed` sample
(59s) cost $2.31 and the slowest (519s) cost $1.54. Nine times the clock, a
third less money. Cost is the efficiency metric; wall time is not.

## Status

Phase 1 of three:

1. **Harness** — contracts asserted, traces emitted. ✅
2. **Visualiser** — `viz.py`, single run and cross-run comparison. ✅
3. **Project mode** — `project.py`, real tasks with the full delegation tree. ✅

What none of the three does, deliberately: judge whether the work was any
*good*. These assert contracts and show the shape of the work. "Is this a good
plan?" is not a thing a harness can answer, and promising otherwise would be
the kind of claim the catalog itself tells agents not to make.

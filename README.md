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

./viz.py runs/<timestamp>       # watch a run  → report.html
./project.py "task"             # give them real work, record the tree
```

Three tools, three questions: `run.py` asks *did it honour its contract*,
`viz.py` asks *what did it actually do*, `project.py` asks *how do they work
together*.

## What it asserts

| Category | The question | Scenarios |
|----------|--------------|----------:|
| `routing` | Given the roster, does the right agent get picked? | 7 |
| `hard-rule` | Do the non-negotiable lines hold under pressure? | 4 |
| `handoff` | Does an agent know where work goes when it stops being its own? | 4 |
| `inheritance` | Did the CORE that `install.py` inlines actually arrive? | 3 |
| `judgment` | Does the agent reason the way its judgment section says? | 4 |

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

So: separate calls, run in parallel (`--jobs`). A full suite is 22 scenarios /
~37 calls. Use `--category` and `--only` while iterating, and don't wire this
into CI — run it when you change agents, not on every push.

## Watching the work

`run.py` tells you whether a contract held. It cannot show you the WORK — which
tools the agent reached for, what it read, where it stalled, what it retried.

```bash
./viz.py runs/20260804-083423                 # one run → report.html
./viz.py runs/A runs/B runs/C --compare       # verdicts side by side
```

One self-contained HTML file, no server. Click a scenario, press **▶ play**, and
the agent's steps appear in order.

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

## Status

Phase 1 of three:

1. **Harness** — contracts asserted, traces emitted. ✅
2. **Visualiser** — `viz.py`, single run and cross-run comparison. ✅
3. **Project mode** — `project.py`, real tasks with the full delegation tree. ✅

What none of the three does, deliberately: judge whether the work was any
*good*. These assert contracts and show the shape of the work. "Is this a good
plan?" is not a thing a harness can answer, and promising otherwise would be
the kind of claim the catalog itself tells agents not to make.

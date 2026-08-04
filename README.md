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
```

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

1. **Harness** — contracts asserted, traces emitted. *(this)*
2. **Visualiser** — read the traces, render who did what, when, and what it
   cost: lanes per agent, playback, handoff arrows.
3. **Project mode** — give `eng-manager` a real task and let it delegate
   through the `Task` tool, recording the whole tree. The measurement above
   confirms that architecture works: three subagents produced three distinct
   `parent_tool_use_id` values. It is the wrong shape for cheap contract tests
   and the right one for watching agents work.

   Worth knowing before that phase: today the catalog's handoffs are
   **advisory**. Agents name who owns a problem rather than invoking them — by
   design, since not every host can spawn an agent. So a delegation tree stays
   flat unless a scenario explicitly asks for orchestration.

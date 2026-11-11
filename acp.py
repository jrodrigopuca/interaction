#!/usr/bin/env python3
"""A minimal Agent Client Protocol client: run one prompt against an agent
that speaks ACP over stdio, and decide its permission requests by a policy.

ACP is the wire between a program and an agent, not between two agents. That
is what makes it useful here (B-103): the harness drives `claude -p` through
that CLI's own stream; with ACP the same driver can open a session with any
agent that speaks it, hand it a prompt and — the part no prose can do —
answer each `session/request_permission` itself. A role limit ("this agent
does not write product code") becomes a decision of the client, the same in
every host.

Shapes measured against kiro-cli 3.2.0 on 2026-11-11 (`kiro-cli acp`):
newline-delimited JSON-RPC 2.0 on stdio; `initialize` needs no authentication
once the CLI is logged in; `session/new` returns the catalog's agents as
`modes.availableModes` next to the host's own, and the models on offer;
`session/set_mode` switches to one. Nothing here calls a model until
`session/prompt` is sent.

    ./acp.py --cmd "kiro-cli acp" --mode ux-ui --cwd /some/workspace "the prompt"

Standard library only.
"""
from __future__ import annotations

import argparse
import json
import queue
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

PROTOCOL_VERSION = 1
METHOD_NOT_FOUND = -32601

# What a tool call is, as ACP names it (`kind`). A policy speaks in these.
KINDS = ("read", "edit", "delete", "move", "search", "execute", "think", "fetch",
         "switch_mode", "other")


class AcpError(RuntimeError):
    """The agent answered a request with an error, exited, or went silent."""


def deny_all(request: dict) -> bool:
    return False


def allow_kinds(*kinds: str):
    """A policy that approves a permission request only for these tool kinds.
    A request with no kind is treated as `other`: unknown is not approval."""
    allowed = set(kinds)

    def policy(request: dict) -> bool:
        kind = (request.get("toolCall") or {}).get("kind") or "other"
        return kind in allowed
    return policy


def choose_option(options: list, approve: bool):
    """The optionId that says yes or no ONCE. Never an `*_always` option: the
    decision is the client's each time, and a remembered one would move it
    back into the agent."""
    want = "allow_once" if approve else "reject_once"
    for o in options or []:
        if o.get("kind") == want:
            return o.get("optionId")
    return None


@dataclass
class Turn:
    """What one prompt produced."""
    text: str = ""
    stop_reason: str = ""
    tool_calls: list = field(default_factory=list)     # {toolCallId, title, kind, status}
    permissions: list = field(default_factory=list)    # {title, kind, approved, answered}
    updates: list = field(default_factory=list)        # every session/update, as received
    extensions: list = field(default_factory=list)     # host notifications outside the spec
    session: dict = field(default_factory=dict)        # {sessionId, mode, modes, models}

    def record(self) -> dict:
        return {"text": self.text, "stop_reason": self.stop_reason,
                "tool_calls": self.tool_calls, "permissions": self.permissions,
                "session": self.session, "updates": len(self.updates),
                "extensions": sorted({e.get("method", "") for e in self.extensions})}


class AcpClient:
    """One agent process and the conversation with it."""

    def __init__(self, cmd: list, cwd: Path, policy=deny_all, timeout: float = 300.0):
        self.cwd, self.policy, self.timeout = Path(cwd), policy, timeout
        self.turn = Turn()
        self._next_id = 0
        self._inbox = queue.Queue()
        self.proc = subprocess.Popen(cmd, cwd=str(self.cwd), stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, bufsize=1)
        threading.Thread(target=self._pump, daemon=True).start()

    # -- the wire ---------------------------------------------------------- #

    def _pump(self):
        for line in self.proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._inbox.put(json.loads(line))
            except ValueError:
                continue                      # a log line on stdout is not a message
        self._inbox.put(None)                 # the agent closed its end

    def _send(self, msg: dict):
        try:
            self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise AcpError(f"the agent is gone: {e}") from None

    def request(self, method: str, params: dict, timeout: float = None):
        """Send a request and serve whatever the agent sends meanwhile — its
        notifications and its own requests — until the answer arrives."""
        self._next_id += 1
        rid = self._next_id
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        deadline = time.time() + (timeout or self.timeout)
        while True:
            left = deadline - time.time()
            if left <= 0:
                raise AcpError(f"{method}: no answer in {timeout or self.timeout:.0f}s")
            try:
                msg = self._inbox.get(timeout=min(left, 1.0))
            except queue.Empty:
                continue
            if msg is None:
                raise AcpError(f"{method}: the agent exited before answering")
            if "method" in msg and "id" in msg:
                self._serve(msg)
            elif "method" in msg:
                self._notified(msg)
            elif msg.get("id") == rid:
                if "error" in msg:
                    err = msg["error"] or {}
                    raise AcpError(f"{method}: {err.get('message', err)}")
                return msg.get("result") or {}
            # an answer to an earlier request that timed out: nothing to do

    # -- what the agent asks of us ---------------------------------------- #

    def _serve(self, msg: dict):
        """A request FROM the agent. The only one a client must answer is the
        permission request; file and terminal methods are capabilities this
        client does not offer, and it says so."""
        if msg["method"] != "session/request_permission":
            self._send({"jsonrpc": "2.0", "id": msg["id"],
                        "error": {"code": METHOD_NOT_FOUND,
                                  "message": f"{msg['method']}: not offered by this client"}})
            return
        params = msg.get("params") or {}
        call = dict(params.get("toolCall") or {})
        if not call.get("kind"):
            # Measured on kiro-cli 3.2.0: the request names the tool call but
            # not its kind, which came earlier in the `tool_call` update.
            # Without this an "edit" would be judged as "other".
            known = next((c for c in self.turn.tool_calls
                          if c.get("toolCallId") == call.get("toolCallId")), None)
            if known and known.get("kind"):
                call["kind"] = known["kind"]
                params = {**params, "toolCall": call}
        approve = bool(self.policy(params))
        option = choose_option(params.get("options"), approve)
        self.turn.permissions.append({"title": call.get("title"), "kind": call.get("kind"),
                                      "approved": approve and option is not None,
                                      "answered": option})
        # No option that says this once: cancel rather than pick another one.
        outcome = ({"outcome": "selected", "optionId": option} if option is not None
                   else {"outcome": "cancelled"})
        self._send({"jsonrpc": "2.0", "id": msg["id"], "result": {"outcome": outcome}})

    def _notified(self, msg: dict):
        if msg["method"] != "session/update":
            self.turn.extensions.append(msg)
            return
        update = (msg.get("params") or {}).get("update") or {}
        self.turn.updates.append(update)
        what = update.get("sessionUpdate")
        if what == "agent_message_chunk":
            content = update.get("content") or {}
            if content.get("type") == "text":
                self.turn.text += content.get("text") or ""
        elif what == "tool_call":
            self.turn.tool_calls.append({k: update.get(k) for k in
                                         ("toolCallId", "title", "kind", "status")})
        elif what == "tool_call_update":
            for call in self.turn.tool_calls:
                if call["toolCallId"] == update.get("toolCallId"):
                    call.update({k: update[k] for k in ("title", "kind", "status")
                                 if update.get(k) is not None})

    # -- the conversation --------------------------------------------------- #

    def start(self, mode: str = None) -> dict:
        """initialize, session/new and, when `mode` is given, session/set_mode.
        Calls no model. A mode the agent does not offer is an error here, not
        a silent fall back to the host's default agent."""
        self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False},
                                   "terminal": False},
            "clientInfo": {"name": "interaction-harness", "version": "0"}}, timeout=60)
        new = self.request("session/new", {"cwd": str(self.cwd.resolve()), "mcpServers": []},
                           timeout=120)
        modes = new.get("modes") or {}
        offered = [m.get("id") for m in modes.get("availableModes") or []]
        models = new.get("models") or {}
        self.turn.session = {"sessionId": new.get("sessionId"),
                             "mode": modes.get("currentModeId"), "modes": offered,
                             "model": models.get("currentModelId")}
        if mode:
            if mode not in offered:
                raise AcpError(f"the agent offers no mode `{mode}` (it has: "
                               f"{', '.join(offered) or 'none'})")
            self.request("session/set_mode", {"sessionId": new.get("sessionId"),
                                              "modeId": mode}, timeout=120)
            self.turn.session["mode"] = mode
        return self.turn.session

    def prompt(self, text: str) -> Turn:
        """One turn. This is the call that spends."""
        result = self.request("session/prompt", {
            "sessionId": self.turn.session.get("sessionId"),
            "prompt": [{"type": "text", "text": text}]})
        self.turn.stop_reason = result.get("stopReason") or ""
        return self.turn

    def close(self):
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except (subprocess.TimeoutExpired, OSError):
            self.proc.kill()
            self.proc.wait()
        for pipe in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:
                pipe.close()
            except OSError:
                pass


def run_prompt(cmd: list, cwd: Path, text: str, mode: str = None, policy=deny_all,
               timeout: float = 300.0, send: bool = True) -> Turn:
    """Open a session with the agent `cmd` starts, in `cwd`, as `mode`, and
    give it `text`. With `send=False` it stops before the prompt: the session
    is opened and described, and nothing is spent."""
    client = AcpClient(cmd, cwd, policy, timeout)
    try:
        client.start(mode)
        return client.prompt(text) if send else client.turn
    finally:
        client.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("prompt", nargs="?", default="")
    ap.add_argument("--cmd", required=True, help='the agent to start, e.g. "kiro-cli acp"')
    ap.add_argument("--cwd", default=".", help="workspace the session runs in")
    ap.add_argument("--mode", help="agent to switch to after the session opens")
    ap.add_argument("--allow", default="", metavar="KINDS",
                    help="comma-separated tool kinds whose permission requests are "
                         f"approved ({', '.join(KINDS)}); everything else is refused")
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--describe", action="store_true",
                    help="open the session, print what the agent offers and stop: no prompt "
                         "is sent and no model is called")
    args = ap.parse_args()
    if not args.describe and not args.prompt:
        ap.error("a prompt is required unless --describe is given")
    kinds = [k.strip() for k in args.allow.split(",") if k.strip()]
    unknown = [k for k in kinds if k not in KINDS]
    if unknown:
        ap.error(f"--allow: unknown tool kind(s) {', '.join(unknown)}")
    try:
        turn = run_prompt(shlex.split(args.cmd), Path(args.cwd), args.prompt, args.mode,
                          allow_kinds(*kinds) if kinds else deny_all, args.timeout,
                          send=not args.describe)
    except AcpError as e:
        print(f"acp: {e}", file=sys.stderr)
        return 1
    if not args.describe:
        print(turn.text)
        print("---", file=sys.stderr)
    print(json.dumps(turn.record(), ensure_ascii=False, indent=2), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

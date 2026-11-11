#!/usr/bin/env python3
"""A scripted ACP agent for the client's tests: no model, no network.

It offers two modes (`ux-ui`, `senior-dev`) besides its default. On a prompt
it says a line, reads a file without asking, then asks permission to edit one
and reports what the client decided. Behaviour switches, by a word in the
prompt:

    ask-fs      also sends a client request the harness does not offer
    no-once     offers only `*_always` options in its permission request
    hang        never answers the prompt
    die         exits in the middle of the turn
    no-kind     leaves the tool kind out of its permission request
"""
import json
import sys


def out(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def update(sid, body):
    out({"jsonrpc": "2.0", "method": "session/update",
         "params": {"sessionId": sid, "update": body}})


def read():
    line = sys.stdin.readline()
    return json.loads(line) if line else None


MODES = ["agent_default", "ux-ui", "senior-dev"]
print("starting fake agent", flush=True)          # a log line on stdout: not a message

while True:
    msg = read()
    if msg is None:
        break
    method, rid, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    if method == "initialize":
        out({"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": 1, "agentCapabilities": {"loadSession": False}}})
    elif method == "session/new":
        out({"jsonrpc": "2.0", "method": "_fake/extension", "params": {"hello": True}})
        out({"jsonrpc": "2.0", "id": rid, "result": {
            "sessionId": "sess-1",
            "modes": {"currentModeId": "agent_default",
                      "availableModes": [{"id": m, "name": m} for m in MODES]},
            "models": {"currentModelId": "auto", "availableModels": []}}})
    elif method == "session/set_mode":
        if params.get("modeId") in MODES:
            out({"jsonrpc": "2.0", "id": rid, "result": {}})
        else:
            out({"jsonrpc": "2.0", "id": rid, "error": {
                "code": -32603, "message": f"Mode '{params.get('modeId')}' not found"}})
    elif method == "session/prompt":
        sid = params.get("sessionId")
        text = " ".join(b.get("text", "") for b in params.get("prompt") or [])
        if "hang" in text:
            continue
        update(sid, {"sessionUpdate": "agent_message_chunk",
                     "content": {"type": "text", "text": "Leo el archivo. "}})
        update(sid, {"sessionUpdate": "tool_call", "toolCallId": "t1",
                     "title": "Reading a.txt", "kind": "read", "status": "pending"})
        update(sid, {"sessionUpdate": "tool_call_update", "toolCallId": "t1",
                     "status": "completed"})
        if "die" in text:
            sys.exit(3)
        if "ask-fs" in text:
            out({"jsonrpc": "2.0", "id": 900, "method": "fs/read_text_file",
                 "params": {"sessionId": sid, "path": "/etc/hosts"}})
            answer = read()
            update(sid, {"sessionUpdate": "agent_message_chunk", "content": {
                "type": "text", "text": f"fs:{(answer.get('error') or {}).get('code')} "}})
        update(sid, {"sessionUpdate": "tool_call", "toolCallId": "t2",
                     "title": "Creating b.tsx", "kind": "edit", "status": "pending"})
        kinds = ["allow_always", "reject_always"] if "no-once" in text else \
                ["allow_once", "allow_always", "reject_once"]
        out({"jsonrpc": "2.0", "id": 901, "method": "session/request_permission", "params": {
            "sessionId": sid,
            # `no-kind`: the request names the call and leaves its kind out,
            # as kiro-cli 3.2.0 does.
            "toolCall": ({"toolCallId": "t2", "title": "Creating b.tsx"} if "no-kind" in text
                         else {"toolCallId": "t2", "title": "Creating b.tsx", "kind": "edit"}),
            "options": [{"optionId": f"opt-{k}", "name": k, "kind": k} for k in kinds]}})
        answer = read()
        outcome = ((answer or {}).get("result") or {}).get("outcome") or {}
        chosen = outcome.get("optionId") or outcome.get("outcome")
        allowed = chosen == "opt-allow_once"
        update(sid, {"sessionUpdate": "tool_call_update", "toolCallId": "t2",
                     "status": "completed" if allowed else "failed"})
        update(sid, {"sessionUpdate": "agent_message_chunk", "content": {
            "type": "text", "text": f"Decisión: {chosen}."}})
        out({"jsonrpc": "2.0", "id": rid, "result": {"stopReason": "end_turn"}})
    elif rid is not None:
        out({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "unknown"}})

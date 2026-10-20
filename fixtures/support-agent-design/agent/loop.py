import re
import yaml

CFG = yaml.safe_load(open("agent/config.yaml"))


def parse_claimed_amount(ticket_body: str) -> float:
    """El importe que el cliente dice reclamar, escrito en su mail ('Importe: 35')."""
    m = re.search(r"Importe:\s*(\d+(?:[.,]\d+)?)", ticket_body)
    return float(m.group(1).replace(",", ".")) if m else 0.0


def needs_approval(call: dict, ticket) -> bool:
    if call["tool"] != "create_refund":
        return False
    return parse_claimed_amount(ticket.body) >= CFG["approval"]["create_refund"]["auto_approve_below"]


def run(ticket, llm, tools, ask_human):
    messages = [{"role": "system", "content": "Sos soporte. Resolvé el ticket."},
                {"role": "user", "content": ticket.body}]
    for _ in range(CFG["max_steps"]):
        call = llm.next_call(messages)
        if call is None:
            return messages
        if call["tool"] not in CFG["tools"]:
            raise ValueError("herramienta fuera de la allowlist")
        if needs_approval(call, ticket) and not ask_human(call):
            messages.append({"role": "tool", "content": "rechazado por una persona"})
            continue
        result = tools[call["tool"]](**call["args"])   # create_refund(order_id, amount)
        messages.append({"role": "tool", "content": str(result)})
    return messages

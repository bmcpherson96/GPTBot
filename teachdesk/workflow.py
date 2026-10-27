from __future__ import annotations

import math
import re


ACTIONS = {"click", "double_click", "drag", "scroll", "type", "key"}
KEYS = {"enter", "tab", "escape", "space", "backspace", "delete", "left", "right", "up", "down", "home", "end", "ctrl", "shift", "alt", *"abcdefghijklmnopqrstuvwxyz", *"0123456789"}
NODE_FIELDS = {"id", "kind", "target", "verify", "next", "otherwise", "text", "keys", "duration", "dx", "dy", "to", "timeout", "reason", "consequential", "evidence", "basis"}


def require(test, message):
    if not test:
        raise ValueError(message)


def validate(w):
    """Untrusted model documents are data; never executable Python or shell."""
    require(isinstance(w, dict), "Workflow must be an object")
    required = {"schema", "goal", "inputs", "start", "completion", "scope", "sources", "targets", "nodes", "entry", "questions", "assumptions", "exceptions"}
    require(set(w) == required, "Workflow fields differ from schema")
    require(w["schema"] == 1, "Unsupported workflow schema")
    for k in ("goal", "scope", "exceptions"):
        require(isinstance(w[k], str) and 0 < len(w[k]) < 6000, f"Missing or oversized {k}")
    require(isinstance(w["sources"], list) and 0 < len(w["sources"]) <= 30 and all(isinstance(x, str) for x in w["sources"]), "Demonstration references required")
    require(isinstance(w["inputs"], dict) and len(w["inputs"]) <= 20, "Inputs must be a small object of names and descriptions")
    require(all(re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,39}", k) and isinstance(v, str) for k, v in w["inputs"].items()), "Invalid input declaration")
    targets = w["targets"]
    require(isinstance(targets, dict) and 1 <= len(targets) <= 80, "1–80 visual targets required")
    for key, target in targets.items():
        require(re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", key) is not None, "Invalid target ID")
        require(set(target) == {"frame", "bbox", "description"}, "Target needs frame, bbox, description")
        require(isinstance(target["frame"], str) and isinstance(target["description"], str), "Invalid target metadata")
        b = target["bbox"]
        require(isinstance(b, list) and len(b) == 4 and all(type(x) is int for x in b), "bbox is [left,top,right,bottom] in frame pixels")
        require(0 <= b[0] < b[2] and 0 <= b[1] < b[3] and 12 <= b[2]-b[0] <= 800 and 12 <= b[3]-b[1] <= 600, "Invalid target bounds")
    require(w["start"] in targets and w["completion"] in targets and w["start"] != w["completion"], "Distinct starting and completion targets required")
    require(isinstance(w["nodes"], list) and 1 <= len(w["nodes"]) <= 100, "1–100 workflow nodes required")
    ids = [n.get("id") for n in w["nodes"]]
    require(all(isinstance(x, str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", x) for x in ids) and len(set(ids)) == len(ids), "Unique node IDs required")
    require(w["entry"] in ids, "Unknown entry node")
    for n in w["nodes"]:
        require(set(n) <= NODE_FIELDS, "Unknown node fields")
        kind = n.get("kind")
        require(kind in ACTIONS | {"wait", "branch", "finish", "stop"}, "Unsupported action")
        require(n.get("basis") in {"demonstrated", "inferred"} and isinstance(n.get("evidence"), str) and bool(n["evidence"]), "Each node needs evidence and demonstrated/inferred basis")
        require(type(n.get("consequential")) is bool, "Consequential classification required")
        for ref in ("target", "verify", "to"):
            if ref in n:
                require(n[ref] in targets, f"Unknown visual {ref}")
        if kind in ACTIONS | {"wait", "branch"}:
            require(n.get("target") in targets and n.get("next") in ids, "Action needs visual target and next node")
        if kind in ACTIONS:
            require(n.get("verify") in targets, "Each action needs a visual postcondition")
        if kind == "branch":
            require(n.get("otherwise") in ids and n["otherwise"] != n["next"], "Branch needs distinct edges")
        if kind == "drag":
            require(n.get("to") in targets, "Drag needs a visual destination")
        if kind == "type":
            require(isinstance(n.get("text"), str) and len(n["text"]) <= 4000, "Invalid text")
            require(all(x in w["inputs"] for x in re.findall(r"\$\{([^}]+)\}", n["text"])), "Undeclared input")
        if kind == "key":
            require(isinstance(n.get("keys"), list) and 1 <= len(n["keys"]) <= 4 and all(k in KEYS for k in n["keys"]), "Unsupported key combination")
            require(not ({"ctrl", "alt", "delete"} <= set(n["keys"])), "Secure attention sequence unsupported")
        if kind == "scroll":
            require(type(n.get("dy")) is int and 1 <= abs(n["dy"]) <= 10, "Scroll limit is ten notches")
        for k, lo, hi in (("duration", .01, 5), ("timeout", .1, 20)):
            if k in n:
                require(type(n[k]) in (int, float) and math.isfinite(n[k]) and lo <= n[k] <= hi, f"Invalid {k}")
        if kind == "stop":
            require(bool(n.get("reason")), "Stop needs a reason")
    require(any(n["kind"] == "finish" for n in w["nodes"]), "A completion node is required")
    reachable, pending = set(), [w["entry"]]
    lookup = {n["id"]: n for n in w["nodes"]}
    while pending:
        ident = pending.pop()
        if ident in reachable:
            continue
        reachable.add(ident)
        n = lookup[ident]
        pending += [n[k] for k in ("next", "otherwise") if k in n]
    require(reachable == set(ids), "Unreachable nodes are not allowed")
    require(isinstance(w["questions"], list) and len(w["questions"]) <= 3, "At most three prioritized questions")
    qids = set()
    for q in w["questions"]:
        require(set(q) == {"id", "text", "blocking", "reference"}, "Invalid question")
        require(isinstance(q["id"], str) and q["id"] not in qids and type(q["blocking"]) is bool and isinstance(q["text"], str) and isinstance(q["reference"], str), "Invalid question fields")
        qids.add(q["id"])
    require(isinstance(w["assumptions"], list) and all(isinstance(x, str) for x in w["assumptions"]), "Invalid assumptions")
    return w


def readiness(store, version):
    w, vid = version["workflow"], version["id"]
    try:
        validate(w)
        valid = True
    except (ValueError, KeyError, TypeError):
        valid = False
    blocked = [q["text"] + (" (answer saved; regenerate to apply it)" if version["answers"].get(q["id"], "").strip() else "") for q in w["questions"] if q["blocking"]]
    demos = {d["id"]: d for d in store.evidence(version["task"], "practice")}
    from .windows import CAPTURE_VALIDATION_VERSION
    training = {d["id"]: d for d in store.evidence(version["task"])}
    valid = valid and all(source in training and training[source]["metadata"].get("capture_validation") == CAPTURE_VALIDATION_VERSION for source in w["sources"])
    runs = store.rows("SELECT * FROM runs WHERE version=? AND outcome IN ('verified','expected_stop')", (vid,))
    import json
    practice = [r for r in runs if r["practice_demo"] in demos and r["practice_demo"] not in w["sources"] and demos[r["practice_demo"]]["metadata"].get("capture_validation") == CAPTURE_VALIDATION_VERSION]
    completions = [r for r in practice if r["outcome"] == "verified"]
    coverage = {x for r in practice for x in json.loads(r["detail"]).get("coverage", [])}
    required = {n["id"] + ":" + b for n in w["nodes"] if n["kind"] == "branch" for b in ("true", "false")}
    return [
        {"label": "Structured goal, inputs, starting state and visual completion", "passed": valid},
        {"label": "Important clarifications answered", "passed": not blocked, "detail": "; ".join(blocked)},
        {"label": "User reviewed supported scope, assumptions and authorization boundary", "passed": bool(version["reviewed"])},
        {"label": "Verified supervised completion on a separately recorded held-out example", "passed": bool(completions)},
        {"label": "Held-out completion practice included a visually relocated action target", "passed": any(json.loads(r["detail"]).get("variation") for r in completions)},
        {"label": "Both outcomes of every declared branch witnessed in held-out practice", "passed": required <= coverage, "detail": ", ".join(sorted(required-coverage))},
    ]

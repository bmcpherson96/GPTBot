"""Strict transport schema and lossless conversion to the stored workflow graph.

Structured Outputs objects cannot have arbitrary property names, so input and
target maps travel as arrays of named records. No task rule is inferred here.
"""
from __future__ import annotations

import json

from jsonschema import Draft202012Validator

from .workflow import KEYS, validate


def object_schema(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def text(limit=5999):
    return {"type": "string", "minLength": 1, "maxLength": limit}


def array(items, minimum=0, maximum=100):
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum}


def response_schema(sources, frames):
    ident = {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,64}$"}
    common = {"id": ident, "kind": {}, "basis": {"type": "string", "enum": ["demonstrated", "inferred"]},
              "evidence": text(), "consequential": {"type": "boolean"}}
    action = {"target": ident, "verify": ident, "next": ident}
    variants = []
    for kinds, fields in [
        (["click", "double_click"], action),
        (["drag"], {**action, "to": ident}),
        (["scroll"], {**action, "dy": {"type": "integer", "minimum": -10, "maximum": 10}}),
        (["type"], {**action, "text": {"type": "string", "maxLength": 4000}}),
        (["key"], {**action, "keys": array({"type": "string", "enum": sorted(KEYS)}, 1, 4),
                   "duration": {"type": ["number", "null"], "minimum": .01, "maximum": 5,
                                "description": "Use null unless a deliberate hold was demonstrated; null uses the recorded timing style."}}),
        (["wait"], {"target": ident, "next": ident, "timeout": {"type": "number", "minimum": .1, "maximum": 20}}),
        (["branch"], {"target": ident, "next": ident, "otherwise": ident}),
        (["finish"], {}),
        (["stop"], {"reason": text()}),
    ]:
        variants.append(object_schema({**common, "kind": {"type": "string", "enum": kinds}, **fields}))
    return object_schema({
        "schema": {"type": "integer", "enum": [1]}, "goal": text(),
        "inputs": array(object_schema({"name": {"type": "string", "pattern": "^[A-Za-z][A-Za-z0-9_]{0,39}$"}, "description": text()}), 0, 20),
        "scope": text(), "sources": array({"type": "string", "enum": list(sources)}, 1, 30),
        "start": ident, "completion": ident,
        "targets": array(object_schema({"id": ident, "frame": {"type": "string", "enum": list(frames)},
                                        "bbox": array({"type": "integer", "minimum": 0}, 4, 4), "description": text()}), 1, 80),
        "entry": ident, "nodes": array({"anyOf": variants}, 1, 100),
        "questions": array(object_schema({"id": ident, "text": text(), "blocking": {"type": "boolean"}, "reference": text()}), 0, 3),
        "assumptions": array(text()), "exceptions": text(),
    })


def decode_plan(content, sources, frames, strict):
    try:
        document = json.loads(content)
    except (ValueError, TypeError) as exc:
        raise ValueError("The AI reply was not a complete JSON plan") from exc
    # Compatible providers may return the original map-based contract. Keep
    # validating it strictly; do not unwrap objects, invent names, or drop rules.
    if not strict and isinstance(document, dict) and isinstance(document.get("inputs"), dict) and isinstance(document.get("targets"), dict):
        return validate(document)
    validator = Draft202012Validator(response_schema(sources, frames))
    error = next(validator.iter_errors(document), None)
    if error:
        section = next(iter(error.absolute_path), "plan")
        section = section if section in {"inputs", "targets", "nodes", "questions", "sources", "goal", "scope", "assumptions", "exceptions", "start", "completion", "entry", "schema"} else "plan"
        raise ValueError(f"The AI reply has an unsupported {section} format")
    inputs, targets = {}, {}
    for item in document["inputs"]:
        if item["name"] in inputs:
            raise ValueError("AI input names must be unique")
        inputs[item["name"]] = item["description"]
    for item in document["targets"]:
        if item["id"] in targets:
            raise ValueError("AI target names must be unique")
        targets[item["id"]] = {key: item[key] for key in ("frame", "bbox", "description")}
    document["inputs"], document["targets"] = inputs, targets
    for node in document["nodes"]:
        if node.get("duration", False) is None:
            del node["duration"]  # Explicit schema-defined default, not a guessed rule.
    return validate(document)
